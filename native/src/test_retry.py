"""Execute patched EnterCloseAC and native SetState in Unicorn.

Constructed game objects and simulated Windows/UI, battle commit, simulation
cleanup, reference release, heap selection and manual loading. Does NOT run
a battle, a game save, resource loading, real windows, or mod scripts.
"""
import json
import struct
import unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
from test_patch import loaded_image, PEFILE, GAME, ROOT, Machine

MANIFEST=json.loads((ROOT/'game/build-manifest.json').read_text())
SYMS=MANIFEST['symbols']
STACK=0x70010000
STOP=0x50001000
MODULE=STOP+0x100
PROC=STOP+0x110
DIALOG=STOP+0x120
DEACTIVATE=STOP+0x130
DEINIT=STOP+0x140
TYPE=STOP+0x150

class CombatMachine:
    def __init__(self,base=0x400000,answer=4,active=True,connection=0,
                 controller=0,local=1,stacks=1,participant=1,auto=1,replay=0,
                 own_dead=2,other_dead=1,alive=5,won=True,api=True):
        self.base,self.answer,self.api=base,answer,api
        self.u=Uc(UC_ARCH_X86,UC_MODE_32)
        self.u.mem_map(base,PEFILE.u32(PEFILE.optional+56))
        self.u.mem_write(base,loaded_image(base))
        self.u.mem_map(0,0x1000) # emulated TEB/FS exception-chain head
        self.u.mem_map(0x30000000,0x200000)
        self.u.mem_map(STACK-0x10000,0x20000)
        self.u.mem_map(STOP&~0xfff,0x1000)
        self.manager=0x30000000
        self.hex=0x30010000
        self.world=0x30020000
        self.players=0x30030000
        self.setup=0x30040000
        self.sp=0x30041000
        self.sim=0x30050000
        self.auto_world=0x30060000
        self.tactical=0x30070000
        self.results=0x30080000
        self.rp=0x30081000
        self.command=0x30090000
        self.p(0,0xdeadbeef)
        self.p(self.manager+8,5)
        self.p(self.manager+0xbc,self.hex)
        self.p(self.manager+0xb0,self.setup)
        self.p(self.manager+0x10c,self.setup)
        self.p(self.manager+0xa0,self.sim)
        self.p(self.manager+0x98,self.command)
        self.b(self.hex+0x2cdc,8 if active else 0)
        self.b(self.hex+0x3c,2)
        self.p(self.hex+0x28,self.world)
        self.p(self.world+0x4f0,self.players)
        self.p(self.world+0x42c,0x300a0000)
        self.p(self.players+0x50,connection)
        self.b(self.setup+0x0c,auto)
        self.p(self.setup+8,0x12345678)
        self.p(self.setup+0x190,replay)
        self.p(self.setup+0x1c,self.setup+0x300)
        self.p(self.setup+0x20,1)
        self.p(self.setup+0x304,self.sp)
        self.b(self.sp+0x4c,2)
        self.p(self.sp+0x78,controller)
        self.b(self.sp+0x181,local)
        self.p(self.sp+0x24,stacks)
        # x=1 catches accidental reuse of attack-position x as retry flag.
        for offset,value in [(0x54,1),(0x58,27),(0x5c,0)]: self.p(self.setup+offset,value)
        self.p(self.sim+0x188,self.auto_world)
        self.p(self.auto_world+0x34fc,self.tactical)
        self.p(self.tactical+0x2e48,self.results)
        self.p(self.sim,self.sim+0x200)
        self.p(self.sim+0x200+0x40,DEACTIVATE)
        self.p(self.sim+0x200+0x38,DEINIT)
        self.p(self.results+0x4c,self.results+0x300)
        self.p(self.results+0x50,1)
        self.p(self.results+0x304,self.rp)
        self.b(self.rp+8,2)
        self.b(self.rp+0x28,int(won))
        self.b(self.rp+0x2a,participant)
        self.p(self.results+0x3c,own_dead+other_dead)
        self.p(self.results+0x38,self.results+0x400)
        self.p(self.results+0x28,alive)
        self.p(self.results+0x24,self.results+0x500)
        self.names={}
        self.entities={}
        self.next_alloc=0x30100000
        self.allocations={}
        for i in range(own_dead+other_dead):
            r=0x300b0000+i*0x1000
            unit=0x300d0000+i*0x1000
            self.p(self.results+0x404+i*8,r)
            self.p(r+0x3d8,100+i)
            self.entities[100+i]=unit
            self.p(unit,unit+0x100)
            self.p(unit+0x100+0x24,TYPE)
            self.b(unit+0x60c,2 if i<own_dead else 7)
            name=['Dawnwatch Veterans','Éowyn 星の騎士'][i%2]
            self.names[unit]=name
            data=unit+0x230
            # Serializer saver fields -> wide string, as in rename tests.
            buf=self.alloc((len(name)+1)*2)
            self.u.mem_write(buf,name.encode('utf-16le')+b'\0\0')
            self.p(data+0x320+8,buf)
            self.p(data+0x320+12,len(name))
        self.initial_allocs=set(self.allocations)
        self.p(base+0xa8e020,MODULE)
        self.p(base+0xa8e028,PROC)
        self.events=[]
        self.messages=[]
        self.current_heap=0x300f0000
        self.stopped=False
        self.u.hook_add(UC_HOOK_CODE,self.hook)

    def p(self,a,v): self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
    def b(self,a,v): self.u.mem_write(a,bytes([v]))
    def d(self,a): return struct.unpack('<I',self.u.mem_read(a,4))[0]
    def alloc(self,size):
        at=self.next_alloc; self.next_alloc+=(size+15)&~15
        self.allocations[at]=size
        assert self.next_alloc<0x30200000
        return at
    def ret(self,pop=0,result=0):
        sp=self.u.reg_read(UC_X86_REG_ESP)
        target=self.d(sp)
        self.u.reg_write(UC_X86_REG_ESP,sp+4+pop)
        self.u.reg_write(UC_X86_REG_EAX,result)
        self.u.reg_write(UC_X86_REG_EIP,target)
    def narrow(self,a):
        raw=bytearray()
        while (c:=bytes(self.u.mem_read(a+len(raw),1)))!=b'\0': raw+=c
        return raw.decode()
    def wide(self,a):
        raw=bytearray()
        while (c:=bytes(self.u.mem_read(a+len(raw),2)))!=b'\0\0':
            raw+=c; assert len(raw)<3000
        return raw.decode('utf-16le')

    def hook(self,u,a,size,_):
        sp=u.reg_read(UC_X86_REG_ESP);this=u.reg_read(UC_X86_REG_ECX)
        r=a-self.base
        if a==STOP:
            self.stopped=True;u.emu_stop()
        elif a==MODULE:
            assert self.narrow(self.d(sp+4))=='user32.dll'
            self.ret(4,0x50002000)
        elif a==PROC:
            assert self.d(sp+4)==0x50002000
            assert self.narrow(self.d(sp+8))=='MessageBoxW'
            self.ret(8,DIALOG if self.api else 0)
        elif a==DIALOG:
            assert self.d(sp+16)==0x12125
            assert self.d(self.manager+8)==5
            self.messages.append(self.wide(self.d(sp+8)))
            self.events.append('preview')
            self.ret(16,self.answer)
        elif r==0x2eed60:
            assert this==self.world+0x32c4
            self.ret(4,self.entities.get(self.d(sp+4),0))
        elif a==TYPE:
            assert self.d(sp+4)==0x471429
            self.ret(4,1)
        elif r==0x113ce0:
            old,n=self.d(sp+4),self.d(sp+8)
            if n:
                new=self.alloc(n)
                if old: self.u.mem_write(new,bytes(self.u.mem_read(old,min(n,self.allocations[old]))))
            else: new=0
            if old: del self.allocations[old]
            self.ret(result=new)
        elif r==0x1137b0:
            del self.allocations[self.d(sp+4)]
            self.ret()
        elif r==0x9cf25c:
            dst,src,n=[self.d(sp+i) for i in (4,8,12)]
            self.u.mem_write(dst,bytes(self.u.mem_read(src,n)))
            self.ret(result=dst)
        elif r==0x801080:
            assert this==self.world
            self.events.append('notify-result' if self.d(sp+4) else 'hide-indicator')
            self.ret(8)
        elif r==0x6d8ad0:
            assert this==self.manager and self.d(sp+4)==self.results
            self.events.append('commit')
            self.ret(4)
        elif a in (DEACTIVATE,DEINIT):
            assert this==self.sim
            self.events.append('deactivate' if a==DEACTIVATE else 'deinitialize')
            self.ret()
        elif r==0x2c3a50:
            assert this==self.sim
            self.events.append('shutdown'); self.ret()
        elif r==0x112920:
            self.ret(result=self.current_heap)
        elif r==0x1128c0:
            self.current_heap=self.d(sp+4); self.ret()
        elif r==0x068b70:
            assert this in (self.sim,self.setup,self.command)
            self.events.append({self.sim:'release-sim',self.setup:'release-setup',self.command:'release-command'}[this])
            self.ret()
        elif r==0x112e80:
            assert this==self.manager+0x10
            self.events.append('clear-heap');self.ret()
        elif r==0x6dd930:
            # We reach the real native manual entry from the REAL SetState.
            assert this==self.manager and self.d(this+8)==1
            assert self.d(this+0xa0)==0 and self.d(this+0x98)==0
            assert self.d(this+0xb0)==self.setup
            assert self.d(this+0x10c)==self.setup
            assert bytes(u.mem_read(self.setup+0x0c,1))==b'\0'
            self.events.append('open-manual')
            self.p(this+8,2)
            self.ret()
        elif r==0x6c6e20:
            raise AssertionError('Autocombat must never reopen from the retry dialog')

    def run(self):
        regs={UC_X86_REG_EBX:0x12345678,UC_X86_REG_ESI:0x23456789,
              UC_X86_REG_EDI:0x34567890,UC_X86_REG_EBP:0x456789ab}
        for r,v in regs.items(): self.u.reg_write(r,v)
        self.u.reg_write(UC_X86_REG_ECX,self.manager)
        self.u.reg_write(UC_X86_REG_ESP,STACK)
        self.p(STACK,STOP)
        self.u.emu_start(self.base+0x6dc210,0,count=500000)
        assert self.stopped,'Instruction limit reached'
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK+4
        assert self.d(0)==0xdeadbeef, 'Native SEH chain not restored'
        for r,v in regs.items(): assert self.u.reg_read(r)==v,'Callee-saved register changed'
        assert self.current_heap==0x300f0000,'Heap selection not restored'
        assert set(self.allocations)==self.initial_allocs,'Preview leaked a name buffer'
        return self.events

class RetryTests(unittest.TestCase):
    def test_retry_cleanup_and_no_commit_under_aslr(self):
        for base in (0x400000,0x10000000,0x80000000):
            with self.subTest(base=hex(base)):
                m=CombatMachine(base)
                self.assertEqual(m.run(),['preview','hide-indicator','deactivate',
                    'deinitialize','shutdown','release-sim','release-command','clear-heap','open-manual'])
                self.assertEqual(m.d(m.manager+8),2)
                text=m.messages[0]
                self.assertIn('VICTORY',text)
                self.assertIn('report: 2',text)
                self.assertIn('Dawnwatch Veterans',text)
                self.assertIn('Éowyn 星の騎士',text)
    def test_accept_applies_once_and_preserves_original_cleanup(self):
        for base in (0x400000,0x10000000,0x80000000):
            for answer in (2,0):
                m=CombatMachine(base,answer=answer,won=False)
                self.assertEqual(m.run(),['preview','notify-result','commit','deactivate',
                    'deinitialize','shutdown','release-sim','release-command','clear-heap','release-setup'])
                self.assertEqual(m.d(m.manager+8),0)
                self.assertEqual(m.d(m.manager+0xb0),0)
                self.assertIn('NO VICTORY',m.messages[0])
    def test_manual_retry_preserves_battle_seed(self):
        for base in (0x400000,0x10000000,0x80000000):
            for seed in (0,0x12345678,0xffffffff):
                m=CombatMachine(base,answer=4)
                m.p(m.setup+8,seed)
                self.assertEqual(m.run(),['preview','hide-indicator','deactivate',
                    'deinitialize','shutdown','release-sim','release-command','clear-heap','open-manual'])
                self.assertEqual(m.d(m.setup+8),seed)
                self.assertEqual(m.d(m.manager+8),2)
    def test_only_retry_button_can_request_manual_combat(self):
        for base in (0x400000,0x10000000,0x80000000):
            for answer in range(12):
                with self.subTest(base=hex(base),answer=answer):
                    m=CombatMachine(base,answer=answer)
                    m.run()
                    self.assertEqual(m.events.count('open-manual'),int(answer==4))
                    self.assertEqual(m.events.count('commit'),int(answer!=4))
                    self.assertEqual(m.d(m.setup+8),0x12345678)
                    self.assertIn('RETRY = discard this result and FIGHT MANUALLY',m.messages[0])
                    self.assertNotIn('AUTO-RESOLVE AGAIN',m.messages[0])
                    self.assertNotIn('new seed',m.messages[0])
    def test_ineligible_battles_use_original_flow(self):
        for args in ({'connection':1},{'connection':2},{'controller':1},{'local':0},
                     {'stacks':0},{'participant':0},{'auto':0},{'replay':1},{'api':False}):
            with self.subTest(args=args):
                m=CombatMachine(**args); events=m.run()
                self.assertFalse(m.messages)
                self.assertEqual(events.count('commit'),1)
                self.assertNotIn('open-manual',events)
    def test_inactive_world_cleanup_without_commit_or_prompt(self):
        m=CombatMachine(active=False)
        self.assertEqual(m.run(),['deactivate','deinitialize','shutdown',
            'release-sim','release-command','clear-heap','release-setup'])
    def test_no_casualties_and_truncated_list(self):
        for count in (0,10):
            m=CombatMachine(own_dead=count)
            m.run();text=m.messages[0]
            self.assertIn(f'report: {count}',text)
            self.assertLess(len(text),1400)
            if count==10: self.assertIn('plus 2 more',text)
    def test_missing_personal_name_uses_engine_fallback(self):
        m=CombatMachine(own_dead=1,other_dead=0)
        unit=m.entities[100]
        # No personal name or active resource: execute the native fallback.
        m.p(unit+0x230+0x320+12,0)
        m.run()
        self.assertIn('Your reported casualties:',m.messages[0])
        self.assertNotIn('Dawnwatch Veterans',m.messages[0])
    def test_fallback_counts_ordinary_deaths_and_resurrection_candidates(self):
        for ordinary in (1,2):
            m=CombatMachine(own_dead=1,other_dead=1,alive=3)
            m.p(m.results+0x14,ordinary)
            m.p(m.results+0x18,m.results+0x600)
            m.p(m.results+0x600,100)
            if ordinary==2:m.p(m.results+0x604,101)
            else:m.p(m.results+0x404,m.d(m.results+0x40c))
            m.p(m.results+0x3c,2-ordinary)
            m.run();text=m.messages[0]
            self.assertIn('Your units in the dead-unit report: 1',text)
            self.assertIn('All sides: 2 reported dead, 3 reported surviving.',text)
            self.assertIn('Dawnwatch Veterans',text)
            self.assertEqual(m.events.count('open-manual'),1)

    def test_invalid_ordinary_death_list_does_not_enter_preview(self):
        for count,buffer in ((16385,0x30080600),(1,0)):
            m=CombatMachine();m.p(m.results+0x14,count);m.p(m.results+0x18,buffer)
            m.run()
            self.assertFalse(m.messages)
            self.assertEqual(m.events.count('commit'),1)
    def test_native_frame_and_exception_handler_unchanged(self):
        original_path=ROOT.parent/'upload/AoW3_Debug.exe'
        if not original_path.exists():
            self.skipTest('Original executable is needed for native-frame byte comparison')
        original=original_path.read_bytes()
        from pe import PE
        p=PE(original)
        for lo,hi in ((0x6dc210,0x6dc238),(0xa46170,0xa461a3)):
            self.assertEqual(original[p.raw(lo):p.raw(hi)],GAME[PEFILE.raw(lo):PEFILE.raw(hi)])
    def test_rename_payload_unchanged(self):
        previous=ROOT.parent/'analysis/rename-v0.2-game/rename-payload.bin'
        if previous.exists():
            old=previous.read_bytes()
            self.assertEqual((ROOT/'game/rename-payload.bin').read_bytes()[:len(old)],old)

if __name__=='__main__': unittest.main(verbosity=2)
