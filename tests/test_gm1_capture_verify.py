import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import gm1_capture_verify as verify
from gm1_program_resume import prepare_prefix


MARKERS = bytes.fromhex("50616e61736f6e696300000064001400444d432d474d31000000000000000000")


def frame(kind, operation, payload):
    size = 1030 if kind == 1 else 16
    raw = bytearray(size)
    raw[0], raw[2], raw[3] = kind, 255, operation
    raw[4:4 + len(payload)] = payload
    raw[-2] = sum(raw[1:-2]) & 255
    return bytes(raw)


def exchange(operation=0x38, index=0x3F80, payload=b"Pa"):
    if operation == 0x38:
        request = frame(8, operation, struct.pack("<HB", index, 0x20))
    else:
        start = verify.BASE + index * verify.BLOCK
        request = frame(1, operation, struct.pack("<II", start, start + verify.BLOCK))
    reply = frame(request[0], 5 if operation == 0x5C else 0x36, payload)
    return [
        {"event": "control_attempt", "setup_hex": "4000000000000000"},
        {"event": "bulk_out_attempt", "bytes": len(request), "hex": request.hex()},
        {"event": "control_attempt", "setup_hex": "4000000001000000"},
        {"event": "bulk_in_type", "bytes": 1, "hex": bytes([request[0]]).hex()},
        {"event": "control_attempt", "setup_hex": "4000000001000000"},
        {"event": "bulk_in", "bytes": len(reply), "hex": reply.hex()},
    ]


def partial_capture(directory, mode="program", prefix=b"", anchor_payloads=None):
    result = directory / "result"
    result.mkdir(parents=True)
    events = []
    secondary = mode in ("secondary", "resume-secondary")
    base_block = (verify.SECONDARY_BASE - verify.BASE) // verify.BLOCK if secondary else 0
    for i in range(16):
        events += exchange(index=0x3F80 + i, payload=MARKERS[2*i:2*i+2])
    if mode in ("resume", "resume-secondary"):
        first = len(prefix) // verify.BLOCK
        anchors = list(dict.fromkeys((0, first // 2, first - 1)))
        for index in anchors:
            payload = prefix[index*verify.BLOCK:(index+1)*verify.BLOCK]
            if anchor_payloads and index in anchor_payloads:
                payload = anchor_payloads[index]
            events += exchange(0x5C, base_block + index, payload)
        program = prefix + b"\x44" * verify.BLOCK
        events += exchange(0x5C, base_block + first, b"\x44" * verify.BLOCK)
        new_bytes = verify.BLOCK
    else:
        program = b"".join(bytes([n]) * verify.BLOCK for n in (0x11, 0x22, 0x33))
        for index in range(3):
            events += exchange(0x5C, base_block + index, program[index*verify.BLOCK:(index+1)*verify.BLOCK])
        new_bytes = len(program)
    pending = exchange(0x5C, base_block + len(program) // verify.BLOCK, b"\0" * verify.BLOCK)[:3]
    events += pending + [
        {"event": "api_result", "step": "prepare_bulk_in", "result": "0xe0004051"},
        {"event": "api_result", "step": "close_interface", "result": "0x00000000"},
    ]
    summary = {"mode": mode, "exit_status": 1, "validated_word_responses": 16,
               "settings_bytes": 32, "program_block_bytes": new_bytes,
               "control_requests_attempted": sum(e["event"] == "control_attempt" for e in events),
               "bulk_writes_attempted": sum(e["event"] == "bulk_out_attempt" for e in events)}
    (result / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (result / "summary.json").write_text(json.dumps(summary))
    (result / "fixed-markers.bin").write_bytes(MARKERS)
    (result / ("program2.bin" if secondary else "program-main.bin")).write_bytes(program)
    return program


class PacketSequenceTests(unittest.TestCase):
    def test_gm5_ui_status_read_is_fixed_to_one_block_and_its_model(self):
        def request_at(address):
            return frame(1, 0x5C, struct.pack("<II", address, address+1024))
        parsed = verify.request(request_at(0x701F9400), "DMC-GM5")
        self.assertEqual(parsed["index"], (0x701F9400-verify.BASE)//1024)
        for model, address in (("DMC-GM1", 0x701F9400),
                               ("DMC-GM5", 0x701F9000), ("DMC-GM5", 0x701F9800)):
            with self.assertRaisesRegex(ValueError, "interval"):
                verify.request(request_at(address), model)

    def test_golden_word_frame_and_two_stage_receive(self):
        events = exchange()
        self.assertEqual(events[1]["hex"], "0800ff38803f20000000000000001600")
        self.assertEqual(events[-1]["hex"], "0800ff3650610000000000000000e600")
        self.assertEqual(verify.parse_events(events)["frames"][0]["payload"], b"Pa")

    def test_missing_second_preparation_is_rejected(self):
        events = exchange()
        del events[4]
        with self.assertRaisesRegex(ValueError, "second IN preparation"):
            verify.parse_events(events)

    def test_corrupt_response_and_wrong_type_are_rejected(self):
        for at, value in ((3, "01"), (5, "0800ff3651610000000000000000e600")):
            events = exchange()
            events[at]["hex"] = value
            with self.assertRaises(ValueError):
                verify.parse_events(events)

    def test_rejects_write_opcode_and_overlong_block_interval(self):
        events = exchange(0x5C, 0, bytes(1024))
        for offset, replacement in ((3, bytes([0x9C])), (8, struct.pack("<I", verify.BASE + 1026))):
            mutated = copy.deepcopy(events)
            raw = bytearray.fromhex(mutated[1]["hex"])
            raw[offset:offset+len(replacement)] = replacement
            raw[-2] = sum(raw[1:-2]) & 255
            mutated[1]["hex"] = raw.hex()
            with self.assertRaises(ValueError):
                verify.parse_events(mutated)

    def test_failed_transaction_requires_explicit_partial_verification(self):
        events = exchange()[:3] + [{"event": "api_result", "step": "prepare_bulk_in", "result": "0xe0004051"}]
        with self.assertRaises(ValueError):
            verify.parse_events(events)
        self.assertEqual(verify.parse_events(events, True)["frames"], [])
        with self.assertRaisesRegex(ValueError, "after a recorded API error"):
            verify.parse_events(events + exchange(), True)

    def test_block_requests_reject_unmapped_gap_and_secondary_end(self):
        for address in (verify.BASE + verify.PROGRAM_BYTES, verify.SECONDARY_BASE - 1024,
                        verify.SECONDARY_BASE + verify.SECONDARY_BYTES):
            events = exchange(0x5C, (address-verify.BASE)//verify.BLOCK, bytes(1024))
            with self.assertRaisesRegex(ValueError, "interval"):
                verify.parse_events(events)
        for address in (verify.SECONDARY_BASE, verify.SECONDARY_BASE + verify.SECONDARY_BYTES - 1024):
            events = exchange(0x5C, (address-verify.BASE)//verify.BLOCK, bytes(1024))
            self.assertEqual(len(verify.parse_events(events)["frames"]), 1)


class ResumeIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.parent = self.root / "parent"
        self.original = partial_capture(self.parent)

    def test_preparation_preserves_original_and_selects_next_address(self):
        output = self.root / "resume"
        output.mkdir()
        manifest = prepare_prefix(self.parent, output)
        self.assertEqual(manifest["next_program_address"], "0x40000c00")
        self.assertEqual((output / "verified-prefix.bin").read_bytes(), self.original)
        self.assertEqual((self.parent / "result/program-main.bin").read_bytes(), self.original)

    def test_corrupted_saved_prefix_is_rejected_before_preparation(self):
        path = self.parent / "result/program-main.bin"
        path.write_bytes(b"X" + self.original[1:])
        output = self.root / "resume"
        output.mkdir()
        with self.assertRaisesRegex(ValueError, "differs from validated packets"):
            prepare_prefix(self.parent, output)
        self.assertFalse((output / "verified-prefix.bin").exists())

    def test_resume_checks_lineage_anchors_and_advance(self):
        output = self.root / "resume"
        output.mkdir()
        prepare_prefix(self.parent, output)
        partial_capture(output, "resume", self.original)
        report = verify.verify_capture(output, True)
        self.assertEqual(report["resume_anchors_verified"], 3)
        self.assertEqual(report["verified_prefix_bytes"], 4096)
        self.assertEqual(report["next_program_address"], "0x40001000")
        self.assertFalse(report["complete"])

    def test_changed_live_anchor_and_lineage_cycle_are_rejected(self):
        output = self.root / "resume"
        output.mkdir()
        prepare_prefix(self.parent, output)
        partial_capture(output, "resume", self.original, {1: b"Y" * verify.BLOCK})
        with self.assertRaisesRegex(ValueError, "anchor differs"):
            verify.verify_capture(output, True)
        path = output / "resume-manifest.json"
        manifest = json.loads(path.read_text())
        manifest["parent_capture"] = str(output)
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "cycle"):
            verify.verify_capture(output, True)

    def test_initializer_dense_and_original_sparse_file_coordinates(self):
        for sparse in (False, True):
            directory = self.root / ("sparse" if sparse else "dense")
            result = directory / "result"
            result.mkdir(parents=True)
            events = []
            for i in range(16):
                events += exchange(index=0x3F80+i, payload=MARKERS[2*i:2*i+2])
            chunks = []
            for n in range(32):
                payload = bytes([n]) * verify.BLOCK
                chunks.append(payload)
                events += exchange(0x5C, 0x5A3800 // verify.BLOCK + n, payload)
            data = b"".join(chunks)
            with (result / "ram-initializer.bin").open("wb") as stream:
                if sparse:
                    stream.seek(0x5A3800)
                stream.write(data)
            (result / "fixed-markers.bin").write_bytes(MARKERS)
            (result / "events.jsonl").write_text("".join(json.dumps(e)+"\n" for e in events))
            (result / "summary.json").write_text(json.dumps({
                "mode": "initializer", "exit_status": 0, "validated_word_responses": 16,
                "settings_bytes": 32, "program_block_bytes": 32768,
                "control_requests_attempted": 144, "bulk_writes_attempted": 48}))
            report = verify.verify_capture(directory)
            self.assertTrue(report["complete"])
            self.assertEqual(report["program_file_base"], "0x405a3800")
            self.assertEqual(report["program_file_offset"], 0x5A3800 if sparse else 0)
            self.assertEqual(report["program_sha256"], verify.digest(data))

    def test_secondary_resume_preserves_nonzero_component_base(self):
        parent = self.root / "secondary"
        prefix = partial_capture(parent, "secondary")
        output = self.root / "secondary-resume"
        output.mkdir()
        manifest = prepare_prefix(parent, output)
        self.assertEqual(manifest["native_resume_mode"], "resume-secondary")
        self.assertEqual(manifest["next_program_address"], "0x41400c00")
        partial_capture(output, "resume-secondary", prefix)
        report = verify.verify_capture(output, True)
        self.assertEqual(report["resume_anchors_verified"], 3)
        self.assertEqual(report["program_file_base"], "0x41400000")
        self.assertEqual(report["verified_prefix_bytes"], 4096)
        self.assertEqual(report["next_program_address"], "0x41401000")

    def test_resume_rejects_mixed_program_components(self):
        output = self.root / "mixed-resume"
        output.mkdir()
        prepare_prefix(self.parent, output)
        partial_capture(output, "resume-secondary", self.original)
        with self.assertRaisesRegex(ValueError, "component differs"):
            verify.verify_capture(output, True)


if __name__ == "__main__":
    unittest.main()
