#!/usr/bin/env python3
"""Verify the recovered GX9 Linux command runner in a bounded ARM emulator.

The input is a hash-pinned proprietary PSM executable from the owner's captured
filesystem. Native ARM instructions run in Unicorn. Every libc/process/file/IPC
operation is mocked: no shell command is executed, no camera is contacted and
no target filesystem is mounted. This does not demonstrate an external entry.
Requires Unicorn 2.1.4, the version used for the recorded controls.
"""
from pathlib import Path
import argparse
import struct
import json
import hashlib
import re
import unicorn as U
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

PSM_SHA = '7cafa9b91050c613b9fa76391f12003cbdd0a8e91f4e2e46dc0b22b1a5166fbd'

class Elf:
 def __init__(self,path):
   self.path=Path(path);self.data=self.path.read_bytes();b=self.data
   if b[:6]!=b"\x7fELF\x01\x01" or struct.unpack_from("<H",b,18)[0]!=40:raise ValueError("ARM ELF32LE required")
   h=struct.unpack_from("<HHIIIIIHHHHHH",b,16);self.ph=[];self.sections={}
   for i in range(h[9]):
    row=struct.unpack_from("<IIIIIIII",b,h[4]+i*h[8]);self.ph.append(row)
   rows=[struct.unpack_from("<10I",b,h[5]+i*h[10]) for i in range(h[11])]
   names=rows[h[12]];names=b[names[4]:names[4]+names[5]]
   for s in rows:
    name=names[s[0]:].split(b"\0")[0].decode();self.sections[name]=s
   symbols=self.sections.get(".dynsym");strings=self.sections.get(".dynstr")
   self.symbols=[];relocs={};self.plt={}
   if symbols and strings:
    strings=b[strings[4]:strings[4]+strings[5]]
    for pos in range(symbols[4],symbols[4]+symbols[5],symbols[9]):
     row=struct.unpack_from("<IIIBBH",b,pos);name=strings[row[0]:].split(b"\0")[0].decode();self.symbols.append((name,*row[1:]))
    for section in (".rel.plt",".rel.dyn"):
     if section not in self.sections:continue
     s=self.sections[section]
     for pos in range(s[4],s[4]+s[5],s[9]):
      address,info=struct.unpack_from("<II",b,pos);relocs[address]=self.symbols[info>>8][0]
   if ".plt" in self.sections:
    s=self.sections[".plt"]
    for off in range(20,s[5]-11,12):
     address=s[3]+off;a,c,d=struct.unpack_from("<III",b,s[4]+off)
     if a&0xfffff000!=0xe28fc000 or c&0xfffff000!=0xe28cc000 or d&0xfffff000!=0xe5bcf000:raise ValueError("Unexpected ARM PLT template")
     def immediate(w):
      n=((w>>8)&15)*2;v=w&255
      return ((v>>n)|(v<<(32-n)))&0xffffffff if n else v
     got=address+8+immediate(a)+immediate(c)+(d&0xfff)
     if got in relocs:self.plt[address]=relocs[got]
 def offset(self,va):
   for t,off,v,pa,size,mem,flags,align in self.ph:
    if t==1 and v<=va<v+size:return off+va-v
   raise ValueError("Address not file backed: "+hex(va))
 def word(self,va):return struct.unpack_from("<I",self.data,self.offset(va))[0]
 def string(self,va):return self.data[self.offset(va):].split(b"\0")[0].decode("utf-8","replace")

REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
STACK,HEAP,RETURN=0x10000000,0x30000000,0x20000000

def run(command,output,entry=0x398d8):
 uc=U.Uc(U.UC_ARCH_ARM,U.UC_MODE_ARM)
 uc.mem_map(0x10000,0x80000)
 for typ,off,va,physical,size,mem,flags,align in e.ph:
  if typ==1:uc.mem_write(va,e.data[off:off+size])
 for address,size in [(STACK,0x20000),(HEAP,0x20000),(RETURN,0x1000)]:uc.mem_map(address,size)
 message=bytearray(488);struct.pack_into('<6I',message,0,0x3c,0,0,0,0,len(command));message[24:24+len(command)]=command.encode()
 uc.mem_write(HEAP,bytes(message));uc.reg_write(UC_ARM_REG_SP,STACK+0x1ff00);uc.reg_write(UC_ARM_REG_LR,RETURN)
 uc.reg_write(UC_ARM_REG_R0,HEAP if entry==0x398d8 else 0x42);uc.reg_write(UC_ARM_REG_R1,HEAP)
 result={'entry':hex(entry),'command':command,'host_commands_executed':False,'native_instructions':0,'system_arguments':[],'messages':[],'threads':[]};position=0
 def string(address):
  value=bytearray()
  for i in range(2048):
   c=uc.mem_read(address+i,1)[0]
   if not c:return bytes(value)
   value.append(c)
  raise ValueError('Unterminated emulated string')
 def ret(value=0):uc.reg_write(UC_ARM_REG_R0,value&0xffffffff);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 def code(uc,address,size,user):
  nonlocal position
  result['native_instructions']+=1
  if address==RETURN:uc.emu_stop();return
  args=[uc.reg_read(reg) for reg in REGS]
  if address in (0x2c248,):ret(0x42);return
  if address in (0x2bfd4,0x3bc64):
   raw=bytes(uc.mem_read(args[1],488));result['messages'].append({'header':list(struct.unpack_from('<6I',raw)),'data_hex':raw[24:24+min(struct.unpack_from('<I',raw,20)[0],464)].hex()});ret(0);return
  name=e.plt.get(address)
  if not name:return
  a,b,c,d=args
  if name in ('printf','free','pthread_attr_init','pthread_attr_setstacksize','pthread_attr_setdetachstate','fclose'):ret(0)
  elif name=='memcpy':uc.mem_write(a,bytes(uc.mem_read(b,c)));ret(a)
  elif name=='strcpy':uc.mem_write(a,string(b)+b'\0');ret(a)
  elif name=='strncpy':uc.mem_write(a,string(b)[:c].ljust(c,b'\0'));ret(a)
  elif name in ('strchr','strrchr'):
   value=string(a);pos=value.find(bytes([b&255])) if name=='strchr' else value.rfind(bytes([b&255]));ret(a+pos if pos>=0 else 0)
  elif name=='sprintf':
   fmt=string(b)
   if fmt==b'/tmp/%s':value=b'/tmp/'+string(c)
   elif fmt==b'%s > %s':value=string(c)+b' > '+string(d)
   else:raise ValueError('Unsupported native format '+repr(fmt))
   uc.mem_write(a,value+b'\0');ret(len(value))
  elif name=='system':result['system_arguments'].append(string(a).decode());ret(0)
  elif name=='fopen':result['fopen_arguments']=[string(a).decode(),string(b).decode()];ret(0x71)
  elif name=='fread':
   assert d==0x71 and b==1 and c==175
   value=output[position:position+c];position+=len(value);uc.mem_write(a,value);ret(len(value))
  elif name=='feof':ret(int(position>=len(output)))
  elif name=='malloc':assert a==488;ret(HEAP+0x1000)
  elif name=='pthread_create':
   result['threads'].append({'function':hex(c),'argument':hex(d),'message_hex':bytes(uc.mem_read(d,488)).hex()});uc.mem_write(a,struct.pack('<I',0x123));ret(0)
  else:raise ValueError('Unimplemented native import '+name+' at '+hex(address))
 uc.hook_add(U.UC_HOOK_CODE,code)
 uc.emu_start(entry,RETURN+4,count=100000)
 assert uc.reg_read(UC_ARM_REG_PC)==RETURN
 result['output_hex']=b''.join(bytes.fromhex(m['data_hex']) for m in result['messages']).hex()
 return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('psm', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.psm.read_bytes()).hexdigest() != PSM_SHA:
        raise ValueError('Expected the verified GX9 PSM executable')
    global e
    e = Elf(args.psm)
    checks = {
        0x2aa68: 0xe350003c,  # compare event ID 60 in the event-name lookup
        0x2aa6c: 0x0a000208,  # branch to its name return
        0x2b294: 0xe59f02dc,  # load the NET_EVT_LINUX_CMD string pointer
        0x2b578: 0x00058f20,
        0x39eb0: 0xe353003c, # same event ID in the test dispatcher
        0x39eb4: 0x0a000028,
        0x39fdc: 0xe59f231c, # load command worker function for pthread_create
        0x3a300: 0x000398d8,
        0x39fe4: 0xebff613a,
        0x39998: 0xebff623d, # both branches call the imported system function
        0x399dc: 0xebff622c,
        0x39a00: 0xe3a020af, # output reads use 175-byte chunks
    }
    for address, expected in checks.items():
        if e.word(address) != expected:
            raise ValueError('Native instruction/literal differs: ' + hex(address))
    if e.string(0x58f20) != 'NET_EVT_LINUX_CMD':
        raise ValueError('Event-name literal differs')
    if e.plt.get(0x12294) != 'system' or e.plt.get(0x124d4) != 'pthread_create':
        raise ValueError('Native calls disagree with ELF dynamic relocations')

    marker = 'printf GX9_CONSOLE_OK'
    short = run(marker, b'GX9_CONSOLE_OK')
    assert short['system_arguments'] == [marker + ' > /tmp/printf']
    assert bytes.fromhex(short['output_hex']) == b'GX9_CONSOLE_OK\r\n'
    assert [m['header'][5] for m in short['messages']] == [14, 2]
    long = run(marker, b'A' * 400)
    assert [m['header'][5] for m in long['messages']] == [175, 175, 50, 2]
    assert bytes.fromhex(long['output_hex']) == b'A' * 400 + b'\r\n'
    redirected = run(marker + ' > /tmp/gx9-proof', b'')
    assert redirected['system_arguments'] == [marker + ' > /tmp/gx9-proof']
    assert not redirected['messages']
    dispatched = run(marker, b'', 0x39e94)
    assert len(dispatched['threads']) == 1
    thread = dispatched['threads'][0]
    assert thread['function'] == '0x398d8'
    message = bytes.fromhex(thread['message_hex'])
    assert len(message) == 488 and message[24:].split(b'\0')[0] == marker.encode()
    assert dispatched['messages'][0]['header'][:2] == [60, 1]
    assert all(m['header'][:2] == [60, 2] for case in (short, long) for m in case['messages'])

    cases = [short, long, redirected, dispatched]
    for case in cases:
        output = bytes.fromhex(case.pop('output_hex'))
        case['returned_bytes'] = len(output)
        case['returned_sha256'] = hashlib.sha256(output).hexdigest()
        for message in case['messages']:
            data = bytes.fromhex(message.pop('data_hex'))
            message['data_bytes'] = len(data)
            message['data_sha256'] = hashlib.sha256(data).hexdigest()
        for thread in case['threads']:
            data = bytes.fromhex(thread.pop('message_hex'))
            thread['message_bytes'] = len(data)
            thread['message_sha256'] = hashlib.sha256(data).hexdigest()
    report = {
        'schema': 1, 'input_sha256': PSM_SHA, 'input_bytes': len(e.data),
        'unicorn_version': U.__version__,
        'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'Captured native ARM dispatcher and command worker with mocked libc and IPC',
        'event_name': 'NET_EVT_LINUX_CMD', 'event_id': 60,
        'internal_message_bytes': 488, 'command_offset': 24,
        'output_length_offset': 20, 'output_chunk_maximum': 175,
        'acknowledgement_type': 1, 'output_type': 2,
        'dispatcher_virtual_address': '0x39e94', 'worker_virtual_address': '0x398d8',
        'native_words_checked': {hex(a): hex(v) for a, v in checks.items()},
        'cases': cases, 'all_controls_passed': True,
        'camera_requests': 0, 'host_shell_commands_executed': 0,
        'external_usb_or_wifi_entry_demonstrated': False,
        'limits': [
            'Libc process/file operations and internal IPC were simulated, not executed on Linux.',
            'An internal 488-byte message is not a USB packet or an exposed Wi-Fi protocol.',
            'No firmware key, main-camera program or live camera shell was recovered by this verifier.',
        ],
    }
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('Four native ARM controls passed; shell execution and IPC were mocked; zero camera requests.')


if __name__ == '__main__':
    main()
