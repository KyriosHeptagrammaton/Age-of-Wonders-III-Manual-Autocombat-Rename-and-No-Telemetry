"""Instruction-level checks, NOT a substitute for testing inside AoW3.

Requires Unicorn 2.1.4. Runs the actual patched x86 entry and the supplied
game's indexed army lookup, string assignment, capacity-growth and
display-name machine code. Individual detail selection is null by default.
The allocator, memcpy, message box, action permission, IsOfType and window
closure are simulated. No game session, UI, serializer or mod is loaded.
"""
import functools
import json
from pathlib import Path
import struct
import sys
import unittest

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
from pe import PE, checksum
from build import HOOK_RVA, CODE_RVA, SYMBOLS, DISPLACED, SOURCE_SHA256, make_payload, patch, sha

ROOT = Path(__file__).resolve().parents[1]
GAME = (ROOT / 'game/AoW3_Debug.exe').read_bytes()
PEFILE = PE(GAME)
OBJECTS = 0x30000000
STACK = 0x70010000
STOP = 0x50001000
MESSAGE = STOP + 0x100
TYPE_CHECK = STOP + 0x200


@functools.lru_cache(None)
def loaded_image(base):
    memory = bytearray(PEFILE.u32(PEFILE.optional + 56))
    headers = PEFILE.u32(PEFILE.optional + 60)
    memory[:headers] = GAME[:headers]
    for s in PEFILE.sections:
        memory[s['rva']:s['rva'] + s['size']] = GAME[s['raw']:s['raw'] + s['size']]
    delta = base - PEFILE.base
    if delta:
        rel_rva, length = struct.unpack_from('<II', GAME, PEFILE.optional + 136)
        at, end = rel_rva, rel_rva + length
        while at < end:
            page, size = struct.unpack_from('<II', memory, at)
            assert size >= 8 and at + size <= end
            for entry_at in range(at + 8, at + size, 2):
                entry = struct.unpack_from('<H', memory, entry_at)[0]
                kind, offset = entry >> 12, entry & 0xfff
                if kind == 0:
                    continue
                assert kind == 3, f'Unexpected relocation type {kind}'
                place = page + offset
                value = struct.unpack_from('<I', memory, place)[0]
                struct.pack_into('<I', memory, place, (value + delta) & 0xffffffff)
            at += size
    return bytes(memory)


class Machine:
    def __init__(self, base, connection=0, selected=True, permitted=True,
                 strategic=True, unit_type=True, capacity=0, hud=True, player=True,
                 stack_type=True, unit_count=6):
        self.base, self.permitted, self.unit_type = base, permitted, unit_type
        self.stack_type = stack_type
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        self.u.mem_map(base, PEFILE.u32(PEFILE.optional + 56))
        self.u.mem_write(base, loaded_image(base))
        self.u.mem_map(OBJECTS, 0x100000)
        self.u.mem_map(STACK - 0x10000, 0x20000)
        self.u.mem_map(STOP & ~0xfff, 0x1000)
        self.state = OBJECTS
        self.controller, self.hud = OBJECTS + 0x100, OBJECTS + 0x200
        self.player, self.manager = OBJECTS + 0x1000, OBJECTS + 0x2000
        self.army = OBJECTS + 0x3000
        self.units = [OBJECTS + 0x30000 + i * 0x1000 for i in range(unit_count)]
        self.unit = self.units[0] if self.units else OBJECTS + 0x30000
        self.data = self.unit + 0x230
        self.input, self.input_text = OBJECTS + 0x5000, OBJECTS + 0x5100
        self.output = OBJECTS + 0x6000
        self.next_alloc = OBJECTS + 0x10000
        self.allocations = {}
        self.messages, self.closed, self.assignments, self.lookups = [], [], [], []
        self.stopped = None
        self.p(self.state + 12, self.controller)
        self.p(self.controller + 0x34, self.hud if hud else 0)
        self.p(self.hud + 8, self.player if player else 0)
        self.p(self.player, OBJECTS + 0x7000)
        self.p(OBJECTS + 0x7000 + 0x108, base + SYMBOLS['strategic_cheats'] + (0 if strategic else 16))
        self.p(self.player + 0xf8, self.manager)
        self.p(self.manager + 0x50, connection)
        self.p(self.player + 0x35c, 0)  # closed individual unit-details panel
        self.p(self.player + 0x238, self.army if selected else 0)
        self.p(self.army, OBJECTS + 0x8200)
        self.p(OBJECTS + 0x8200 + 0x24, TYPE_CHECK)
        self.p(self.army + 0x250, OBJECTS + 0x9000)
        self.p(self.army + 0x254, unit_count)
        self.p(OBJECTS + 0x8000 + 0x24, TYPE_CHECK)
        self.p(self.input + 8, self.input_text)
        self.p(self.input + 12, 512)
        for i, unit in enumerate(self.units):
            self.p(unit, OBJECTS + 0x8000)
            ref = OBJECTS + 0xa000 + i * 0x20
            self.p(OBJECTS + 0x9000 + i * 8 + 4, ref)
            self.p(ref + 12, unit)
            data = unit + 0x230
            # Localized first/last names exercise clearing old tags and text.
            for offset, text in [(0x314, 'OLD_FIRST_TAG'), (0x370, 'OLD_LAST_TAG')]:
                buf = self.alloc(32)
                self.u.mem_write(buf, text.encode() + b'\0')
                self.p(data + offset, buf)
                self.p(data + offset + 4, 31)
            for offset, text in [(0x320, 'Original'), (0x37c, 'Surname')]:
                if capacity:
                    buf = self.alloc((capacity + 1) * 2)
                    self.u.mem_write(buf, text[:capacity].encode('utf-16le') + b'\0\0')
                    self.p(data + offset + 8, buf)
                    self.p(data + offset + 12, capacity)
        self.p(base + SYMBOLS['message_box_iat'], MESSAGE)
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def p(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value))

    def d(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def alloc(self, size):
        ptr = self.next_alloc
        self.next_alloc += (size + 15) & ~15
        assert self.next_alloc < OBJECTS + 0x20000
        self.allocations[ptr] = size
        return ptr

    def wide(self, obj):
        if not self.d(obj + 12):
            return ''
        ptr = self.d(obj + 8)
        raw = bytearray()
        while (ch := bytes(self.u.mem_read(ptr + len(raw), 2))) != b'\0\0':
            raw.extend(ch)
            assert len(raw) < 2048
        return raw.decode('utf-16le')

    def narrow(self, ptr):
        raw = bytearray()
        while (ch := bytes(self.u.mem_read(ptr + len(raw), 1))) != b'\0':
            raw.extend(ch)
            assert len(raw) < 2048
        return raw.decode('ascii')

    def ret(self, pop=0, result=0):
        sp = self.u.reg_read(UC_X86_REG_ESP)
        target = self.d(sp)
        self.u.reg_write(UC_X86_REG_ESP, sp + 4 + pop)
        self.u.reg_write(UC_X86_REG_EAX, result)
        self.u.reg_write(UC_X86_REG_ECX, 0x11112222)  # volatile-register clobber
        self.u.reg_write(UC_X86_REG_EDX, 0x33334444)
        self.u.reg_write(UC_X86_REG_EIP, target)

    def hook(self, uc, address, size, _):
        sp = uc.reg_read(UC_X86_REG_ESP)
        this = uc.reg_read(UC_X86_REG_ECX)
        rva = address - self.base
        if address == STOP or rva == SYMBOLS['original_resume']:
            self.stopped = 'return' if address == STOP else 'passthrough'
            uc.emu_stop()
        elif rva == SYMBOLS['can_generate_actions']:
            assert this == self.player
            self.ret(result=int(self.permitted))
        elif address == TYPE_CHECK:
            if this == self.army:
                assert self.d(sp + 4) == 0x47142c
                self.ret(4, int(self.stack_type))
            else:
                assert this in self.units and self.d(sp + 4) == 0x471429
                self.ret(4, int(self.unit_type))
        elif rva == SYMBOLS['stack_get_unit']:
            assert this == self.army
            index = self.d(sp + 4)
            assert index < self.d(self.army + 0x254)
            self.lookups.append(index)
            # Execute the actual game's reference lookup instructions.
        elif address == MESSAGE:
            assert self.d(sp + 4) == 0
            self.messages.append(self.narrow(self.d(sp + 8)))
            self.ret(16, 1)
        elif rva == SYMBOLS['close_window']:
            self.closed.append((this, self.d(sp + 4), self.d(sp + 8)))
            self.ret(8)
        elif rva == 0x113ce0:  # game's realloc wrapper (cdecl)
            old, size = self.d(sp + 4), self.d(sp + 8)
            new = self.alloc(size)
            if old:
                self.u.mem_write(new, bytes(self.u.mem_read(old, min(size, self.allocations[old]))))
            self.ret(result=new)
        elif rva == 0x9cf25c:  # imported memcpy thunk (cdecl)
            dst, src, size = [self.d(sp + i) for i in (4, 8, 12)]
            self.u.mem_write(dst, bytes(self.u.mem_read(src, size)))
            self.ret(result=dst)
        elif rva in (SYMBOLS['assign_narrow'], SYMBOLS['assign_wide']):
            self.assignments.append((rva, this, self.d(sp + 4)))
            # Continue through the ACTUAL engine instructions.

    def command(self, text):
        self.stopped = None
        self.u.mem_write(self.input_text, text.encode('utf-16le') + b'\0\0')
        registers = {UC_X86_REG_EAX: 0x11223344, UC_X86_REG_EBX: 0x12345678,
                     UC_X86_REG_ECX: self.state, UC_X86_REG_EDX: 0x22334455,
                     UC_X86_REG_ESI: 0x34567890, UC_X86_REG_EDI: 0x456789ab,
                     UC_X86_REG_EBP: 0x56789abc, UC_X86_REG_EFLAGS: 0x246}
        for reg, value in registers.items():
            self.u.reg_write(reg, value)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.p(STACK, STOP)
        self.p(STACK + 4, self.input)
        self.u.emu_start(self.base + HOOK_RVA, 0, count=100000)
        assert self.stopped, 'Instruction limit reached'
        if self.stopped == 'return':
            assert self.u.reg_read(UC_X86_REG_ESP) == STACK + 8
        else:
            assert self.u.reg_read(UC_X86_REG_ESP) == STACK - 8
            assert self.u.reg_read(UC_X86_REG_EBP) == STACK - 4
            assert self.d(STACK - 4) == registers[UC_X86_REG_EBP]
            assert self.d(STACK - 8) == 0xffffffff
        for reg, value in registers.items():
            if reg != UC_X86_REG_EBP or self.stopped != 'passthrough':
                assert self.u.reg_read(reg) == value, f'Register {reg} was not preserved'

    def display(self, index=0):
        self.stopped = None
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.p(self.output + 12, 0)  # output scratch object starts empty
        self.u.reg_write(UC_X86_REG_ECX, self.units[index] + 0x230)
        self.p(STACK, STOP)
        self.p(STACK + 4, self.output)
        self.u.emu_start(self.base + 0x7c27c0, 0, count=100000)
        assert self.stopped == 'return'
        assert self.u.reg_read(UC_X86_REG_ESP) == STACK + 8
        return self.wide(self.output)


class PatchTests(unittest.TestCase):
    def test_pe_structure_and_rebuild(self):
        payload, _ = make_payload()
        PEFILE.validate_image_layout()
        section = PEFILE.sections[-2]
        self.assertEqual(section['name'], '.aowname')
        self.assertEqual(GAME[section['raw']:section['raw'] + len(payload)], payload)
        self.assertEqual(PEFILE.u32(section['header'] + 36), 0x60000020)
        state = PEFILE.sections[-1]
        self.assertEqual((state['name'],state['rva'],state['size'],state['virtual_size']),
                         ('.aowdata',0xfc8000,0,0x1000))
        self.assertEqual(PEFILE.u32(state['header']+36),0xc0000080)
        self.assertEqual(PEFILE.u32(PEFILE.optional + 64), checksum(GAME, PEFILE.optional + 64))
        original_path = Path(sys.argv[0]).resolve().parents[2] / 'upload/AoW3_Debug.exe'
        if original_path.exists():
            original = original_path.read_bytes()
            self.assertEqual(sha(original), SOURCE_SHA256)
            self.assertEqual(patch(original, payload), GAME)
            damaged = bytearray(original)
            damaged[-1] ^= 1
            with self.assertRaises(ValueError):
                patch(damaged, payload)
        with self.assertRaises(ValueError):
            patch(GAME, payload)

    def test_success_and_display_under_aslr(self):
        names = ['Mira of the Dawn', 'Éowyn 星の騎士', 'X' * 80, 'A']
        for base in [0x400000, 0x10000000, 0x80000000]:
            for capacity in [0, 4, 100]:
                for name in names:
                    with self.subTest(base=hex(base), capacity=capacity, name=name):
                        m = Machine(base, capacity=capacity)
                        m.command('ReNaMeUnIt   1   ' + name)
                        self.assertEqual(m.wide(m.data + 0x320), name)
                        self.assertEqual(m.wide(m.data + 0x37c), '')
                        self.assertEqual(m.narrow(m.d(m.data + 0x314)), '')
                        self.assertEqual(m.narrow(m.d(m.data + 0x370)), '')
                        self.assertEqual(m.display(), name)
                        self.assertEqual(len(m.messages), 1)
                        self.assertEqual(m.closed, [(m.controller, 0, 1)])

    def test_repeat_rename(self):
        m = Machine(0x10000000)
        for name in ['First Name', 'Second Name with More Letters', '短名']:
            m.command('renameunit 1 ' + name)
            self.assertEqual(m.display(), name)

    def test_original_commands_pass_through(self):
        for text in ['', 'tasman', 'HEIN', 'r', 'rename', 'renameunits Name', 'renameunitX', 'rénámeunit Test']:
            with self.subTest(text=text):
                m = Machine(0x10000000)
                m.command(text)
                self.assertEqual(m.stopped, 'passthrough')
                self.assertEqual(m.messages, [])
                self.assertEqual(m.closed, [])
                self.assertEqual(m.assignments, [])

    def test_bad_names_do_not_write(self):
        for text in ['renameunit', 'renameunit ', 'renameunit    ',
                     'renameunit 1 ' + 'X' * 81, 'renameunit 1 tab\there',
                     'renameunit 1 bad\x7f', 'renameunit 1', 'renameunit 1 ',
                     'renameunit 1    ', 'renameunit Name Without Position']:
            with self.subTest(text=text):
                m = Machine(0x400000, capacity=100)
                m.command(text)
                self.assertEqual(m.stopped, 'return')
                self.assertEqual(m.assignments, [])
                self.assertEqual(m.wide(m.data + 0x320), 'Original')
                self.assertIn('Use 1-80', m.messages[0])

    def test_invalid_contexts_do_not_write(self):
        for setting in [dict(connection=1), dict(connection=2), dict(connection=3),
                        dict(selected=False), dict(permitted=False), dict(strategic=False),
                        dict(unit_type=False), dict(hud=False), dict(player=False),
                        dict(stack_type=False)]:
            with self.subTest(setting=setting):
                m = Machine(0x10000000, capacity=100, **setting)
                m.command('renameunit 1 New Name')
                self.assertEqual(m.assignments, [])
                self.assertEqual(m.wide(m.data + 0x320), 'Original')
                self.assertEqual(len(m.messages), 1)

    def test_each_army_position_with_details_closed(self):
        for slot in range(1, 7):
            with self.subTest(slot=slot):
                m = Machine(0x10000000, capacity=100)
                self.assertEqual(m.d(m.player + 0x35c), 0)
                m.command(f'renameunit {slot} Chosen Unit')
                self.assertEqual(m.lookups, [slot - 1])
                for i, unit in enumerate(m.units):
                    expected = 'Chosen Unit' if i == slot - 1 else 'Original'
                    self.assertEqual(m.wide(unit + 0x230 + 0x320), expected)
                self.assertEqual(m.display(slot - 1), 'Chosen Unit')

    def test_slot_bounds_and_overflow(self):
        for slot in ['0', '-1', '+1', '7', '2147483647', '2147483648',
                     '999999999999999999999999', '1x', '1.0']:
            with self.subTest(slot=slot):
                m = Machine(0x400000, capacity=100)
                m.command(f'renameunit {slot} New Name')
                self.assertEqual(m.assignments, [])
                self.assertEqual(m.lookups, [])
                self.assertEqual(m.wide(m.data + 0x320), 'Original')
                self.assertEqual(len(m.messages), 1)
        m = Machine(0x400000, unit_count=0)
        m.command('renameunit 1 New Name')
        self.assertEqual(m.assignments, [])
        self.assertEqual(m.lookups, [])

    def test_uses_current_army_and_not_old_detail_selection(self):
        m = Machine(0x10000000, capacity=100)
        # Even an unusable old detail pointer must never be read.
        m.p(m.player + 0x35c, 0xffffffff)
        m.command('renameunit 2 Second')
        self.assertEqual(m.display(1), 'Second')
        before = len(m.assignments)
        m.p(m.player + 0x238, 0)  # army no longer selected
        m.command('renameunit 2 Third')
        self.assertEqual(len(m.assignments), before)
        self.assertEqual(m.display(1), 'Second')

    def test_extended_army_and_expired_reference(self):
        m = Machine(0x10000000, capacity=100, unit_count=7)
        m.command('renameunit 7 Seventh')
        self.assertEqual(m.display(6), 'Seventh')
        m = Machine(0x400000, capacity=100)
        m.p(OBJECTS + 0xa000 + 12, 0)  # reference resolves to no live unit
        m.command('renameunit 1 New Name')
        self.assertEqual(m.assignments, [])
        self.assertEqual(len(m.messages), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
