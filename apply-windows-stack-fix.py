#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Reproduce the experimental Windows guest-stack workaround, revision 2.

Only the original chenxiao07/KytyPS5 v20261017 Windows executable is accepted.
The exact result matches the local build that reached gameplay. See WINDOWS-STACK-FIX.md.
"""
from pathlib import Path
import argparse, struct, hashlib, json, shutil, pefile
from keystone import Ks, KS_ARCH_X86, KS_MODE_64

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='Original v20261017 kyty_emulator.exe')
parser.add_argument('--output-dir', type=Path, help='New folder for the patched executable and runtime DLLs')
args = parser.parse_args()
source = args.source.resolve(strict=True)
output = args.output_dir or source.parent / 'local-stack-fix-v2'
destination = output.resolve() / source.name
if destination == source:
    parser.error('The output must not overwrite the original executable')
if destination.exists():
    parser.error('Output executable already exists; choose a new output directory')
expected_source_sha256 = '88f2545f5e261f2a4f085c1a8e487a2f2a94ffe7a3ad02fc098752919e9a0764'
expected_result_sha256 = '4912aa46d0a89dd07086fe9b4f96ded5e2b72b8eeb84fb0ebeefa9331460bb87'
if hashlib.sha256(source.read_bytes()).hexdigest() != expected_source_sha256:
    parser.error('Unsupported executable: this patch is ONLY for the original Windows v20261017 release')
raw=bytearray(source.read_bytes())
pe=pefile.PE(data=raw)
entry=0xC3BEF0
expected=bytes.fromhex('554881ecd0000000488dac2480000000')
assert pe.get_data(entry,len(expected))==expected
def align(v,a): return (v+a-1)//a*a
new_rva=align(pe.OPTIONAL_HEADER.SizeOfImage,pe.OPTIONAL_HEADER.SectionAlignment)
asm=f'''
    push rbx
    sub rsp, 0x70
    mov [rsp+0x58], rcx
    mov rax, [rcx+8]
    mov rcx, [rax+0x98]
    mov rax, 0x200000000
    cmp rcx, rax
    jb done
    mov rax, 0x800000000
    cmp rcx, rax
    jae done
    mov eax, 0x30
    mov rbx, gs:[rax]
    cmp rcx, [rbx+0x10]
    jb register_stack
    cmp rcx, [rbx+8]
    jbe done
register_stack:
    lea rdx, [rsp+0x20]
    mov r8d, 48
    call qword ptr [rip+0x11223344]
    cmp rax, 48
    jne done
    cmp dword ptr [rsp+0x40], 0x1000
    jne done
    mov rax, [rsp+0x28]
    mov rdx, [rsp+0x38]
    add rdx, [rsp+0x20]
    mov [rbx+8], rdx
    mov [rbx+0x10], rax
done:
    mov rcx, [rsp+0x58]
    add rsp, 0x70
    pop rbx
'''
encoded,_=Ks(KS_ARCH_X86,KS_MODE_64).asm(asm,addr=new_rva)
code=bytearray(encoded)
sentinel=code.index(bytes.fromhex('ff1544332211'))
vq=next(s.address-pe.OPTIONAL_HEADER.ImageBase for i in pe.DIRECTORY_ENTRY_IMPORT
        for s in i.imports if s.name==b'VirtualQuery')
struct.pack_into('<i',code,sentinel+2,vq-(new_rva+sentinel+6))
code.extend(expected[:8])
code.extend(b'\xe9'+struct.pack('<i',entry+8-(new_rva+len(code)+5)))
# RunOnGuestStack originally uses zero bounds to suppress __chkstk on guest
# stacks. Preserve that deliberate behavior explicitly, including after a
# guest fiber switches to another stack, while giving Windows real bounds.
chk_entry=0xC61560
chk_expected=bytes.fromhex('4883ec104c891424')
assert pe.get_data(chk_entry,8)==chk_expected
chk_rva=new_rva+len(code)
chk_asm='''
    push r10
    push r11
    lea r10, [rsp+16]
    mov r11, 0x200000000
    cmp r10, r11
    jb native_stack
    mov r11, 0x800000000
    cmp r10, r11
    jae native_stack
    pop r11
    pop r10
    ret
native_stack:
    pop r11
    pop r10
'''
chk_bytes,_=Ks(KS_ARCH_X86,KS_MODE_64).asm(chk_asm,addr=chk_rva)
code.extend(chk_bytes)
code.extend(chk_expected)
code.extend(b'\xe9'+struct.pack('<i',chk_entry+8-(new_rva+len(code)+5)))
# Fibers can switch before any fault on their new stack. Register the new
# stack at the actual switch, so __chkstk in Windows runtime DLLs also sees
# the active fiber's allocation rather than the previous fiber's stack.
fiber_pattern=bytes.fromhex('4989fa4889f04d8b5a48498b1a498b6a08')
text=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.text')
text_bytes=text.get_data()
assert text_bytes.count(fiber_pattern)==1, 'Unexpected fiber-restore code'
fiber_entry=text.VirtualAddress+text_bytes.index(fiber_pattern)
fiber_rva=new_rva+len(code)
fiber_asm='''
    push rbx
    sub rsp, 0x50
    mov rbx, rdi
    mov rcx, [rbx+0x40]
    lea rdx, [rsp+0x20]
    mov r8d, 48
    call qword ptr [rip+0x11223344]
    cmp rax, 48
    jne restore_context
    cmp dword ptr [rsp+0x40], 0x1000
    jne restore_context
    mov eax, 0x30
    mov rcx, gs:[rax]
    mov rax, [rsp+0x28]
    mov rdx, [rsp+0x20]
    add rdx, [rsp+0x38]
    mov [rcx+0x10], rax
    mov [rcx+8], rdx
restore_context:
    add rsp, 0x50
    pop rbx
'''
fiber_bytes,_=Ks(KS_ARCH_X86,KS_MODE_64).asm(fiber_asm,addr=fiber_rva)
fiber_code=bytearray(fiber_bytes)
at=fiber_code.index(bytes.fromhex('ff1544332211'))
struct.pack_into('<i',fiber_code,at+2,vq-(fiber_rva+at+6))
code.extend(fiber_code)
code.extend(fiber_pattern[:6])
code.extend(b'\xe9'+struct.pack('<i',fiber_entry+6-(new_rva+len(code)+5)))
header=pe.sections[-1].get_file_offset()+40
assert header+40<=min(s.PointerToRawData for s in pe.sections if s.PointerToRawData)
offset=align(len(raw),pe.OPTIONAL_HEADER.FileAlignment)
size=align(len(code),pe.OPTIONAL_HEADER.FileAlignment)
raw.extend(b'\0'*(offset-len(raw))+code+b'\0'*(size-len(code)))
raw[header:header+40]=struct.pack('<8sIIIIIIHHI',b'.stkfix',len(code),new_rva,size,offset,0,0,0,0,0x60000020)
struct.pack_into('<H',raw,pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'),len(pe.sections)+1)
struct.pack_into('<I',raw,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),align(new_rva+len(code),pe.OPTIONAL_HEADER.SectionAlignment))
struct.pack_into('<I',raw,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfCode'),pe.OPTIONAL_HEADER.SizeOfCode+size)
off=pe.get_offset_from_rva(entry)
raw[off:off+5]=b'\xe9'+struct.pack('<i',new_rva-entry-5)
chk_off=pe.get_offset_from_rva(chk_entry)
raw[chk_off:chk_off+5]=b'\xe9'+struct.pack('<i',chk_rva-chk_entry-5)
fiber_off=pe.get_offset_from_rva(fiber_entry)
raw[fiber_off:fiber_off+5]=b'\xe9'+struct.pack('<i',fiber_rva-fiber_entry-5)
updated=pefile.PE(data=raw)
struct.pack_into('<I',raw,updated.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'),updated.generate_checksum())
result_sha256 = hashlib.sha256(raw).hexdigest()
if result_sha256 != expected_result_sha256:
    raise RuntimeError('Generated executable differs from the known revision 2 result; no output was written')
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_bytes(raw)
for dll in source.parent.glob('*.dll'): shutil.copy2(dll,destination.parent/dll.name)
metadata=dict(original=source.name,patched=destination.name,original_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),patched_sha256=hashlib.sha256(raw).hexdigest(),handler_rva=hex(entry),wrapper_rva=hex(new_rva),chkstk_rva=hex(chk_entry),chkstk_wrapper_rva=hex(chk_rva),fiber_restore_rva=hex(fiber_entry),fiber_wrapper_rva=hex(fiber_rva),wrapper=code.hex())
(destination.parent/'patch-details.json').write_text(json.dumps(metadata,indent=2))
print(json.dumps(metadata,indent=2))
