import importlib.util
from pathlib import Path
import struct
import unittest


spec = importlib.util.spec_from_file_location(
    "ptp_device_info", Path(__file__).resolve().parents[1]/"tools"/"ptp_device_info.py")
ptp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ptp)


def fixture(serial="PRIVATE-SERIAL"):
    # Independent PTP wire fixture, including an empty capture-format list.
    def string(value):
        raw = value.encode("utf-16-le")+b"\0\0"
        return bytes([len(raw)//2])+raw
    return (bytes.fromhex("6400060000006400000000")
            + bytes.fromhex("0200000001101b10")
            + bytes.fromhex("010000000440")
            + bytes.fromhex("0100000006d4")
            + bytes.fromhex("00000000")
            + bytes.fromhex("010000000138")
            + string("Panasonic")+string("TEST-CAMERA")+string("1.1")+string(serial))


class PTPInfoTests(unittest.TestCase):
    def test_decodes_wire_dataset_and_omits_serial(self):
        result = ptp.parse_device_info(fixture())
        self.assertEqual(result["manufacturer"], "Panasonic")
        self.assertEqual(result["model"], "TEST-CAMERA")
        self.assertEqual(result["operations"], ["0x1001", "0x101b"])
        self.assertEqual(result["device_properties"], ["0xd406"])
        self.assertEqual(result["capture_formats"], [])
        self.assertTrue(result["serial_omitted"])
        self.assertNotIn("PRIVATE-SERIAL", str(result))

    def test_truncation_at_every_dataset_boundary_is_rejected(self):
        data = fixture()
        for length in range(len(data)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                ptp.parse_device_info(data[:length])

    def test_rejects_unterminated_string_and_trailing_data(self):
        for data in (fixture()[:-2]+b"xx", fixture()+b"\0"):
            with self.assertRaises(ValueError):
                ptp.parse_device_info(data)

    def test_rejects_oversized_array(self):
        data = bytearray(fixture())
        struct.pack_into("<I", data, 11, 0xffffffff)
        with self.assertRaisesRegex(ValueError, "Excessive"):
            ptp.parse_device_info(bytes(data))

    def test_response_header_and_actual_transaction_id(self):
        result = ptp.parse_response(bytes.fromhex("0c000000030001200d000000"))
        self.assertEqual(result["transaction_id"], 13)
        self.assertEqual(result["code"], "0x2001")

    def test_rejects_non_ok_or_malformed_response(self):
        for raw in ("0c0000000300052001000000", "0c0000000200012001000000",
                    "100000000300012001000000", "0000"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                ptp.parse_response(bytes.fromhex(raw))


if __name__ == "__main__":
    unittest.main()
