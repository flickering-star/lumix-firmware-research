#!/usr/bin/env python3
"""Record Lumix aspect-ratio evidence on a computer connected to the camera."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import http.client
import json
from pathlib import Path
import socket
import sys
from urllib.parse import urlencode, urlsplit
import xml.etree.ElementTree as ET

MAX_RESPONSE = 8 * 1024 * 1024
QUERIES = (
    ("state", {"mode": "getstate"}),
    ("capability", {"mode": "getinfo", "type": "capability"}),
    ("allmenu", {"mode": "getinfo", "type": "allmenu"}),
    ("curmenu", {"mode": "getinfo", "type": "curmenu"}),
    ("aspectratio", {"mode": "getsetting", "type": "aspectratio"}),
    ("pictsize", {"mode": "getsetting", "type": "pictsize"}),
)
# Recovered from Image App 1.10.14; availability on GM5 is unverified.
# See docs/reverse-engineering.md for source paths and model-family limits.
EXTENDED_QUERIES = (
    ("lens", {"mode": "getinfo", "type": "lens"}),
    ("curmode", {"mode": "getinfo", "type": "curmode"}),
    ("ddd", {"mode": "getinfo", "type": "ddd"}),
    ("camsetting", {"mode": "getinfo", "type": "camsetting"}),
)


def response_info(body: bytes) -> dict:
    """HTTP 200 alone is insufficient: the application can return err-* in it."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return {"result": None, "xml": False, "aspect_nodes": []}
    result = next((e.text.strip() for e in root.iter()
                   if e.tag.rsplit("}", 1)[-1] == "result" and e.text), None)
    nodes = []
    for element in root.iter():
        if "aspect" in element.tag.lower() or any(
            "aspect" in str(v).lower() for v in element.attrib.values()
        ):
            nodes.append(ET.tostring(element, encoding="unicode"))
    return {"result": result, "xml": True, "aspect_nodes": nodes,
            "root_tag": root.tag.rsplit("}", 1)[-1]}


def camera_address(host: str):
    address = urlsplit("//" + host)
    if (not address.hostname or address.username or address.password
            or address.path or address.query or address.fragment):
        raise ValueError("Use a camera hostname/IP, optionally followed by :port")
    return address


def request_capture(host: str, params: dict, timeout: float) -> tuple[int, list, bytes]:
    address = camera_address(host)
    # This client runs on the user's LAN, not through an Internet download proxy.
    connection = http.client.HTTPConnection(address.hostname, address.port or 80, timeout=timeout)
    try:
        connection.request("GET", "/cam.cgi?" + urlencode(params), headers={"Connection": "close"})
        response = connection.getresponse()
        body = response.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            raise ValueError("Camera response exceeds the 8 MiB capture limit")
        return response.status, response.getheaders(), body
    finally:
        connection.close()


def request(host: str, params: dict, timeout: float) -> tuple[int, bytes]:
    status, _, body = request_capture(host, params, timeout)
    return status, body


def console_banner(host: str, timeout: float, port: int = 23) -> tuple[dict, bytes]:
    """Connect once, send no application bytes, retain any unsolicited banner."""
    address = camera_address(host)
    record = {"port": port, "application_bytes_sent": 0, "shell_confirmed": False}
    body = b""
    try:
        with socket.create_connection((address.hostname, port), timeout=timeout) as connection:
            record["tcp_connected"] = True
            connection.settimeout(min(timeout, 2.0))
            try:
                body = connection.recv(4096)
                record["observation"] = "banner_received" if body else "peer_closed"
            except socket.timeout:
                record["observation"] = "open_without_banner"
    except OSError as exc:
        record.setdefault("tcp_connected", False)
        record["error"] = str(exc)
    return record, body


def snapshot(host: str, out: Path, label: str, firmware: str, timeout: float,
             pair: bool = False, extended: bool = False, check_console: bool = False,
             client_id: str = "0", client_name: str = "GM5 Aspect Research") -> dict:
    camera_address(host)
    out.mkdir(parents=True, exist_ok=False)
    report = {"schema": 2, "label": label, "firmware_user_reported": firmware,
              "host": host, "created_utc": datetime.now(timezone.utc).isoformat(),
              "pair_requested": pair, "extended_requested": extended, "responses": []}
    queries = list(QUERIES) + (list(EXTENDED_QUERIES) if extended else [])
    if pair:
        # Explicit opt-in: may show an approval prompt on the camera.
        queries.insert(0, ("pair", {"mode": "accctrl", "type": "req_acc",
                                    "value": client_id, "value2": client_name}))
    for index, (name, params) in enumerate(queries):
        record = {"name": name, "params": params, "ok": False}
        try:
            status, headers, body = request_capture(host, params, timeout)
            filename = f"{index:02d}_{name}.response"
            (out / filename).write_bytes(body)
            record.update(response_info(body))
            content_type = next((v for k, v in headers if k.lower() == "content-type"), "")
            record.update({"http_status": status, "headers": headers,
                           "content_type": content_type, "file": filename, "bytes": len(body),
                           "sha256": hashlib.sha256(body).hexdigest()})
            record["ok"] = status == 200 and record["result"] == "ok"
            if (name == "camsetting" and status == 200 and body
                    and content_type.split(";", 1)[0].strip().lower() == "application/octet-stream"
                    and not record["xml"]):
                record.update(ok=True, response_kind="binary_settings_candidate",
                              format_validated=False)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            record["error"] = str(exc)
        report["responses"].append(record)
        print(f"{name}: " + ("ok" if record["ok"] else str(
            record.get("error") or record.get("result") or "unrecognized response")))
    # Strictly distinguish incomplete probes from an entirely successful capture.
    report["all_queries_ok"] = all(r["ok"] for r in report["responses"])
    if check_console:
        record, body = console_banner(host, timeout)
        if body:
            filename = "console-23.banner"
            (out / filename).write_bytes(body)
            record.update(file=filename, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        report["console_banner"] = record
        print("console: " + record.get("observation", record.get("error", "unknown")))
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def compare(left: Path, right: Path) -> str:
    changes = []
    for directory in (left, right):
        if not (directory / "summary.json").is_file():
            raise ValueError(f"Not a capture directory (summary.json missing): {directory}")
    for name, _ in QUERIES + EXTENDED_QUERIES:
        if name not in dict(QUERIES) and not any(
                list(d.glob(f"[0-9][0-9]_{name}.response")) for d in (left, right)):
            continue
        # Work only with known response filenames, never paths from camera XML.
        def text_at(directory: Path) -> str:
            candidates = list(directory.glob(f"[0-9][0-9]_{name}.response"))
            if len(candidates) != 1:
                return "[response unavailable]\n"
            content = candidates[0].read_bytes()
            if name == "camsetting":
                return f"{len(content)} bytes; SHA-256 {hashlib.sha256(content).hexdigest()}\n"
            try:
                root = ET.fromstring(content)
                ET.indent(root)
                return ET.tostring(root, encoding="unicode") + "\n"
            except ET.ParseError:
                return content.decode("utf-8", errors="replace")
        changes.extend(difflib.unified_diff(
            text_at(left).splitlines(keepends=True),
            text_at(right).splitlines(keepends=True),
            fromfile=f"{left.name}/{name}", tofile=f"{right.name}/{name}"))
    return "".join(changes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot", help="Read state, menus and aspect-ratio settings")
    snap.add_argument("--host", default="192.168.54.1")
    snap.add_argument("--out", type=Path, required=True, help="New directory; existing captures are preserved")
    snap.add_argument("--label", required=True, help="e.g. japan-4x3 or global-16x9")
    snap.add_argument("--firmware", default="unknown", help="Version shown in the camera menu")
    snap.add_argument("--timeout", type=float, default=5)
    snap.add_argument("--pair", action="store_true", help="Request a session; approve it on the camera if prompted")
    snap.add_argument("--client-id", default="0", help="Pairing value observed in the app capture, if needed")
    snap.add_argument("--client-name", default="GM5 Aspect Research", help="Pairing client name")
    snap.add_argument("--extended", action="store_true", help="Also read lens, curmode, ddd and binary camsetting (GM5 support unverified)")
    snap.add_argument("--console-banner", action="store_true", help="Connect once to TCP 23 and listen; send no shell commands")
    diff = commands.add_parser("compare", help="Compare two saved captures offline")
    diff.add_argument("left", type=Path)
    diff.add_argument("right", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "compare":
            print(compare(args.left, args.right) or "No response differences.", end="\n")
            return 0
        if args.timeout <= 0:
            parser.error("--timeout must be positive")
        report = snapshot(args.host, args.out, args.label, args.firmware, args.timeout, args.pair,
                          args.extended, args.console_banner, args.client_id, args.client_name)
        return 0 if report["all_queries_ok"] else 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
