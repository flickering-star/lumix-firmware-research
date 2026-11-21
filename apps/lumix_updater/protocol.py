"""Checked service framing shared by both desktop platforms.

The sole write constructor targets the selected model's updater-policy halfword.
The app never exposes an arbitrary USB command, address or value editor.
"""
from __future__ import annotations

import struct
from .models import model_spec


class ProtocolError(ValueError):
    pass


def checksum(data: bytes) -> int:
    return sum(data[1:-2]) & 255


def read_packet(address: int) -> bytes:
    if type(address) is not int or address & 1023 or not 0 <= address < 0xFFFFFC00:
        raise ProtocolError("Unaligned or invalid read address")
    result = bytearray(1030)
    result[:4] = b"\x01\0\xff\x5c"
    struct.pack_into("<II", result, 4, address, address + 1024)
    result[-2] = checksum(result)
    return bytes(result)


def check_frame(data: bytes, header: bytes, size: int) -> None:
    if (len(data) != size or data[:4] != header or data[-1]
            or data[-2] != checksum(data)):
        raise ProtocolError("The camera returned an incomplete or invalid service reply")


def read_reply(data: bytes) -> bytes:
    check_frame(data, b"\x01\0\xff\x05", 1030)
    return data[4:-2]


def policy_packet(value: int, model='DMC-GM5') -> bytes:
    if type(value) is not int or value not in (0, 1):
        raise ProtocolError("Only the reviewed policy values are supported")
    spec=model_spec(model)
    result = bytearray(16)
    result[:4] = b"\x08\0\xff\x9c"
    struct.pack_into("<IH", result, 4, spec['policy_ram']+spec['policy_ram_offset'], value)
    result[-2] = checksum(result)
    return bytes(result)


def policy_ack(data: bytes) -> None:
    check_frame(data, b"\x08\0\xff\x01", 16)
    if any(data[4:14]):
        raise ProtocolError("The camera did not acknowledge the policy change")


class Service:
    """A transport plus an explicit model-profile read allowlist."""

    def __init__(self, transport, allowed_pages, *, model='DMC-GM5'):
        self.transport = transport
        self.allowed_pages = frozenset(allowed_pages)
        model_spec(model)
        self.model=model

    def read(self, address):
        if address not in self.allowed_pages:
            raise ProtocolError("Read is outside the selected camera profile")
        request=read_packet(address)
        payload=read_reply(self.transport.exchange(request, 1, 1030))
        if payload==request[4:-2]:
            raise ProtocolError('The service buffer was not replaced with camera memory')
        return payload

    def set_policy(self, value):
        policy_ack(self.transport.exchange(policy_packet(value,self.model), 8, 16))
