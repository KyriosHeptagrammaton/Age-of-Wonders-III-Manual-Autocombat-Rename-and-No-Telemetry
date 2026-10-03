"""Instruction-level async UI tests using the exact patched game code.

Executes native state transitions, EnterCloseAC, Lua callback wrappers and
hook ABIs. Iggy drawing, helper population and platform/resource services
are simulated. This cannot validate actual Flash rendering or gameplay.
"""
import struct
import unittest
from unicorn.x86_const import *
from test_retry import CombatMachine, SYMS, STACK, STOP

BASES=(0x400000,0x10000000,0x80000000)
HIDE=STOP+0x200
STATE_NOTIFY=STOP+0x210

class NativeMachine(CombatMachine):
    def __init__(self,base=0x400000,**kwargs):
        super().__init__(base,**kwargs)
        self.pending=base+0xfc8000
        self.player=0x300a1000
        self.hp=0x300a2000
        self.hud=0x300a3000
        self.sm=self.hud+0x35c
        self.idle=0x300a4000
        self.modal=0x300a5000
        self.other=0x300a6000
        self.p(self.players+0x14,self.players+0x500)
        self.p(self.players+0x18,1)
        self.p(self.players+0x504,self.player)
        self.p(self.player+0x164,self.hud)
        self.p(self.hud+8,self.player)
        self.b(self.hp+0x28,2)
        self.p(self.hud,self.hud+0x100)
        self.p(self.hud+0x168,HIDE)
        self.p(self.sm,self.hud+0x200)
        self.p(self.hud+0x234,STATE_NOTIFY)
        self.p(self.sm+0x20,self.idle)
        self.p(self.sm+0x34,self.hud)
        for address,identity in ((self.idle,0),(self.modal,2),(self.other,3)):
            self.p(address,address+0x300)
            self.p(address+8,identity)
            self.p(address+12,self.sm)
            self.p(address+0x33c,base+0x642ed0)
            self.p(address+0x340,base+0x642ed0)
        self.p(self.modal+0x33c,base+0x5af570)
        self.p(self.modal+0x340,base+0x54c540)
        self.commands=[]
        self.vars={}
        self.native_killed_ids=[]
        self.stop_at=None
        self.stopped_at=None
        self.unit_mode=False
        self.result_addition=0x300ef000
        self.tier_links={}

    def hook(self,u,a,size,_):
        sp=u.reg_read(UC_X86_REG_ESP);this=u.reg_read(UC_X86_REG_ECX)
        r=a-self.base
        if a==self.stop_at:
            self.stopped_at=a;u.emu_stop();return
        if r==0x5f37e0:
            assert this==self.player
            self.ret(result=self.hp)
        elif r==0x6f4ec0:
            assert this==self.sm+8
            identity=self.d(sp+4)
            assert identity in (0,2)
            self.ret(4,identity)
        elif r==0x6f1dd0:
            assert this==self.sm+8
            self.ret(4,{0:self.idle,2:self.modal}[self.d(sp+4)])
        elif a==STATE_NOTIFY:
            assert this==self.sm
            assert self.d(sp+8)==self.d(self.sm+0x20)
            self.ret(8)
        elif r==0x2c91c0:
            assert this==self.hud and self.d(sp+8)==0
            self.events.append('show:'+self.narrow(self.d(sp+4)))
            self.ret(8)
        elif a==HIDE:
            assert this==self.hud
            self.events.append('hide:'+self.narrow(self.d(sp+4)))
            self.ret(4)
        elif r==0x194ae0:
            self.commands.append(('call',self.narrow(self.d(sp+4))))
            assert self.d(sp+8)==1
            self.ret(8)
        elif r==0x195420:
            self.commands.append(('open',self.narrow(self.d(sp+4))))
            self.ret(4)
        elif r in (0x195640,0x195910,0x1957f0):
            key=self.narrow(self.d(sp+4))
            v=self.d(sp+8)
            if r==0x1957f0:v=self.wide(v)
            self.commands.append(('var',key,v));self.vars[key]=v
            self.ret(8)
        elif r==0x612170:
            c=self.d(sp+4)
            assert self.narrow(self.d(this+8))=='HUD_CombatResults'
            assert self.d(this+0xc)==self.hud
            assert self.d(this+0x34)==self.setup
            assert self.d(self.pending+40)==1 # scoped unit override
            assert self.d(self.manager+0xa0)==self.sim
            self.events.append('engine-panels')
            self.commands.extend([('call','StartUpdate'),('call','EndUpdate')])
            # Give both helper lists and controller data real owned buffers;
            # execute the game's destructors and emulated allocator cleanup.
            for offset in (0x14,0x24):
                buf=self.alloc(16)
                self.p(this+offset+4,buf)
                self.p(this+offset+8,2)
                self.p(this+offset+12,16)
            buf=self.alloc(32)
            self.p(c+8,buf);self.p(c+12,8);self.p(c+16,32)
            self.ret(4)
        elif r==0x5e4c90:
            assert self.narrow(self.d(this+8))=='HUD_CombatResults'
            self.ret(4)
        elif r==0x236a40:
            assert self.d(sp+4)==0x1234 # fake Lua state
            assert self.d(sp+16)==0x4718a7
            self.ret(result=self.modal)
        elif r==0x233690:
            assert self.d(sp+4)==0x1234
            self.ret(result=1)
        elif r==0x2356c0:
            assert self.d(sp+4)==0x1234
            self.ret()
        elif r in (0x7bede0,0x5ec2e0) and self.unit_mode:
            raise AssertionError('Detached-result preview called a live-context API')
        elif r==0x147940 and self.unit_mode:
            # Resource-link resolution is an engine service. Tier lookup,
            # next-medal selection and XP arithmetic execute original code.
            self.ret(result=self.tier_links.get(this,0))
        elif r==0x778a20:
            raise AssertionError('Preview must not cancel the battle request')
        elif r==0x6cb980:
            # Only used when a regression executes the native death-list
            # consumer. Record its IDs without killing any fixture units.
            assert this==self.manager
            self.native_killed_ids.append(self.d(sp+4))
            self.ret(8)
        else:
            super().hook(u,a,size,_)

    def invoke(self,rva,args=(),this=0,callee_pop=0,regs=None,stop=None):
        self.stopped=False;self.stopped_at=None;self.stop_at=stop
        defaults={UC_X86_REG_EBX:0x12345678,UC_X86_REG_ESI:0x23456789,
                  UC_X86_REG_EDI:0x34567890,UC_X86_REG_EBP:0x456789ab}
        if regs:defaults.update(regs)
        for r,v in defaults.items():self.u.reg_write(r,v)
        self.u.reg_write(UC_X86_REG_ECX,this)
        self.u.reg_write(UC_X86_REG_ESP,STACK)
        self.p(STACK,STOP)
        for i,v in enumerate(args):self.p(STACK+4+4*i,v)
        self.u.emu_start(self.base+rva,0,count=500000)
        if stop:
            assert self.stopped_at==stop
        else:
            assert self.stopped,'Instruction limit reached'
            assert self.u.reg_read(UC_X86_REG_ESP)==STACK+4+callee_pop
            for r,v in defaults.items():assert self.u.reg_read(r)==v
        assert self.d(0)==0xdeadbeef
        assert self.current_heap==0x300f0000
        assert set(self.allocations)==self.initial_allocs
        self.stop_at=None

    def ready(self):self.invoke(0x54c8d0,(0x1234,))
    def manual(self):self.invoke(0x54c780,(0x1234,))
    def accept(self):self.invoke(0x54c7b0,(0x1234,))
    def tick(self):
        self.invoke(0x6de7e9,regs={UC_X86_REG_ESI:self.manager-0x2eb0},
                    stop=self.base+0x6de7ef)
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK
        assert self.u.reg_read(UC_X86_REG_ESI)==self.manager-0x2eb0
        assert self.u.reg_read(UC_X86_REG_EAX)==self.d(self.manager+8)


class NativeTests(unittest.TestCase):
    def test_tooltip_health_matches_preview_bar_without_changing_units(self):
        # Execute the real tooltip's HP loads/pushes up to native AddF.
        # The old build supplies 55/60 even when its preview bar says 19/70.
        cases=[('alive',19,70),('dead-id',19,70),('dead-snapshot',19,70),
               ('alive',999,70),('alive',-1,70),('alive',37,0)]
        for base in BASES:
            for kind,hp,maximum in cases:
                with self.subTest(base=base,kind=kind,hp=hp,maximum=maximum):
                    m=NativeMachine(base,own_dead=1,other_dead=0,alive=0);m.run();m.unit_mode=True
                    unit=m.entities[100];data=unit+0x230;r=m.d(m.results+0x404)
                    m.p(unit+0x10,100);m.p(data+0x18,unit);m.p(data+0x28,60);m.p(data+0x1e8,55)
                    m.p(r+0x30,maximum);m.p(r+0x1f0,hp)
                    m.p(m.results+0x3c,int(kind=='dead-snapshot'))
                    if kind=='alive':m.p(m.results+0x28,1);m.p(m.results+0x504,r)
                    if kind=='dead-id':m.p(m.results+0x14,1);m.p(m.results+0x18,m.results+0x600);m.p(m.results+0x600,100)
                    helper=m.result_addition;c=helper+0x100;m.p(helper+12,m.hud);m.p(m.pending+40,1)
                    m.vars.update(unitMaxHp=60,unitCurrHp=55)
                    before=bytes(m.u.mem_read(unit,0x700)),bytes(m.u.mem_read(r,0x400))
                    m.invoke(SYMS['native_unit'],(helper,base,c,unit))
                    expected=(m.vars['unitCurrHp'],m.vars['unitMaxHp'])
                    m.u.reg_write(UC_X86_REG_EFLAGS,0x246)
                    m.invoke(0x60ce77,regs={UC_X86_REG_ESI:data,UC_X86_REG_EDI:c},stop=base+0x13c280)
                    sp=m.u.reg_read(UC_X86_REG_ESP)
                    self.assertEqual((m.d(sp+12),m.d(sp+16)),expected)
                    self.assertEqual(m.d(sp+4),c);self.assertEqual(m.wide(m.d(sp+8)),'%d/%d[hp/]')
                    self.assertEqual(m.u.reg_read(UC_X86_REG_ESI),data);self.assertEqual(m.u.reg_read(UC_X86_REG_EDI),c)
                    self.assertEqual(m.u.reg_read(UC_X86_REG_EFLAGS)&0xcd5,0x246&0xcd5)
                    self.assertEqual((bytes(m.u.mem_read(unit,0x700)),bytes(m.u.mem_read(r,0x400))),before)

    def test_tooltip_health_keeps_unrelated_native_values(self):
        for guard in ('no-preview','not-rendering','unmatched','detached'):
            m=NativeMachine(own_dead=1,other_dead=0,alive=0);m.run()
            unit=m.entities[100];data=unit+0x230;r=m.d(m.results+0x404)
            m.p(unit+0x10,100);m.p(data+0x18,unit);m.p(data+0x28,60);m.p(data+0x1e8,55)
            m.p(r+0x30,70);m.p(r+0x1f0,19);m.p(m.pending+40,1)
            if guard=='no-preview':m.p(m.pending+28,0)
            if guard=='not-rendering':m.p(m.pending+40,0)
            if guard=='unmatched':m.p(unit+0x10,999)
            if guard=='detached':m.p(data+0x18,0)
            m.invoke(0x60ce77,regs={UC_X86_REG_ESI:data},stop=m.base+0x13c280)
            sp=m.u.reg_read(UC_X86_REG_ESP);self.assertEqual((m.d(sp+12),m.d(sp+16)),(55,60))

    def test_pending_keeps_simulation_setup_and_campaign_uncommitted(self):
        for base in BASES:
            m=NativeMachine(base)
            events=m.run()
            self.assertEqual(events,['show:HUD_CombatResults',
                'show:HUD_SkillBook_Vignette','engine-panels','notify-result'])
            self.assertFalse(m.messages)
            for offset,value in ((8,5),(0xa0,m.sim),(0xb0,m.setup),(0x98,m.command)):
                self.assertEqual(m.d(m.manager+offset),value)
            self.assertEqual(m.d(m.pending+28),1)
            self.assertEqual(m.d(m.sm+0x20),m.modal)
            self.assertEqual(m.commands[:3],[('call','BeginRetryPreview'),
                ('call','StartUpdate'),('open','DataObject')])
            for _ in range(8):m.tick()
            self.assertNotIn('commit',m.events)
            self.assertEqual(m.d(m.setup+8),0x12345678)

    def test_manual_uses_original_seed_and_discards_once(self):
        for base in BASES:
            for seed in (0,0x12345678,0xffffffff):
                m=NativeMachine(base);m.p(m.setup+8,seed)
                m.run();m.ready();m.manual();m.manual();m.accept();m.tick();m.tick()
                self.assertEqual(m.events.count('open-manual'),1)
                self.assertNotIn('commit',m.events)
                self.assertEqual(m.events.count('release-sim'),1)
                self.assertEqual(m.d(m.setup+8),seed)
                self.assertEqual(m.d(m.pending+28),0)
                self.assertEqual(m.d(m.sm+0x20),m.idle)

    def test_accept_and_native_close_commit_once(self):
        for base in BASES:
            for close in ('accept','native','retreat'):
                m=NativeMachine(base,won=False);m.run();m.ready()
                self.assertEqual(m.vars['bottomText'],'Defeat')
                if close=='accept':m.accept();m.manual();m.accept()
                elif close=='native':m.invoke(0x138320,(0,1),m.sm,8)
                else:m.invoke(0x54c7e0,(0x1234,))
                m.tick();m.tick()
                self.assertEqual(m.events.count('commit'),1)
                self.assertEqual(m.events.count('release-setup'),1)
                self.assertNotIn('open-manual',m.events)
                self.assertEqual(m.d(m.setup+8),0x12345678)

    def test_missing_or_unresponsive_swf_falls_back_without_reroll(self):
        for base in BASES:
            for answer in (4,2):
                m=NativeMachine(base,answer=answer);m.run()
                # Old SWF has no ready handshake. Hold to timeout, not a commit.
                m.p(m.pending+36,178);m.tick()
                self.assertNotIn('commit',m.events)
                m.tick()
                self.assertEqual(len(m.messages),1)
                self.assertEqual(m.events.count('open-manual'),int(answer==4))
                self.assertEqual(m.events.count('commit'),int(answer!=4))
                self.assertEqual(m.d(m.pending+28),0)

    def test_no_timeout_after_handshake_and_first_choice_wins(self):
        m=NativeMachine();m.run()
        m.manual();m.accept() # callbacks before ready cannot mutate the battle
        self.assertEqual(m.d(m.pending+32),0)
        m.ready();m.p(m.pending+36,0xffffffff);m.tick()
        self.assertFalse(m.messages)
        self.assertEqual(m.d(m.pending+28),2)
        m.accept();m.manual();m.tick()
        self.assertEqual(m.events.count('commit'),1)

    def test_existing_modal_uses_fallback(self):
        m=NativeMachine();m.p(m.sm+0x20,m.other)
        m.run()
        self.assertEqual(len(m.messages),1)
        self.assertNotIn('engine-panels',m.events)
        self.assertEqual(m.d(m.sm+0x20),m.other)

    def test_regular_modal_methods_keep_original_prologues(self):
        for base in BASES:
            for entry,resume,stack_delta in (
                (0x5af570,0x5af576,-4),(0x54c540,0x54c546,-8),
                (0x5adbf0,0x5adbf5,-8),(0x54c5d0,0x54c5d6,-12),
                (0x54c660,0x54c666,-16),(0x6103b0,0x6103b5,-8)):
                m=NativeMachine(base)
                m.invoke(entry,(m.idle,),m.modal,stop=base+resume)
                self.assertEqual(m.u.reg_read(UC_X86_REG_ESP),STACK+stack_delta)
                self.assertEqual(m.u.reg_read(UC_X86_REG_EBP),STACK-4)

    def test_destroyed_manager_clears_pending_state(self):
        for base in BASES:
            m=NativeMachine(base);m.run()
            m.invoke(0x6b3f00,this=m.manager,stop=base+0x6b3f05)
            self.assertEqual(bytes(m.u.mem_read(m.pending,48)),b'\0'*48)

    def test_unit_outcomes_are_read_only_and_preserve_mod_stats(self):
        for base in BASES:
            for dead,hp,maxhp,level,mind,ghoul in (
                (True,25,200,6,False,False),
                (False,88,150,9,True,True),
                (False,-4,250,3,False,False),
                (False,999,180,3,False,False)):
                m=NativeMachine(base,own_dead=1,other_dead=0,alive=0)
                m.run();m.unit_mode=True
                m.vars.update(ghoul=int(ghoul),xp='pre-battle tooltip')
                m.commands.clear()
                unit=m.entities[100];r=m.d(m.results+0x404)
                m.p(unit+0x10,100);m.p(unit+0x258,90);m.p(unit+0x48c,3)
                m.p(r+0x30,maxhp);m.p(r+0x1f0,hp);m.p(r+0x264,level)
                m.b(r+0x3dd,7 if mind else 2)
                if not dead:
                    m.p(m.results+0x3c,0);m.p(m.results+0x28,1)
                    m.p(m.results+0x504,r)
                helper=m.result_addition
                m.p(helper+0xc,m.hud);m.p(m.pending+40,1)
                before=bytes(m.u.mem_read(unit,0x700))
                result_before=bytes(m.u.mem_read(r,0x400))
                m.invoke(SYMS['native_unit'],(helper,base,helper+0x100,unit))
                self.assertEqual(m.vars['unitCurrHp'],0 if dead else min(max(hp,0),maxhp))
                self.assertEqual(m.vars['unitMaxHp'],maxhp)
                self.assertEqual(m.vars['level'],level)
                self.assertEqual(m.vars['levelUp'],int(level>3))
                self.assertEqual(m.vars['isMindControlled'],int(mind))
                self.assertEqual(m.vars['ghoul'],int(ghoul))
                self.assertEqual(m.vars['xp'],'Experience: 0')
                written={cmd[1] for cmd in m.commands if cmd[0]=='var'}
                self.assertIn('xp',written)
                self.assertNotIn('ghoul',written)
                self.assertEqual(bytes(m.u.mem_read(unit,0x700)),before)
                self.assertEqual(bytes(m.u.mem_read(r,0x400)),result_before)

    def test_detached_result_at_high_heap_addresses_through_real_unit_hook(self):
        # The supplied dump has both unit and result addresses above 2 GiB.
        # No context pointers are attached to the result snapshot. The old
        # patch enters IsGhoul here and is rejected by the regression guard.
        for base in BASES:
            m=NativeMachine(base,own_dead=1,other_dead=0,alive=1)
            m.run();m.unit_mode=True
            m.u.mem_map(0xb6059000,0x1000)
            m.u.mem_map(0xcb11b000,0x1000)
            unit=0xb60593a0;r=0xcb11b380
            m.p(unit+0x10,100);m.p(unit+0x258,90);m.p(unit+0x48c,3)
            m.p(r+0x3d8,100);m.p(r+0x30,140);m.p(r+0x1f0,70)
            m.p(r+0x264,4);m.b(r+0x3dd,7);m.b(unit+0x60c,2)
            m.p(m.results+0x404,r);m.p(m.results+0x504,r)
            helper=m.result_addition;c=helper+0x100
            m.p(helper+0xc,m.hud);m.p(m.pending+40,1)
            m.vars.update(ghoul=1,xp='modded pre-battle XP')
            before=(bytes(m.u.mem_read(unit,0x700)),bytes(m.u.mem_read(r,0x400)))
            frame=STACK+0x800
            m.p(frame-0x44,unit);m.p(frame-0x10,helper)
            name=helper+0x200;m.u.mem_write(name,b'AddTroopData\0')
            m.invoke(SYMS['unit_hook'],(name,1),c,8,
                regs={UC_X86_REG_EBP:frame,UC_X86_REG_ESI:c,UC_X86_REG_EDI:4})
            self.assertEqual(m.vars['unitCurrHp'],0) # dead-list priority
            self.assertEqual(m.vars['unitMaxHp'],140)
            self.assertEqual(m.vars['level'],4)
            self.assertEqual(m.vars['isMindControlled'],1)
            self.assertEqual(m.vars['xp'],'Experience: 0')
            self.assertEqual(m.vars['ghoul'],1)
            self.assertEqual(m.commands[-1],('call','AddTroopData'))
            self.assertEqual((bytes(m.u.mem_read(unit,0x700)),
                              bytes(m.u.mem_read(r,0x400))),before)

    def test_hero_leader_unmatched_and_unscoped_keep_native_values(self):
        for mode in ('hero','leader','unmatched','unscoped'):
            m=NativeMachine(own_dead=1,other_dead=0,alive=0)
            m.run();m.unit_mode=True
            unit=m.entities[100];r=m.d(m.results+0x404)
            m.p(unit+0x10,100);m.p(unit+0x258,90);m.p(r+0x264,9)
            if mode in ('hero','leader'):m.b(unit+0x4a0+(mode=='leader'),1)
            if mode=='unmatched':m.p(unit+0x10,999)
            helper=m.result_addition;m.p(helper+0xc,m.hud)
            m.p(m.pending+40,int(mode!='unscoped'))
            m.vars.update(ghoul=1,xp='original tooltip',level=1,levelUp=1)
            m.commands.clear()
            m.invoke(SYMS['native_unit'],(helper,m.base,helper+0x100,unit))
            self.assertEqual(m.vars['xp'],'original tooltip')
            self.assertEqual(m.vars['ghoul'],1)
            self.assertEqual(m.vars['level'],1)
            self.assertEqual(m.vars['levelUp'],int(mode=='unscoped'))
            if mode=='unscoped':self.assertFalse(m.commands)

    def test_ordinary_death_ids_match_engine_and_mark_both_armies(self):
        for base in BASES:
            m=NativeMachine(base,own_dead=1,other_dead=1,alive=0)
            # These casualties have only entity IDs, no result snapshots.
            m.p(m.results+0x3c,0)
            m.p(m.results+0x14,2);m.p(m.results+0x18,m.results+0x600)
            m.p(m.results+0x600,100);m.p(m.results+0x604,101)
            m.run()
            # Execute the exact original KillDeadUnits integer-list loop,
            # stopping before its subsequent resurrection handling. This
            # grounds the fixture's layout in the game's real consumer.
            m.invoke(0x6d31b0,(m.results,m.result_addition),m.manager,
                     stop=base+0x6d3214)
            self.assertEqual(m.native_killed_ids,[100,101])
            m.unit_mode=True
            helper=m.result_addition;m.p(helper+0xc,m.hud);m.p(m.pending+40,1)
            for identity,level in ((100,3),(101,6)):
                unit=m.entities[identity];m.p(unit+0x10,identity)
                m.vars.update(unitCurrHp=55,unitMaxHp=120,level=level,
                              xp='pre-battle XP',ghoul=0,isMindControlled=1)
                before=bytes(m.u.mem_read(unit,0x700))
                m.invoke(SYMS['native_unit'],(helper,base,helper+0x100,unit))
                self.assertEqual(m.vars['unitCurrHp'],0)
                self.assertEqual(m.vars['unitMaxHp'],120)
                self.assertEqual(m.vars['level'],level)
                self.assertEqual(m.vars['isMindControlled'],0)
                self.assertEqual(bytes(m.u.mem_read(unit,0x700)),before)

    def test_surviving_defender_health_rank_and_conversion(self):
        for base in BASES:
            for converted in (False,True):
                m=NativeMachine(base,own_dead=0,other_dead=1,alive=1)
                unit=m.entities[100];r=m.d(m.results+0x404)
                m.p(unit+0x10,100);m.p(unit+0x48c,2)
                m.p(r+0x30,180);m.p(r+0x1f0,37);m.p(r+0x264,4)
                m.b(r+0x3dd,2 if converted else 7)
                m.p(m.results+0x3c,0);m.p(m.results+0x504,r)
                m.run();m.unit_mode=True
                helper=m.result_addition;m.p(helper+0xc,m.hud);m.p(m.pending+40,1)
                m.vars.update(xp='defender XP',ghoul=1)
                before=(bytes(m.u.mem_read(unit,0x700)),bytes(m.u.mem_read(r,0x400)))
                m.invoke(SYMS['native_unit'],(helper,base,helper+0x100,unit))
                for key,value in (('unitCurrHp',37),('unitMaxHp',180),('level',4),
                                  ('levelUp',1),('isMindControlled',int(converted)),
                                  ('xp','Experience: 0'),('ghoul',1)):
                    self.assertEqual(m.vars[key],value)
                self.assertEqual((bytes(m.u.mem_read(unit,0x700)),
                                  bytes(m.u.mem_read(r,0x400))),before)

    def test_preview_xp_uses_result_and_native_modded_tier_threshold(self):
        for base in BASES:
            for level,xp,expected in ((0,11,17),(2,52,93),(4,165,231),
                                      (5,300,311),(8,515,551),(1005,90000,80231)):
                m=NativeMachine(base,own_dead=1,other_dead=0,alive=0)
                unit=m.entities[100];r=m.d(m.results+0x404)
                m.p(unit+0x10,100);m.p(unit+0x48c,0)
                m.p(unit+0x498,7) # pre-battle XP: UnitData+0x268
                m.p(r+0x264,level);m.p(r+0x270,xp)
                resource=0x300ed000;tier=0x300ee000
                m.p(r+0x10,resource)
                m.tier_links[resource+0x478]=tier
                for i,value in enumerate((0,17,41,93,157,231)):
                    m.p(tier+0x9c+4*i,value)
                m.p(tier+0xb4,80)
                m.run();m.unit_mode=True
                helper=m.result_addition;m.p(helper+0xc,m.hud);m.p(m.pending+40,1)
                m.vars['xp']='pre-battle XP'
                before=bytes(m.u.mem_read(r,0x400)),bytes(m.u.mem_read(unit,0x700))
                # Confirm offset against the actual native XP formatter's
                # load instruction without entering its context-dependent part.
                m.invoke(0x5ec432,regs={UC_X86_REG_EBX:r+8},stop=base+0x5ec438)
                self.assertEqual(m.u.reg_read(UC_X86_REG_EDI),xp)
                m.invoke(SYMS['native_unit'],(helper,base,helper+0x100,unit))
                self.assertEqual(m.vars['xp'],f'Experience: {xp} / {expected}')
                self.assertEqual((bytes(m.u.mem_read(r,0x400)),bytes(m.u.mem_read(unit,0x700))),before)

    def test_ordinary_casualty_xp_is_explicitly_before_battle(self):
        m=NativeMachine(own_dead=1,other_dead=0,alive=0)
        unit=m.entities[100];m.p(unit+0x10,100);m.p(unit+0x498,23)
        m.p(m.results+0x3c,0);m.p(m.results+0x14,1)
        m.p(m.results+0x18,m.results+0x600);m.p(m.results+0x600,100)
        m.run();m.unit_mode=True
        helper=m.result_addition;m.p(helper+0xc,m.hud);m.p(m.pending+40,1)
        m.invoke(SYMS['native_unit'],(helper,m.base,helper+0x100,unit))
        self.assertEqual(m.vars['xp'],'Experience before battle: 23')

    def test_result_stack_redirect_and_add_troop_hook_abi(self):
        for base in BASES:
            m=NativeMachine(base,own_dead=1,other_dead=0)
            m.run();m.unit_mode=True
            helper=m.result_addition;c=helper+0x100;unit=m.entities[100]
            m.p(helper+0xc,m.hud);m.p(m.pending+40,1)
            m.invoke(0x6103b0,(c,0x11223344,6),helper,stop=base+0x610050)
            self.assertEqual(m.u.reg_read(UC_X86_REG_ESP),STACK)
            self.assertEqual(m.u.reg_read(UC_X86_REG_ECX),helper)
            # Execute the CALL replacement with the original caller's locals.
            frame=STACK+0x800
            m.p(frame-0x44,unit);m.p(frame-0x10,helper)
            # Unmatched unit: verifies scoped badge reset and tail-call ABI.
            name=helper+0x200;m.u.mem_write(name,b'AddTroopData\0')
            m.invoke(SYMS['unit_hook'],(name,1),c,8,
                regs={UC_X86_REG_EBP:frame,UC_X86_REG_ESI:c,UC_X86_REG_EDI:7})
            self.assertEqual(m.commands[-1],('call','AddTroopData'))

if __name__=='__main__':unittest.main(verbosity=2)
