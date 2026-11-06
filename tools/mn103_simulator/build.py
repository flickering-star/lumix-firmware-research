#!/usr/bin/env python3
"""Build a pinned GNU AM33-2 simulator and the local GM5 offline harness.

Downloads into ignored work/, preserves GNU licensing, and installs no system
packages. A documented sed recipe fix is required on BSD/macOS hosts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

VERSION = "16.3"
URL = f"https://ftp.gnu.org/gnu/gdb/gdb-{VERSION}.tar.xz"
ARCHIVE_SHA256 = "bcfcd095528a987917acf9fff3f1672181694926cc18d609c99d0042c00224c5"
PATCHES = {
    "sim/Makefile.in": ("35b052c0a7dd60eb30ca1496d447343b28c4334ade4cda7eb38da40318a28bf8",
                        "0967c8a646087071bfea0aacd6c13ec738d3eba6f912f0abb80fbe7709a88679"),
    "sim/common/local.mk": ("d07e5a79385312cc127bb946dcf0ce3141d6ffca3958f5d87ef98f9c8de0fb0c",
                            "5490848a4619200b94ecf4ebabc73682cb38c458fd005ecf20a3e5feedb547fa"),
}
OPTIONS = ["--target=mn10300-elf", "--disable-gdb", "--disable-gdbserver", "--enable-sim",
           "--disable-nls", "--disable-werror", "--without-python", "--without-guile",
           "--without-debuginfod", "--without-zstd"]
AM33_ORIGINAL_SHA256 = "e10def0a98dab57f36d85cda7beeb79365bd0e14d4b76ebf4cf634b3fbe07438"


def artifact(path: Path) -> dict:
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def run_logged(command: list[str], directory: Path, log: Path) -> None:
    print(f"Running {command[0]}; log {log}", flush=True)
    with log.open("a") as stream:
        stream.write(json.dumps(command)+"\n")
        stream.flush()
        result = subprocess.run(command, cwd=directory, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError(f"Command failed: {command[0]}\n"+"\n".join(log.read_text().splitlines()[-35:]))


def build(work: Path, jobs: int, cc: str, variant: str | None = None) -> dict:
    if variant is not None and not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", variant):
        raise ValueError("Invalid harness variant label")
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    archive = work/f"gdb-{VERSION}.tar.xz"
    if not archive.exists():
        subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                        "--max-time", "300", "--output", str(archive), URL], check=True)
    if artifact(archive)["sha256"] != ARCHIVE_SHA256:
        raise ValueError("GNU archive hash differs from pinned source")
    source, output = work/f"gdb-{VERSION}", work/"gdb-mn10300-build"
    if not (source/"configure").exists():
        names = subprocess.check_output(["tar", "-tJf", str(archive)], text=True).splitlines()
        if any(not name.startswith(f"gdb-{VERSION}/") or ".." in Path(name).parts for name in names):
            raise ValueError("Unexpected archive paths")
        subprocess.run(["tar", "-xJf", str(archive), "-C", str(work)], check=True)
    patched = []
    for name, (before, after) in PATCHES.items():
        path = source/name
        digest = artifact(path)["sha256"]
        if digest == before:
            raw = path.read_bytes()
            if raw.count(b";p}'") != 1:
                raise ValueError("Unexpected GNU module-scanner recipe")
            path.write_bytes(raw.replace(b";p}'", b";p;}'"))
        if artifact(path)["sha256"] != after:
            raise ValueError(f"Unexpected source modification: {path}")
        patched.append({"path": name, "original_sha256": before, "patched_sha256": after,
                        "purpose": "BSD sed requires a separator before the closing command-group brace."})
    adapter = Path(__file__).resolve().parent
    extension = adapter/"short-swaps.igen"
    am33 = source/"sim/mn10300/am33.igen"
    raw = am33.read_bytes()
    marker = b"\n// GM5 harness: documented short swap encodings.\n"
    original = raw.split(marker)[0]
    if hashlib.sha256(original).hexdigest() != AM33_ORIGINAL_SHA256:
        raise ValueError("Unexpected original GNU AM33 instruction definitions")
    patched_am33 = original+marker+extension.read_bytes()
    if raw != patched_am33:
        am33.write_bytes(patched_am33)
    patched.append({"path": "sim/mn10300/am33.igen", "original_sha256": AM33_ORIGINAL_SHA256,
                    "patched_sha256": artifact(am33)["sha256"], "extension": artifact(extension),
                    "purpose": "Add short swap/swaph encodings listed in GNU's opcode table, using its existing long-form semantics."})
    output.mkdir(exist_ok=True)
    configure = [str(source/"configure"), *OPTIONS]
    if not (output/"Makefile").exists():
        run_logged(configure, output, output/"configure-repro.log")
    make_command = ["make", f"-j{jobs}", "all-sim", "MAKEINFO=true"]
    run_logged(make_command, output, output/"build-repro.log")
    modules = output/"sim/mn10300/modules.c"
    if "  sim_install_engine," not in modules.read_text():
        raise ValueError("Execution engine module is absent; simulator results would be invalid")
    runner = Path(__file__).resolve().parent/"runner.c"
    binary = output/("gm5-mn103-sim-"+variant if variant else "gm5-mn103-sim")
    command = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
               '-DPACKAGE="gm5-emulator"', '-DPACKAGE_VERSION="0.1"',
               "-I", str(output/"bfd"), "-I", str(source/"include"), str(runner)]
    host_arch = subprocess.check_output(["file", str(output/"sim/mn10300/run")], text=True).strip()
    if platform.system() == "Darwin":
        if "x86_64" in host_arch:
            command[1:1] = ["-arch", "x86_64"]
        elif "arm64" in host_arch:
            command[1:1] = ["-arch", "arm64"]
    # Use GNU's existing optional instruction-prefix hook in a separate engine
    # object. The source archive and generated instruction semantics stay intact.
    generated_engine = output/"sim/mn10300/engine.c"
    hooked_engine = output/"gm5-engine.c"
    hooked_engine.write_bytes(b'#include "hooks.h"\n'+generated_engine.read_bytes())
    include_dirs = [output, output/"sim", source/"sim", source/"sim/mn10300", source/"sim/common",
                    output/"sim/mn10300", output/"gnulib/import", source/"gnulib/import",
                    output/"bfd", source/"include", source, adapter]
    native_flags = [cc, "-std=gnu11", "-O2", "-DHAVE_CONFIG_H", "-DPOLL_QUIT_INTERVAL=0x20",
                    "-DWITH_TARGET_WORD_BITSIZE=32", "-DWITH_TARGET_WORD_MSB=31"]
    if platform.system() == "Darwin":
        native_flags[1:1] = command[1:3] if command[1] == "-arch" else []
    for directory in include_dirs:
        native_flags += ["-I", str(directory)]
    hook_objects, hook_commands = [], []
    for src, obj in ((hooked_engine, output/"gm5-engine.o"), (adapter/"hooks.c", output/"gm5-hooks.o"),
                     (adapter/"devices.c", output/"gm5-devices.o"), (adapter/"nor_model.c", output/"gm5-nor-model.o"),
                     (adapter/"control_model.c", output/"gm5-control-model.o")):
        hook_command = [*native_flags, "-c", str(src), "-o", str(obj)]
        run_logged(hook_command, output, output/"harness-build.log")
        hook_commands.append(hook_command)
        hook_objects.append(obj)
    command += [str(path) for path in hook_objects]
    libraries = [output/"sim/mn10300/libsim.a", output/"opcodes/.libs/libopcodes.a",
                 output/"bfd/.libs/libbfd.a", output/"gnulib/import/libgnu.a", output/"libiberty/libiberty.a"]
    command += [str(path) for path in libraries]
    command += ["-lz", "-lm"]
    if platform.system() == "Darwin":
        command += ["-liconv", "-ltermcap"]
    command += ["-o", str(binary)]
    run_logged(command, output, output/"harness-build.log")
    report = {"schema": 1, "scope": "GNU AM33-2 CPU core with offline GM5 execution harness",
              "gnu_archive": dict(artifact(archive), url=URL), "build_recipe_patches": patched,
              "configure_command": configure, "make_command": make_command,
              "harness_compile_command": command, "host_executable_architecture": host_arch,
              "instrumented_engine_compile_commands": hook_commands,
              "gnu_libraries": [artifact(path) for path in libraries], "generated_modules": artifact(modules),
              "original_generated_engine": artifact(generated_engine),
              "instrumented_engine_copy": artifact(hooked_engine),
              "execution_hooks": [artifact(adapter/name) for name in ("hooks.c", "hooks.h")],
              "device_sources": [artifact(adapter/name) for name in ("devices.c", "devices.h", "nor_model.c", "nor_model.h", "control_model.c", "control_model.h")],
              "instrumentation": "GNU's instruction-prefix hook adds bounded stops/traces; generated CPU instruction semantics are unchanged.",
              "harness_source": artifact(runner), "build_driver": artifact(Path(__file__)),
              "executable": artifact(binary), "camera_contacted": False,
              "license": "GNU core and linked harness: GPL-3.0-or-later; GNU notices retained in source tree."}
    report["variant"] = variant
    receipt = "gm5-emulator-build-"+variant+".json" if variant else "gm5-emulator-build.json"
    (output/receipt).write_text(json.dumps(report, indent=2)+"\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path("work/toolchain"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--cc", default=shutil.which("clang") or shutil.which("cc"))
    parser.add_argument("--variant", help="Build a separately named harness and receipt, preserving the default executable")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8 or not args.cc:
        parser.error("A C compiler and1..8build jobs are required")
    try:
        report = build(args.work, args.jobs, args.cc, args.variant)
        print("Built offline CPU harness: "+report["executable"]["path"])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Build failed: {error}\n")


if __name__ == "__main__":
    main()
