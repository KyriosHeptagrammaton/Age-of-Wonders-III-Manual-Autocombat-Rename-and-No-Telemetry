#!/usr/bin/env python3
"""Build a reversible, exact-version AoW3 debug rename/retry prototype.

Requires Python 3.8+, GCC and GNU binutils, e.g. Linux/WSL.
The input executable is never overwritten. No game files are downloaded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from pe import PE, checksum

SOURCE_SHA256 = '233584a414e16f624a5531b10e1491896e4b17a074e585364fec7d11c692d763'
HOOK_RVA = 0x54ddb0
DISPLACED = bytes.fromhex('55 8b ec 6a ff')
CODE_RVA = 0xfc2000
STATE_RVA = 0xfc8000
SYMBOLS = dict(original_resume=HOOK_RVA + 5, get_hud=0x5ea5f0,
               can_generate_actions=0x635c00, strategic_cheats=0x63a820,
               assign_narrow=0x116880, assign_wide=0x139250,
               close_window=0x138320, message_box_iat=0xa8e658,
               stack_get_unit=0x82ef20,
               close_ac_resume=0x6dc240, close_ac_cleanup=0x6dc2d2,
               close_ac_commit=0x6dc28a,
               close_ac_epilogue=0x6dc38e, battle_set_state=0x6dda80,
               set_current_heap=0x1128c0,
               ui_entry_resume=0x5af576, ui_exit_resume=0x54c546,
               ui_refresh_resume=0x5adbf5, manual_resume=0x54c5d6,
               auto_resume=0x54c666, ready_resume=0x54c8fa,
               ready_done=0x54c912, retreat_resume=0x54c803,
               retreat_done=0x54c836, world_tick_resume=0x6de7ef,
               manager_dtor_resume=0x6b3f05, result_units_resume=0x6103b5,
               setup_units=0x610050, iggy_call=0x194ae0,
               combat_complete=0x69a110, tooltip_health_resume=0x60ce80,
               rename_click_resume=0x54ab09, rename_click_done=0x54ab1e,
               rename_submit_resume=0x56d6b5, rename_exit_resume=0x54d396)

RETRY_HOOKS = [
    (0x6dc238, bytes.fromhex('8b f1 8b 8e bc 00 00 00'), 'retry_entry', 0xe9),
    (0x6dc2ca, bytes.fromhex('e8 f1 65 a3 ff'), 'retry_accept_done', 0xe8),
    (0x6dc385, bytes.fromhex('6a 00 8b ce e8 f2 16 00 00'), 'retry_finish', 0xe9),
]

NATIVE_HOOKS = [
    (0x60ce77, bytes.fromhex('8b 4e 28 8b 96 e8 01 00 00'), 'tooltip_health_hook', 0xe9),
    (0x6d65ec, bytes.fromhex('e8 1f 3b fc ff'), 'combat_report_hook', 0xe8),
    (0x5af570, bytes.fromhex('55 8b ec 8b 45 08'), 'ui_entry_hook', 0xe9),
    (0x54c540, bytes.fromhex('55 8b ec 56 8b f1'), 'ui_exit_hook', 0xe9),
    (0x5adbf0, bytes.fromhex('55 8b ec 6a ff'), 'ui_refresh_hook', 0xe9),
    (0x54c5d0, bytes.fromhex('55 8b ec 83 ec 08'), 'manual_hook', 0xe9),
    (0x54c660, bytes.fromhex('55 8b ec 83 ec 0c'), 'auto_hook', 0xe9),
    (0x54c8f4, bytes.fromhex('8b 8e 54 01 00 00'), 'ready_hook', 0xe9),
    (0x54c7fc, bytes.fromhex('8b ce e8 ed dd 09 00'), 'retreat_hook', 0xe9),
    (0x6de7e9, bytes.fromhex('8b 86 b8 2e 00 00'), 'world_tick_hook', 0xe9),
    (0x6b3f00, bytes.fromhex('55 8b ec 6a ff'), 'manager_dtor_hook', 0xe9),
    (0x6103b0, bytes.fromhex('55 8b ec 6a ff'), 'result_units_hook', 0xe9),
    (0x610362, bytes.fromhex('e8 79 47 b8 ff'), 'unit_hook', 0xe8),
]

TELEMETRY_HOOKS = [
    (0x357000, bytes.fromhex('55 8b ec 6a ff'), 'telemetry_disabled', 0xe9),
    (0x3575d0, bytes.fromhex('55 8b ec 6a ff'), 'telemetry_disabled', 0xe9),
]
CLICK_RENAME_HOOKS = [
    (0x54ab04, bytes.fromhex('83 c4 10 8b cc'), 'rename_click_hook', 0xe9),
    (0x5e57f1, bytes.fromhex('e8 ea f2 ba ff'), 'rename_panel_hook', 0xe8),
    (0x54d389, bytes.fromhex('5e 5d c2 04 00'), 'rename_opened_hook', 0xe9),
    (0x54d390, bytes.fromhex('55 8b ec 8b 45 08'), 'rename_exit_hook', 0xe9),
    (0x56d6b0, bytes.fromhex('55 8b ec 6a ff'), 'rename_submit_hook', 0xe9),
]
STATIC_PATCHES = [
    # Always use the existing "false" string in the startup status log.
    (0x074f5a, bytes.fromhex('75 05'), bytes.fromhex('90 90')),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def make_payload():
    source = Path(__file__).parent
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        obj, elf, binary = (directory / f'payload.{ext}' for ext in ('o', 'elf', 'bin'))
        subprocess.run(['as', '--32', str(source / 'rename.S'), '-o', str(obj)], check=True)
        retry_asm, retry_c = directory / 'retry-asm.o', directory / 'retry-c.o'
        subprocess.run(['as', '--32', str(source / 'retry.S'), '-o', str(retry_asm)], check=True)
        subprocess.run(['gcc', '-m32', '-Os', '-ffreestanding', '-fPIC', '-fno-plt',
                        '-fno-stack-protector', '-fno-asynchronous-unwind-tables',
                        '-fno-unwind-tables', '-fno-builtin', '-mno-sse', '-mno-mmx',
                        '-mpreferred-stack-boundary=2', '-mincoming-stack-boundary=2',
                        '-Wall', '-Wextra', '-Werror', '-c', str(source / 'retry.c'),
                        '-o', str(retry_c)], check=True)
        telemetry = directory / 'telemetry.o'
        subprocess.run(['as', '--32', str(source / 'telemetry.S'), '-o', str(telemetry)], check=True)
        native_asm, native_c = directory / 'native-asm.o', directory / 'native-c.o'
        subprocess.run(['as', '--32', str(source / 'native.S'), '-o', str(native_asm)], check=True)
        subprocess.run(['gcc', '-m32', '-Os', '-ffreestanding', '-fPIC', '-fno-plt',
                        '-fno-stack-protector', '-fno-asynchronous-unwind-tables',
                        '-fno-unwind-tables', '-fno-builtin', '-mno-sse', '-mno-mmx',
                        '-mpreferred-stack-boundary=2', '-mincoming-stack-boundary=2',
                        '-Wall', '-Wextra', '-Werror', '-c', str(source / 'native.c'),
                        '-o', str(native_c)], check=True)
        definitions = [f'--defsym={name}={value}' for name, value in SYMBOLS.items()]
        click_asm, click_c = directory / 'click-asm.o', directory / 'click-c.o'
        subprocess.run(['as', '--32', str(source / 'click_rename.S'), '-o', str(click_asm)], check=True)
        subprocess.run(['gcc', '-m32', '-Os', '-ffreestanding', '-fPIC', '-fno-plt',
                        '-fno-stack-protector', '-fno-asynchronous-unwind-tables',
                        '-fno-unwind-tables', '-fno-builtin', '-mno-sse', '-mno-mmx',
                        '-mpreferred-stack-boundary=2', '-mincoming-stack-boundary=2',
                        '-Wall', '-Wextra', '-Werror', '-c', str(source / 'click_rename.c'),
                        '-o', str(click_c)], check=True)
        subprocess.run(['ld', '-m', 'elf_i386', '-T', str(source / 'payload.ld'),
                        *definitions, str(obj), str(retry_asm), str(retry_c), str(telemetry),
                        str(native_asm), str(native_c), str(click_asm), str(click_c),
                        '-o', str(elf)], check=True)
        relocations = subprocess.check_output(['readelf', '-r', str(elf)], text=True)
        if 'There are no relocations' not in relocations:
            raise ValueError('Payload still needs relocations')
        if subprocess.check_output(['nm', '-u', str(elf)], text=True).strip():
            raise ValueError('Unresolved payload symbols')
        subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', str(elf), str(binary)], check=True)
        symbols = {}
        for line in subprocess.check_output(['nm', '-n', str(elf)], text=True).splitlines():
            parts = line.split()
            if len(parts) == 3:
                symbols[parts[2]] = int(parts[0], 16)
        return binary.read_bytes(), symbols


def patch(original, payload, symbols=None, disable_telemetry=True):
    if sha(original) != SOURCE_SHA256:
        raise ValueError('Unsupported executable SHA-256. Use the exact uploaded original debug build.')
    data = bytearray(original)
    pe = PE(data)
    pe.validate_image_layout()
    if pe.u16(pe.pe + 4) != 0x14c or pe.u32(pe.optional + 56) != CODE_RVA:
        raise ValueError('Unexpected PE architecture or image size')
    at = pe.raw(HOOK_RVA)
    if data[at:at + 5] != DISPLACED:
        raise ValueError('Original hook bytes differ')
    if symbols is None:
        rebuilt, symbols = make_payload()
        if payload != rebuilt:
            raise ValueError('Payload does not match this source build')
    if pe.imports()[('user32.dll', 'MessageBoxA')] != SYMBOLS['message_box_iat']:
        raise ValueError('Unexpected import layout')
    if pe.u32(pe.optional + 128) or pe.u32(pe.optional + 132):
        raise ValueError('Refusing to invalidate a PE certificate table')
    next_header = pe.table + 40 * pe.count
    if next_header + 80 > pe.u32(pe.optional + 60) or any(data[next_header:next_header + 80]):
        raise ValueError('No unused section-header space')
    if align(CODE_RVA+len(payload),0x1000)>STATE_RVA:
        raise ValueError('Payload overlaps the writable state section')
    raw_end = max(s['raw'] + s['size'] for s in pe.sections)
    if raw_end != len(data):
        raise ValueError('Unexpected executable overlay')
    file_align, section_align = pe.u32(pe.optional + 36), pe.u32(pe.optional + 32)
    raw = align(len(data), file_align)
    raw_size = align(len(payload), file_align)
    data.extend(b'\0' * (raw - len(data)))
    data.extend(payload)
    data.extend(b'\0' * (raw_size - len(payload)))
    # Keep sections adjacent in memory, as required by the Windows PE format.
    # The reserved code capacity is zero-filled up to the fixed state RVA.
    # v0.6 used len(payload), leaving an invalid four-page gap before .aowdata.
    struct.pack_into('<8sIIIIIIHHI', data, next_header, b'.aowname', STATE_RVA-CODE_RVA, CODE_RVA,
                     raw_size, raw, 0, 0, 0, 0, 0x60000020)
    struct.pack_into('<8sIIIIIIHHI', data, next_header+40, b'.aowdata', 0x1000, STATE_RVA,
                     0, 0, 0, 0, 0, 0, 0xc0000080)
    struct.pack_into('<H', data, pe.pe + 6, pe.count + 2)
    struct.pack_into('<I', data, pe.optional + 4, pe.u32(pe.optional + 4) + raw_size)
    struct.pack_into('<I', data, pe.optional + 12, pe.u32(pe.optional + 12) + 0x1000)
    struct.pack_into('<I', data, pe.optional + 56, align(STATE_RVA + 0x1000, section_align))
    data[at:at + 5] = b'\xe9' + struct.pack('<i', CODE_RVA - (HOOK_RVA + 5))
    extra_ranges = set()
    telemetry_hooks = TELEMETRY_HOOKS if disable_telemetry else []
    static_patches = STATIC_PATCHES if disable_telemetry else []
    for rva, expected, label, opcode in RETRY_HOOKS + telemetry_hooks + NATIVE_HOOKS + CLICK_RENAME_HOOKS:
        where = pe.raw(rva)
        if original[where:where+len(expected)] != expected:
            raise ValueError(f'Unexpected original hook at {rva:#x}')
        data[where:where+len(expected)] = (bytes([opcode])
            + struct.pack('<i', symbols[label]-(rva+5)) + b'\x90'*(len(expected)-5))
        extra_ranges.update(range(where,where+len(expected)))
    for rva, expected, replacement in static_patches:
        where = pe.raw(rva)
        if len(expected) != len(replacement) or original[where:where+len(expected)] != expected:
            raise ValueError(f'Unexpected static patch at {rva:#x}')
        data[where:where+len(expected)] = replacement
        extra_ranges.update(range(where,where+len(expected)))
    check_at = pe.optional + 64
    struct.pack_into('<I', data, check_at, 0)
    struct.pack_into('<I', data, check_at, checksum(data, check_at))
    # Existing sections, import table, relocation table and optional flags stay intact.
    allowed = set(range(next_header, next_header + 80)) | set(range(at, at + 5)) | extra_ranges
    for start, size in [(pe.pe + 6, 2), (pe.optional + 4, 4),
                        (pe.optional + 12, 4), (pe.optional + 56, 4), (check_at, 4)]:
        allowed.update(range(start, start + size))
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(original, data))):
        raise AssertionError('Unexpected modification outside patch/header locations')
    PE(data).validate_image_layout()
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    parser.add_argument('output_directory', type=Path)
    parser.add_argument('--telemetry-default', action='store_true',
                        help='Diagnostic variant: preserve the original telemetry settings and code')
    args = parser.parse_args()
    output = args.output_directory / 'AoW3_Debug.exe'
    if output.resolve() == args.original.resolve() or output.exists():
        parser.error('Choose a new output directory; existing executable files are never overwritten.')
    original = args.original.read_bytes()
    if sha(original) != SOURCE_SHA256:
        parser.error('Unsupported input SHA-256; no files were modified.')
    payload, symbols = make_payload()
    modified = patch(original, payload, symbols, disable_telemetry=not args.telemetry_default)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(modified)
    (args.output_directory / 'rename-payload.bin').write_bytes(payload)
    manifest = dict(version='0.7.2', status='preview tooltip health matches result bar; new tooltip fix awaits in-game confirmation',
                    original_sha256=sha(original), patched_sha256=sha(modified),
                    payload_sha256=sha(payload), payload_size=len(payload),
                    hook_rva=HOOK_RVA, retry_hook_rvas=[h[0] for h in RETRY_HOOKS],
                    telemetry_disabled=not args.telemetry_default,
                    telemetry_hook_rvas=[] if args.telemetry_default else [h[0] for h in TELEMETRY_HOOKS],
                    native_hook_rvas=[h[0] for h in NATIVE_HOOKS],
                    click_rename_hook_rvas=[h[0] for h in CLICK_RENAME_HOOKS],
                    rename_state_rva=STATE_RVA+0x40,
                    report_guard_rva=STATE_RVA+0x80,
                    telemetry_log_patch_rva=None if args.telemetry_default else STATIC_PATCHES[0][0],
                    new_section_rva=CODE_RVA, writable_state_rva=STATE_RVA, symbols=symbols)
    (args.output_directory / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'symbols'}, indent=2))


if __name__ == '__main__':
    main()
