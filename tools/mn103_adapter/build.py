#!/usr/bin/env python3
"""Build a local offline MN103 decoder from hash-checked GNU sources.

Requires a C compiler and curl. Downloads only the three GNU source files;
does not install packages or modify system tools. GNU sources are GPLv3+.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


SOURCES = {
    "opcodes/m10300-dis.c": "3e90bed29c09a7b5bb37775835a2514e97ca9f34a63356fc94f339812f2886d3",
    "opcodes/m10300-opc.c": "248c10cfe1ac537021241297512fda789d09627a3c60d466015e3f63462c1148",
    "include/opcode/mn10300.h": "99e1076f08acfb0512c8df1a5e91a8c6f5e04bc68cddc1c31071f1e83c923b3d",
}
SOURCE_ROOT = "https://gnu.googlesource.com/binutils-gdb/+/refs/tags/binutils-2_42/"


def record(path):
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=Path("work/toolchain/mn10300"))
    parser.add_argument("--cc", default=shutil.which("clang") or shutil.which("cc"))
    args = parser.parse_args()
    try:
        if not args.cc:
            raise ValueError("A C compiler is required")
        curl = shutil.which("curl")
        if not curl:
            raise ValueError("curl is required for verified HTTPS source acquisition")
        args.build_dir.mkdir(parents=True, exist_ok=True)
        sources = []
        for name, expected in SOURCES.items():
            path = args.build_dir / name
            url = SOURCE_ROOT + name + "?format=TEXT"
            if not path.exists():
                import base64
                result = subprocess.run(
                    [curl, "--fail", "--silent", "--show-error", "--location",
                     "--proto", "=https", "--connect-timeout", "10", "--max-time", "30", url],
                    check=True, capture_output=True)
                data = base64.b64decode(result.stdout, validate=True)
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError(f"Downloaded source hash differs: {name}")
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as output:
                    output.write(data)
            entry = record(path)
            if entry["sha256"] != expected:
                raise ValueError(f"Existing GNU source hash differs: {name}")
            sources.append(dict(entry, url=url))
        adapter = Path(__file__).resolve().parent
        executable = args.build_dir / "mn103-dis"
        command = [args.cc, "-O0", "-include", "string.h", "-I", str(adapter),
                   "-I", str(args.build_dir / "include"), str(adapter / "main.c"),
                   str(args.build_dir / "opcodes/m10300-dis.c"),
                   str(args.build_dir / "opcodes/m10300-opc.c"), "-o", str(executable)]
        subprocess.run(command, check=True)
        receipt = {"schema": 1, "gnu_sources": sources, "compile_command": command,
                   "adapter_sources": [record(adapter / name) for name in
                                       ("main.c", "sysdep.h", "opintl.h", "disassemble.h")],
                   "executable": record(executable), "camera_code_executed": False}
        (args.build_dir / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"Built offline decoder: {executable}")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
