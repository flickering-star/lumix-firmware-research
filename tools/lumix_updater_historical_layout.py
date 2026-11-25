"""Historical ABI checker retained for offline research of the 0.2.10 override.

These are hashes of bounded instructions, not complete firmware pages. Build
metadata, unrelated routines and initializer contents are deliberately excluded.
No firmware bytes or camera keys are embedded here. The desktop application
does not import this checker or expose a revision/build bypass in 0.2.11.
"""
from __future__ import annotations

import hashlib
import struct

from apps.lumix_updater.models import model_spec


# Each range has one purpose in the host's two service operations. In particular,
# the unused nonzero-mode branch of command9c is outside the checked ranges.
CODE = {
    'DMC-GM1': (
        ('service dispatcher', 0x40369F7C, 33, '7cf15d05f93491f4d7fe01086ca3e627d5c30aa52423b1c1201a47518deac7b1'),
        ('memory-read dispatch', 0x4036A19C, 8, '9a09f25f26e3625e4201a2e704fd0a52a08a02b4d79ae23f9dfb412ecc24a546'),
        ('halfword-write dispatch', 0x4036A164, 8, '39b129169dcf2e1494637ffbed53cf7173f904d077ffc2733042492f6a078087'),
        ('memory-read handler', 0x4036B711, 141, '0db882980307581c7283eb751b590747e5cdb39b51e1f34f546b550fb39102cc'),
        ('direct halfword-write handler', 0x4036B379, 86, 'aca4323b23f0b35f71e6c0c181187d114f89b976c09a64f3f42286fe9d20d3f7'),
        ('halfword-write acknowledgment', 0x4036B3DF, 11, 'ca358e63779f5ad3f53d8b50e6ac7d7e136d8f12c716a22f7afd9230a0c98826'),
    ),
    'DMC-GM5': (
        ('service dispatcher', 0x4036CC89, 33, '0f0d90b8343b36fe71e138f4eb31aadf4adfecf20ad6ec90b2829850bc5180db'),
        ('memory-read dispatch', 0x4036CEA9, 8, '9a09f25f26e3625e4201a2e704fd0a52a08a02b4d79ae23f9dfb412ecc24a546'),
        ('halfword-write dispatch', 0x4036CE71, 8, '39b129169dcf2e1494637ffbed53cf7173f904d077ffc2733042492f6a078087'),
        ('memory-read handler', 0x4036E41E, 141, 'f3f94ec5301b11c2e506454e62062ac13066a2c1becf95ddcef88202447226fb'),
        ('direct halfword-write handler', 0x4036E086, 86, '8d09cd47394c72c3277ad0808a96d0f19445aa83c3bf88ebe03b1973972a342e'),
        ('halfword-write acknowledgment', 0x4036E0EC, 11, 'ca358e63779f5ad3f53d8b50e6ac7d7e136d8f12c716a22f7afd9230a0c98826'),
    ),
}

TABLE = {'DMC-GM1': 0x4057B98C, 'DMC-GM5': 0x4061E494}
COPY = 0x40003000
COPY_SHAPE_SHA = '8a8517b6acb91bab3806281e0268d64a4a3a3831015146c43fc44f49bc4c29e4'
# The same GM5 instruction templates accept both 0110 and 0111. Search only
# their small updater-entry window; a four-byte function shift is not a layout
# incompatibility. The allowance must use the flag saved by that entry.
POLICY_JOB = {
    'DMC-GM1': (0x4154A240, 0x4154A310, 0x8E, 15,
        '585d87c4179621d895aa70277845b6ef38d79e88d38ebbce99b9ba1728c71df4',
        'af748656f933efb90b1cd1f75118ac09e0cfb8749c21f93f4fc864ab38a4c77d'),
    'DMC-GM5': (0x4154FB70, 0x4154FC50, 0x8F, 14,
        '62365c3533f4a9eb9c89b25881a77c2027fc471c62f0632f34f5b958a355904a',
        '84a0e0f2ebc3fb0e1d1792c65688b173beb30a624bd84d976689a81f7986eb3e'),
}


def _ranges(model):
    model_spec(model)
    yield from ((at, size) for _, at, size, _ in CODE[model])
    for opcode in (0x5C, 0x9C):
        yield TABLE[model]+4*opcode, 4
    yield COPY, 30
    start, end, *_ = POLICY_JOB[model]
    yield start, end-start


def layout_pages(model):
    return frozenset(page for at, size in _ranges(model)
        for page in range(at & ~1023, ((at+size-1) & ~1023)+1024, 1024))


def _read(pages, address, size):
    result = bytearray()
    while size:
        page = address & ~1023
        raw = pages[page]
        if len(raw) != 1024:
            raise ValueError('Camera memory reply is incomplete')
        count = min(size, 1024-(address-page))
        result.extend(raw[address-page:address-page+count])
        address += count
        size -= count
    return bytes(result)


def check_layout(model, pages):
    """Validate only the updater's fixed addresses and the code that uses them."""
    spec = model_spec(model)

    def incompatible(detail):
        raise ValueError('The '+spec['token']+' update layout is incompatible: '+detail+
            '. No camera change was made.')

    for name, at, size, digest in CODE[model]:
        if hashlib.sha256(_read(pages, at, size)).hexdigest() != digest:
            incompatible(name+f' at 0x{at:08x} differs')
    for opcode, index in ((0x5C, 1), (0x9C, 2)):
        actual = struct.unpack('<I', _read(pages, TABLE[model]+4*opcode, 4))[0]
        if actual != CODE[model][index][1]:
            incompatible(f'service command 0x{opcode:02x} has moved')

    # Check the actual ROM-to-RAM mapping, not the complete initialized data.
    # The source/end/destination immediates may change provided this flag still
    # maps to the host's fixed RAM halfword and both bytes are in the copy.
    copy = bytearray(_read(pages, COPY, 30))
    source, end, destination = (struct.unpack_from('<I', copy, at)[0] for at in (2, 8, 18))
    for at in (2, 8, 18):
        copy[at:at+4] = bytes(4)
    if hashlib.sha256(copy).hexdigest() != COPY_SHAPE_SHA:
        incompatible('the policy initializer copy routine differs')
    rom = spec['policy_rom']+spec['policy_rom_offset']
    ram = spec['policy_ram']+spec['policy_ram_offset']
    if (any(value & 3 for value in (source, end, destination))
            or not 0x40000000 <= source <= rom < rom+2 <= end <= 0x40000000+spec['sizes']['program']
            or destination+(rom-source) != ram):
        incompatible('the update-policy ROM/RAM mapping has moved')

    start, end, delta, allowance_size, entry_sha, allowance_sha = POLICY_JOB[model]
    window = _read(pages, start, end-start)
    for offset in range(len(window)-delta-allowance_size+1):
        if (hashlib.sha256(window[offset:offset+15]).hexdigest() == entry_sha
                and hashlib.sha256(window[offset+delta:offset+delta+allowance_size]).hexdigest() == allowance_sha):
            return
    incompatible('the updater no longer reads the expected policy flag')
