"""The short physical proof must distinguish correct packets from correct firmware."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from gm5_region_proof import collect, short_capture, PATCH_WINDOWS

OBSERVATION = ROOT / "evidence/gm5-region-physical-observation.json"
CAPTURE = ROOT / "captures/gm5-region-check-fVZhFe1y"


@unittest.skipUnless(OBSERVATION.exists() and CAPTURE.exists(), "Requires retained private physical captures")
class RegionPhysicalProofTests(unittest.TestCase):
    def test_valid_proof_replays_but_stock_byte_in_valid_packet_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = collect(OBSERVATION, directory / "valid.json")
            self.assertTrue(report["physical_patch_windows_match_exact_candidate"])
            self.assertFalse(report["complete_main_readback_performed"])
            changed = directory / "changed"
            shutil.copytree(CAPTURE / "result", changed / "result")
            window = changed / "result/language-normalizer.bin"
            payload = bytearray(window.read_bytes())
            self.assertEqual(payload[0x100], 0xAB)
            original_payload = bytes(payload)
            payload[0x100] = 0xC5  # Restore the original Japanese-only dispatch byte.
            window.chmod(0o600)
            window.write_bytes(payload)
            transcript = changed / "result/events.jsonl"
            events = [json.loads(line) for line in transcript.read_text().splitlines()]
            edits = 0
            for event in events:
                if event["event"] != "bulk_in":
                    continue
                frame = bytearray.fromhex(event["hex"])
                if len(frame) == 1030 and frame[4:-2] == original_payload:
                    frame[4 + 0x100] = 0xC5
                    frame[-2] = sum(frame[1:-2]) & 255
                    event["hex"] = frame.hex()
                    edits += 1
            self.assertEqual(edits, 1)
            transcript.chmod(0o600)
            transcript.write_text("".join(json.dumps(event) + "\n" for event in events))
            # The altered file and checksum-valid transcript agree with each other.
            short_capture(changed, "region-check", PATCH_WINDOWS)
            observation = json.loads(OBSERVATION.read_text())
            observation["patch_capture"] = str(changed)
            altered_observation = directory / "observation.json"
            altered_observation.write_text(json.dumps(observation))
            with self.assertRaisesRegex(ValueError, "Physical patch window differs"):
                collect(altered_observation, directory / "invalid.json")
            self.assertFalse((directory / "invalid.json").exists())


if __name__ == "__main__":
    unittest.main()
