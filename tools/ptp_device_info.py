#!/usr/bin/env python3
"""Parse a saved PTP GetDeviceInfo dataset offline, omitting its serial number."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def take(self, count: int) -> bytes:
        if count < 0 or count > len(self.data)-self.offset:
            raise ValueError(f"Truncated PTP dataset at byte {self.offset}")
        result = self.data[self.offset:self.offset+count]
        self.offset += count
        return result

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def string(self) -> str:
        units = self.take(1)[0]
        if not units:
            return ""
        raw = self.take(units*2)
        if raw[-2:] != b"\0\0":
            raise ValueError("PTP string is missing its terminator")
        return raw[:-2].decode("utf-16-le")

    def array(self) -> list[str]:
        count = self.u32()
        if count > 4096:
            raise ValueError("Excessive PTP code-array length")
        return [f"0x{self.u16():04x}" for _ in range(count)]


def parse_device_info(data: bytes) -> dict:
    """Accept a dataset, without its USB data-container header."""
    r = Reader(data)
    result = {
        "standard_version": r.u16(),
        "vendor_extension_id": r.u32(),
        "vendor_extension_version": r.u16(),
        "vendor_extension_description": r.string(),
        "functional_mode": r.u16(),
    }
    for field in ("operations", "events", "device_properties", "capture_formats", "image_formats"):
        result[field] = r.array()
    for field in ("manufacturer", "model", "device_version"):
        result[field] = r.string()
    r.string()  # Consume and validate the serial; never put it in the report.
    if r.offset != len(data):
        raise ValueError(f"Unexpected trailing bytes after DeviceInfo: {len(data)-r.offset}")
    result.update(serial_omitted=True, dataset_bytes=len(data),
                  dataset_sha256=hashlib.sha256(data).hexdigest(),
                  dataset_consumed_exactly=True)
    return result


def parse_response(data: bytes) -> dict:
    if len(data) < 12:
        raise ValueError("Truncated PTP response container")
    length, kind, code, transaction = struct.unpack_from("<IHHI", data)
    if length != len(data) or kind != 3 or (length-12) % 4:
        raise ValueError("Invalid PTP response container length/type")
    if code != 0x2001:
        raise ValueError(f"PTP operation did not succeed: 0x{code:04x}")
    return {"container_length": length, "container_type": kind, "code": hex(code),
            "transaction_id": transaction,
            "parameters": [struct.unpack_from("<I", data, at)[0] for at in range(12, length, 4)]}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dataset", type=Path)
    p.add_argument("--response", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    try:
        result = parse_device_info(args.dataset.read_bytes())
        if args.response:
            result["response"] = parse_response(args.response.read_bytes())
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    except (OSError, ValueError) as error:
        p.exit(1, f"PTP parse failed: {error}\n")


if __name__ == "__main__":
    main()
