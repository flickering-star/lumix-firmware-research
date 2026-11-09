#!/usr/bin/env python3
"""Validate saved GX9 service transfers offline; never open a device or network.

Reads the private JSON/JSONL captures made by the Windows transport. A valid
checksum or an echoed request is not counted as a successful memory read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FRAME_BYTES = {8: 16, 1: 1030, 3: 8198}


def checked_frame(data: bytes) -> bytes:
    if not data or len(data) != FRAME_BYTES.get(data[0]):
        raise ValueError("Unknown frame class or incorrect length")
    if data[1] ^ data[2] != 255:
        raise ValueError("Sequence complement differs")
    if data[-1] or data[-2] != sum(data[1:-2]) & 255:
        raise ValueError("Checksum or terminator differs")
    return data


def decode_exchange(request: bytes, reply: bytes) -> dict:
    checked_frame(request)
    checked_frame(reply)
    if request[1:3] != reply[1:3]:
        raise ValueError("Response sequence differs from request")
    result = {
        "operation": hex(request[3]),
        "request_class": request[0],
        "response_class": reply[0],
        "request_sha256": hashlib.sha256(request).hexdigest(),
        "response_sha256": hashlib.sha256(reply).hexdigest(),
        "successful_read": False,
    }
    if request[3] in (0x35, 0x38):
        result.update(area=hex(request[6]), word_index=int.from_bytes(request[4:6], "little"))
    elif request[3] in (0x70, 0x75):
        if request[0] != 8 or any(request[8:14]):
            raise ValueError('Relative-word request geometry differs')
        result["word_index"] = int.from_bytes(request[4:8], "little")
    elif request[3] == 0x9B:
        if request[0] != 8 or any(request[8:14]):
            raise ValueError("Absolute-word request geometry differs")
        result["source_address"] = hex(int.from_bytes(request[4:8], "little"))
    elif request[3] == 0x9C:
        if request[0] != 8 or any(request[10:14]):
            raise ValueError("Absolute-word write geometry differs")
        result.update(destination_address=hex(int.from_bytes(request[4:8], "little")),
                      requested_word_hex=request[8:10].hex())
    elif request[3] == 0x5C:
        start = int.from_bytes(request[4:8], "little")
        end = int.from_bytes(request[8:12], "little")
        if end < start or end-start > 1024 or (start | end) & 1:
            raise ValueError("Block interval outside the reviewed aligned 1 KiB bound")
        result.update(start=hex(start), end_exclusive=hex(end), requested_source_bytes=end-start)
    if reply == request:
        result["result"] = "request_echo"
    elif request[3] == 0x9C and reply == bytes.fromhex("0800ff01000000000000000000000000"):
        # An ACK alone does not establish that the addressed memory changed.
        result.update(result="write_ack", write_acknowledged=True)
    elif reply[0] == 8 and reply[3] == 1 and not any(reply[5:14]):
        result.update(result="error_reply", status=reply[4])
    elif (request[3] in (0x35, 0x38, 0x70, 0x75, 0x9B)
          and reply[0] == 8 and reply[3] == 0x36 and not any(reply[6:14])):
        result.update(result="word_reply", successful_read=True, word_hex=reply[4:6].hex())
    elif request[3] in (0x3E, 0x5C) and reply[0] in (1, 3) and reply[3] == 5:
        result.update(result="bulk_reply", successful_read=True,
                      payload_bytes=len(reply)-6,
                      payload_sha256=hashlib.sha256(reply[4:-2]).hexdigest())
        if request[3] == 0x5C and result["requested_source_bytes"] == 0:
            result.update(result="empty_range_reply", successful_read=False)
        elif (request[3] == 0x5C
              and reply[4:4+result["requested_source_bytes"]]
              == request[4:4+result["requested_source_bytes"]]):
            result.update(result="unchanged_requested_bytes", successful_read=False)
    else:
        raise ValueError("Unclassified response; no read claim can be made")
    return result


def decode_events(events: list[dict]) -> list[dict]:
    exchanges = []
    request = None
    response_type = None
    failed = False
    for event in events:
        if event.get("event") != "bulk":
            continue
        if failed:
            raise ValueError("Another bulk transfer followed a transport failure")
        data = bytes.fromhex(event["hex"])
        if len(data) != event["bytes"]:
            raise ValueError("Logged byte count differs")
        status = event["status"]
        if status < 0:
            if request is None:
                raise ValueError("Transport failed without a pending request")
            exchanges.append({"operation": hex(request[3]), "result": "transport_failure",
                              "successful_read": False, "libusb_status": status,
                              "endpoint": event["endpoint"], "transferred_bytes": len(data),
                              "request_sha256": hashlib.sha256(request).hexdigest()})
            failed = True
            request = None
            continue
        if status != 0:
            raise ValueError("Unexpected nonzero successful libusb status")
        if event["endpoint"] == 1:
            if request is not None:
                raise ValueError("New request before previous response completed")
            request = checked_frame(data)
            response_type = None
        elif event["endpoint"] == 0x82:
            if request is None:
                raise ValueError("Response without a request")
            if response_type is None:
                if len(data) != 1 or data[0] not in FRAME_BYTES:
                    raise ValueError("Invalid response-type transfer")
                response_type = data[0]
            else:
                if not data or data[0] != response_type:
                    raise ValueError("Type-byte and full response disagree")
                exchanges.append(decode_exchange(request, data))
                request = None
                response_type = None
        else:
            raise ValueError("Unexpected endpoint in service capture")
    if request is not None:
        raise ValueError("Capture ends with an incomplete exchange")
    return exchanges


def read_capture(directory: Path) -> dict:
    if (directory / "events.jsonl").is_file():
        path = directory / "events.jsonl"
        raw = path.read_bytes()
        events = [json.loads(line) for line in raw.splitlines()]
    elif (directory / "events.json").is_file():
        path = directory / "events.json"
        raw = path.read_bytes()
        events = json.loads(raw)
    else:
        path = directory / "stdout.bin"
        raw = path.read_bytes()
        events = json.loads(raw.decode("utf-8-sig"))["events"]
    transactions = decode_events(events)
    return {"capture": directory.name, "event_source": path.name,
            "event_source_sha256": hashlib.sha256(raw).hexdigest(),
            "service_requests": len(transactions),
            "successful_words": sum(t["result"] == "word_reply" for t in transactions),
            "transactions": transactions}


def selftest() -> None:
    # Independent, captured wire bytes, including an echo and an error reply.
    request = bytes.fromhex("0800ff35002010000000000000006400")
    reply = bytes.fromhex("0800ff36f2b00000000000000000d700")
    assert decode_exchange(request, reply)["word_hex"] == "f2b0"
    assert not decode_exchange(request, request)["successful_read"]
    error = bytes.fromhex("0800ff01030000000000000000000300")
    assert decode_exchange(request, error)["result"] == "error_reply"
    empty_request = bytes.fromhex("0100ff5c") + bytes(1024) + bytes.fromhex("5b00")
    empty_reply = bytes.fromhex("0100ff05") + bytes(1024) + bytes.fromhex("0400")
    empty = decode_exchange(empty_request, empty_reply)
    assert empty["result"] == "empty_range_reply" and not empty["successful_read"]
    for bad in (reply[:-1], reply[:4] + b"\0" + reply[5:]):
        try:
            checked_frame(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Corrupt/truncated frame accepted")
    try:
        decode_events([{"event": "bulk", "endpoint": 0x82, "status": 0,
                        "bytes": 1, "hex": "08"}])
    except ValueError:
        pass
    else:
        raise AssertionError("Response without request accepted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, nargs="*")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    selftest()
    if args.selftest and not args.captures:
        print("Captured-frame controls passed; no camera or network accessed.")
        return
    if not args.captures:
        parser.error("Provide a capture directory or --selftest")
    result = {"schema": 1, "scope": "Offline wire validation, not GX9 handler identification",
              "captures": [read_capture(p) for p in args.captures]}
    output = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(output)
        print(f"Validated {len(args.captures)} saved captures into {args.out}")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
