#!/usr/bin/env python3
"""Archive official Panasonic download pages or firmware with provenance."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit
import urllib.request
import zipfile

INDEX = "https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/index.html"
MAX_DOWNLOAD = 256 * 1024 * 1024


def official_url(url: str) -> str:
    address = urlsplit(url)
    host = (address.hostname or "").lower()
    if (address.scheme != "https" or address.username or address.password
            or address.port not in (None, 443) or not any(
                host == domain or host.endswith("." + domain)
                for domain in ("panasonic.com", "panasonic.jp", "panasonic.co.jp"))):
        raise ValueError("Expected an HTTPS URL on an official Panasonic domain")
    return url


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Links(HTMLParser):
    def __init__(self, base: str):
        super().__init__()
        self.base = base
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            self.current = {"url": urljoin(self.base, href), "text": ""} if href else None

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.current["text"] = " ".join(self.current["text"].split())
            self.links.append(self.current)
            self.current = None


def fetch(url: str, referer: str | None = None) -> tuple[bytes, dict]:
    official_url(url)
    headers = {"User-Agent": "GM5-firmware-research/0.1"}
    if referer:
        headers["Referer"] = official_url(referer)
    # Retains the session's proxy and CA configuration. TLS verification stays enabled.
    opener = urllib.request.build_opener(OfficialRedirect())
    with opener.open(urllib.request.Request(url, headers=headers), timeout=60) as response:
        official_url(response.url)
        body = response.read(MAX_DOWNLOAD + 1)
        if len(body) > MAX_DOWNLOAD:
            raise ValueError("Download exceeds 256 MiB")
        metadata = {"source_url": url, "final_url": response.url,
                    "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                    "http_status": response.status,
                    "content_type": response.headers.get("Content-Type"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                    "hash_note": "Locally recorded SHA-256; not a publisher signature or published checksum."}
        return body, metadata


def archive_members(body: bytes) -> list[tuple[str, bytes]]:
    """Validate the entire ZIP and extract just one unambiguously named GM5 binary."""
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = archive.infolist()
        if sum(m.file_size for m in members) > MAX_DOWNLOAD:
            raise ValueError("Uncompressed archive exceeds 256 MiB")
        binaries = [m for m in members if not m.is_dir() and m.filename.lower().endswith(".bin")]
        if len(binaries) != 1 or "gm5" not in Path(binaries[0].filename).name.lower():
            raise ValueError("Archive must contain exactly one GM5-named .bin; inspect other packages separately")
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP CRC verification failed for {bad!r}")
        member = binaries[0]
        return [(Path(member.filename).name, archive.read(member))]


def acquire(url: str, out: Path, page: bool, referer: str | None = None) -> dict:
    if out.exists():
        raise ValueError("Output directory already exists; choose a new directory")
    body, metadata = fetch(url, referer)
    if page:
        if "html" not in (metadata["content_type"] or "").lower():
            raise ValueError("Expected a firmware download HTML page")
        parser = Links(metadata["final_url"])
        parser.feed(body.decode("utf-8", errors="replace"))
        metadata["links"] = parser.links
        metadata["gm5_links"] = [link for link in parser.links
                                 if re.search(r"gm5", link["url"] + " " + link["text"], re.I)]
        metadata["firmware_downloaded"] = False
        files = [("page.html", body)]
    else:
        name = Path(unquote(urlsplit(metadata["final_url"]).path)).name
        if not name or "gm5" not in name.lower():
            raise ValueError("Firmware URL must end in a GM5-named .zip or .bin")
        if name.lower().endswith(".zip"):
            files = [(name, body)] + archive_members(body)
        elif name.lower().endswith(".bin") and body and not body.lstrip().lower().startswith((b"<html", b"<!doctype")):
            files = [(name, body)]
        else:
            raise ValueError("Expected a nonempty .bin or a verified .zip archive")
        metadata["firmware_downloaded"] = True
        metadata["files"] = [{"name": n, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                             for n, b in files]
    out.mkdir(parents=True, exist_ok=False)
    for name, data in files:
        (out / name).write_bytes(data)
    (out / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--index", action="store_true", help="Read the official firmware index; do not guess a version")
    source.add_argument("--page", help="Read an official detail/confirmation page and list GM5 links")
    source.add_argument("--url", help="Download an exact official GM5 archive URL found on those pages")
    parser.add_argument("--referer", help="Official confirmation page, if required by the download server")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = acquire(INDEX if args.index else (args.page or args.url), args.out,
                         bool(args.index or args.page), args.referer)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if "gm5_links" in report:
        print(json.dumps(report["gm5_links"], indent=2))
        if not report["gm5_links"]:
            print("No GM5 links found on this page. This alone does not establish update availability.")
    print(f"Saved evidence in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
