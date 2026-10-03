"""Execute the native finish-notification and victory/defeat selection code.

World notification, HUD iteration, combat-result participant/win lookup and
the patched preview/accept paths execute real game instructions. The final
HUD audio service, game lookup, type query and window drawing are simulated.
This verifies sound dispatch and timing, not audible output in Windows.
"""
import unittest
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP
from test_native import NativeMachine, BASES, STOP
from test_retry import MODULE

WORLD_TYPE=STOP+0x230


class SoundMachine(NativeMachine):
    def __init__(self,base=0x400000,missing_user32=False,**kwargs):
        super().__init__(base,**kwargs)
        self.missing_user32=missing_user32
        self.application=0x300f1000
        self.settings=0x300f3000
        self.p(self.players,self.players+0x600)
        self.p(self.players+0x624,WORLD_TYPE)
        self.p(self.hud+0x3930,self.hud) # embedded combat indicator's HUD
        self.p(self.player+0xf8,self.players)
        self.p(self.players+8,self.application)
        self.p(self.hex+0x1c,0x300f2000)
        self.p(0x300f2018,self.settings)
        self.sounds=[]

    def hook(self,u,a,size,data):
        sp=u.reg_read(UC_X86_REG_ESP);this=u.reg_read(UC_X86_REG_ECX)
        r=a-self.base
        if r==0x801080:
            assert this==self.world
            self.events.append('notify-result' if self.d(sp+4) else 'hide-indicator')
            # Run the actual notification and all participant/win decisions.
        elif a==WORLD_TYPE:
            assert this==self.players and self.d(sp+4)==0x460032
            self.ret(4,1)
        elif r==0x2d1da0:
            assert this==self.application
            self.ret(result=self.hex)
        elif r==0x5fd9d0:
            assert this==self.hud
            link=self.d(sp+4)-self.settings
            assert link in (0x410,0x430)
            self.sounds.append('victory' if link==0x410 else 'defeat')
            self.events.append('sound:'+self.sounds[-1])
            self.ret(4)
        elif a==MODULE and self.missing_user32:
            self.ret(4,0)
        else:
            super().hook(u,a,size,data)


class SoundTests(unittest.TestCase):
    def test_native_victory_and_defeat_sound_when_preview_opens(self):
        for base in BASES:
            for won in (True,False):
                m=SoundMachine(base,won=won)
                before=bytes(m.u.mem_read(m.results,0x1000))
                m.run()
                self.assertEqual(m.sounds,['victory' if won else 'defeat'])
                self.assertLess(m.events.index('engine-panels'),
                                m.events.index('sound:'+m.sounds[0]))
                self.assertNotIn('commit',m.events)
                self.assertEqual(bytes(m.u.mem_read(m.results,0x1000)),before)
                self.assertEqual(m.d(m.manager+0xa0),m.sim)
                self.assertEqual(m.d(m.setup+8),0x12345678)
                # Reentry, the ready callback, refresh and idle ticks are silent.
                m.run();m.ready();m.ready()
                m.invoke(0x5adbf0,this=m.modal)
                for _ in range(3):m.tick()
                self.assertEqual(len(m.sounds),1)
                self.assertNotIn('commit',m.events)

    def test_accept_manual_and_native_close_do_not_repeat_sound(self):
        for base in BASES:
            for won in (True,False):
                for action in ('accept','manual','close'):
                    m=SoundMachine(base,won=won);m.run();m.ready()
                    if action=='close':m.invoke(0x138320,(0,1),m.sm,8)
                    else:getattr(m,action)()
                    m.tick();m.tick()
                    self.assertEqual(m.sounds,['victory' if won else 'defeat'])
                    self.assertEqual(m.events.count('notify-result'),1)
                    self.assertEqual(m.events.count('commit'),int(action!='manual'))
                    self.assertEqual(m.events.count('open-manual'),int(action=='manual'))
                    self.assertEqual(m.d(m.setup+8),0x12345678)
                    self.assertEqual(bytes(m.u.mem_read(m.pending,48)),b'\0'*48)

    def test_timeout_fallback_and_missing_dialog_api_do_not_repeat_sound(self):
        for base in BASES:
            for answer,api,missing in ((2,True,False),(4,True,False),
                                      (2,False,False),(2,True,True)):
                m=SoundMachine(base,answer=answer,api=api,missing_user32=missing)
                m.run();m.p(m.pending+36,179);m.tick();m.tick()
                self.assertEqual(m.sounds,['victory'])
                self.assertEqual(m.events.count('notify-result'),1)
                self.assertEqual(m.events.count('commit'),int(answer!=4))
                self.assertEqual(m.events.count('open-manual'),int(answer==4))
                self.assertEqual(m.d(m.setup+8),0x12345678)

    def test_original_flow_without_native_preview_keeps_completion_sound(self):
        for base in BASES:
            for mode in ('busy-modal','network'):
                m=SoundMachine(base,answer=2,won=False)
                if mode=='busy-modal':m.p(m.sm+0x20,m.other)
                else:m.p(m.players+0x50,1)
                m.run()
                self.assertNotIn('engine-panels',m.events)
                self.assertEqual(m.sounds,['defeat'])
                self.assertEqual(m.events.count('commit'),1)

    def test_next_battle_not_suppressed_when_objects_are_reused(self):
        m=SoundMachine();m.run();m.ready();m.accept();m.tick()
        self.assertEqual(m.sounds,['victory'])
        # The fixture's cleanup services are simulated, so the same addresses
        # can stand in for newly allocated objects in the next battle.
        m.p(m.manager+8,5);m.p(m.manager+0xb0,m.setup)
        m.p(m.manager+0xa0,m.sim);m.p(m.manager+0x98,m.command)
        m.b(m.rp+0x28,0)
        m.run();m.ready();m.manual();m.tick()
        self.assertEqual(m.sounds,['victory','defeat'])
        self.assertEqual(m.events.count('commit'),1)
        self.assertEqual(m.events.count('open-manual'),1)


if __name__=='__main__':unittest.main(verbosity=2)
