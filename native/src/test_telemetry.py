"""Exercise native telemetry entry hooks and the existing status-log branch.

Runs x86 instructions at relocated image bases. No real game or network is
started. The native disabled-submit path supplies the return-value baseline.
"""
import json
import struct
import unittest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
from test_patch import loaded_image, PEFILE, ROOT

STOP=0x50001000
DATA=0x30000000
STACK=0x70010000
ERROR=0x80004005
BASES=(0x400000,0x10000000,0x80000000)
SYMS=json.loads((ROOT/'game/build-manifest.json').read_text())['symbols']

def machine(base):
    u=Uc(UC_ARCH_X86,UC_MODE_32)
    u.mem_map(base,PEFILE.u32(PEFILE.optional+56))
    u.mem_write(base,loaded_image(base))
    u.mem_map(DATA,0x20000)
    u.mem_map(STACK-0x10000,0x20000)
    u.mem_map(STOP&~0xfff,0x1000)
    u.mem_map(0,0x1000)
    return u

def put(u,at,value):u.mem_write(at,struct.pack('<I',value&0xffffffff))
def get(u,at):return struct.unpack('<I',u.mem_read(at,4))[0]

class TelemetryTests(unittest.TestCase):
    def test_initialization_and_submission_stay_disabled(self):
        for base in BASES:
            for entry in (0x357000,0x3575d0):
                for active in (0,1):
                    with self.subTest(base=hex(base),entry=hex(entry),active=active):
                        u=machine(base)
                        before=bytearray(b'\xa5'*0x1f4);before[8]=active
                        u.mem_write(DATA,bytes(before))
                        regs={UC_X86_REG_EBX:0x11111111,UC_X86_REG_ESI:0x22222222,
                              UC_X86_REG_EDI:0x33333333,UC_X86_REG_EBP:0x44444444,
                              UC_X86_REG_ECX:DATA,UC_X86_REG_EDX:0x55555555}
                        for r,v in regs.items():u.reg_write(r,v)
                        u.reg_write(UC_X86_REG_ESP,STACK)
                        put(u,STACK,STOP);put(u,STACK+4,0);put(u,0,0xdeadbeef)
                        seen=[]
                        def hook(u,a,size,_):
                            seen.append(a)
                            if a==STOP:u.emu_stop();return
                            self.assertTrue(a==base+entry or
                                base+SYMS['telemetry_disabled']<=a<base+SYMS['telemetry_disabled']+12,
                                'Telemetry hook entered another game/API routine')
                        u.hook_add(UC_HOOK_CODE,hook)
                        u.emu_start(base+entry,0,count=100)
                        self.assertEqual(seen[-1],STOP)
                        self.assertEqual(u.reg_read(UC_X86_REG_EAX),ERROR)
                        self.assertEqual(u.reg_read(UC_X86_REG_ESP),STACK+8)
                        self.assertEqual(get(u,0),0xdeadbeef)
                        for r,v in regs.items():self.assertEqual(u.reg_read(r),v)
                        before[8]=0
                        self.assertEqual(bytes(u.mem_read(DATA,len(before))),bytes(before))

    def test_disabled_status_matches_original_submit_path(self):
        for base in BASES:
            u=machine(base)
            # Restore only this original entry; execute its disabled branch.
            u.mem_write(base+0x3575d0,bytes.fromhex('55 8b ec 6a ff'))
            u.reg_write(UC_X86_REG_ECX,DATA)
            u.reg_write(UC_X86_REG_ESP,STACK)
            put(u,STACK,STOP);put(u,STACK+4,0);put(u,0,0xdeadbeef)
            stopped=[]
            def hook(u,a,size,_):
                if a==STOP:stopped.append(True);u.emu_stop()
            u.hook_add(UC_HOOK_CODE,hook)
            u.emu_start(base+0x3575d0,0,count=100)
            self.assertTrue(stopped)
            self.assertEqual(u.reg_read(UC_X86_REG_EAX),ERROR)
            self.assertEqual(u.reg_read(UC_X86_REG_ESP),STACK+8)
            self.assertEqual(get(u,0),0xdeadbeef)

    def test_startup_log_reports_disabled_for_all_settings(self):
        for base in BASES:
            for endpoint_empty in (0,1):
                for identity in (42,0xffffffff):
                    for opted_in in (0,1):
                        u=machine(base)
                        put(u,DATA+0xeaa4,DATA+0x10000)
                        put(u,DATA+0x10000+0x4c,identity)
                        put(u,STACK+8,DATA+0x11000)
                        u.mem_write(DATA+0x11000+0x3c,bytes([opted_in]))
                        for r,v in [(UC_X86_REG_ESI,DATA),(UC_X86_REG_EBX,0),
                                    (UC_X86_REG_EBP,STACK),(UC_X86_REG_ESP,STACK-0x200)]:
                            u.reg_write(r,v)
                        logged=[];stopped=[]
                        def hook(u,a,size,_):
                            sp=u.reg_read(UC_X86_REG_ESP)
                            if a==base+0x114410:
                                u.reg_write(UC_X86_REG_EAX,endpoint_empty)
                                u.reg_write(UC_X86_REG_EIP,get(u,sp))
                                u.reg_write(UC_X86_REG_ESP,sp+4)
                            elif a==base+0x11aa30:
                                self.assertEqual(get(u,sp+4),base+0xa9081c)
                                logged.append(get(u,sp+8))
                                u.reg_write(UC_X86_REG_EIP,get(u,sp))
                                u.reg_write(UC_X86_REG_ESP,sp+4)
                            elif a==base+0x074f6f:
                                stopped.append(True);u.emu_stop()
                        u.hook_add(UC_HOOK_CODE,hook)
                        u.emu_start(base+0x074f32,0,count=100)
                        self.assertTrue(stopped)
                        self.assertEqual(logged,[base+0xbf40ec])
                        self.assertEqual(u.reg_read(UC_X86_REG_ESP),STACK-0x200)

if __name__=='__main__':unittest.main(verbosity=2)
