"""Pinned official firmware download with an equivalent local BIN/ZIP path."""
from __future__ import annotations

import hashlib
import io
import certifi
from pathlib import Path
import ssl
import urllib.request
import zipfile

OFFICIAL_PAGE = "https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gm5.html"
OFFICIAL_URL = "https://av.jpn.support.panasonic.com/support/share/eww/en/dsc/fts/mac/GM5__V11.zip"
BIN_SHA = "d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243"
ZIP_SHA = "0e9be7b3bb0eb0378f67110efe3ef7657d7b7920f9a52e1534653029ef21e515"
BIN_SIZE, ZIP_SIZE = 31901184, 31905359


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_firmware(data):
    if len(data) == BIN_SIZE and sha(data) == BIN_SHA:
        return data
    if data[:4] == b"PK\x03\x04":
        if len(data) > 40 * 1024 * 1024:
            raise ValueError("The firmware archive is larger than the supported download")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = [i for i in archive.infolist() if not i.is_dir()]
            if (len(files) != 1 or files[0].filename != "GM5__V11.bin"
                    or files[0].file_size != BIN_SIZE or files[0].flag_bits & 1):
                raise ValueError("Expected the official ZIP containing only GM5__V11.bin")
            # Read exactly one named member; never extract paths from a ZIP.
            raw = archive.read(files[0])
            if sha(raw) == BIN_SHA:
                return raw
    raise ValueError("This is not the supported official GM5 1.1 firmware (SHA-256 differs)")


def load_local(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 40 * 1024 * 1024:
        raise ValueError("Select a supported GM5 firmware BIN or ZIP")
    return checked_firmware(path.read_bytes())


def download(progress=lambda *_: None):
    request = urllib.request.Request(OFFICIAL_URL, headers={"Referer": OFFICIAL_PAGE,
        "User-Agent": "LumixFirmwareUpdater/0.1"})
    # Frozen Python must not depend on the build machine's certificate path.
    context=ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        if response.status != 200 or not response.url.startswith("https://av.jpn.support.panasonic.com/"):
            raise ValueError("The official download location changed; select a verified local BIN/ZIP")
        output = bytearray()
        while True:
            block = response.read(256 * 1024)
            if not block:
                break
            output.extend(block)
            if len(output) > ZIP_SIZE:
                raise ValueError("The official archive size changed; select a verified local BIN/ZIP")
            progress(len(output), ZIP_SIZE)
    if len(output) != ZIP_SIZE or sha(output) != ZIP_SHA:
        raise ValueError("The official download hash differs; select a verified local BIN/ZIP")
    return checked_firmware(output)
