"""Execute click-to-rename hooks, native modal transitions and real string code.

The engine's Lua argument extraction, entity lookup and Iggy drawing are
simulated. No Windows game, renderer, save loader or mod is run here.
"""
import unittest
from unicorn.x86_const import *
from test_native import NativeMachine, BASES, STATE_NOTIFY
from test_retry import SYMS, STACK, STOP

UNIT_STATE_TYPE=STOP+0x300
ABILITY=STOP+0x310

class RenameMachine(NativeMachine):
    def __init__(self,base=0x400000,hero=False):
        super().__init__(base)
        self.rename=base+0xfc8040
        self.unit_state=0x300a7000
        self.unit_sm=0x300a8000
        self.helper=0x300a9000
        self.action=0x300aa000
        self.input=0x300ab000
        self.input_text=0x300ac000
        self.unit=self.entities[100]
        self.hero=hero
        self.permitted=True
        self.action_type=0x47004a
        self.ability_clicks=[]
        self.deliveries=[]
        self.assignments=[]
        self.p(self.player,self.player+0x800)
        self.p(self.player+0x908,base+0x63a820)
        self.p(self.player+0xf4,self.world)
        self.p(self.player+0xf8,self.players)
        self.p(self.player+0x35c,self.unit)
        self.p(self.player+0x364,0)
        self.p(self.unit+0x10,100)
        self.p(self.unit_state,self.unit_state+0x400)
        self.p(self.unit_state+0x424,UNIT_STATE_TYPE)
        self.p(self.unit_state+0x494,ABILITY)
        self.p(self.unit_state+0xc,self.unit_sm)
        self.p(self.unit_sm+0x20,self.unit_state)
        self.p(self.unit_sm+0x34,self.hud)
        self.p(self.modal+8,10)
        self.p(self.modal+0x33c,base+0x54d350)
        self.p(self.modal+0x340,base+0x54d390)
        self.battle_modal=self.other
        self.p(self.battle_modal+8,2)
        self.p(self.battle_modal+0x33c,base+0x5af570)
        self.p(self.battle_modal+0x340,base+0x54c540)
        self.p(self.helper+8,base+0xb2abd0)
        self.p(self.helper+0xc,self.hud)
        self.p(self.helper+0x10,self.unit+0x230)
        self.p(self.input+8,self.input_text)

    def hook(self,u,a,size,_):
        sp=u.reg_read(UC_X86_REG_ESP);this=u.reg_read(UC_X86_REG_ECX)
        r=a-self.base
        if a==self.stop_at:
            self.stopped_at=a;u.emu_stop();return
        if a==UNIT_STATE_TYPE:
            assert this==self.unit_state
            self.ret(4,int(self.d(sp+4)==(0x472453 if self.hero else 0x472451)))
        elif a==ABILITY:
            assert this==self.unit_state
            value=self.narrow(self.d(sp+4))
            self.ability_clicks.append(value)
            # Native by-value TEString cleanup; this service fixture doesn't
            # run ability lookup or construct a strategic ability window.
            buf=self.d(sp+4)
            if self.d(sp+8): del self.allocations[buf]
            self.ret(12)
        elif r==0x635c00:
            assert this==self.player
            self.ret(result=int(self.permitted))
        elif r==0x6f4ec0:
            assert this==self.sm+8
            identity=self.d(sp+4)
            assert identity in (0,2,10)
            self.ret(4,identity)
        elif r==0x6f1dd0:
            assert this==self.sm+8
            self.ret(4,{0:self.idle,2:self.battle_modal,10:self.modal}[self.d(sp+4)])
        elif a==STATE_NOTIFY:
            assert this==self.sm
            self.p(self.hud+0x37c,self.d(self.sm+0x20))
            self.ret(8)
        elif r==0x236a40:
            assert self.d(sp+4)==0x1234
            self.action_type=self.d(sp+16)
            self.ret(result={0x47004a:self.unit_state,0x473003:self.modal,
                             0x4718a7:self.battle_modal}[self.action_type])
        elif r==0x233750:
            assert self.d(sp+4)==0x1234 and self.d(sp+8)==2
            self.ret(result=self.action)
        elif r==0x2c7280:
            assert this==self.hud
            name=self.narrow(self.d(sp+4))
            self.deliveries.append((name,list(self.commands)))
            self.commands=[]
            self.ret(8)
        elif r==0x113830:
            # TEString's fresh allocation uses this cdecl allocator, whereas
            # TEWString growth uses realloc. Both are engine/platform services.
            self.ret(result=self.alloc(self.d(sp+4)))
        elif r==0x1905be:
            # GiveFocus has executed the original game's serializer. Inspect
            # the real command word before its epilogue restores ESI; Iggy
            # command consumption/rendering remain outside this emulator.
            c=u.reg_read(UC_X86_REG_ESI)
            end=self.d(c+0xc)
            assert end>=4 and self.d(self.d(c+8)+end-4)==0x1b
            self.commands.append(('give-focus',))
        elif r in (0x116880,0x139250):
            self.assignments.append((r,this))
            # Continue through actual string assignment and allocation code.
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
            for r,v in defaults.items():assert self.u.reg_read(r)==v, r
        assert self.d(0)==0xdeadbeef
        self.stop_at=None

    def click(self,action='__aow3_rename_unit_v064__'):
        self.u.mem_write(self.action,action.encode()+b'\0')
        self.invoke(0x54aae0,(0x1234,)) # complete native Lua wrapper

    def pump(self):
        queued=self.d(self.sm+0x28)
        assert queued in (self.idle,self.modal)
        # TEStateMachine::HandleSwitching clears the queued pointer before
        # calling SetStateInternal (verified against the exported EK method).
        self.p(self.sm+0x28,0)
        self.invoke(0x136170,(queued,),this=self.sm,callee_pop=4)

    def open(self):
        self.click();self.pump()

    def submit(self,name):
        self.u.mem_write(self.input_text,name.encode('utf-16le')+b'\0\0')
        self.invoke(0x56d6b0,(self.input,),this=self.modal,callee_pop=4)

    def cancel(self):
        self.invoke(0x54d3d0,(0x1234,)) # complete native Cancel Lua wrapper

    def panel(self):
        self.invoke(0x5e57b0,this=self.helper) # real controller ctor/dtor

    def personal_name(self,unit=None):
        p=self.d((unit or self.unit)+0x230+0x328)
        return self.wide(p) if p else ''


class ClickRenameTests(unittest.TestCase):
    def test_open_requests_game_keyboard_focus_before_swf_setup(self):
        for base in BASES:
            m=RenameMachine(base);before=set(m.allocations)
            m.open()
            window,commands=m.deliveries[-1]
            self.assertEqual(window,'HUD_NameChanger')
            self.assertEqual(commands[0],('give-focus',))
            self.assertEqual(commands[-1],('call','BeginUnitRename'))
            self.assertEqual(commands.count(('give-focus',)),1)
            self.assertEqual(set(m.allocations),before)
            m.cancel()
            self.assertEqual(m.d(m.sm+0x20),m.idle)
            m.open()
            self.assertEqual(m.deliveries[-1][1][0],('give-focus',))

    def test_native_click_prefills_exact_selected_name_at_aslr_bases(self):
        for base in BASES:
            for hero in (False,True):
                m=RenameMachine(base,hero);before=set(m.allocations)
                m.click()
                self.assertEqual(m.d(m.rename),1)
                self.assertEqual(m.d(m.sm+0x28),m.modal)
                self.assertEqual(m.d(m.sm+0x20),m.idle)
                self.assertEqual(m.deliveries,[])
                m.pump()
                self.assertEqual(m.d(m.rename),2)
                self.assertEqual(m.events,['show:HUD_NameChanger','show:HUD_SkillBook_Vignette'])
                self.assertEqual(m.vars['CurrentUnitName'],'Dawnwatch Veterans')
                self.assertEqual(m.deliveries[-1][1][-1],('call','BeginUnitRename'))
                self.assertEqual(set(m.allocations),before)
                self.assertFalse(m.ability_clicks)

    def test_submit_changes_only_captured_unit_using_engine_strings(self):
        for base in BASES:
            for name in ('Dawnwatch','Éowyn 星の騎士','The "Watch" \\ North','A'*80):
                m=RenameMachine(base);m.open();other=m.entities[101]
                other_before=bytes(m.u.mem_read(other,0x900))
                m.assignments=[];m.submit(name)
                self.assertEqual(m.personal_name(),name)
                self.assertEqual(m.vars['UnitName'],name)
                self.assertEqual(m.deliveries[-1][0],'HUD_FloatingHeroBackground')
                self.assertEqual(m.deliveries[-1][1][-1],('call','UnitRenameApplied'))
                data=m.unit+0x230
                self.assertEqual(m.assignments,[(0x116880,data+0x314),(0x139250,data+0x320),
                                               (0x116880,data+0x370),(0x139250,data+0x37c)])
                self.assertEqual(bytes(m.u.mem_read(other,0x900)),other_before)
                self.assertEqual(m.d(m.rename),3)
                self.assertEqual(m.d(m.sm+0x28),m.idle)
                self.assertEqual(m.d(m.sm+0x20),m.modal)
                m.submit('Second click ignored')
                self.assertEqual(m.personal_name(),name)
                m.pump()
                self.assertEqual(bytes(m.u.mem_read(m.rename,40)),bytes(40))
                self.assertEqual(m.d(m.sm+0x20),m.idle)
                self.assertEqual(bytes(m.u.mem_read(m.unit_state+0x120,1)),b'\x01')

    def test_cancel_keeps_names_and_frees_modal_for_next_rename(self):
        m=RenameMachine();m.open();before=bytes(m.u.mem_read(m.unit,0x900))
        m.cancel()
        self.assertEqual(bytes(m.u.mem_read(m.unit,0x900)),before)
        self.assertEqual(m.d(m.rename),0)
        self.assertEqual(m.events[-2:],['hide:HUD_SkillBook_Vignette','hide:HUD_NameChanger'])
        m.open();self.assertEqual(m.d(m.rename),2)

    def test_invalid_names_keep_dialog_open_and_do_not_write(self):
        for name in ('','   ','A'*81,'Bad\nName','Bad\tName','Bad\x7fName'):
            m=RenameMachine();m.open();before=bytes(m.u.mem_read(m.unit,0x900))
            m.submit(name)
            self.assertEqual(m.d(m.rename),2)
            self.assertEqual(m.d(m.sm+0x28),0)
            self.assertEqual(bytes(m.u.mem_read(m.unit,0x900)),before)
            self.assertEqual(m.deliveries[-1][1][-1],('call','UnitRenameRejected'))
            m.submit('  Valid name  ')
            self.assertEqual(m.personal_name(),'Valid name')

    def test_panel_eligibility_and_click_guard_agree(self):
        for case in ('normal','enemy','preview','no_selection','network','inactive','tactical','snapshot','busy','queued'):
            m=RenameMachine()
            if case=='enemy':m.b(m.unit+0x60c,7)
            if case=='preview':m.p(m.player+0x364,m.unit+0x230)
            if case=='no_selection':m.p(m.player+0x35c,0)
            if case=='network':m.p(m.players+0x50,1)
            if case=='inactive':m.permitted=False
            if case=='tactical':m.p(m.player+0x908,m.base+0x63a830)
            if case=='snapshot':m.entities[100]=0
            if case=='busy':m.p(m.idle+8,2)
            if case=='queued':m.p(m.sm+0x28,m.modal)
            m.panel()
            self.assertEqual(m.vars['CanRenameUnit'],int(case=='normal'),case)
            self.assertEqual(m.deliveries[-1][1][-1],('call','EndUpdate'))
            m.click()
            self.assertEqual(m.d(m.rename),int(case=='normal'),case)

    def test_other_windows_and_resource_panels_do_not_gain_rename(self):
        m=RenameMachine()
        m.p(m.helper+0x10,m.entities[101]+0x230)
        m.panel();self.assertEqual(m.vars['CanRenameUnit'],0)
        m=RenameMachine();m.p(m.helper+8,m.base+0xb2d468)
        m.panel();self.assertNotIn('CanRenameUnit',m.vars)
        self.assertEqual(m.deliveries[-1][1],[('call','EndUpdate')])

    def test_dialog_keeps_original_target_when_selection_or_panel_changes(self):
        for base in BASES:
            for case in ('selection','selection_cleared','panel_changed','preview'):
                m=RenameMachine(base);m.open();other=m.entities[101]
                before=bytes(m.u.mem_read(other,0x900))
                if case=='selection':m.p(m.player+0x35c,other)
                if case=='selection_cleared':m.p(m.player+0x35c,0)
                if case=='panel_changed':m.p(m.unit_sm+0x20,0)
                if case=='preview':m.p(m.player+0x364,other+0x230)
                m.submit('Original unit')
                self.assertEqual(m.personal_name(),'Original unit',case)
                self.assertEqual(bytes(m.u.mem_read(other,0x900)),before,case)
                m.pump()
                self.assertEqual(m.d(m.rename),0)

    def test_identity_ownership_and_world_revalidated_with_visible_failure(self):
        for case in ('recycled_id','removed','owner','world','permission','network'):
            m=RenameMachine();m.open()
            before=bytes(m.u.mem_read(m.unit,0x900))
            other=m.entities[101];other_before=bytes(m.u.mem_read(other,0x900))
            if case=='recycled_id':m.p(m.unit+0x10,102);m.entities[102]=m.unit
            if case=='removed':m.entities[100]=0
            if case=='owner':m.b(m.unit+0x60c,7)
            if case=='world':m.p(m.player+0xf4,m.auto_world)
            if case=='permission':m.permitted=False
            if case=='network':m.p(m.players+0x50,1)
            before=bytes(m.u.mem_read(m.unit,0x900))
            m.assignments=[];m.submit('Wrong target')
            self.assertEqual(m.assignments,[],case)
            self.assertEqual(bytes(m.u.mem_read(m.unit,0x900)),before,case)
            self.assertEqual(bytes(m.u.mem_read(other,0x900)),other_before,case)
            self.assertEqual(m.d(m.rename),2,case)
            self.assertEqual(m.deliveries[-1][1][-1],('call','UnitRenameUnavailable'),case)
            self.assertEqual(m.d(m.sm+0x28),0,case)

    def test_normal_ability_click_uses_original_virtual_method_and_string_cleanup(self):
        for base in BASES:
            m=RenameMachine(base);before=set(m.allocations)
            m.click('0000015900000218')
            self.assertEqual(m.ability_clicks,['0000015900000218'])
            self.assertEqual(m.d(m.rename),0)
            self.assertEqual(set(m.allocations),before)

    def test_city_submit_preserves_native_entry_and_has_no_unit_side_effect(self):
        for base in BASES:
            m=RenameMachine(base)
            m.invoke(0x56d6b0,(m.input,),this=m.modal,stop=base+0x56d6b5)
            self.assertEqual(m.u.reg_read(UC_X86_REG_ESP),STACK-8)
            self.assertEqual(m.u.reg_read(UC_X86_REG_EBP),STACK-4)
            self.assertEqual(m.d(STACK-8),0xffffffff)
            self.assertEqual(m.d(m.rename),0)
            self.assertEqual(m.deliveries,[])
            self.assertEqual(m.assignments,[])

    def test_city_dialog_entry_and_exit_do_not_prefill_unit_or_leave_state(self):
        m=RenameMachine()
        m.invoke(0x138320,(10,1),this=m.sm,callee_pop=8)
        self.assertEqual(m.d(m.rename),0)
        self.assertEqual(m.deliveries,[])
        m.cancel();self.assertEqual(m.d(m.rename),0)

    def test_world_teardown_clears_unit_context_without_touching_other_world(self):
        m=RenameMachine();m.open();m.p(m.hex+0x28,m.auto_world)
        m.invoke(SYMS['native_forget'],(m.manager,m.base))
        self.assertEqual(m.d(m.rename),2)
        m.p(m.hex+0x28,m.world)
        m.invoke(SYMS['native_forget'],(m.manager,m.base))
        self.assertEqual(bytes(m.u.mem_read(m.rename,40)),bytes(40))

    def test_rename_before_and_after_accepting_autocombat(self):
        for base in BASES:
            m=RenameMachine(base)
            m.open();m.submit('Before the battle');m.pump()
            self.assertEqual(m.personal_name(),'Before the battle')
            m.run();m.ready();m.accept();m.tick()
            self.assertEqual(m.d(m.pending),0)
            self.assertEqual(m.d(m.rename),0)
            self.assertEqual(m.d(m.sm+0x20),m.idle)
            m.open();m.submit('After the battle');m.pump()
            self.assertEqual(m.personal_name(),'After the battle')

if __name__=='__main__':unittest.main(verbosity=2)
