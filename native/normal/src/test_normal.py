"""Execute normal-build hooks/adapters and native state/serialization code.
Services requiring Windows, graphics, resources, or a running campaign are mocked.
These tests do not replace an in-game smoke test.
"""
import json,struct,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
import build
from pe import PE
ROOT=Path(__file__).resolve().parents[1]
GAME=(ROOT/'game/AoW3.exe').read_bytes();P=PE(GAME)
SYMS=json.loads((ROOT/'game/build-manifest.json').read_text())['symbols']
STACK=0x70010000;STOP=0x50001000
SERVICES={n:STOP+0x100+i*0x10 for i,n in enumerate(['deactivate','deinit','delete','valid','tls_get','tls_set','hide','state_notify','type','indicator','module','proc','dialog','enter_cs','leave_cs','window_find','window_add'])}
REGS=[UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]

def loaded(base):
    out=bytearray(P.u32(P.optional+56));out[:P.u32(P.optional+60)]=GAME[:P.u32(P.optional+60)]
    for s in P.sections:out[s['rva']:s['rva']+s['size']]=GAME[s['raw']:s['raw']+s['size']]
    for rva in build.relocations(P):struct.pack_into('<I',out,rva,(struct.unpack_from('<I',out,rva)[0]+base-0x400000)&0xffffffff)
    return bytes(out)

class Machine:
    def __init__(self,base=0x400000,ui=True):
        self.base=base;self.u=Uc(UC_ARCH_X86,UC_MODE_32)
        self.u.mem_map(base,P.u32(P.optional+56));self.u.mem_write(base,loaded(base))
        for at,n in [(0,0x1000),(0x30000000,0x200000),(STACK-0x10000,0x20000),(STOP&~0xfff,0x1000)]:self.u.mem_map(at,n)
        self.events=[];self.vars={};self.commands=[];self.next_alloc=0x30100000;self.allocations={};self.answer=4
        self.manager=0x30000000;self.hex=0x30010000;self.world=0x30020000;self.players=0x30030000
        self.setup=0x30040000;self.sp=0x30041000;self.sim=0x30050000;self.auto_world=0x30060000
        self.tactical=0x30070000;self.results=0x30080000;self.rp=0x30081000;self.command=0x30090000
        self.player=0x300a1000;self.hp=0x300a2000;self.hud=0x300a3000;self.sm=0x300ac000
        self.idle=0x300b0000;self.modal=0x300b1000;self.name_modal=0x300b2000
        self.unit_state=0x300b3000;self.unit_sm=0x300b4000;self.unit=0x300c0000
        self.pending=base+build.STATE_RVA;self.rename=self.pending+0x40
        self.p(0,0xdeadbeef)
        for off,v in [(8,5),(0xa0,self.hex),(0x94,self.setup),(0xf0,self.setup),(0x84,self.sim),(0x7c,self.command)]:self.p(self.manager+off,v)
        self.b(self.hex+0x2cdc,8);self.b(self.hex+0x3c,2);self.p(self.hex+0x28,self.world)
        self.p(self.world+0x408,self.players);self.p(self.world+0x38c,0x300e1000)
        self.p(self.players,self.players+0x800);self.p(self.players+0x824,SERVICES['type'])
        self.p(self.players+0x14,self.players+0x500);self.p(self.players+0x18,1);self.p(self.players+0x504,self.player)
        self.p(self.player,self.player+0x800);self.p(self.player+0x908,base+0x65fb40)
        self.p(self.player+0xc8,2);self.p(self.player+0xcc,self.world);self.p(self.player+0xd0,self.players)
        self.p(self.player+0x13c,self.hud if ui else 0);self.p(self.player+0x334,self.unit)
        self.p(self.world+0x3414,self.hex);self.p(self.hex+0x22b0,self.hex+0x1000)
        self.p(self.hex+0x1014,self.hex+0x1100);self.p(self.hex+0x1018,1);self.p(self.hex+0x1104,self.hp)
        self.b(self.hp+0x28,2);self.p(self.hud+8,self.player);self.p(self.hud+0x354,self.idle)
        self.p(self.hud+0xdc,0x300ae800);self.p(0x300ae828,SERVICES['window_find']);self.p(0x300ae804,SERVICES['window_add']);self.b(self.hud+0xd8,1);self.p(self.hud+0xd0,1)
        self.p(self.hud,self.hud+0x100);self.p(self.hud+0x168,SERVICES['hide']);self.p(self.hud+0xd4,0x300e8000)
        self.p(self.sm,self.sm+0x400);self.p(self.sm+0x434,SERVICES['state_notify']);self.p(self.sm+0x34,self.hud)
        self.p(self.sm+0x20,self.idle);self.p(self.sm+0x10,self.sm+0x200);self.p(self.sm+0x14,3)
        for i,(obj,identity,entry,leave) in enumerate([(self.idle,0,base+0x32cf70,base+0x32cf70),(self.modal,2,base+0x54c970,base+0x54cb20),(self.name_modal,10,base+0x5536e0,base+0x5537b0)]):
            self.p(self.sm+0x204+8*i,obj);self.p(obj,obj+0x300);self.p(obj+8,identity);self.p(obj+12,self.sm)
            self.p(obj+0x33c,entry);self.p(obj+0x340,leave)
        self.p(self.unit_sm+0x20,self.unit_state);self.p(self.unit_sm+0x34,self.hud)
        self.p(self.unit_state+12,self.unit_sm);self.p(self.unit_state,self.unit_state+0x300);self.p(self.unit_state+0x324,SERVICES['type'])
        self.p(self.unit,self.unit+0x100);self.p(self.unit+0x124,SERVICES['type']);self.p(self.unit+0x10,101);self.b(self.unit+0x60c,2)
        self.p(self.unit+0x258,60);self.p(self.unit+0x418,55);self.p(self.unit+0x48c,1)
        self.set_name('Old Name')
        self.b(self.setup+0xc,1);self.p(self.setup+8,0x12345678);self.p(self.setup+0x1c,self.setup+0x300)
        self.p(self.setup+0x20,1);self.p(self.setup+0x304,self.sp);self.b(self.sp+0x4c,2)
        self.b(self.sp+0x181,1);self.p(self.sp+0x24,1)
        self.p(self.sim+0x16c,self.auto_world);self.p(self.auto_world+0x3414,self.tactical);self.p(self.tactical+0x2e20,self.results)
        self.p(self.sim,self.sim+0x200);self.p(self.sim+4,1)
        for off,n in [(0x40,'deactivate'),(0x38,'deinit'),(0xc,'delete')]:self.p(self.sim+0x200+off,SERVICES[n])
        self.p(self.command,self.command+0x200);self.p(self.command+4,1);self.p(self.command+0x20c,SERVICES['delete'])
        self.p(self.results+0x4c,self.results+0x300);self.p(self.results+0x50,1);self.p(self.results+0x304,self.rp)
        self.b(self.rp+8,2);self.b(self.rp+0x28,1);self.b(self.rp+0x2a,1)
        self.current_heap=0x300e0000;self.original_heap=self.current_heap
        self.p(self.current_heap,self.current_heap+0x200);self.p(self.current_heap+0x230,SERVICES['valid'])
        self.p(base+0xcd0d3c,1)
        for rva,name in [(0xad8184,'tls_get'),(0xad80c8,'tls_set'),(0xad803c,'module'),(0xad8044,'proc'),(0xad8090,'enter_cs'),(0xad8094,'leave_cs')]:self.p(base+rva,SERVICES[name])
        self.stopped=False;self.stop_at=None;self.actions=True;self.unit_type=True;self.lookup=True;self.ports=[]
        self.u.hook_add(UC_HOOK_CODE,self.hook)
    def p(self,a,v):self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
    def b(self,a,v):self.u.mem_write(a,bytes([v]))
    def d(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
    def byte(self,a):return self.u.mem_read(a,1)[0]
    def narrow(self,a):
        out=bytearray()
        while a and self.byte(a):out.append(self.byte(a));a+=1
        return out.decode()
    def wide(self,a):
        out=bytearray()
        while a and self.u.mem_read(a,2)!=b'\0\0':out+=self.u.mem_read(a,2);a+=2
        return out.decode('utf-16le')
    def alloc(self,n):
        p=self.next_alloc;self.next_alloc+=(n+15)&~15;self.allocations[p]=n;return p
    def string(self,s,wide=False):
        b=s.encode('utf-16le' if wide else 'utf8')+(b'\0\0' if wide else b'\0');p=self.alloc(len(b));self.u.mem_write(p,b);return p
    def set_name(self,s):
        p=self.string(s,True);self.p(self.unit+0x550+8,p);self.p(self.unit+0x550+12,len(s))
    def ret(self,pop=0,value=0):
        sp=self.u.reg_read(UC_X86_REG_ESP);target=self.d(sp);self.u.reg_write(UC_X86_REG_EAX,value)
        self.u.reg_write(UC_X86_REG_ESP,sp+4+pop);self.u.reg_write(UC_X86_REG_EIP,target)
    def parse(self,buffer):
        at=self.d(buffer);end=at+self.d(buffer+4)
        while at<end:
            op=self.d(at);at+=4
            def text():
                nonlocal at
                n=self.d(at);at+=4;s=self.u.mem_read(at,n).decode('utf8');at+=n;return s
            # Native serialization is verified below; strings have byte counts.
            if op in (1,2,5,7,8):
                key=text()
                if op==1:self.commands.append(('call',key,self.byte(at)));at+=1
                elif op==2:self.commands.append(('open',key))
                elif op==5:self.vars[key]=self.d(at);at+=4
                elif op==8:self.vars[key]=self.byte(at);at+=1
                else:
                    n=self.d(at);at+=4;self.vars[key]=bytes(self.u.mem_read(at,n*2)).decode('utf-16le');at+=n*2
            elif op in (3,11,27):self.commands.append(('op',op))
            else:raise AssertionError(f'Unknown command {op} at {at-4:x}')
        assert at==end
    def hook(self,u,a,size,_):
        sp=u.reg_read(UC_X86_REG_ESP);ecx=u.reg_read(UC_X86_REG_ECX);eax=u.reg_read(UC_X86_REG_EAX);r=a-self.base
        if a==STOP:self.stopped=True;u.emu_stop();return
        if a==self.stop_at:u.emu_stop();return
        if a in SERVICES.values():
            name=next(k for k,v in SERVICES.items() if v==a)
            if name=='tls_get':self.ret(4,self.current_heap)
            elif name=='tls_set':self.current_heap=self.d(sp+8);self.ret(8,1)
            elif name=='valid':self.ret(value=1)
            elif name=='type':self.ret(4,int(self.unit_type))
            elif name in ('deactivate','deinit'):self.events.append(name);self.ret()
            elif name=='delete':self.events.append('delete:'+('sim' if ecx==self.sim else 'command'));self.ret(4)
            elif name=='hide':self.events.append('hide:'+self.narrow(self.d(sp+4)));self.ret(4)
            elif name=='state_notify':self.p(self.hud+0x354,self.d(sp+4));self.ret(8)
            elif name=='module':self.ret(4,STOP+0x800)
            elif name=='proc':self.ret(8,SERVICES['dialog'])
            elif name=='dialog':self.events.append('fallback');self.ret(16,self.answer)
            elif name=='window_find':self.ret(4,0xffffffff)
            elif name=='window_add':self.ports.append(self.narrow(self.d(sp+4)));self.ret(8)
            elif name in ('enter_cs','leave_cs'):self.ports.append(name);self.ret(4)
            else:raise AssertionError(name)
        elif r==0xde360:
            old=self.d(sp+4);n=u.reg_read(UC_X86_REG_EDI)
            if n:
                p=self.alloc(n)
                if old:self.u.mem_write(p,bytes(self.u.mem_read(old,min(n,self.allocations.get(old,0)))));self.allocations.pop(old,None)
            else:p=0;self.allocations.pop(old,None)
            self.ret(value=p)
        elif r==0x1862e0:self.allocations.pop(u.reg_read(UC_X86_REG_EDI),None);self.ret()
        elif r==0x25170:raise AssertionError('wrong memcpy address')
        elif r==0xa50170:
            dest,src,n=[self.d(sp+4+i*4) for i in range(3)];self.u.mem_write(dest,bytes(self.u.mem_read(src,n)));self.ret(value=dest)
        elif r==0x65f810:assert self.d(sp+4)==self.player;self.ret(4,int(self.actions))
        elif r==0xedc20:
            assert eax==self.world+0x31fc
            out,key=self.d(sp+4),self.d(sp+8);assert self.d(key)==101
            node=self.world+0x800;self.p(node+12,self.unit);self.p(out,node if self.lookup else self.d(self.world+0x3200));self.ret(8,out)
        elif r==0x267da0:raise AssertionError('wrong show address')
        elif r==0x147960:
            self.parse(self.d(sp+8));self.ret(8)
        elif r==0x4dccd0:
            helper=self.d(sp+4);controller=ecx
            assert self.d(helper+12)==self.hud and self.d(helper+0x34)==self.setup
            assert self.d(self.pending+40)==1
            self.events.append('panels');self.parse(controller+8);self.ret(4)
        elif r==0x5af920:
            assert self.d(sp+4)==self.hud+0x38b8
            self.events.append('sound' if self.d(sp+8) else 'indicator-hide');self.ret(8)
        elif r==0x684c20:
            assert u.reg_read(UC_X86_REG_EDX)==self.manager and ecx==self.results
            self.events.append('commit');self.ret()
        elif r==0x102880:self.events.append('sim-cleanup');self.ret(4)
        elif r==0x7c8c10:
            assert u.reg_read(UC_X86_REG_ESI)==self.manager
            self.events.append('idle');self.p(self.manager+0x94,0);self.ret()
        elif r==0x6827d0:
            assert self.d(sp+4)==self.manager and self.byte(self.setup+12)==0
            self.events.append('manual');self.ret(4)
        elif r==0x682970:raise AssertionError('AUTOCOMBAT REROLL')
        elif r==0x638a60:self.events.append(('report',[self.d(sp+4+i*4) for i in range(7)]));self.ret(28)
        elif r==0x545430:raise AssertionError('wrong RVA')
    def invoke(self,rva,args=(),this=0,pop=0,regs=None,stop=None):
        self.stopped=False;self.stop_at=stop
        values={r:0x12345678+i*0x11111111 for i,r in enumerate(REGS)}
        if regs:values.update(regs)
        for r,v in values.items():self.u.reg_write(r,v)
        self.u.reg_write(UC_X86_REG_ECX,this);self.u.reg_write(UC_X86_REG_ESP,STACK);self.p(STACK,STOP)
        for i,v in enumerate(args):self.p(STACK+4+i*4,v)
        try:self.u.emu_start(self.base+rva,0,count=1000000)
        except Exception as e:raise AssertionError(f'{e}; EIP={self.u.reg_read(UC_X86_REG_EIP):x}, RVA={self.u.reg_read(UC_X86_REG_EIP)-self.base:x}') from e
        if stop:assert self.u.reg_read(UC_X86_REG_EIP)==stop
        else:
            assert self.stopped,'Instruction limit reached'
            assert self.u.reg_read(UC_X86_REG_ESP)==STACK+4+pop
            for r in REGS:
                v=values[r]
                assert self.u.reg_read(r)==v,(r,hex(self.u.reg_read(r)),hex(v))
        return self.u.reg_read(UC_X86_REG_EAX)
    def begin(self):self.invoke(SYMS['n_close_ac'],this=self.manager)
    def choose(self,op):self.invoke(SYMS['native_modal'],(self.modal,self.base,op))
    def tick(self):self.invoke(SYMS['native_tick'],(self.manager,self.base))

class NormalTests(unittest.TestCase):
    def test_tooltip_health_matches_preview_bar_without_changing_units(self):
        cases=[('alive',19,70),('dead-id',19,70),('dead-snapshot',19,70),
               ('alive',999,70),('alive',-1,70),('alive',37,0)]
        for base in (0x400000,0x10000000,0x80000000):
            for kind,hp,maximum in cases:
                with self.subTest(base=base,kind=kind,hp=hp,maximum=maximum):
                    m=Machine(base);m.begin();data=m.unit+0x230;r=m.alloc(0x400);buf=m.alloc(8)
                    m.p(data+0x18,m.unit);m.p(r+0x3d8,101);m.p(r+0x30,maximum);m.p(r+0x1f0,hp)
                    m.p(buf+4,r)
                    if kind=='alive':m.p(m.results+0x24,buf);m.p(m.results+0x28,1)
                    if kind=='dead-snapshot':m.p(m.results+0x38,buf);m.p(m.results+0x3c,1)
                    if kind=='dead-id':m.p(m.results+0x14,1);m.p(m.results+0x18,buf);m.p(buf,101)
                    helper=m.alloc(60);c=m.alloc(20);m.p(helper+12,m.hud);m.p(c,base+0xb0850c);m.p(c+4,1)
                    m.p(m.pending+40,1);m.vars.update(unitCurrHp=55,unitMaxHp=60)
                    before=bytes(m.u.mem_read(m.unit,0x700)),bytes(m.u.mem_read(r,0x400))
                    m.invoke(SYMS['native_unit'],(helper,base,c,m.unit));m.parse(c+8)
                    expected=(m.vars['unitCurrHp'],m.vars['unitMaxHp'])
                    frame=STACK+0x800;m.p(frame+8,c);m.u.reg_write(UC_X86_REG_EFLAGS,0x246)
                    m.invoke(0x4c6774,regs={UC_X86_REG_EBX:data,UC_X86_REG_EBP:frame},stop=base+0xf1e70)
                    sp=m.u.reg_read(UC_X86_REG_ESP)
                    self.assertEqual((m.d(sp+8),m.d(sp+12)),expected)
                    self.assertEqual(m.wide(m.d(sp+4)),'%d/%d[hp/]');self.assertEqual(m.u.reg_read(UC_X86_REG_ESI),c)
                    self.assertEqual(m.u.reg_read(UC_X86_REG_EBX),data);self.assertEqual(m.u.reg_read(UC_X86_REG_EBP),frame)
                    self.assertEqual(m.u.reg_read(UC_X86_REG_EFLAGS)&0xcd5,0x246&0xcd5)
                    self.assertEqual((bytes(m.u.mem_read(m.unit,0x700)),bytes(m.u.mem_read(r,0x400))),before)

    def test_tooltip_health_keeps_unrelated_native_values(self):
        for guard in ('no-preview','not-rendering','unmatched','detached'):
            m=Machine();m.begin();data=m.unit+0x230;r=m.alloc(0x400);buf=m.alloc(8)
            m.p(data+0x18,m.unit);m.p(r+0x3d8,101);m.p(r+0x30,70);m.p(r+0x1f0,19)
            m.p(buf+4,r);m.p(m.results+0x24,buf);m.p(m.results+0x28,1);m.p(m.pending+40,1)
            if guard=='no-preview':m.p(m.pending+28,0)
            if guard=='not-rendering':m.p(m.pending+40,0)
            if guard=='unmatched':m.p(m.unit+0x10,999)
            if guard=='detached':m.p(data+0x18,0)
            frame=STACK+0x800;m.p(frame+8,m.alloc(20))
            m.invoke(0x4c6774,regs={UC_X86_REG_EBX:data,UC_X86_REG_EBP:frame},stop=m.base+0xf1e70)
            sp=m.u.reg_read(UC_X86_REG_ESP);self.assertEqual((m.d(sp+8),m.d(sp+12)),(55,60))

    def test_preview_manual_accept_and_aslr(self):
        for base in (0x400000,0x10000000,0x80000000):
            for manual in (True,False):
                with self.subTest(base=base,manual=manual):
                    m=Machine(base);m.begin()
                    self.assertEqual(m.events,['panels','sound']);self.assertEqual(m.d(m.manager+0x84),m.sim)
                    m.choose(3);m.choose(4 if manual else 5);m.tick()
                    self.assertEqual(m.events.count('sound'),1)
                    self.assertEqual(m.events.count('commit'),0 if manual else 1)
                    self.assertIn('manual' if manual else 'idle',m.events)
                    self.assertEqual(m.d(m.setup+8),0x12345678)
                    self.assertEqual(m.d(m.manager+0x84),0);self.assertEqual(m.d(m.manager+0x7c),0)
                    self.assertEqual(m.current_heap,m.original_heap);self.assertEqual(m.d(0),0xdeadbeef)
                    self.assertEqual(m.d(m.pending),0);self.assertEqual(m.d(m.pending+0x80),0)
    def test_rename_click_submit(self):
        for base in (0x400000,0x80000000):
            m=Machine(base);token=m.string('__aow3_rename_unit_v064__')
            m.invoke(0x53f610,(token,32,1),this=m.unit_state,pop=12)
            self.assertEqual(m.d(m.rename),1);self.assertNotIn(token,m.allocations)
            self.assertEqual(m.d(m.sm+0x28),m.name_modal)
            # Native name OnEntry is tested separately; open callback runs after it.
            m.p(m.sm+0x28,0);m.p(m.sm+0x20,m.name_modal);m.p(m.hud+0x354,m.name_modal)
            m.invoke(SYMS['rename_opened'],(m.name_modal,base))
            self.assertEqual(m.vars['CurrentUnitName'],'Old Name')
            inp=m.alloc(16);m.p(inp+8,m.string('  New Éowyn 星  ',True))
            m.invoke(0x553390,(m.name_modal,inp),pop=8)
            self.assertEqual(m.wide(m.d(m.unit+0x558)),'New Éowyn 星')
            self.assertEqual(m.d(m.sm+0x28),m.idle)
            self.assertEqual(m.byte(m.unit_state+0xf8),1)
    def test_single_player_and_participant_guards(self):
        changes=[('network',0x50,1),('network',0x50,2),('auto',12,0),('replay',0x190,1),('controller',0x78,1),('local',0x181,0),('stacks',0x24,0),('participant',0x2a,0)]
        for what,offset,value in changes:
            with self.subTest(what=what,value=value):
                m=Machine()
                obj={'network':m.players,'auto':m.setup,'replay':m.setup,'controller':m.sp,'local':m.sp,'stacks':m.sp,'participant':m.rp}[what]
                (m.b if what in ('auto','local','participant') else m.p)(obj+offset,value)
                m.begin();self.assertNotIn('panels',m.events);self.assertNotIn('fallback',m.events)
                self.assertIn('commit',m.events);self.assertNotIn('manual',m.events)
    def test_timeout_and_no_second_autocombat(self):
        for answer in (4,2):
            m=Machine();m.answer=answer;m.begin()
            m.choose(4);m.tick();self.assertNotIn('manual',m.events)
            m.p(m.pending+36,179);m.tick()
            self.assertEqual(m.events.count('sound'),1);self.assertEqual(m.events.count('fallback'),1)
            self.assertIn('manual' if answer==4 else 'commit',m.events)
    def test_original_fallback(self):
        for answer in (4,2):
            m=Machine(ui=False);m.answer=answer;m.begin()
            self.assertIn('fallback',m.events);self.assertNotIn('panels',m.events)
            self.assertIn('manual' if answer==4 else 'commit',m.events)
    def test_native_modal_button_hooks(self):
        for hook,reg,choice in [(0x54e0d0,UC_X86_REG_EAX,1),(0x54e1d0,UC_X86_REG_EAX,2),(0x54e300,UC_X86_REG_EAX,2)]:
            m=Machine();m.begin();m.choose(3)
            m.invoke(hook,regs={reg:m.modal});self.assertEqual(m.d(m.pending+32),choice)
        m=Machine();m.begin();m.invoke(0x54d620,this=m.modal);self.assertEqual(m.events,['panels','sound'])
        m.invoke(0x54cb20,(0,),this=m.modal,pop=4);self.assertEqual(m.d(m.pending+32),2)
    def test_ready_and_world_tick_hooks(self):
        m=Machine();m.begin()
        m.invoke(SYMS['ready_hook'],regs={UC_X86_REG_EDI:m.modal},stop=m.base+0x54ea7f)
        self.assertEqual(m.d(m.pending+28),2)
        m.choose(5)
        m.invoke(SYMS['world_tick_hook'],regs={UC_X86_REG_EAX:m.manager},stop=m.base+0x682d80)
        self.assertIn('commit',m.events)
    def test_report_hook_exact_scope(self):
        for matches in (True,False):
            m=Machine();g=m.pending+0x80
            for i,v in enumerate([m.manager,m.results,m.setup,m.hp]):m.p(g+4*i,v)
            frame=0x7000f000;m.p(frame+8,m.manager)
            args=[m.hp+0x1700,m.results,m.setup,0x300d0000,1,0,1]
            if not matches:args[2]+=4
            m.invoke(SYMS['combat_report_hook'],args,pop=28,regs={UC_X86_REG_EBX:m.hp,UC_X86_REG_EBP:frame})
            expected=args[:];expected[-1]=0 if matches else 1
            self.assertEqual(m.events[-1],('report',expected))
    def test_result_units_hook_routes_only_pending_render(self):
        for active in (False,True):
            m=Machine();helper=m.alloc(60);m.p(helper+12,m.hud)
            if active:m.p(m.pending+28,2);m.p(m.pending+16,m.hud);m.p(m.pending+40,1)
            target=m.base+(0x4ddee0 if active else 0x4de3f5)
            m.invoke(0x4de3f0,(helper,0,0,0),stop=target)
    def test_snapshot_health_rank_conversion_and_xp(self):
        m=Machine();m.begin();helper=m.alloc(60);c=m.alloc(20);m.p(helper+12,m.hud)
        # Keep native constructor and native Iggy serialization, mock only delivery.
        m.p(c,m.base+0xb0850c);m.p(c+4,1);m.p(m.pending+40,1)
        result=m.alloc(0x400);m.p(result+0x3d8,101);m.p(result+0x30,70);m.p(result+0x1f0,19)
        m.p(result+0x264,2);m.p(result+0x270,37);m.b(result+0x3dd,7)
        buf=m.alloc(8);m.p(buf+4,result);m.p(m.results+0x24,buf);m.p(m.results+0x28,1)
        resource=m.alloc(0x500);tier=m.alloc(0x200)
        for data in (result+8,m.unit+0x230):m.p(data+8,resource)
        m.p(resource+0x48c,1);m.b(resource+0x490,1);m.p(resource+0x494,tier)
        m.p(tier+0x9c+3*4,80)
        # GetTier's cached UnitResource getter is 0x910d20; actual resource links execute.
        m.invoke(SYMS['native_unit'],(helper,m.base,c,m.unit))
        m.parse(c+8)
        self.assertEqual(m.vars['unitCurrHp'],19);self.assertEqual(m.vars['unitMaxHp'],70)
        self.assertEqual(m.vars['level'],2);self.assertEqual(m.vars['levelUp'],1);self.assertEqual(m.vars['isMindControlled'],1)
        self.assertEqual(m.vars['xp'],'Experience: 37 / 80')
        self.assertEqual(m.d(m.unit+0x418),55);self.assertEqual(m.d(m.unit+0x48c),1)
        self.assertEqual(m.byte(m.unit+0x60c),2)
    def test_native_name_entry_and_exit(self):
        m=Machine();token=m.string('__aow3_rename_unit_v064__')
        m.invoke(0x53f610,(token,32,1),this=m.unit_state,pop=12)
        m.p(m.sm+0x28,0);m.p(m.sm+0x20,m.name_modal)
        m.invoke(0x5536e0,(m.idle,),this=m.name_modal,pop=4)
        self.assertEqual(m.vars['CurrentUnitName'],'Old Name');self.assertIn(('op',27),m.commands)
        self.assertIn(('call','BeginUnitRename',1),m.commands)
        m.invoke(0x5537b0,(m.idle,),this=m.name_modal,pop=4);self.assertEqual(m.d(m.rename),0)
    def test_rename_rejects_invalid_context(self):
        for change in ('network','owner','snapshot','no-selection','not-found','not-allowed'):
            m=Machine();token=m.string('__aow3_rename_unit_v064__')
            if change=='network':m.p(m.players+0x50,1)
            elif change=='owner':m.b(m.unit+0x60c,7)
            elif change=='snapshot':m.p(m.player+0x33c,m.unit+0x230)
            elif change=='no-selection':m.p(m.player+0x334,0)
            elif change=='not-found':m.lookup=False
            else:m.actions=False
            m.invoke(0x53f610,(token,32,1),this=m.unit_state,pop=12)
            self.assertEqual(m.d(m.rename),0,change)
    def test_rename_keeps_identity_and_rejects_bad_text(self):
        for bad in ('','   ','A'*81,'Bad\nName'):
            m=Machine();token=m.string('__aow3_rename_unit_v064__')
            m.invoke(0x53f610,(token,32,1),this=m.unit_state,pop=12)
            m.invoke(SYMS['rename_opened'],(m.name_modal,m.base))
            inp=m.alloc(16);m.p(inp+8,m.string(bad,True))
            m.invoke(0x553390,(m.name_modal,inp),pop=8)
            self.assertEqual(m.wide(m.d(m.unit+0x558)),'Old Name');self.assertEqual(m.d(m.rename),2)
        m=Machine();token=m.string('__aow3_rename_unit_v064__')
        m.invoke(0x53f610,(token,32,1),this=m.unit_state,pop=12);m.invoke(SYMS['rename_opened'],(m.name_modal,m.base))
        m.p(m.player+0x334,0);inp=m.alloc(16);m.p(inp+8,m.string('Captured Unit',True))
        m.invoke(0x553390,(m.name_modal,inp),pop=8)
        self.assertEqual(m.wide(m.d(m.unit+0x558)),'Captured Unit')
    def test_unrelated_name_and_ability_passthrough(self):
        m=Machine();inp=m.alloc(16)
        m.invoke(0x553390,(m.name_modal,inp),stop=m.base+0x553395)
        token=m.string('NormalAbility')
        m.invoke(0x53f610,(token,32,1),this=m.unit_state,stop=m.base+0x53f615)
        self.assertIn(token,m.allocations)
    def test_panel_hook_serializes_eligibility(self):
        m=Machine();helper=m.alloc(40);c=m.alloc(20)
        m.p(helper+8,m.string('HUD_FloatingHeroBackground'));m.p(helper+12,m.hud);m.p(helper+16,m.unit+0x230)
        m.p(c,m.base+0xb0850c);m.p(c+4,1)
        m.invoke(SYMS['rename_panel_hook'],(m.string('UpdateDataObject'),1),pop=8,regs={UC_X86_REG_EAX:c,UC_X86_REG_EBX:helper})
        m.parse(c+8);self.assertEqual(m.vars['CanRenameUnit'],1);self.assertEqual(m.commands[-1],('call','UpdateDataObject',1))
    def test_telemetry_abi(self):
        m=Machine()
        for rva in (0x30bfa0,0x30cb80):
            m.b(m.unit+8,1);self.assertEqual(m.invoke(rva,(m.unit,0),pop=8),0x80004005);self.assertEqual(m.byte(m.unit+8),0)

if __name__=='__main__':unittest.main()
