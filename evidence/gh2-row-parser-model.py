"""Offline behavioral model of GH2 1.2 routine 0x401dfa87, not a camera tool.

This does not execute firmware and does not establish a vulnerability in GM5.
Its purpose is to check the consequence of the traced loop's lack of a
destination-capacity parameter while respecting the caller's text-size checks.
"""
from pathlib import Path
import hashlib
import json


def hex_word(data):
    """Match 0x401dfa3b: A..F/a..f special case; other characters use low nibble."""
    value = 0
    for character in data:
        nibble = ((character | 0x20) - 87 if 65 <= character <= 70
                  or 97 <= character <= 102 else character & 15)
        value = value * 16 + nibble
    return value & 0xffff


def model(data):
    pos = data.find(b"H000")
    if pos < 0:
        return b""
    pos += 4
    output = bytearray()
    while pos < len(data):
        character = data[pos]
        if character == 0:
            break
        if character == 10 and data[pos + 1:pos + 2] == b"H":
            pos += 6
        elif character in (10, 13, 44, 32):
            pos += 1
        else:
            if pos + 4 > len(data):
                raise ValueError("This model does not read past the supplied source")
            output.extend(hex_word(data[pos:pos + 4]).to_bytes(2, "little"))
            pos += 4
    return bytes(output)


def main():
    report = {"scope": "GH2 native-loop behavioral model; firmware not executed",
              "valid_gm1_format_controls": [], "synthetic_size_controls": []}
    for suffix in ("F", "U"):
        source = Path(f"work/gm1-settings/GM1{suffix}.TXT")
        expected = Path(f"work/gm1-settings/GM1{suffix}.words-little.bin").read_bytes()
        decoded = model(source.read_bytes())
        assert decoded == expected
        report["valid_gm1_format_controls"].append({
            "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "decoded_bytes": len(decoded), "canonical_word_serialization_matches": True})
    # These strings exist only in memory; no altered restore file is produced.
    for area, text_size, expected_size in (("GH2 update", 22587, 8192),
                                           ("GH2 fixed", 89407, 32768)):
        count = (text_size - 4) // 4
        data = b"H000" + b"1111" * count + b"\r" * (text_size - 4 - 4 * count)
        assert len(data) == text_size
        decoded = model(data)
        report["synthetic_size_controls"].append({
            "area": area, "caller_expected_text_bytes": text_size,
            "synthetic_text_bytes": len(data), "caller_size_condition_satisfied": True,
            "synthetic_input_sha256": hashlib.sha256(data).hexdigest(),
            "modeled_output_bytes": len(decoded), "expected_area_bytes": expected_size,
            "modeled_excess_bytes": len(decoded) - expected_size})
    report["limitations"] = [
        "Static control-flow review plus a Python model, not native firmware execution.",
        "No physical GH2 behavior, memory corruption impact or exploitability validated.",
        "No evidence yet that GM1 or GM5 contains the same parser or same allocation layout.",
        "Only the reviewed caller's size check is modeled; other preconditions remain unmodeled.",
        "No settings file for import was saved, sent or restored."]
    Path("work/gh2-settings-code/parser-model-controls.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
