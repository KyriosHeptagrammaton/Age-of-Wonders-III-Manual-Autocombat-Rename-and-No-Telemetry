"""Verify native combat-event construction during accepted preview resolution.

Executes EnterCloseAC, TriggerPlayerEvents and CombatComplete, including the
real AutoOpen/LogOnly stores, involved-player list and reference release.
Campaign application, event allocation/setup/history insertion, quest service,
audio and drawing are simulated. No live game, event panel or save is run.
"""
import struct
import unittest
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_EIP
from test_sound import SoundMachine
from test_native import BASES, STOP

COMMIT_SERVICE=STOP+0x400


class ReportMachine(SoundMachine):
    def __init__(self,base=0x400000,separate_report_setup=False,**kwargs):
        super().__init__(base,**kwargs)
        self.guard=base+0xfc8080
        self.turn=0x30140000
        self.visual=0x30141000
        self.hp=0x30150000
        self.enemy=0x30154000
        self.report_setup=0x30148000 if separate_report_setup else self.setup
        if separate_report_setup:
            self.u.mem_write(self.report_setup,bytes(self.u.mem_read(self.setup,0x1000)))
            self.p(self.manager+0x10c,self.report_setup)
        self.p(self.hex+0x22b0,self.turn)
        self.p(self.turn+0x14,self.turn+0x100)
        self.p(self.turn+0x18,2)
        self.history=[]
        self.event_data={}
        for i,(player,identity) in enumerate(((self.hp,2),(self.enemy,7))):
            self.p(self.turn+0x104+8*i,player)
            self.b(player+0x28,identity)
            self.p(player+0x50,self.turn+0x200)
            self.p(player+0x1890+0xec,player)
        self.p(self.turn+0x20c,self.hex)
        self.p(self.results+0x50,2)
        self.p(self.results+0x30c,self.rp+0x100)
        self.b(self.rp+0x108,7);self.b(self.rp+0x12a,1)
        self.b(self.rp+0x128,not kwargs.get('won',True))
        # The simulated campaign-commit service delegates event construction
        # to the real TriggerPlayerEvents, then returns with the original ABI.
        code=b'\x8b\x44\x24\x04\x68'+struct.pack('<I',self.visual)+b'\x50\xe8'
        code+=struct.pack('<i',base+0x6d6550-(COMMIT_SERVICE+len(code)+4))
        code+=b'\xc2\x04\x00'
        self.u.mem_write(COMMIT_SERVICE,code)

    def hook(self,u,a,size,data):
        sp=u.reg_read(UC_X86_REG_ESP);this=u.reg_read(UC_X86_REG_ECX)
        r=a-self.base
        if r==0x6d8ad0:
            assert this==self.manager and self.d(sp+4)==self.results
            self.events.append('commit')
            u.reg_write(UC_X86_REG_EIP,COMMIT_SERVICE)
        elif r==0x6f1dd0 and this==self.turn+0xc:
            pass # Execute the original turn-player list lookup.
        elif r==0x7b4c30:
            assert this==self.visual
            assert self.d(sp+4)&255 in (2,7)
            self.ret(4,1) # Both fixture players participated.
        elif r==0x685550:
            event=0x30160000+len(self.event_data)*0x1000
            self.p(this+4,event);self.p(event+4,1)
            self.p(event+0x21c,event+0x800);self.p(event+0x224,16)
            self.event_data[event]=None
            self.ret()
        elif r==0x653de0:
            values=tuple(self.d(sp+4+4*i) for i in range(6))
            assert values[:3]==(self.results,self.report_setup,self.visual)
            self.event_data[this]=values
            self.b(this+0x228,0x5a);self.b(this+0x229,0x5a)
            self.ret(24)
        elif r in (0x791bd0,0x791bc0):
            assert this==self.report_setup
            self.ret(result=2 if r==0x791bd0 else 7)
        elif r==0x697280:
            event=self.d(sp+4);player=this-0x1890
            assert player in (self.hp,self.enemy)
            # Capture the actual values written by the unmodified constructor.
            self.history.append(dict(event=event,player=player,
                auto=self.u.mem_read(event+0x228,1)[0],
                log=self.u.mem_read(event+0x229,1)[0],
                data=self.event_data[event]))
            self.p(event+4,self.d(event+4)+1) # history owns the event
            self.ret(4)
        elif r==0x6d23e0:
            assert this==self.hex+0x3238
            self.events.append('empire-quest-check')
            self.ret(8)
        else:
            super().hook(u,a,size,data)

    def own_reports(self):return [r for r in self.history if r['player']==self.hp]


class ReportTests(unittest.TestCase):
    def test_accept_keeps_native_history_without_reopening_report(self):
        for base in BASES:
            for won in (True,False):
                m=ReportMachine(base,won=won);m.run();m.ready();m.accept();m.tick()
                self.assertEqual(m.events.count('commit'),1)
                self.assertEqual(len(m.history),2)
                own=m.own_reports()[0]
                self.assertEqual(own['auto'],0)
                self.assertEqual(own['log'],0) # stays in normal event list
                self.assertEqual(tuple(v&255 for v in own['data'][3:]),
                                 (int(won),int(not won),2))
                self.assertEqual(m.history[1]['auto'],1) # other player's report
                for row in m.history:
                    self.assertEqual(m.d(row['event']+4),1)
                    self.assertEqual(m.d(row['event']+0x220),2)
                    self.assertEqual(bytes(m.u.mem_read(row['event']+0x800,2)),b'\x02\x07')
                self.assertEqual(m.events.count('empire-quest-check'),2)
                self.assertEqual(bytes(m.u.mem_read(m.guard,16)),b'\0'*16)
                self.assertEqual(m.sounds,['victory' if won else 'defeat'])

    def test_native_close_and_timeout_accept_skip_the_duplicate(self):
        for base in BASES:
            for close in ('native','timeout','missing-api'):
                m=ReportMachine(base,answer=2,api=close!='missing-api');m.run()
                if close=='native':
                    m.ready();m.invoke(0x138320,(0,1),m.sm,8)
                else:m.p(m.pending+36,179)
                m.tick();m.tick()
                self.assertEqual([r['auto'] for r in m.own_reports()],[0])
                self.assertEqual(m.events.count('commit'),1)
                self.assertEqual(bytes(m.u.mem_read(m.guard,16)),b'\0'*16)

    def test_distinct_retained_report_setup_is_matched(self):
        # TriggerPlayerEvents uses manager+10c, not the simulation's +b0 setup.
        for base in BASES:
            m=ReportMachine(base,separate_report_setup=True)
            m.run();m.ready();m.accept();m.tick()
            self.assertEqual([r['auto'] for r in m.own_reports()],[0])
            self.assertEqual(m.own_reports()[0]['data'][1],m.report_setup)

    def test_manual_retry_creates_no_report_and_later_manual_result_opens(self):
        for base in BASES:
            m=ReportMachine(base);m.run();m.ready();m.manual();m.tick()
            self.assertFalse(m.history)
            self.assertEqual(m.events.count('open-manual'),1)
            self.assertEqual(bytes(m.u.mem_read(m.guard,16)),b'\0'*16)
            self.assertEqual(m.d(m.setup+8),0x12345678)
            # Simulate a later manual result's event phase, using same pointers.
            m.invoke(0x6d6550,(m.results,m.visual),m.manager,8)
            self.assertEqual([r['auto'] for r in m.own_reports()],[1])

    def test_original_results_without_preview_continue_to_open(self):
        for mode in ('busy-modal','network'):
            m=ReportMachine(answer=2)
            if mode=='busy-modal':m.p(m.sm+0x20,m.other)
            else:m.p(m.players+0x50,1)
            m.run()
            self.assertEqual([r['auto'] for r in m.own_reports()],[1])
            self.assertEqual(m.events.count('commit'),1)

    def test_suppression_requires_matching_manager_result_setup_and_player(self):
        for base in BASES:
            for field in range(4):
                m=ReportMachine(base)
                values=[m.manager,m.results,m.setup,m.hp]
                values[field]+=0x100
                for i,value in enumerate(values):m.p(m.guard+4*i,value)
                m.invoke(0x6d6550,(m.results,m.visual),m.manager,8)
                self.assertEqual([r['auto'] for r in m.own_reports()],[1])

    def test_following_battle_reusing_addresses_is_not_suppressed(self):
        m=ReportMachine();m.run();m.ready();m.accept();m.tick()
        self.assertEqual([r['auto'] for r in m.own_reports()],[0])
        m.invoke(0x6d6550,(m.results,m.visual),m.manager,8)
        self.assertEqual([r['auto'] for r in m.own_reports()],[0,1])


if __name__=='__main__':unittest.main(verbosity=2)
