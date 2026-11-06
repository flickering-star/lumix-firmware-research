import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gm1_capture_verify as verify
from gm5_flash_backup import prepare_prefix
from test_gm1_capture_verify import exchange, frame
from test_gm1_native_writer import HARNESS


def partial(directory, *, mode="nor-backup", prefix=b"", parent=None):
    result = directory / "result"
    result.mkdir(parents=True)
    events = [{"event": "registry_identity", "product_name": "DMC-GM5", "vendor_id": 0x04DA,
               "product_id": 0x2370, "interface": [255, 160, 176], "configuration": 1,
               "alternate_setting": 0, "endpoints": 3}]
    for n in range(16):
        events += exchange(index=0x3F80+n, payload=verify.GM5_CONTROL[2*n:2*n+2])
    blocks = len(prefix)//1024
    secondary = mode in ("secondary", "resume-secondary")
    base_block = (verify.SECONDARY_BASE-verify.BASE)//1024 if secondary else 0
    if prefix:
        for n in dict.fromkeys((0, blocks//2, blocks-1)):
            events += exchange(0x5C, base_block+n, prefix[1024*n:1024*n+1024])
    new = b"\xa5"*1024 if prefix else b"\xa5"*3072
    for n in range(len(new)//1024):
        events += exchange(0x5C, base_block+blocks+n, new[1024*n:1024*n+1024])
    events += exchange(0x5C, base_block+blocks+len(new)//1024, bytes(1024))[:3]
    events += [{"event": "api_result", "step": "prepare_bulk_in", "result": "0xe0004051"}]
    summary = {"model": "DMC-GM5", "mode": mode, "exit_status": 1, "validated_word_responses": 16,
               "settings_bytes": 32, "program_block_bytes": len(new),
               "control_requests_attempted": sum(e["event"] == "control_attempt" for e in events),
               "bulk_writes_attempted": sum(e["event"] == "bulk_out_attempt" for e in events)}
    (result / "events.jsonl").write_text("".join(json.dumps(e)+"\n" for e in events))
    (result / "summary.json").write_text(json.dumps(summary))
    (result / "fixed-markers.bin").write_bytes(verify.GM5_CONTROL)
    filename = "program2.bin" if secondary else "program-main.bin" if mode in ("program", "resume") else "flash32m.bin"
    (result / filename).write_bytes(prefix+new)
    return prefix+new


class BackupTests(unittest.TestCase):
    def test_main_resume_is_model_sized_and_cannot_mix_with_full_nor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = partial(root/"first", mode="program")
            output = root/"resume"; output.mkdir()
            with self.assertRaisesRegex(ValueError, "nor"):
                prepare_prefix(root/"first", output)
            manifest = prepare_prefix(root/"first", output, "program")
            self.assertEqual(manifest["native_resume_mode"], "resume")
            self.assertEqual(manifest["next_program_address"], "0x40000c00")
            data = partial(output, mode="resume", prefix=original)
            report = verify.verify_capture(output, allow_incomplete=True)
            self.assertEqual(report["program_file_base"], "0x40000000")
            self.assertEqual(report["resume_anchors_verified"], 3)
            self.assertEqual(report["program_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual((root/"first/result/program-main.bin").read_bytes(), original)

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS SDK")
    def test_native_main_only_wrapper_bounds_under_sanitizers(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory/"main-bounds.c"
            # Rename only the outer wrapper main, retaining its exact macro
            # selection, and test the same static block-request boundary.
            wrapper = (root/"tools/gm5_flash_backup_macos.c").read_text()
            wrapper = wrapper.replace('"gm1_usb_probe_macos.c"', json.dumps(str(root/"tools/gm1_usb_probe_macos.c")))
            wrapper = wrapper.replace("int main(int argc, char **argv)", "int wrapper_main(int argc, char **argv)")
            source.write_text("#define PROBE_GM5_MAIN_ONLY\n"+wrapper+"\nint main(void) {\n"
                              "uint8_t packet[BLOCK_FRAME_BYTES];\n"
                              "return PROGRAM_BYTES != 0x800000 || selftest() || !block_request(packet, 0x407ffc00) "
                              "|| block_request(packet, 0x40800000) || block_request(packet, 0x3ffffc00);\n}\n")
            binary = directory/"main-bounds"
            subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-deprecated-declarations", "-fsanitize=address,undefined", str(source),
                            "-framework", "IOKit", "-framework", "CoreFoundation", "-o", str(binary)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_program2_resume_rechecks_anchors_and_rejects_component_mix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = partial(root/"first", mode="secondary")
            output = root/"resume"; output.mkdir()
            with self.assertRaisesRegex(ValueError, "nor"):
                prepare_prefix(root/"first", output)
            manifest = prepare_prefix(root/"first", output, "program2")
            self.assertEqual(manifest["next_program_address"], "0x41400c00")
            data = partial(output, mode="resume-secondary", prefix=original)
            report = verify.verify_capture(output, allow_incomplete=True)
            self.assertEqual(report["program_file_base"], "0x41400000")
            self.assertEqual(report["resume_anchors_verified"], 3)
            self.assertEqual(report["program_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual((root/"first/result/program2.bin").read_bytes(), original)

    def test_full_nor_opt_in_is_model_specific_and_bounded(self):
        def request(address):
            return frame(1, 0x5C, struct.pack("<II", address, address+1024))
        for address in (0x40800000, 0x413FFC00, 0x41FFFC00):
            verify.request(request(address), "DMC-GM5", full_nor=True)
            with self.assertRaises(ValueError):
                verify.request(request(address), "DMC-GM5")
        for address in (0x3FFFFC00, 0x42000000):
            with self.assertRaises(ValueError):
                verify.request(request(address), "DMC-GM5", full_nor=True)
        with self.assertRaises(ValueError):
            verify.request(request(0x41FFFC00), "DMC-GM1", full_nor=True)

    def test_interrupted_backup_resume_preserves_original_and_rechecks_anchors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = partial(root / "first")
            output = root / "resume"
            output.mkdir()
            manifest = prepare_prefix(root / "first", output)
            self.assertEqual(manifest["next_program_address"], "0x40000c00")
            self.assertEqual((output / "verified-prefix.bin").read_bytes(), original)
            data = partial(output, mode="resume-nor-backup", prefix=original)
            report = verify.verify_capture(output, allow_incomplete=True)
            self.assertEqual(report["verified_prefix_bytes"], 4096)
            self.assertEqual(report["resume_anchors_verified"], 3)
            self.assertEqual(report["program_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual((root / "first/result/flash32m.bin").read_bytes(), original)
            changed = bytearray((output / "verified-prefix.bin").read_bytes())
            changed[100] ^= 1
            (output / "verified-prefix.bin").write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "prefix"):
                verify.verify_capture(output, allow_incomplete=True)

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS SDK")
    def test_native_full_nor_bounds_and_resume_under_sanitizers(self):
        root = Path(__file__).resolve().parents[1]
        harness = HARNESS.replace("events = tmpfile();", "if (selftest()) return 1; events = tmpfile();")
        harness = harness.replace("fclose(events);\n    return", "ok = ok && read_program_blocks(usb, 1, 2, argv[1], \"upper.bin\", 32767, 32767, 1, false, NULL, NULL) && verify_file(argv[1], \"upper.bin\", 32767, 1);\n    fclose(events);\n    return")
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "backup-test.c"
            source.write_text("#define PROBE_GM5\n#define PROBE_GM5_FULL_NOR\n#define main shared_main\n#include "
                              + json.dumps(str(root / "tools/gm1_usb_probe_macos.c"))
                              + "\n#undef main\n" + harness)
            binary = directory / "backup-test"
            subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-deprecated-declarations", "-fsanitize=address,undefined", str(source),
                            "-framework", "IOKit", "-framework", "CoreFoundation", "-o", str(binary)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(binary), str(directory)], check=True, capture_output=True, text=True)
            self.assertEqual((directory / "upper.bin").stat().st_size, 1024)


if __name__ == "__main__":
    unittest.main()
