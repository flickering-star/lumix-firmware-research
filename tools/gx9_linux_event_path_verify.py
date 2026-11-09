#!/usr/bin/env python3
"""Check GX9 internal event routing using captured ARM code and mocked I/O.

Requires Unicorn 2.1.4 and three hash-pinned executables from the recovered
filesystems. All sockets, ICC/shared-memory operations and HTTP environment
values are simulated. This tool does not access a camera, network or shell.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import unicorn as U
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
)

from gx9_linux_command_verify import Elf, PSM_SHA


NWA_SHA = '21b904a78c80c5b6e505af5f2cfdbfde6365558fd1169675685363d012782a77'
CGI_SHA = '81d5439c888fc5b78e042e649c968cbd6c05093b213ba0cf2c46b0e0e65edc6f'
STACK, HEAP, RETURN = 0x10000000, 0x30000000, 0x20000000
REGISTERS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
SOCKET = 0x42


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Machine:
    def __init__(self, elf):
        self.elf = elf
        self.uc = U.Uc(U.UC_ARCH_ARM, U.UC_MODE_ARM)
        self.uc.mem_map(0x10000, 0x100000)
        for kind, offset, address, physical, size, memory, flags, alignment in elf.ph:
            if kind == 1:
                self.uc.mem_write(address, elf.data[offset:offset + size])
        for address, size in [(STACK, 0x20000), (HEAP, 0x40000), (RETURN, 0x1000)]:
            self.uc.mem_map(address, size)
        self.native_instructions = 0
        self.finished = False
        self.hooks = {}
        self.imports = {}
        self.uc.hook_add(U.UC_HOOK_CODE, self.code)

    def read(self, address, size):
        return bytes(self.uc.mem_read(address, size))

    def write(self, address, data):
        self.uc.mem_write(address, bytes(data))

    def word(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def put_word(self, address, value):
        self.write(address, struct.pack('<I', value))

    def string(self, address):
        for length in range(2048):
            if not self.read(address + length, 1)[0]:
                return self.read(address, length)
        raise ValueError('Unterminated emulated string')

    def ret(self, value=0):
        self.uc.reg_write(UC_ARM_REG_R0, value & 0xffffffff)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def stop(self):
        self.finished = True
        self.uc.emu_stop()

    def code(self, uc, address, size, user):
        self.native_instructions += 1
        if address == RETURN:
            self.stop()
            return
        args = [uc.reg_read(register) for register in REGISTERS]
        if address in self.hooks:
            self.hooks[address](*args)
            return
        name = self.elf.plt.get(address)
        if name is None:
            return
        if name not in self.imports:
            raise ValueError('Unmocked native import: ' + name)
        self.imports[name](*args)

    def run(self, entry, args=()):
        self.uc.reg_write(UC_ARM_REG_SP, STACK + 0x1ff00)
        self.uc.reg_write(UC_ARM_REG_LR, RETURN)
        for register, value in zip(REGISTERS, args):
            self.uc.reg_write(register, value)
        self.uc.emu_start(entry, RETURN + 4, count=20000)
        if not self.finished:
            raise ValueError('Native instruction bound reached')
        return self.uc.reg_read(UC_ARM_REG_R0)

    def memory_imports(self):
        def memcpy(a, b, c, d):
            if c > 4096:
                raise ValueError('Emulated copy exceeds bound')
            self.write(a, self.read(b, c))
            self.ret(a)
        self.imports.update(memcpy=memcpy, strlen=lambda a, *rest: self.ret(len(self.string(a))),
                            printf=lambda *args: self.ret(0))
        self.imports['gettimeofday'] = lambda a, *rest: (
            self.write(a, bytes(8)), self.ret(0))


def native_checks(elf, words):
    for address, expected in words.items():
        if elf.word(address) != expected:
            raise ValueError('Native instruction/literal differs at ' + hex(address))
    return {hex(a): hex(w) for a, w in words.items()}


def subscription(psm, nwa):
    """Run PSM's actual NWA socket setup and filter-selection call."""
    vm = Machine(psm)
    result = {'socket_calls': [], 'connect_calls': [], 'filter_writes': []}

    def socket(a, b, c, d):
        assert (a, b, c) == (1, 1, 0)
        result['socket_calls'].append({'family': a, 'type': b, 'protocol': c})
        vm.ret(SOCKET)

    def connect(a, b, c, d):
        assert a == SOCKET and vm.read(b, 2) == b'\x01\0'
        path = vm.string(b + 2).decode()
        assert path == '/tmp/unix_sockstream_nwa'
        result['connect_calls'].append({'path': path, 'address_bytes': c})
        vm.ret(0)

    def write(a, b, c, d):
        assert a == SOCKET and c == 18
        value = vm.read(b, c)
        result['filter_writes'].append(list(value))
        vm.ret(c)

    vm.memory_imports()
    vm.imports.update(socket=socket, connect=connect, write=write)
    vm.imports['stpcpy'] = lambda a, b, *rest: (
        vm.write(a, vm.string(b) + b'\0'), vm.ret(a + len(vm.string(b))))
    vm.hooks[0x4e8ec] = lambda *args: vm.ret(0)  # simulated host event registration
    vm.run(0x4e93c, (0x72194,))
    expected = nwa.data[nwa.offset(0x123b2):nwa.offset(0x123b2) + 18]
    assert result['filter_writes'] == [list(expected)] and expected[0] == 1
    assert len(result['connect_calls']) == 1 and len(result['socket_calls']) == 1
    result.update(native_instructions=vm.native_instructions, selector=1,
                  event_group_shift=12, linux_command_group_enabled=True,
                  socket_io_mocked=True)
    return result, expected


def route_icc_message(nwa, message, filter_bytes):
    """Run one NWA ICC receive iteration through its real subscription filter."""
    vm = Machine(nwa)
    result = {'icc_reads': 0, 'messages_sent': []}
    vm.write(HEAP, message)
    vm.put_word(0x22628, 0x55)
    vm.put_word(0x2265c, 1)
    vm.put_word(0x22660, SOCKET)
    vm.write(0x22668, filter_bytes)
    iterations = 0

    def loop(*args):
        nonlocal iterations
        iterations += 1
        if iterations == 2:
            vm.stop()

    def icc_read(a, b, c, d):
        assert a == 0x55 and c == 8 and d == 0xffffffff
        result['icc_reads'] += 1
        vm.write(b, bytes(8))
        vm.ret(8)

    def send(a, b, c, d):
        assert (a, c, d) == (SOCKET, 488, 0)
        value = vm.read(b, c)
        assert value == message
        result['messages_sent'].append({'bytes': c, 'sha256': sha(value)})
        vm.ret(c)

    vm.hooks.update({0x111d8: loop, 0x11a1c: icc_read,
                     0x11a8c: lambda *args: vm.ret(0),
                     0x11abc: lambda *args: vm.ret(HEAP),
                     0x11aa4: lambda *args: vm.ret(0),
                     0x11a74: lambda *args: vm.ret(0)})
    vm.memory_imports()
    vm.imports.update(send=send, pthread_mutex_lock=lambda *args: vm.ret(0),
                      pthread_mutex_unlock=lambda *args: vm.ret(0))
    vm.run(0x111bc)
    assert iterations == 2 and result['icc_reads'] == 1
    result.update(native_instructions=vm.native_instructions,
                  shared_memory_and_icc_mocked=True)
    return result


def receive_and_dispatch(psm, message, ready=True):
    """Run PSM's real socket receive, validation and global event dispatcher."""
    vm = Machine(psm)
    result = {'recv_calls': 0, 'command_dispatcher_reached': False}
    row, client, poll = HEAP + 0x1000, HEAP + 0x1100, HEAP + 0x1200
    vm.write(row, struct.pack('<4I', 0, client, 1, 0))
    vm.write(client, struct.pack('<3I', SOCKET, 0, 0))
    vm.write(poll, struct.pack('<3I', int(ready), 0, SOCKET))

    def recv(a, b, c, d):
        assert (a, c, d) == (SOCKET, 488, 0)
        result['recv_calls'] += 1
        vm.write(b, message)
        vm.ret(len(message))

    def dispatched(a, b, c, d):
        assert a == SOCKET and vm.read(b, 488) == message
        result['command_dispatcher_reached'] = True
        vm.stop()  # stop before thread creation; worker has a separate verifier

    vm.memory_imports()
    vm.imports['recv'] = recv
    vm.hooks[0x39e94] = dispatched
    vm.run(0x4e80c, (row, poll))
    result['native_instructions'] = vm.native_instructions
    return result


def cgi_message(cgi, query, decoded=None):
    """Run the FastCGI message constructor with a simulated request environment."""
    vm = Machine(cgi)
    address = b'127.0.0.1'
    env = {b'REMOTE_ADDR': HEAP + 0x1000, b'QUERY_STRING': HEAP + 0x1100}
    vm.write(env[b'REMOTE_ADDR'], address + b'\0')
    vm.write(env[b'QUERY_STRING'], query + b'\0')
    vm.memory_imports()
    vm.imports['getenv'] = lambda a, *rest: vm.ret(env[vm.string(a)])

    def strtol(a, b, c, d):
        assert c == 16 and len(vm.string(a)) == 2
        text = vm.string(a).decode('ascii')
        assert all(char in '0123456789abcdefABCDEF' for char in text)
        vm.put_word(b, a + 2)
        vm.ret(int(text, 16))

    vm.imports['strtol'] = strtol
    status = vm.run(0x11b8c, (HEAP,))
    result = {'query_bytes': len(query), 'status': hex(status),
              'native_instructions': vm.native_instructions}
    if status == 0:
        message = vm.read(HEAP, 488)
        assert struct.unpack_from('<2I', message) == (0x6000, 0)
        assert message[16:32].split(b'\0')[0] == address
        assert message[184:].split(b'\0')[0] == (query if decoded is None else decoded)
        result.update(event_id='0x6000', message_bytes=488, message_sha256=sha(message))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--psm', type=Path, required=True)
    parser.add_argument('--nwa', type=Path, required=True)
    parser.add_argument('--cgi', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    inputs = {}
    for name, path, digest in [('psm', args.psm, PSM_SHA), ('nwa', args.nwa, NWA_SHA),
                               ('cam.fcgi', args.cgi, CGI_SHA)]:
        elf = Elf(path)
        if sha(elf.data) != digest:
            raise ValueError('Expected verified GX9 executable: ' + name)
        inputs[name] = elf
    psm, nwa, cgi = (inputs[name] for name in ('psm', 'nwa', 'cam.fcgi'))
    checks = {
        'psm': native_checks(psm, {0x721a0: 0x6fb4c, 0x721a8: 0x4e93c,
                                  0x721b8: 0x4e80c, 0x4e9e4: 0xea0002eb,
                                  0x4f5d4: 0x6fc34, 0x3329c: 0xe353003c,
                                  0x335c0: 0xea001a33}),
        'nwa': native_checks(nwa, {0x119c0: 0x12318, 0x12224: 0x123a0,
                                  0x112ec: 0xe5d00010, 0x1130c: 0xebfffedc}),
        'cam.fcgi': native_checks(cgi, {0x11bc4: 0xe3a03a06,
                                       0x11bf0: 0x0a000030, 0x11bfc: 0xe35000bf}),
    }
    linked, selected_filter = subscription(psm, nwa)
    command = b'printf GX9_ROUTE_ONLY'
    message = bytearray(488)
    struct.pack_into('<6I', message, 0, 60, 0, 0, 0, 0, len(command))
    message[24:24 + len(command)] = command
    routed = route_icc_message(nwa, bytes(message), selected_filter)
    assert len(routed['messages_sent']) == 1
    excluded_filter = bytearray(selected_filter)
    excluded_filter[0] = 0
    excluded = route_icc_message(nwa, bytes(message), bytes(excluded_filter))
    assert not excluded['messages_sent']
    dispatched = receive_and_dispatch(psm, bytes(message))
    assert dispatched['command_dispatcher_reached'] and dispatched['recv_calls'] == 1
    idle = receive_and_dispatch(psm, bytes(message), ready=False)
    assert not idle['command_dispatcher_reached'] and idle['recv_calls'] == 0
    cgi_cases = [cgi_message(cgi, value, decoded) for value, decoded in [
        (b'mode=getstate', None), (b'mode=linuxcmd&value=GX9_ROUTE_ONLY', None),
        (b'event=60&mode=linuxcmd', None),
        (b'event=%36%30&value=GX9+ROUTE', b'event=60&value=GX9 ROUTE'),
        (b'A' * 191, None), (b'A' * 192, None)]]
    assert all(case['status'] == '0x0' for case in cgi_cases[:-1])
    assert cgi_cases[-1]['status'] == '0xffffffff'
    report = {
        'schema': 1, 'scope': 'Captured ARM event routing with mocked ICC, sockets and HTTP environment',
        'unicorn_version': U.__version__, 'verifier_sha256': sha(Path(__file__).read_bytes()),
        'inputs': {name: {'bytes': len(elf.data), 'sha256': sha(elf.data)}
                   for name, elf in inputs.items()},
        'native_words_checked': checks, 'internal_event_id': '0x3c',
        'internal_message_bytes': 488, 'nwa_subscription': linked,
        'icc_event_routing': routed, 'excluded_filter_control': excluded,
        'psm_receive_and_dispatch': dispatched, 'socket_not_ready_control': idle,
        'fastcgi_constructor_cases': cgi_cases, 'all_controls_passed': True,
        'host_socket_operations': 0, 'host_shell_commands_executed': 0, 'camera_requests': 0,
        'external_usb_or_wifi_entry_demonstrated': False,
        'limits': [
            'The event payload and ICC shared-memory descriptor were supplied by the emulator.',
            'The route proves internal native control flow, not that USB or Wi-Fi can create event 60.',
            'The HTTP constructor emits event 0x6000; downstream query interpretation is a separate path.',
            'No command worker was executed here; its separate verifier mocks system and file operations.',
        ],
    }
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('Native NWA subscription, ICC routing, PSM dispatch and HTTP constructor controls passed; all I/O mocked.')


if __name__ == '__main__':
    main()
