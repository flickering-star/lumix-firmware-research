"""Offline, pinned GM1/GM5 package construction shared by macOS and Windows.

Inputs are the hash-checked official download and a camera-derived key. The
app ships XOR patches, never complete firmware, settings or calibration data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import zlib

from .download import checked_firmware, sha
from .models import model_spec
from .duration import apply_duration
from .languages import apply_languages
from .preservation import check_preserved

START, DIRECTORY, ENTRY = 0x600, 0x2EC, 92
DESTINATIONS = {'program': 0, 'guires': 0x800000, 'program2': 0x1400000}
SIZES = {'program': 0x800000, 'guires': 0xC00000, 'program2': 0x360000}
ADVERTISED = 0x011F
STOCK_RESTORE_RESET = (
    'Before installing Stock Program Restore, reset the camera settings '
    'while the patched firmware is still running.'
)


def entries(raw, *, unsigned=False,model='DMC-GM5'):
    spec=model_spec(model)
    if len(raw) < START or raw[:4] != b'UPD\0' or raw[12:24].split(b'\0')[0] != spec['token'].encode('ascii'):
        raise ValueError('Not a supported '+spec['token']+' update container')
    if struct.unpack_from('<II', raw, 4) != (512,512) or raw[0x2A0:0x2E0] != raw[:64]:
        raise ValueError('Unsupported update header layout')
    markers = (b'panasonic\0\0\0', b'\0anasonic\0\0\0') if unsigned else (b'panasonic\0\0\0',)
    if (raw[0x200:0x20C] not in markers or struct.unpack_from('<I',raw,0x3C)[0] != len(raw)-512
            or struct.unpack_from('<I',raw,0x40)[0] != zlib.crc32(raw[512:])):
        raise ValueError('Update header length, marker or checksum differs')
    count = struct.unpack_from('<I',raw,0x2E8)[0]
    if not 1 <= count <= 8: raise ValueError('Unsupported component count')
    result=[];position=START;names=set();ranges=[]
    for i in range(count):
        values=struct.unpack_from('<12s4I32s16s16s',raw,DIRECTORY+ENTRY*i)
        name,relative,size,destination,flags,digest,iv,reserved=values
        name=name.rstrip(b'\0').decode('ascii')
        if (not name or name in names or relative+512!=position or not size or size%16
                or position+size>len(raw) or flags!=3):
            raise ValueError('Unsupported component name, layout or cipher')
        if destination%0x20000 or destination+size>0x2000000:
            raise ValueError('Component destination escapes the reviewed flash')
        if any(destination<b and a<destination+size for a,b in ranges):
            raise ValueError('Component destinations overlap')
        names.add(name);ranges.append((destination,destination+size))
        result.append(dict(name=name,offset=position,size=size,destination=destination,
                           digest=digest.hex(),iv=iv,reserved=reserved))
        position+=size
    if position!=len(raw):raise ValueError('Unexpected data after the update payload')
    return result


def decode_original(raw, key, codec, progress=lambda *_:None,*,model='DMC-GM5'):
    spec=model_spec(model);destinations=spec['destinations'];sizes=spec['sizes']
    raw=checked_firmware(raw,model)
    result={};directory=entries(raw,model=model)
    for i,entry in enumerate(e for e in directory if e['name'] in destinations):
        name=entry['name']
        if entry['destination']!=destinations[name] or entry['size']!=sizes[name]:
            raise ValueError('Official component geometry differs')
        progress('Decoding '+name, i, 3)
        plain=codec.transform(raw[entry['offset']:entry['offset']+entry['size']],key,entry['iv'])
        if sha(plain)!=entry['digest']:
            raise ValueError('The connected camera key does not decode the supported official firmware')
        result[name]=plain
    if set(result)!=set(destinations):raise ValueError('Official program components are missing')
    return result


def apply_delta(source, raw, metadata):
    if sha(raw)!=metadata['patch_sha256'] or sha(source)!=metadata['source_sha256']:
        raise ValueError('Bundled patch or official component hash differs')
    decoder=zlib.decompressobj()
    data=decoder.decompress(raw,40*1024*1024)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or data[:8]!=b'LUMIXDP1':
        raise ValueError('Invalid bounded patch encoding')
    size,count=struct.unpack_from('<II',data,8)
    if size!=len(source) or count>size:raise ValueError('Invalid patch geometry')
    output=bytearray(source);position=16;last=0
    for _ in range(count):
        if position+8>len(data):raise ValueError('Truncated patch record')
        at,n=struct.unpack_from('<II',data,position);position+=8
        if at<last or not n or at+n>size or position+n>len(data):
            raise ValueError('Overlapping or out-of-range patch record')
        output[at:at+n]=bytes(a^b for a,b in zip(output[at:at+n],data[position:position+n]))
        position+=n;last=at+n
    if position!=len(data) or sha(output)!=metadata['target_sha256']:
        raise ValueError('Reconstructed firmware does not match the reviewed target')
    return bytes(output)


def catalog(root=None,*,model='DMC-GM5'):
    model_spec(model)
    root=Path(root) if root else Path(__file__).parent/'patches'
    value=json.loads((root/'catalog.json').read_text(encoding='utf-8'))
    if value.get('model')!=model:
        directory=value.get('models',{}).get(model)
        if not isinstance(directory,str) or Path(directory).name!=directory or directory in ('.','..'):
            raise ValueError('The bundled catalog has no reviewed '+model+' patches')
        expected=value.get('model_catalog_sha256',{}).get(model)
        root=root/directory
        raw=(root/'catalog.json').read_bytes()
        if expected is None or sha(raw)!=expected:raise ValueError('The model-specific catalog hash differs')
        value=json.loads(raw)
    if value.get('schema')!=1 or value.get('model')!=model or set(value['choices'])!={'stable','luts','restore'}:
        raise ValueError('Unsupported bundled patch catalog')
    return root,value


def catalog_assets(root=None):
    """Validate every model and the complete recursive shipped file inventory."""
    root=Path(root) if root else Path(__file__).parent/'patches'
    main=json.loads((root/'catalog.json').read_text(encoding='utf-8'))
    models=main.get('models',{main.get('model'):'.'})
    if not models or any(m not in ('DMC-GM1','DMC-GM5') for m in models):
        raise ValueError('Unexpected model inventory in the patch catalog')
    expected={'catalog.json':sha((root/'catalog.json').read_bytes())};profiles={}
    for model in models:
        directory,manifest=catalog(root,model=model)
        prefix=directory.relative_to(root)
        expected[str(prefix/'catalog.json')]=sha((directory/'catalog.json').read_bytes())
        profiles[model]=manifest['supported_camera_profiles']
        for choice in manifest['choices'].values():
            for part in choice['components'].values():
                name=part['file']
                if name:
                    if Path(name).name!=name or not name.endswith('.lxdp') or sha((directory/name).read_bytes())!=part['patch_sha256']:
                        raise ValueError('Bundled model patch file differs')
                    expected[str(prefix/name)]=part['patch_sha256']
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if actual!=set(expected):raise ValueError('Undeclared files in the bundled patch tree')
    return expected,profiles


def build(raw, key, codec, choice, *, assets=None, progress=lambda *_:None,camera_profile='gm5-factory-0111',
          model='DMC-GM5',remove_limit=False):
    spec=model_spec(model);destinations=spec['destinations']
    raw=checked_firmware(raw,model)
    root,manifest=catalog(assets,model=model)
    if choice not in manifest['choices']:raise ValueError('Choose a supported patch or stock restore')
    plan=manifest['choices'][choice]
    if camera_profile not in spec['profiles'].values():
        raise ValueError('Unsupported camera profile for firmware preparation')
    if type(remove_limit) is not bool:raise ValueError('Invalid recording-limit option')
    remove_limit=remove_limit and choice!='restore'
    components=plan['components']
    if choice=='restore' and camera_profile=='gm5-official-0110':
        components=manifest.get('restore_components_by_profile',{}).get(camera_profile)
        if components is None:raise ValueError('The bundled patches do not include this camera’s stock restore')
    if list(components)!=['program','guires','program2']:
        raise ValueError('The selected patch must contain exactly the three reviewed program components')
    decoded=decode_original(raw,key,codec,progress,model=model)
    templates={e['name']:e for e in entries(raw,model=model)}
    parts=[]
    preservation={}
    language_catalog=None
    target_revision=0x0110 if model=='DMC-GM1' or choice=='restore' and camera_profile=='gm5-official-0110' else 0x0111
    for name in components:
        if name not in destinations:raise ValueError('Patch requests an unreviewed component')
        patch=components[name]
        original=decoded[name]
        if patch['file']:
            filename=patch['file']
            if Path(filename).name!=filename or not filename.endswith('.lxdp'):
                raise ValueError('Invalid bundled patch filename')
            plain=apply_delta(original,(root/filename).read_bytes(),patch)
        else:
            plain=original
            if sha(plain)!=patch['target_sha256']:raise ValueError('Stock component hash differs')
        length=patch['write_bytes']
        if length%0x20000 or not 0<length<=len(plain):raise ValueError('Patch length is not a complete erase sector')
        if name=='program':
            if struct.unpack_from('<2H',plain,0x6A0)!=(target_revision,target_revision):
                raise ValueError('Reconstructed firmware differs from the selected internal revision')
            policy=spec['policy_rom']-0x40000000+spec['policy_rom_offset']
            if plain[policy:policy+2]!=(1 if choice=='restore' else 0).to_bytes(2,'little'):
                raise ValueError('Reconstructed update policy differs from the selected patch')
            if choice=='luts' and (length!=spec['lut_program_bytes']
                    or plain[length:]!=b'\xff'*(len(plain)-length)):
                raise ValueError('LUT update would overwrite or omit undeclared flash data')
        if remove_limit:plain=apply_duration(plain,name,model,plan)
        if name=='program' and choice!='restore':
            plain,language_catalog=apply_languages(plain,model)
        preservation[name]=check_preserved(plain,name,model,target_revision)
        parts.append((name,destinations[name],plain[:length]))
    if not parts or parts[0][0]!='program':raise ValueError('Program must be the first update component')
    output=bytearray(raw[:START]);encrypted=[]
    for i,(name,_,plain) in enumerate(parts):
        progress('Encoding '+name,i,len(parts))
        encoded=codec.transform(plain,key,templates[name]['iv'],encrypt=True)
        if codec.transform(encoded,key,templates[name]['iv'])!=plain:
            raise ValueError('Firmware encoding failed its complete round trip')
        encrypted.append(encoded)
    output.extend(b''.join(encrypted))
    output[0x200]=0;output[0x220:0x260]=bytes(64)
    struct.pack_into('<HH',output,0x1C,spec['advertised'],spec['advertised'])
    struct.pack_into('<I',output,0x3C,len(output)-512)
    output[0x2A0:0x2E0]=output[:64]
    struct.pack_into('<I',output,0x2E8,len(parts))
    output[DIRECTORY:START]=bytes(START-DIRECTORY)
    position=START
    for i,(name,destination,plain) in enumerate(parts):
        template=templates[name]
        struct.pack_into('<12s4I32s16s16s',output,DIRECTORY+ENTRY*i,name.encode('ascii'),
            position-512,len(plain),destination,3,hashlib.sha256(plain).digest(),template['iv'],template['reserved'])
        position+=len(plain)
    struct.pack_into('<I',output,0x40,zlib.crc32(output[512:]))
    checked=entries(output,unsigned=True,model=model)
    for entry,(name,destination,plain) in zip(checked,parts):
        if (entry['name'],entry['destination'],entry['digest'],entry['size'])!=(name,destination,sha(plain),len(plain)):
            raise ValueError('Final package directory does not match the reviewed payload')
    source_revision=next(v for v,p in spec['profiles'].items() if p==camera_profile)
    limitations=list(plan['limitations'])
    if language_catalog is not None:
        limitations.append('All '+str(len(language_catalog['language_ids']))+
            ' native firmware languages are available through the Language menu in every camera region.')
    if choice=='restore':
        limitations.insert(0, STOCK_RESTORE_RESET)
    if remove_limit:
        limitations.append('Experimental recording-duration patch: removes the reviewed regional 1,799-second policy.'+
            (' Also selects the existing longer-duration fallback for the mapped format cap; native rate scaling still applies.'
             if plan.get('duration_variant')=='regional-and-format-v2' else '')+
            ' Card capacity, file-size, encoder and thermal paths remain. Uninterrupted long recordings and file segmentation still need camera testing.')
    if source_revision!=target_revision:
        limitations.append('The camera still displays firmware 1.1; its internal program revision changes from 0110 to the reviewed factory revision 0111. Stock restore returns the original official 0110 components.')
    report=dict(model=model,choice=choice,bytes=len(output),sha256=sha(output),camera_profile=camera_profile,
        components=[dict(name=n,destination=d,bytes=len(p),sha256=sha(p)) for n,d,p in parts],
        advertised_version='1.1f' if model=='DMC-GM5' else '1.1 (header 0111)',installed_version_preserved=source_revision==target_revision,
        duration_policy_removed=remove_limit,
        duration_scope=plan.get('duration_variant','regional-only-v1') if remove_limit else None,
        displayed_version_preserved=True,source_internal_revision=f'{source_revision:04x}',
        target_internal_revision=f'{target_revision:04x}',
        native_preservation=preservation,
        language_catalog=language_catalog,
        settings_and_body_calibration_excluded=True,limitations=limitations)
    return bytes(output),report
