"""Use each reviewed firmware's complete native language catalog.

Language IDs and ordering come from its existing UI-list initializer. Every
regional list operand in menu construction and saved-language validation is
redirected to that catalog. No replacement list or camera RAM allocation is
introduced.
"""

import re
import struct


BASE = 0x40000000
PROFILES = {
    "DMC-GM1": dict(
        master=0x405B7BA4, catalog_bytes=0xD8,
        normalizer=(0x4022713F, 0x4022723F),
        menu=(0x400E1DFB, 0x400E1F29), regional_lists=16,
        hide=0x400E3541,
        japanese=(
            (0x403FADE4, 0x40227207, 0x4022718F),
            (0x4037786C, 0x400E1F13, 0x400E1E59),
        ),
    ),
    "DMC-GM5": dict(
        master=0x4065889C, catalog_bytes=0xD8,
        normalizer=(0x40211EC6, 0x40211FFD),
        menu=(0x400A8427, 0x400A85A5), regional_lists=20,
        hide=0x400AA01D,
        japanese=(
            (0x40491900, 0x40211FC5, 0x40211FAB),
            (0x40379BF0, 0x400A858F, 0x400A8565),
        ),
    ),
}


def catalog_rows(main, address, limit):
    """Read the observed native eight-byte menu rows up to their sentinel."""
    offset = address - BASE
    if offset < 0 or offset + limit > len(main):
        raise ValueError("Language list escapes the reviewed program")
    rows = []
    seen = set()
    for index in range(0, limit, 8):
        ident, state, reserved, auxiliary = struct.unpack_from("<HBBI", main, offset + index)
        if ident == 0xFFFF:
            if not rows or state or reserved or auxiliary:
                raise ValueError("Invalid native language-list terminator")
            return rows
        if ident > 255 or state != 4 or reserved or auxiliary or ident in seen:
            raise ValueError("Invalid native language-list entry")
        seen.add(ident)
        rows.append(ident)
    raise ValueError("Native language list has no bounded terminator")


def list_operands(main, bounds, register, limit):
    """Inventory native MOV-immediate references inside one reviewed routine."""
    start, end = (value - BASE for value in bounds)
    opcode = b"\xfc" + bytes([0xDC + register])
    operands = []
    for match in re.finditer(re.escape(opcode), main[start:end]):
        instruction = start + match.start()
        target = struct.unpack_from("<I", main, instruction + 2)[0]
        try:
            ids = catalog_rows(main, target, limit)
        except ValueError:
            continue
        operands.append(dict(address=BASE + instruction + 2, target=target, ids=ids))
    return operands


def apply_languages(main, model):
    try:
        profile = PROFILES[model]
    except KeyError:
        raise ValueError("No reviewed language catalog for this model") from None
    ids = catalog_rows(main, profile["master"], profile["catalog_bytes"])
    if (len(ids) + 1) * 8 != profile["catalog_bytes"]:
        raise ValueError("Complete catalog does not match the existing native menu buffer")
    normalizer = list_operands(main, profile["normalizer"], 0, profile["catalog_bytes"])
    menu = list_operands(main, profile["menu"], 1, profile["catalog_bytes"])
    if (len(normalizer) != profile["regional_lists"] or len(menu) != profile["regional_lists"]
            or {item["target"] for item in normalizer} != {item["target"] for item in menu}):
        raise ValueError("Regional language-list inventory differs")
    regional_ids = {ident for item in normalizer for ident in item["ids"]}
    # An already converted image has the master catalog at every operand.
    if regional_ids != set(ids):
        raise ValueError("Complete catalog and regional language resources disagree")
    data = bytearray(main)
    edits = []

    def replace(address, before, after, purpose):
        offset = address - BASE
        if len(before) != len(after) or data[offset:offset + len(before)] != before:
            raise ValueError("Language patch preimage differs")
        if before != after:
            data[offset:offset + len(before)] = after
            edits.append(dict(address=address, before=before.hex(), after=after.hex(), purpose=purpose))

    for group, operands in (("validation", normalizer), ("menu", menu)):
        for item in operands:
            replace(item["address"], struct.pack("<I", item["target"]),
                    struct.pack("<I", profile["master"]), "Use complete native catalog for " + group)
    hide = profile["hide"] - BASE
    if data[hide] not in (0xC9, 0xCA):
        raise ValueError("Language-item visibility branch differs")
    replace(profile["hide"], bytes(data[hide:hide + 1]), b"\xca", "Expose Language in Setup")
    for address, original, previous_unlock in profile["japanese"]:
        value = struct.unpack_from("<I", data, address - BASE)[0]
        if value not in (original, previous_unlock):
            raise ValueError("Japanese language dispatch differs")
        replace(address, struct.pack("<I", value), struct.pack("<I", original),
                "Restore original dispatch after replacing every regional list")
    return bytes(data), dict(
        model=model, language_ids=ids, catalog_address=profile["master"],
        catalog_bytes=profile["catalog_bytes"], edits=edits,
        original_region_dispatch_restored=True, menu_ram_bytes_added=0,
        native_language_ids_or_order_changed=False,
    )
