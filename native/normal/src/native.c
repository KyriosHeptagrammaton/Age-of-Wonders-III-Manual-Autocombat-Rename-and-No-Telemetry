/* Native, asynchronous autocombat decision screen for the exact normal build.
 * Uses the existing modal state and original results SWF. The simulation and
 * setup stay owned by the battle manager until a decision. No campaign edits,
 * fake history events, save-format extensions, or random-number generation.
 */
typedef unsigned int u32;
typedef unsigned char u8;
typedef unsigned short wch;
typedef void *ptr;
#define TC __attribute__((thiscall))
#define WORD(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define BYTE(p,o) (*(u8 *)((u8 *)(p)+(o)))
#define PTR(p,o) (*(ptr *)((u8 *)(p)+(o)))
#include "engine.h"
#define STATE_RVA 0xf28000

typedef struct {
    ptr manager, setup, results, world, hud, sm, modal;
    u32 phase, choice, ticks, rendering, won;
} Pending;
/* Loader-zeroed, non-executable writable section; no absolute relocations. */
#define PENDING ((Pending *)(base+STATE_RVA))
/* Separate from the pending modal and rename state. This guard exists only
 * during the synchronous EnterCloseAC call resolving a displayed preview. */
typedef struct { ptr manager,results,setup,player; } ReportGuard;
#define REPORT_GUARD ((ReportGuard *)(base+STATE_RVA+0x80))
enum { WAIT_UI=1, READY=2, RESOLVE=3, FALLBACK=4 };
enum { MANUAL=1, ACCEPT=2 };

typedef ptr (TC *Get)(ptr);
typedef void (TC *Void)(ptr);
typedef void (TC *One)(ptr,ptr);
typedef void (TC *Call)(ptr,const char *,int);
typedef void (TC *Open)(ptr,const char *);
typedef void (TC *VarInt)(ptr,const char *,int);
typedef void (TC *VarWide)(ptr,const char *,const wch *);
typedef void (TC *Setup)(ptr,const char *,ptr,ptr,int,int,int);
typedef void (TC *SetState)(ptr,int,int);
typedef void (TC *Notify)(ptr,ptr,ptr);
typedef int (TC *IndexedInt)(ptr,int);
extern void rename_forget(ptr,u32);

static ptr item(ptr list,u32 n) { return PTR(PTR(list,8),8*n+4); }
static int list_ok(ptr list,u32 limit) {
    return WORD(list,12)<=limit && (!WORD(list,12) || PTR(list,8));
}
static void clear(Pending *p) {
    u32 i;
    for (i=0;i<sizeof(*p)/4;++i) ((u32 *)p)[i]=0;
}
static void clear_report(ReportGuard *g) {
    g->manager=0;g->results=0;g->setup=0;g->player=0;
}
static int matches(Pending *p,ptr modal) {
    return p->phase && modal && modal==p->modal;
}
static void call(u32 base __attribute__((unused)),ptr c,const char *name) {
    n_call(c,name,1);
}
static void integer(u32 base __attribute__((unused)),ptr c,const char *key,int n) {
    n_int(c,key,n);
}
static void boolean(u32 base __attribute__((unused)),ptr c,const char *key,int n) {
    n_bool(c,key,n);
}
static void wide(u32 base __attribute__((unused)),ptr c,const char *key,const wch *s) {
    n_wide(c,key,s);
}
static void ascii(u32 base __attribute__((unused)),ptr c,const char *key,const char *s) {
    wch buffer[192];u32 n=0;
    while (s[n] && n<191) { buffer[n]=(u8)s[n];++n; }
    buffer[n]=0;wide(base,c,key,buffer);
}
static void dispose(u32 base __attribute__((unused)),ptr helper,ptr controller) {
    n_list_dispose((u8 *)helper+0x24);
    n_list_dispose((u8 *)helper+0x14);
    n_buffer_dispose((u8 *)controller+8);
}
static void init(u32 base __attribute__((unused)),Pending *p,ptr helper,ptr controller) {
    n_controller(base,controller);
    n_helper(base,helper);
    n_setup(helper,"HUD_CombatResults",p->hud,p->setup,0,0,0);
}
static void render(u32 base __attribute__((unused)),Pending *p) {
    u32 c[5],h[15];
    if (p->rendering) return;
    p->rendering=1;
    init(base,p,h,c);
    call(base,c,"BeginRetryPreview");
    call(base,c,"StartUpdate");
    n_open(c,"DataObject");
    ascii(base,c,"centerText","Autocombat");
    ascii(base,c,"bottomText",p->won ? "Victory" : "Defeat");
    ascii(base,c,"combatInfo","");
    boolean(base,c,"hero1Lost",0);
    boolean(base,c,"hero2Lost",0);
    boolean(base,c,"lastEventInList",1);
    /* Refresh supplies the engine's army panels, portraits and unit tooltips.
     * The two narrow unit-data hooks substitute uncommitted outcome values. */
    n_refresh(h,c);
    dispose(base,h,c);
    p->rendering=0;
}
static void hide(u32 base __attribute__((unused)),Pending *p) {
    u32 c[5],h[15];
    init(base,p,h,c);
    call(base,c,"EndRetryPreview");
    n_flush(h,c);
    dispose(base,h,c);
    Open hide_window=(Open)PTR(PTR(p->hud,0),0x68);
    hide_window(p->hud,"HUD_CombatResults");
    hide_window(p->hud,"HUD_SkillBook_Vignette");
}

/* Returns -1 for the old Windows fallback, -2 for fallback after the finish
 * notification, 1 manual, 2 pending, 3 accept without repeating notification. */
int native_begin(ptr manager,u32 base __attribute__((unused)),ptr world,ptr setup,ptr results,ptr rp) {
    Pending *p=PENDING;
    ptr players,player=0,hud=0,modal,sm,hp;
    u32 i,id=BYTE(PTR(manager,0xa0),0x3c);
    if (p->phase) {
        if (p->manager!=manager || p->setup!=setup || p->results!=results) return -1;
        if (p->phase==RESOLVE || p->phase==FALLBACK) {
            int choice=p->phase==FALLBACK ? -2 : (p->choice==MANUAL ? 1 : 3);
            clear(p);
            return choice;
        }
        return 2;
    }
    players=PTR(world,0x408);
    if (!players || !list_ok((u8 *)players+0xc,256)) return -1;
    for (i=0;i<WORD(players,0x18);++i) {
        player=item((u8 *)players+0xc,i);
        if (!player || !PTR(player,0x13c)) continue;
        hp=n_hex_player(player);
        if (hp && BYTE(hp,0x28)==id) { hud=PTR(player,0x13c);break; }
    }
    if (!hud || PTR(hud,8)!=player) return -1;
    modal=PTR(hud,0x354);
    if (!modal || WORD(modal,8)!=0 || !(sm=PTR(modal,0xc))) return -1;
    if (PTR(sm,0x34)!=hud || PTR(sm,0x20)!=modal || PTR(sm,0x28)
        || BYTE(sm,0x2c)) return -1;
    p->manager=manager;p->world=world;p->setup=setup;p->results=results;
    p->hud=hud;p->sm=sm;p->phase=WAIT_UI;p->won=BYTE(rp,0x28);
    n_state(sm,2,1);
    if (!p->modal || PTR(sm,0x20)!=p->modal) {
        clear(p);
        return -1;
    }
    /* This exact notification only plays the participant's native battle-roll
     * victory/defeat SFX and hides the indicator; it does not apply results.
     * Notify -> player HUDs -> TCombatIndicatorS::OnFinishAutoCombat.
     * Accept returns 3 so EnterCloseAC does not play it a second time. */
    n_notify(world,results,(u8 *)setup+0x54);
    return 2;
}

/* Called with all registers saved. Intercept only our pending modal. */
int native_modal(ptr modal,u32 base __attribute__((unused)),u32 operation) {
    Pending *p=PENDING;
    if (operation==0) { /* OnEntry */
        if (p->phase!=WAIT_UI || !modal || PTR(modal,0xc)!=p->sm
            || WORD(modal,8)!=2) return 0;
        p->modal=modal;
        n_show(p->hud,"HUD_CombatResults",0);
        n_show(p->hud,"HUD_SkillBook_Vignette",0);
        render(base,p);
        return 1;
    }
    if (!matches(p,modal)) return 0;
    if (operation==1) { /* OnExit, including keyboard/other native close */
        if (!p->choice) p->choice=ACCEPT;
        hide(base,p);
    } else if (operation==2) { /* Refresh; preview is immutable. */
        return 1;
    } else if (operation==3) { /* Only the patched SWF emits this handshake. */
        if (p->phase==WAIT_UI) p->phase=READY;
    } else if (operation==4 || operation==5) {
        if (!p->choice && p->phase==READY)
            p->choice=operation==4 ? MANUAL : ACCEPT;
    }
    return 1;
}

void native_tick(ptr manager,u32 base __attribute__((unused))) {
    Pending *p=PENDING;
    if (!p->phase || p->manager!=manager || p->phase>=RESOLVE) return;
    if (WORD(manager,8)!=5 || PTR(manager,0x94)!=p->setup) {
        /* A lifecycle transition owns the native object cleanup. */
        clear(p);return;
    }
    int timeout=p->phase==WAIT_UI && ++p->ticks>=180;
    if (!p->choice && !timeout) return;
    if (PTR(p->sm,0x20)==p->modal)
        n_state(p->sm,0,1);
    p->phase=timeout ? FALLBACK : RESOLVE;
    ReportGuard *g=REPORT_GUARD;
    g->manager=manager;g->results=p->results;
    /* TriggerPlayerEvents uses the retained report setup at +10c, which
     * need not be the same object as the simulation setup at +b0. */
    g->setup=PTR(manager,0xf0);
    g->player=n_hex_player(PTR(p->hud,8));
    n_close_ac(manager);
    clear_report(g);
}

void native_forget(ptr manager,u32 base __attribute__((unused))) {
    Pending *p=PENDING;
    if (p->manager==manager) clear(p);
    if (REPORT_GUARD->manager==manager) clear_report(REPORT_GUARD);
    rename_forget(manager,base);
}

/* The hook is only the participant CombatComplete call in TriggerPlayerEvents.
 * Suppress its AutoOpen argument for this exact preview's local player. The
 * original event construction, outcome data and AddEvent still execute. */
int native_skip_report(ptr manager,u32 base __attribute__((unused)),ptr player,ptr results,ptr setup) {
    ReportGuard *g=REPORT_GUARD;
    return g->manager && g->player && g->manager==manager
        && g->player==player && g->results==results && g->setup==setup;
}

int native_result_units(ptr helper,u32 base __attribute__((unused))) {
    Pending *p=PENDING;
    return p->phase && p->rendering && PTR(helper,0xc)==p->hud;
}

static char *digits(char *s,u32 n) {
    char reverse[10];u32 count=0;
    do { reverse[count++]=(char)('0'+n%10);n/=10; } while (n);
    while (count) *s++=reverse[--count];
    *s=0;return s;
}
static char *text(char *s,const char *value) {
    while (*value) *s++=*value++;
    *s=0;return s;
}
/* A result's embedded UnitData has no live context. Read its XP directly
 * and ask only the read-only tier lookup/medal arithmetic for the denominator.
 * Do not call the full XP/ability formatter, IsGhoul, activate a snapshot,
 * or change either the live unit or simulation to draw the preview. */
static void experience(u32 base __attribute__((unused)),ptr c,ptr unit,ptr result) {
    ptr live=(u8 *)unit+0x230,data=result ? (u8 *)result+8 : live,tier=0;
    char buffer[96],*s=buffer;
    u32 xp=WORD(data,0x268),level=WORD(data,0x25c);
    if (BYTE(live,0x270) || BYTE(live,0x271)) return;
    s=text(s,result ? "Experience: " : "Experience before battle: ");
    s=digits(s,xp);
    if (result && level<=1005 && !BYTE(data,0x270) && !BYTE(data,0x271)) {
        tier=n_tier(data);
        if (!tier && PTR(data,8)==PTR(live,8)) tier=n_tier(live);
        if (tier) {
            int next=n_threshold(tier,level<1005 ? (int)level+1 : 1005);
            if (next>0) { s=text(s," / ");digits(s,(u32)next); }
        }
    }
    ascii(base,c,"xp",buffer);
}

/* Shared by the result bar and the native tooltip's health line. */
static ptr unit_result(Pending *p,ptr unit,u32 *dead) {
    ptr result=0;u32 i,id=WORD(unit,0x10);
    *dead=0;
    /* Ordinary deaths are TEIntList entity IDs at results+8, not full
     * snapshots. Native KillDeadUnits reads count +0x14, buffer +0x18,
     * stride 4. The +0x30 object list covers resurrection candidates. */
    for (i=0;i<WORD(p->results,0x14);++i)
        if (WORD(PTR(p->results,0x18),4*i)==id) { *dead=1;break; }
    for (i=0;i<WORD(p->results,0x3c);++i) {
        ptr r=item((u8 *)p->results+0x30,i);
        if (r && WORD(r,0x3d8)==id) { result=r;*dead=1;break; }
    }
    if (!result) for (i=0;i<WORD(p->results,0x28);++i) {
        ptr r=item((u8 *)p->results+0x1c,i);
        if (r && WORD(r,0x3d8)==id) { result=r;break; }
    }
    return result;
}
static void result_health(ptr unit,ptr result,u32 dead,int *maximum,int *current) {
    if (result) {
        int max=(int)WORD(result,0x30),hp=(int)WORD(result,0x1f0);
        if (max<1) max=(int)WORD(unit,0x258);
        if (hp<0 || dead) hp=0;
        if (hp>max) hp=max;
        *maximum=max;*current=hp;
    } else if (dead) *current=0;
}

/* The native tooltip is formatted from the live unit so its resource/context
 * remain valid. Substitute only its two HP arguments during this preview.
 * No detached snapshot is passed to the full formatter, and no unit is edited. */
void native_tooltip_health(ptr data,u32 base,int *maximum,int *current) {
    Pending *p=PENDING;ptr unit,result;u32 dead;
    if (!p->phase || !p->rendering || !p->results || !data) return;
    unit=PTR(data,0x18);
    if (!unit || (u8 *)unit+0x230!=(u8 *)data) return;
    result=unit_result(p,unit,&dead);
    result_health(unit,result,dead,maximum,current);
}

void native_unit(ptr helper,u32 base,ptr c,ptr unit) {
    Pending *p=PENDING;
    ptr result;u32 dead;
    if (!unit || !native_result_units(helper,base)) return;
    result=unit_result(p,unit,&dead);
    /* Always clear values not supplied by the pre-combat helper, so a
     * previously viewed history event cannot leave stale result badges. */
    boolean(base,c,"levelUp",0);
    boolean(base,c,"isMindControlled",0);
    if (!result) {
        /* The original helper has already supplied this unit's portrait,
         * rank, max HP and tooltip. Zero HP selects the native death visual. */
        if (dead) { integer(base,c,"unitCurrHp",0);experience(base,c,unit,0); }
        return;
    }
    int max=(int)WORD(unit,0x258),hp=(int)WORD(unit,0x418);
    result_health(unit,result,dead,&max,&hp);
    integer(base,c,"unitMaxHp",max);
    integer(base,c,"unitCurrHp",hp);
    boolean(base,c,"isMindControlled",BYTE(result,0x3dd)!=BYTE(unit,0x60c));
    /* Keep the live helper's ghoul flag. The independent XP tooltip uses
     * snapshot scalars and resource data without the unsafe live formatter. */
    experience(base,c,unit,result);
    if (!BYTE(unit,0x4a0) && !BYTE(unit,0x4a0+1)) {
        integer(base,c,"level",WORD(result,0x264));
        boolean(base,c,"levelUp",WORD(result,0x264)>WORD(unit,0x48c));
    }
}
