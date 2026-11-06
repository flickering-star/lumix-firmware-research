"""Exercise real local HTTP requests and hostile/corrupt input handling."""
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import zipfile


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load("camera_probe")
firmware = load("firmware_inspect")
acquire = load("firmware_acquire")
image_app = load("image_app_inventory")


class MockCamera(BaseHTTPRequestHandler):
    seen = []
    fail_aspect = False
    malformed = False
    binary_settings = False

    @classmethod
    def payload(cls, params):
        content_type = "text/xml"
        if cls.binary_settings and params.get("type") == ["camsetting"]:
            body = b"\x00\xff\x10settings\x00\x80"
            content_type = "application/octet-stream; charset=binary"
        elif cls.malformed:
            body = b"<html>not a camera response</html>"
        elif cls.fail_aspect and params.get("type") == ["aspectratio"]:
            body = b"<camrply><result>err_param</result></camrply>"
        else:
            body = b'<camrply><result>ok</result><menu id="aspectratio"><item value="4:3"/></menu></camrply>'
        return content_type, body

    def do_GET(self):
        params = parse_qs(urlsplit(self.path).query)
        self.seen.append(params)
        content_type, body = self.payload(params)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class OfflineConnection:
    """Socket-free fixture; still exercises request encoding and response parsing."""
    def __init__(self, *args, **kwargs):
        pass

    def request(self, method, path, headers):
        if method != "GET":
            raise AssertionError("Unexpected method")
        params = parse_qs(urlsplit(path).query)
        MockCamera.seen.append(params)
        content_type, body = MockCamera.payload(params)
        self.raw = (f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n").encode() + body

    def makefile(self, mode):
        return io.BytesIO(self.raw)

    def getresponse(self):
        response = probe.http.client.HTTPResponse(self)
        response.begin()
        return response

    def close(self):
        pass


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_camera(self, *, fail=False, malformed=False, pair=False, extended=False, binary=False,
                   client_id="0", client_name="GM5 Aspect Research", offline=False):
        MockCamera.seen = []
        MockCamera.fail_aspect = fail
        MockCamera.malformed = malformed
        MockCamera.binary_settings = binary
        if offline:
            with patch.object(probe.http.client, "HTTPConnection", OfflineConnection):
                with contextlib.redirect_stdout(io.StringIO()):
                    report = probe.snapshot("fixture.invalid", self.root / "capture", "fixture-not-GM5",
                                            "fixture", 2, pair=pair, extended=extended,
                                            client_id=client_id, client_name=client_name)
            return report, list(MockCamera.seen)
        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), MockCamera)
        except PermissionError:
            self.skipTest("Sandbox denies loopback socket binding; socket-free fixtures run separately")
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                report = probe.snapshot(f"127.0.0.1:{server.server_port}", self.root / "capture",
                                        "simulator-not-GM5", "simulator", 2, pair=pair,
                                        extended=extended, client_id=client_id, client_name=client_name)
            return report, list(MockCamera.seen)
        finally:
            server.shutdown()
            worker.join()
            server.server_close()

    def test_snapshot_uses_only_get_queries_and_preserves_exact_bytes(self):
        report, seen = self.run_camera()
        self.assertTrue(report["all_queries_ok"])
        self.assertEqual(len(seen), 6)
        self.assertTrue(all(p["mode"][0] in {"getstate", "getinfo", "getsetting"} for p in seen))
        for response in report["responses"]:
            body = (self.root / "capture" / response["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), response["sha256"])
        self.assertTrue(report["responses"][1]["aspect_nodes"])
        with self.assertRaises(FileExistsError):
            probe.snapshot("unused", self.root / "capture", "unused", "unused", 2)

    def test_http_200_camera_error_is_not_success(self):
        report, seen = self.run_camera(fail=True)
        self.assertFalse(report["all_queries_ok"])
        self.assertEqual(sum(r["ok"] for r in report["responses"]), 5)
        self.assertEqual(len(seen), 6)
        self.assertTrue((self.root / "capture" / "summary.json").exists())

    def test_unrecognized_response_is_not_success(self):
        report, _ = self.run_camera(malformed=True)
        self.assertFalse(report["all_queries_ok"])

    def test_pairing_only_when_requested_and_url_encoding(self):
        report, seen = self.run_camera(pair=True)
        self.assertEqual(seen[0]["mode"], ["accctrl"])
        self.assertEqual(seen[0]["value2"], ["GM5 Aspect Research"])
        self.assertEqual(len(seen), 7)

    def test_namespace_and_malformed_xml(self):
        body = b'<r xmlns="urn:test"><result>ok</result><setting type="aspectratio" value="16:9"/></r>'
        self.assertEqual(probe.response_info(body)["result"], "ok")
        self.assertEqual(len(probe.response_info(body)["aspect_nodes"]), 1)
        self.assertFalse(probe.response_info(b"<truncated")["xml"])

    def test_extended_probe_retains_binary_settings_and_http_headers(self):
        report, seen = self.run_camera(extended=True, binary=True, offline=True)
        self.assertEqual(len(seen), 10)
        self.assertTrue(all(p["mode"][0] in {"getstate", "getinfo", "getsetting"} for p in seen))
        record = report["responses"][-1]
        self.assertEqual(record["response_kind"], "binary_settings_candidate")
        self.assertTrue(record["ok"])
        self.assertFalse(record["format_validated"])
        self.assertFalse(record["xml"])
        self.assertEqual((self.root / "capture" / record["file"]).read_bytes(), b"\x00\xff\x10settings\x00\x80")
        self.assertIn("application/octet-stream", record["content_type"])
        self.assertTrue(record["headers"])

    def test_extended_probe_does_not_treat_html_as_settings(self):
        report, _ = self.run_camera(extended=True, malformed=True, offline=True)
        self.assertFalse(report["responses"][-1]["ok"])

    def test_pairing_values_can_match_the_installed_app_without_query_injection(self):
        client_id = "4D454930-0100-1000-8001-EXAMPLE"
        name = "Research & type=unexpected"
        _, seen = self.run_camera(pair=True, client_id=client_id, client_name=name, offline=True)
        self.assertEqual(seen[0]["value"], [client_id])
        self.assertEqual(seen[0]["value2"], [name])
        self.assertEqual(seen[0]["type"], ["req_acc"])

    def test_console_banner_sends_no_application_bytes_or_claims_shell(self):
        with patch.object(probe.socket, "create_connection") as connect:
            connection = connect.return_value.__enter__.return_value
            connection.recv.return_value = b"engineering console\r\n"
            record, body = probe.console_banner("127.0.0.1", 1)
            connection.send.assert_not_called()
            connection.sendall.assert_not_called()
            self.assertTrue(record["tcp_connected"])
            self.assertFalse(record["shell_confirmed"])
            self.assertEqual(body, b"engineering console\r\n")
            connection.recv.side_effect = probe.socket.timeout()
            record, body = probe.console_banner("127.0.0.1", 1)
            self.assertEqual(record["observation"], "open_without_banner")
            self.assertEqual(body, b"")

    def test_app_inventory_preserves_templates_locations_and_scope(self):
        source = self.root / "source"
        source.mkdir()
        (source / "Commands.java").write_text(
            'String query = "/cam.cgi?mode=getinfo&type=camsetting";\n'
            'String template = "/cam.cgi?mode=%s&type=%s";\n'
            'String log = "debug shell candidate";\n')
        (source / "Commands.smali").write_text(
            'const-string v0, "/cam.cgi?mode=getinfo&type=camsetting"\n')
        (source / "unrelated.xml").write_text('"/cam.cgi?mode=not_code"')
        report = image_app.inventory(source)
        self.assertEqual(report["source_file_count"], 2)
        self.assertEqual(report["unique_cgi_literal_count"], 2)
        row = next(r for r in report["cgi_literals"] if "camsetting" in r["literal"])
        self.assertEqual(len(row["locations"]), 2)
        self.assertEqual(row["locations"][0]["line"], 1)
        self.assertEqual(dict(row["query_fields"])["type"], "camsetting")
        self.assertEqual(report["review_candidates"][0]["line"], 3)
        self.assertTrue(report["limitations"])

    def test_offline_comparison_shows_aspect_change(self):
        left, right = self.root / "left", self.root / "right"
        left.mkdir()
        right.mkdir()
        for directory, value in [(left, "4:3"), (right, "16:9")]:
            (directory / "summary.json").write_text('{"schema": 1}')
            (directory / "04_aspectratio.response").write_text(
                f'<r><result>ok</result><aspectratio>{value}</aspectratio></r>')
        diff = probe.compare(left, right)
        self.assertIn("-  <aspectratio>4:3</aspectratio>", diff)
        self.assertIn("+  <aspectratio>16:9</aspectratio>", diff)

    def test_binary_triage_does_not_modify_input_or_claim_decryption(self):
        path = self.root / "fixture.bin"
        content = b"UPD\0" + bytes(range(256)) * 30 + b"\0cam.cgi aspectratio\0"
        path.write_bytes(content)
        report = firmware.inspect(path, 256)
        self.assertEqual(path.read_bytes(), content)
        self.assertEqual(report["sha256"], hashlib.sha256(content).hexdigest())
        self.assertAlmostEqual(report["entropy_windows"][1]["entropy"], 8.0)
        self.assertIn("not validated", report["container_hint"])
        self.assertIn("aspectratio", report["keyword_strings"][0]["text"])
        self.assertEqual(firmware.entropy(b"\0" * 100), 0)

    def test_empty_image_is_rejected(self):
        path = self.root / "empty.bin"
        path.touch()
        with self.assertRaises(ValueError):
            firmware.inspect(path)

    def test_only_official_https_urls_including_redirects(self):
        for url in ["http://panasonic.jp/fw.zip", "https://panasonic.jp.evil.test/fw.zip",
                    "https://panasonic.jp@evil.test/fw.zip", "https://panasonic.jp:444/fw.zip"]:
            with self.assertRaises(ValueError):
                acquire.official_url(url)
        self.assertEqual(acquire.official_url(acquire.INDEX), acquire.INDEX)
        with self.assertRaises(ValueError):
            acquire.OfficialRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test/fw.zip")

    def test_zip_crc_and_no_path_traversal(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("../../GM5_TEST.bin", b"fixture payload for archive CRC verification")
        data = output.getvalue()
        self.assertEqual(acquire.archive_members(data)[0][0], "GM5_TEST.bin")
        damaged = bytearray(data)
        damaged[data.index(b"fixture payload")] ^= 1
        with self.assertRaises((zipfile.BadZipFile, ValueError)):
            acquire.archive_members(bytes(damaged))

    def test_unrelated_firmware_not_accepted_as_gm5(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("S5_OTHER.bin", b"unrelated")
        with self.assertRaises(ValueError):
            acquire.archive_members(output.getvalue())


if __name__ == "__main__":
    unittest.main()
