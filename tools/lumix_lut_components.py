#!/usr/bin/env python3
"""Reproduce reviewed LUT components from exact locally decoded official inputs.

This offline tool writes private component files, not an SD update container.
It opens no camera. Use the desktop updater to encode/install an SD package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

LAYOUTS = {
    'DMC-GM1': (('program',0,0x900000,0x880000),
        ('guires',0x900000,0xB00000,0xB00000),('program2',0x1400000,0x360000,0x360000)),
    'DMC-GM5': (('program',0,0x800000,0x7A0000),
        ('guires',0x800000,0xC00000,0xC00000),('program2',0x1400000,0x360000,0x360000))}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply(source, component):
    if len(source)!=component['bytes'] or sha(source)!=component['source_sha256']:
        raise ValueError('Original component length or SHA-256 differs')
    result=bytearray(source);end=0
    for record in component['edits']:
        at=record['offset'];before=bytes.fromhex(record['before']);after=bytes.fromhex(record['after'])
        if (type(at) is not int or not 1<=len(before)<=256 or len(before)!=len(after)
                or before==after or at<end or at+len(before)>len(result)
                or source[at:at+len(before)]!=before):
            raise ValueError('Patch preimage, bounds or ordering differs')
        result[at:at+len(before)]=after;end=at+len(before)
    result=bytes(result)
    if sha(result)!=component['target_sha256']:
        raise ValueError('Complete patched-component SHA-256 differs')
    return result


def build(recipe_path, inputs, output):
    recipe=json.loads(Path(recipe_path).read_text(encoding='utf-8'))
    layout=LAYOUTS.get(recipe.get('model'))
    if (recipe.get('schema')!=1 or recipe.get('kind')!='lumix-lut-components'
            or layout is None or len(recipe['components'])!=3):
        raise ValueError('Unsupported LUT component recipe')
    output=Path(output).absolute()
    if output.exists():
        raise FileExistsError('Choose a new private output directory')
    prepared=[]
    for component,(name,destination,size,write) in zip(recipe['components'],layout):
        if (component['name'],component['destination'],component['bytes'],component['write_bytes'])!=(
                name,destination,size,write):
            raise ValueError('Recipe component geometry differs')
        source=Path(inputs[name])
        if source.stat().st_size!=size:
            raise ValueError('Original component length differs: '+name)
        raw=apply(source.read_bytes(),component)
        if name=='program' and raw[write:]!=b'\xff'*(size-write):
            raise ValueError('Saved LUT bank exclusion differs')
        prepared.append((name,raw,write))
    # Validate every input/output before publishing any plausible component.
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.lumix-components-',dir=output.parent) as temporary:
        ready=Path(temporary)/'ready';ready.mkdir()
        components=[]
        for name,raw,write in prepared:
            target=ready/(name+'.bin');target.write_bytes(raw)
            if sha(target.read_bytes())!=sha(raw):
                raise ValueError('Saved component verification failed')
            components.append(dict(name=name,bytes=len(raw),sha256=sha(raw),write_bytes=write))
        report=dict(schema=1,recipe=recipe['id'],model=recipe['model'],
            recipe_sha256=sha(Path(recipe_path).read_bytes()),components=components,
            update_container_created=False,camera_contacted=False,sd_card_written=False)
        (ready/'build-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        if output.exists():
            raise FileExistsError('Output directory appeared during preparation')
        os.rename(ready,output)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe',type=Path,required=True)
    for name in ('program','guires','program2'):
        parser.add_argument('--'+name,type=Path,required=True,help='Decoded official '+name+' component')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=build(args.recipe,{name:getattr(args,name) for name in ('program','guires','program2')},args.out)
        print('Reproduced '+result['model']+' LUT components; no camera or SD operation performed.')
    except (OSError,ValueError,KeyError) as error:
        parser.exit(1,'Component build refused: '+str(error)+'\n')
