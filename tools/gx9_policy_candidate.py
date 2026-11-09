#!/usr/bin/env python3
"""Prepare a fixed GX9 1.4 policy-one research candidate, offline only.

Requires independently verified physical policy readback. Preserves the full
official 1.4 layout, patches the same flag in the program shadow and fixed bank, and
advertises header revision 0x141 to pass the modeled version gate. Outputs stay
under work/, use a research-only filename, and are not marked ready to install.
No camera, network, SD-card access or firmware installation is performed.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

from panasonic_buffer_key_check import CODEC, WRAPPER, HostCodec, selftest
from gx9_update_decode import MAIN_RAM_SHA, KEY_OFFSET, KEY_SHA, decode_bytes
from gx9_update_auth_verify import (
    PROGRAM_SHA, public_key, openssl_check, native_attempt, signed_extent,
)
from gx9_update_policy_capture_verify import verify as verify_physical_policy
from gx9_update_route_verify import Machine, CONTEXT, FIRMWARE
from gx9_policy_persistence_verify import FIX_SHA, FIX_OFFSET, verify as verify_persistence
from tz30_control_verify import records


V14_SHA = 'e26e4b422e9d46dffb7d93eaabd061bb3e49e2d84654dffc1d892f7f25126e7a'
PATCH_OFFSET = 0x9801a
ENCODE = r'''
int gx9_encode(const uint8_t *input, size_t length, uint8_t *output,
               const uint8_t key[16], const uint8_t iv[16]) {
    if (!length || length % 16 || length > 16777216) return 0;
    uint8_t previous[16], schedule[176], block[16];
    memcpy(previous, iv, 16);
    expand_key(key, schedule, 5);
    for (size_t offset = 0; offset < length; offset += 16) {
        for (unsigned i = 0; i < 16; i++) block[i] = input[offset+i] ^ previous[i];
        encrypt_block(block, output+offset, schedule, 5);
        memcpy(previous, output+offset, 16);
    }
    return 1;
}
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Encoder:
    def __init__(self, directory):
        compiler = shutil.which('cc')
        if compiler is None:
            raise ValueError('A host C compiler is required')
        source = directory / 'encoder.c'
        source.write_text((WRAPPER + ENCODE).replace('CODEC_PATH', json.dumps(str(CODEC))))
        library = directory / ('encoder.dylib' if sys.platform == 'darwin' else 'encoder.so')
        subprocess.run([compiler, '-std=c11', '-O3', '-fPIC',
                        '-dynamiclib' if sys.platform == 'darwin' else '-shared',
                        str(source), '-o', str(library)], check=True, capture_output=True)
        self.library = C.CDLL(str(library))
        self.library.pana_initialize.restype = C.c_int
        if self.library.pana_initialize() != 1:
            raise ValueError('Independent encryption/decryption codec controls failed')
        self.function = self.library.gx9_encode
        pointer = C.POINTER(C.c_ubyte)
        self.function.argtypes = [pointer, C.c_size_t, pointer, pointer, pointer]
        self.function.restype = C.c_int

    def encode(self, data, key, iv):
        source = (C.c_ubyte * len(data)).from_buffer_copy(data)
        output = (C.c_ubyte * len(data))()
        k = (C.c_ubyte * 16).from_buffer_copy(key)
        v = (C.c_ubyte * 16).from_buffer_copy(iv)
        if self.function(source, len(data), output, k, v) != 1:
            raise ValueError('Fixed component encryption extent rejected')
        return bytes(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--program', type=Path, required=True)
    parser.add_argument('--main-ram', type=Path, required=True)
    parser.add_argument('--policy-capture', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    root_work = Path(__file__).resolve().parents[1] / 'work'
    output = args.outdir.resolve()
    if output == root_work.resolve() or root_work.resolve() not in output.parents:
        raise ValueError('Candidate outputs must stay in a fresh directory under this checkout work/')
    original, program, ram = (p.read_bytes() for p in (args.firmware, args.program, args.main_ram))
    if sha(original) != V14_SHA or sha(program) != PROGRAM_SHA or sha(ram) != MAIN_RAM_SHA:
        raise ValueError('Pinned official 1.4 or independently captured RAM input differs')
    physical = verify_physical_policy(args.policy_capture, args.program)
    key = ram[KEY_OFFSET:KEY_OFFSET + 16]
    if sha(key) != KEY_SHA:
        raise ValueError('Verified component-decryption key differs')
    entries = records(original, b'MC282')
    index, entry = next((i, e) for i, e in enumerate(entries) if e['name'] == 'program')
    if (entry['flags'] != 3 or entry['bytes'] != len(program)
            or entry['field32'] != PROGRAM_SHA or program[PATCH_OFFSET:PATCH_OFFSET + 2] != b'\0\0'):
        raise ValueError('Expected official program record or policy zero differs')
    patched = program[:PATCH_OFFSET] + b'\x01' + program[PATCH_OFFSET + 1:]
    fixed = (args.program.parent / 'eep_fix.plaintext.bin').read_bytes()
    if sha(fixed) != FIX_SHA or fixed[FIX_OFFSET:FIX_OFFSET + 2] != b'\0\0':
        raise ValueError('Expected verified fixed-bank component with default policy zero')
    patched_fixed = fixed[:FIX_OFFSET] + b'\x01' + fixed[FIX_OFFSET + 1:]
    persistence = verify_persistence(program, fixed, ram)
    if (persistence['fresh_bank_reload_after_simulated_update']['policy_after_reload'] != 1
            or not persistence['all_owner_fixed_bank_differences_preserved_by_native_preprocessing']):
        raise ValueError('Fixed-bank persistence or identity preservation control failed')
    changes = {'program': (program, patched, PATCH_OFFSET),
               'eep_fix': (fixed, patched_fixed, FIX_OFFSET)}
    output.mkdir(mode=0o700)
    report = {
        'schema': 1, 'scope': 'Offline preparation of a policy-one research candidate; not installation approval',
        'ready_to_install': False, 'camera_or_network_access': False, 'physical_writes': 0,
        'verifier_sha256': sha(Path(__file__).read_bytes()), 'codec_source_sha256': sha(CODEC.read_bytes()),
        'source_firmware_sha256': V14_SHA, 'source_program_sha256': PROGRAM_SHA,
        'source_ram_sha256': MAIN_RAM_SHA, 'key_sha256': KEY_SHA,
        'physical_policy_proof': {'policy_values_read': physical['policy_values_read'],
                                  'complete_original_block_restored': physical['complete_original_metadata_block_restored'],
                                  'event_source_sha256': physical['wire']['event_source_sha256']},
        'program_patch': {'offset': hex(PATCH_OFFSET), 'linked_address': '0x03f1801a',
                          'before_hex': '00', 'after_hex': '01', 'changed_plaintext_bytes': 1},
        'fixed_bank_patch': {'offset': hex(FIX_OFFSET), 'before_hex': '00', 'after_hex': '01',
                             'changed_plaintext_bytes': 1,
                             'reason': 'Native fixed-bank reload overwrites the program shadow'},
        'candidate_fixed_bank_sha256': sha(patched_fixed),
        'native_fixed_bank_persistence': persistence,
        'candidate_program_sha256': sha(patched),
        'source_header_version': '0x140', 'candidate_header_advertised_version': '0x141',
        'header_type_low_nibble': original[0x20] & 15,
        'program_version_bytes_changed': False, 'components': [],
    }
    report_path = output / 'candidate-report.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='gx9-candidate-codec-') as folder:
        folder = Path(folder)
        encoder = Encoder(folder)
        decoder = HostCodec(folder)
        selftest(decoder)
        candidate = bytearray(original)
        digest_ranges = []
        for changed_name, (plain, changed_plain, offset) in changes.items():
            number, changed_entry = next((i, e) for i, e in enumerate(entries) if e['name'] == changed_name)
            at, size = changed_entry['file_offset'], changed_entry['bytes']
            iv = bytes.fromhex(changed_entry['field16'])
            if changed_entry['flags'] != 3 or sha(plain) != changed_entry['field32']:
                raise ValueError('Expected verified encrypted source component')
            rebuilt_original = encoder.encode(plain, key, iv)
            if rebuilt_original != original[at:at + size]:
                raise ValueError('Full original re-encryption differs: ' + changed_name)
            report[changed_name + '_original_reencryption_byte_identical'] = True
            cipher = encoder.encode(changed_plain, key, iv)
            prefix = offset // 16 * 16
            if cipher[:prefix] != original[at:at + prefix]:
                raise ValueError('Cipher prefix changed before patched block: ' + changed_name)
            candidate[at:at + size] = cipher
            digest_at = 0x2ec + number * 0x5c + 0x1c
            candidate[digest_at:digest_at + 32] = hashlib.sha256(changed_plain).digest()
            digest_ranges.append((digest_at, digest_at + 32))
            print(changed_name + ': complete original ciphertext reproduced; fixed flag encoded.', flush=True)
        struct.pack_into('<H', candidate, 0x1c, 0x141)
        candidate[0x2a0:0x2e0] = candidate[:0x40]
        struct.pack_into('<I', candidate, 0x40, zlib.crc32(candidate[512:]))
        updated = records(candidate, b'MC282')
        for before, after in zip(entries, updated):
            start, length = after['file_offset'], after['bytes']
            raw = bytes(candidate[start:start + length])
            if not length:
                continue
            plain = decode_bytes(decoder, raw, key, bytes.fromhex(after['field16'])) if after['flags'] == 3 else raw
            if sha(plain) != after['field32']:
                raise ValueError('Rebuilt package component failed full plaintext digest: ' + after['name'])
            changed_component = after['name'] in changes
            if not changed_component and raw != original[start:start + length]:
                raise ValueError('Unrelated component changed: ' + after['name'])
            if changed_component and plain != changes[after['name']][1]:
                raise ValueError('Decode differs from the exact one-byte component patch: ' + after['name'])
            report['components'].append({'name': after['name'], 'bytes': length,
                                          'plaintext_sha256': sha(plain), 'complete_hash_verified': True,
                                          'stored_bytes_unchanged_from_source': not changed_component})
            print(after['name'] + ': rebuilt complete plaintext verified', flush=True)
        openssl_folder = folder / 'signature'
        openssl_folder.mkdir()
        start, end, _ = signed_extent(candidate)
        digest = hashlib.sha256(candidate[start:end]).digest()
        if openssl_check(Path('/usr/bin/openssl'), openssl_folder, public_key(program),
                         digest[::-1], bytes(candidate[0x220:0x260])):
            raise ValueError('Changed candidate unexpectedly retains a valid original signature')
        report['original_signature_invalid_for_candidate_as_expected'] = True
    machine = Machine(program, bytes(candidate[:512]))
    machine.put_word(CONTEXT + 0x1000 + 0x18, 0x140)
    status = machine.call(0x4015762, FIRMWARE, CONTEXT + 0x1000, 0)
    if status != 0:
        raise ValueError('Candidate header failed native model/version validation')
    report['native_model_version_status'] = hex(status)
    gate = native_attempt(program, bytes(candidate), policy_halfword=1)
    if not gate['directory_gate_reached'] or gate['signature_calls'] or gate['payload_hash_checks_selected']:
        raise ValueError('Candidate failed the native policy-one directory gate')
    report['native_policy_one_gate'] = gate
    metadata_changes = [i for i in range(0x1000) if original[i] != candidate[i]]
    allowed = {0x1c, 0x1d, 0x2bc, 0x2bd, *range(0x40, 0x44)}
    for start, end in digest_ranges:
        allowed.update(range(start, end))
    if not set(metadata_changes) <= allowed:
        raise ValueError('Unexpected outer metadata change')
    report['changed_metadata_file_offsets'] = [hex(i) for i in metadata_changes]
    path = output / 'gx9-v14-policy-one.research-upd'
    with path.open('xb') as stream:
        stream.write(candidate)
    path.chmod(0o400)
    program_path = output / 'program.policy-one.plaintext.bin'
    with program_path.open('xb') as stream:
        stream.write(patched)
    program_path.chmod(0o400)
    fixed_path = output / 'eep_fix.policy-one.plaintext.bin'
    with fixed_path.open('xb') as stream:
        stream.write(patched_fixed)
    fixed_path.chmod(0o400)
    report.update(candidate_file=path.name, candidate_bytes=len(candidate), candidate_sha256=sha(candidate),
                  verified_nonempty_components=len(report['components']), directory_records=len(updated),
                  other_nonempty_components_byte_identical=33, preparation_complete=True,
                  changed_nonempty_components=['program', 'eep_fix'])
    report['limits'] = [
        'The complete flash writer and subsequent boot of this changed program remain unvalidated.',
        'A successful physical RAM policy test is not a completed firmware update.',
        'Default policy zero rejects this intentionally unsigned candidate; a live policy-one route would be required.',
        'The advertised package revision changes to 0x141; the program version remains its original 1.4 bytes.',
        'No candidate was copied to an SD card or sent to a camera.',
    ]
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print('Research candidate prepared under work/; ready_to_install remains false.')


if __name__ == '__main__':
    main()
