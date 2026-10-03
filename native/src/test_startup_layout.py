"""PE packaging regression for the v0.6 startup failure.

No Windows loader or game is run. These checks catch the concrete section
layout defect missed by instruction-only tests, and prove the diagnostic
variant restores just the three telemetry edits relative to the fixed EXE.
"""
from pathlib import Path
import struct
import unittest
from pe import PE, checksum
from build import CODE_RVA, STATE_RVA, TELEMETRY_HOOKS, STATIC_PATCHES

ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'game/AoW3_Debug.exe').read_bytes()
ALT=(ROOT/'telemetry-default/AoW3_Debug.exe').read_bytes()

class StartupLayoutTests(unittest.TestCase):
    def test_both_variants_have_adjacent_sections_and_correct_checksum(self):
        for data in (MAIN,ALT):
            p=PE(data)
            p.validate_image_layout()
            self.assertEqual(p.u32(p.optional+64),checksum(data,p.optional+64))
            code,state=p.sections[-2:]
            self.assertEqual(code['rva'],CODE_RVA)
            self.assertEqual(code['virtual_size'],STATE_RVA-CODE_RVA)
            self.assertEqual(code['rva']+code['virtual_size'],state['rva'])
            self.assertEqual(p.u32(code['header']+36),0x60000020)
            self.assertEqual(p.u32(state['header']+36),0xc0000080)

    def test_original_and_pre_native_patch_layouts_remain_valid(self):
        paths=[ROOT.parent/'upload/AoW3_Debug.exe',
               ROOT.parent/'analysis/retry-v0.4-released-game/AoW3_Debug.exe']
        found=False
        for path in paths:
            if path.exists():
                found=True
                PE(path.read_bytes()).validate_image_layout()
        if not found:self.skipTest('Original/previous executable not available')

    def test_v06_gap_is_rejected(self):
        p=PE(MAIN);bad=bytearray(MAIN)
        code=p.sections[-2]
        payload=(ROOT/'game/rename-payload.bin').read_bytes()
        struct.pack_into('<I',bad,code['header']+8,len(payload))
        with self.assertRaisesRegex(ValueError,'Non-adjacent image section .aowdata'):
            PE(bad).validate_image_layout()

    def test_historical_v061_fix_changes_no_runtime_instructions(self):
        path=ROOT.parent/'analysis/v06-released-checkpoint/game/AoW3_Debug.exe'
        fixed=ROOT.parent/'analysis/v061-released-checkpoint/game/AoW3_Debug.exe'
        if not path.exists() or not fixed.exists():
            self.skipTest('Released v0.6/v0.6.1 comparison not available')
        main=fixed.read_bytes()
        old=path.read_bytes();p=PE(old)
        self.assertEqual(len(main),len(old))
        allowed=set(range(p.sections[-2]['header']+8,p.sections[-2]['header']+12))
        allowed.update(range(p.optional+64,p.optional+68))
        differences={i for i,(a,b) in enumerate(zip(old,main)) if a!=b}
        self.assertTrue(differences)
        self.assertTrue(differences<=allowed)
        self.assertEqual((fixed.parent/'rename-payload.bin').read_bytes(),
                         (path.parent/'rename-payload.bin').read_bytes())

    def test_telemetry_alternative_restores_only_original_hooks(self):
        p=PE(MAIN);allowed=set(range(p.optional+64,p.optional+68))
        for rva,expected,label,opcode in TELEMETRY_HOOKS:
            at=p.raw(rva)
            self.assertEqual(ALT[at:at+len(expected)],expected)
            allowed.update(range(at,at+len(expected)))
        for rva,expected,replacement in STATIC_PATCHES:
            at=p.raw(rva)
            self.assertEqual(ALT[at:at+len(expected)],expected)
            allowed.update(range(at,at+len(expected)))
        self.assertEqual(len(MAIN),len(ALT))
        self.assertTrue({i for i,(a,b) in enumerate(zip(MAIN,ALT)) if a!=b}<=allowed)
        path=ROOT.parent/'upload/AoW3_Debug.exe'
        if path.exists():
            original=path.read_bytes();o=PE(original)
            for lo,hi in ((0x074f32,0x074f9d),(0x357000,0x357740)):
                self.assertEqual(ALT[p.raw(lo):p.raw(hi)],original[o.raw(lo):o.raw(hi)])

    def test_layout_guard_rejects_invalid_image_size_and_raw_range(self):
        p=PE(MAIN)
        for at,value in ((p.optional+56,p.u32(p.optional+56)+0x1000),
                         (p.sections[-2]['header']+20,len(MAIN)+0x1000)):
            bad=bytearray(MAIN);struct.pack_into('<I',bad,at,value)
            with self.assertRaises(ValueError):PE(bad).validate_image_layout()

if __name__=='__main__':unittest.main(verbosity=2)
