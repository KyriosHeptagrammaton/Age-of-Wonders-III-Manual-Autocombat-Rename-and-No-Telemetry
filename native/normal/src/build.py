#!/usr/bin/env python3
"""Build the exact-version normal AoW3 runtime. Input is never overwritten."""
import argparse, hashlib, json, struct, subprocess, tempfile
from pathlib import Path
from pe import PE, checksum
SOURCE_SHA256='9fd625d451ae534cf877b7850c614677f4d2d6209741bf85035e79f081a796d4'
CODE_RVA=0xf22000
STATE_RVA=0xf28000
SOURCE=Path(__file__).parent
PROFILE=json.loads((SOURCE/'profile.json').read_text())
SYMBOLS=PROFILE['symbols']
HOOKS=PROFILE['hooks']
def sha(b):return hashlib.sha256(b).hexdigest()
def align(v,a):return (v+a-1)//a*a

def make_payload():
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);objects=[]
        for name in ['hooks.S','engine.S','retry.c','native.c','click_rename.c']:
            obj=tmp/(name+'.o');objects.append(str(obj))
            if name.endswith('.S'):
                cmd=['as','--32',str(SOURCE/name),'-o',str(obj)]
            else:
                cmd=['gcc','-m32','-Os','-ffreestanding','-fPIC','-fno-plt','-fno-stack-protector','-fno-asynchronous-unwind-tables','-fno-unwind-tables','-fno-builtin','-mno-sse','-mno-mmx','-mpreferred-stack-boundary=2','-mincoming-stack-boundary=2','-Wall','-Wextra','-Werror','-c',str(SOURCE/name),'-o',str(obj)]
            subprocess.run(cmd,check=True)
        elf=tmp/'payload.elf';binary=tmp/'payload.bin'
        subprocess.run(['ld','-m','elf_i386','-T',str(SOURCE/'payload.ld'),*[f'--defsym={k}={v}' for k,v in SYMBOLS.items()],*objects,'-o',str(elf)],check=True)
        if 'There are no relocations' not in subprocess.check_output(['readelf','-r',str(elf)],text=True):raise ValueError('Unresolved relocation')
        if subprocess.check_output(['nm','-u',str(elf)],text=True).strip():raise ValueError('Unresolved symbol')
        subprocess.run(['objcopy','-O','binary','-j','.text',str(elf),str(binary)],check=True)
        symbols={}
        for line in subprocess.check_output(['nm','-n',str(elf)],text=True).splitlines():
            parts=line.split()
            if len(parts)==3:symbols[parts[2]]=int(parts[0],16)
        return binary.read_bytes(),symbols

def relocations(p):
    rva,size=p.u32(p.optional+136),p.u32(p.optional+140)
    at=p.raw(rva);end=at+size;out=set()
    while at<end:
        page,block=struct.unpack_from('<II',p.data,at)
        if block<8 or at+block>end:raise ValueError('Invalid relocation block')
        for pos in range(at+8,at+block,2):
            value=p.u16(pos)
            if value>>12==3:out.add(page+(value&0xfff))
            elif value>>12!=0:raise ValueError('Unsupported relocation')
        at+=block
    return out

def patch(original,payload,symbols,disable_telemetry=True):
    if sha(original)!=SOURCE_SHA256:raise ValueError('Unsupported normal executable SHA-256')
    p=PE(original);p.validate_image_layout();data=bytearray(original)
    if p.u16(p.pe+4)!=0x14c or p.u32(p.optional+56)!=CODE_RVA:raise ValueError('Unexpected architecture/layout')
    if p.u32(p.optional+128) or p.u32(p.optional+132):raise ValueError('Unexpected certificate table')
    head=p.table+40*p.count
    if head+80>p.u32(p.optional+60) or any(data[head:head+80]):raise ValueError('No section-header space')
    if align(CODE_RVA+len(payload),0x1000)>STATE_RVA:raise ValueError('Payload overlaps state')
    if max(s['raw']+s['size'] for s in p.sections)!=len(data):raise ValueError('Unexpected overlay')
    raw=align(len(data),p.u32(p.optional+36));size=align(len(payload),p.u32(p.optional+36))
    data.extend(b'\0'*(raw-len(data)));data.extend(payload);data.extend(b'\0'*(size-len(payload)))
    struct.pack_into('<8sIIIIIIHHI',data,head,b'.aowname',STATE_RVA-CODE_RVA,CODE_RVA,size,raw,0,0,0,0,0x60000020)
    struct.pack_into('<8sIIIIIIHHI',data,head+40,b'.aowdata',0x1000,STATE_RVA,0,0,0,0,0,0,0xc0000080)
    struct.pack_into('<H',data,p.pe+6,p.count+2)
    for offset,value in [(4,p.u32(p.optional+4)+size),(12,p.u32(p.optional+12)+0x1000),(56,STATE_RVA+0x1000)]:struct.pack_into('<I',data,p.optional+offset,value)
    allowed=set(range(head,head+80));relocs=relocations(p)
    for hook in HOOKS:
        if hook['symbol']=='telemetry_disabled' and not disable_telemetry:continue
        rva=hook['rva'];expected=bytes.fromhex(hook['expected']);at=p.raw(rva)
        if data[at:at+len(expected)]!=expected:raise ValueError(f'Hook mismatch {rva:#x}')
        if any(rva<=r<rva+len(expected) or r<rva<r+4 for r in relocs):raise ValueError(f'Hook overlaps PE relocation {rva:#x}')
        data[at:at+len(expected)]=bytes([hook['opcode']])+struct.pack('<i',symbols[hook['symbol']]-(rva+5))+b'\x90'*(len(expected)-5)
        allowed.update(range(at,at+len(expected)))
    check=p.optional+64
    struct.pack_into('<I',data,check,0);struct.pack_into('<I',data,check,checksum(data,check))
    for off,n in [(p.pe+6,2),(p.optional+4,4),(p.optional+12,4),(p.optional+56,4),(check,4)]:allowed.update(range(off,off+n))
    if any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(original,data))):raise AssertionError('Unexpected modification')
    PE(data).validate_image_layout()
    return bytes(data)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--telemetry-default',action='store_true');args=parser.parse_args()
    path=args.output/'AoW3.exe'
    if path.exists() or path.resolve()==args.original.resolve():parser.error('Choose a new output directory')
    original=args.original.read_bytes();payload,symbols=make_payload()
    modified=patch(original,payload,symbols,not args.telemetry_default)
    args.output.mkdir(parents=True,exist_ok=True);path.write_bytes(modified)
    (args.output/'rename-payload.bin').write_bytes(payload)
    manifest=dict(version='0.7.2',build='normal',status='normal v0.7.1 reported working; new tooltip health fix awaits in-game confirmation',original_sha256=sha(original),patched_sha256=sha(modified),payload_sha256=sha(payload),payload_size=len(payload),telemetry_disabled=not args.telemetry_default,new_section_rva=CODE_RVA,writable_state_rva=STATE_RVA,symbols=symbols)
    (args.output/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='symbols'},indent=2))
if __name__=='__main__':main()
