"""Pinned native startup and shared SD ranges: firmware edits are forbidden.

Hashes come from the reviewed original GM1 0110 and GM5 0110/0111 components.
They are independent of patch catalogs. They cover known bootstrap, kernel,
filesystem-worker, file-API and dispatcher ranges, not a complete boot model.
The owner's prohibition applies to every native startup path, including paths
outside these bounded checks; never weaken these pins to admit a new feature.
"""
import hashlib

from .models import model_spec


RANGES = {
    'DMC-GM1': {
        'program': (
            ('native reset and early startup', 0, 0x20000),
            ('native main startup', 0x4F000, 0x52000),
            ('native file API', 0x246E00, 0x247000)),
        'program2': (
            ('native filesystem and kernel startup', 0x1AD000, 0x1F5000),
            ('native SD dispatcher tables', 0x223000, 0x224000))},
    'DMC-GM5': {
        'program': (
            ('native reset and early startup', 0, 0x20000),
            ('native main startup', 0x4F000, 0x52000),
            ('native file API', 0x236200, 0x236400)),
        'program2': (
            ('native filesystem workers', 0x1BC000, 0x1F4000),
            ('native kernel startup', 0x200000, 0x205000),
            ('native SD dispatcher tables', 0x237000, 0x238000))}}

HASHES = {
    'gm1-official-0110': {
        'program': (
            'f253bea2874b152adf372b19e178dce076ac767b59ab1bfb739a7d420f3c92b7',
            '5678cb1af7b2519d4346179d2f446e9e39d3fa2916bde4762c97e15768a3bf50',
            'f9041e36539ae966a1eef4e689c5b14fa03c21340b14ef4a9817a517b6b42407'),
        'program2': (
            'f1915d24b5718bce47507f4de13f4e87d11dc646a83c6946d3127e7349f11de2',
            '7b99f17c755cc83ecb7dc903403e8893c6d5d6342f67b9459ac511a2be277d69')},
    'gm5-official-0110': {
        'program': (
            'd6856df0b5365b8702f16f85836136039bd0c17fc32a06349dc7b03719c7b2e8',
            '454a664f28fe8abc2d7665d38c8b262051b60b63d67b5459286756d6aca38694',
            'cc6ef3e992ce7b297acd22a000d7198326ab7b8d450384e990a7e802b8a32b35'),
        'program2': (
            '2877d47d04b8b634af2cc8577371b71308093d90653f483f831b39d9d8866d8b',
            '37a83706e9f5f583925deeee72eab02a28985f68bfb7179481fe382c9785d4ed',
            '4b4e18bbff5c80e4a074fdcb04d30e96c5e7517843b9d10448604112e6f1bb89')},
    'gm5-factory-0111': {
        'program': (
            '22c256803572ab4e2cf0035f2ce5b14f3f7167350291a6fef99f420728d21a5b',
            '454a664f28fe8abc2d7665d38c8b262051b60b63d67b5459286756d6aca38694',
            'd39a5d8ede99b95a4aa57ca86ae847cb412cd12df5f4caf72385721e3fb4e7e0'),
        'program2': (
            'a26de77e750624ba9c8f1ac86812306024226fa4c46c60f46de50a865f12c851',
            '870a7e23d8bf7dd3eba58e4ae66475d32147de5b36e0476641111bda48eb62bd',
            'a9e5d21379ff338d3ba0ca102886f6716d38394ecc72d07614e1f0c7e5bcb58f')}}


def check_preserved(plain, component, model, revision):
    spec = model_spec(model)
    if component == 'guires':
        return []
    if component not in ('program', 'program2') or revision not in spec['profiles']:
        raise ValueError('Unknown native-preservation profile')
    regions = RANGES[model][component]
    expected = HASHES[spec['profiles'][revision]][component]
    if len(regions) != len(expected) or len(plain) != spec['sizes'][component]:
        raise ValueError('Native-preservation geometry differs')
    result = []
    for (name, start, end), digest in zip(regions, expected):
        actual = hashlib.sha256(plain[start:end]).hexdigest()
        if actual != digest:
            raise ValueError('Firmware changes '+name+'. Native startup and shared SD changes are forbidden; exFAT overlays are withdrawn.')
        result.append(dict(name=name, offset=start, bytes=end-start, sha256=actual))
    return result
