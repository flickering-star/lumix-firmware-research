"""In-memory five-round CBC through the bundled native codec."""
from __future__ import annotations

import ctypes as C
from pathlib import Path
import sys
import threading


class Codec:
    def __init__(self, library=None):
        filename = "lumix-codec.dll" if sys.platform == "win32" else "liblumix-codec.dylib"
        path = Path(library) if library else Path(__file__).parent / "native" / filename
        self.library = C.CDLL(str(path.resolve()))
        self.lock = threading.Lock()
        check = self.library.lumix_codec_selftest
        check.restype, check.argtypes = C.c_int, []
        if check():
            raise ValueError("The bundled firmware codec failed its self-test")
        self.function = self.library.lumix_codec_cbc
        self.function.restype = C.c_int
        self.function.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t, C.c_void_p, C.c_void_p, C.c_int]

    def transform(self, data, key, iv, *, encrypt=False):
        if not data or len(data) % 16 or len(key) != 16 or len(iv) != 16:
            raise ValueError("Invalid firmware cipher block geometry")
        source = C.create_string_buffer(data, len(data))
        output = C.create_string_buffer(len(data))
        with self.lock:
            status = self.function(source, output, len(data), C.create_string_buffer(key, 16),
                                   C.create_string_buffer(iv, 16), int(encrypt))
        if status:
            raise ValueError("Firmware cipher operation failed")
        return output.raw
