/* Click-to-rename for the exact supplied debug executable.  All addresses
 * are RVAs. Names use the existing serialized TUnitData personal-name fields.
 * UI input never becomes an army index or a resource/type name edit. */
typedef unsigned int u32;
typedef unsigned char u8;
typedef unsigned short wch;
typedef void *ptr;
#define TC __attribute__((thiscall))
#define WORD(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define BYTE(p,o) (*(u8 *)((u8 *)(p)+(o)))
#define PTR(p,o) (*(ptr *)((u8 *)(p)+(o)))
#define FN(type,rva) ((type)(base+(rva)))

typedef ptr (TC *Get)(ptr);
typedef ptr (TC *Find)(ptr,int);
typedef u8 (TC *IsType)(ptr,int);
typedef u8 (TC *Allowed)(ptr);
typedef void (TC *Void)(ptr);
typedef void (TC *One)(ptr,ptr);
typedef void (TC *Open)(ptr,const char *);
typedef void (TC *Call)(ptr,const char *,int);
typedef void (TC *Bool)(ptr,const char *,int);
typedef void (TC *Wide)(ptr,const char *,const wch *);
typedef void (TC *Push)(ptr,const char *,ptr);
typedef void (TC *State)(ptr,int,int);
typedef void (*Free)(ptr);

enum { REQUESTED=1, EDITING=2, CLOSING=3 };
typedef struct {
    u32 phase;
    ptr hud,player,world,sm,modal,unit_state,unit_sm,unit;
    u32 id;
} Rename;
/* Battle-preview state occupies the first 48 bytes of .aowdata. */
#define RENAME ((Rename *)(base+0xfc8040))

static void clear(Rename *p) {
    u32 i;for (i=0;i<sizeof(*p)/4;++i) ((u32 *)p)[i]=0;
}
static int equal(const char *a,const char *b) {
    if (!a || !b) return 0;
    while (*a && *a==*b) { ++a;++b; }
    return *a==*b;
}
static int is_type(ptr p,int id) {
    return p && ((IsType)PTR(PTR(p,0),0x24))(p,id);
}
/* Use the current engine-owned selection only to find an ID. Resolve that
 * ID through the world's entity manager before editing any unit data. */
static ptr player_context(u32 base,ptr hud) {
    ptr player,manager;
    if (!hud || !(player=PTR(hud,8))) return 0;
    if (WORD(PTR(player,0),0x108)!=base+0x63a820) return 0;
    manager=PTR(player,0xf8);
    if (!manager || WORD(manager,0x50) || !PTR(player,0xf4)) return 0;
    if (!FN(Allowed,0x635c00)(player)) return 0;
    return player;
}
static ptr owned_unit(u32 base,ptr player,u32 id,ptr expected) {
    ptr unit,hp;
    unit=FN(Find,0x2eed60)((u8 *)PTR(player,0xf4)+0x32c4,(int)id);
    if (!unit || unit!=expected || !is_type(unit,0x471429) || WORD(unit,0x10)!=id) return 0;
    hp=FN(Get,0x5f37e0)(player);
    return hp && BYTE(unit,0x60c)==BYTE(hp,0x28) ? unit : 0;
}
static ptr target(u32 base,ptr hud) {
    ptr player=player_context(base,hud),selected;
    if (!player || PTR(player,0x364)) return 0;
    selected=PTR(player,0x35c);
    if (!selected) return 0;
    return owned_unit(base,player,WORD(selected,0x10),selected);
}
static ptr idle_machine(ptr hud) {
    ptr modal,sm;
    if (!hud || !(modal=PTR(hud,0x37c)) || WORD(modal,8)) return 0;
    sm=PTR(modal,0xc);
    if (!sm || PTR(sm,0x34)!=hud || PTR(sm,0x20)!=modal
        || PTR(sm,0x28) || BYTE(sm,0x2c)) return 0;
    return sm;
}
static void send(u32 base,ptr hud,ptr c,const char *callback) {
    FN(Call,0x194ae0)(c,callback,1);
    FN(Push,0x2c7280)(hud,"HUD_NameChanger",(u8 *)c+8);
    FN(Void,0x15de20)((u8 *)c+8);
}
static int same_context(u32 base,Rename *p,ptr modal) {
    return p->phase && p->modal==modal && modal &&
        PTR(modal,0xc)==p->sm && FN(Get,0x5ea5f0)(modal)==p->hud;
}
static ptr same_unit(u32 base,Rename *p) {
    ptr player=player_context(base,p->hud);
    if (player!=p->player || !player || PTR(player,0xf4)!=p->world) return 0;
    /* The dialog owns the original identity. Selection and floating-panel
     * state are transient and must not silently invalidate confirmation.
     * Resolve first: never dereference an expired captured entity pointer. */
    return owned_unit(base,player,p->id,p->unit);
}

static void unavailable(u32 base,Rename *p) {
    u32 c[5];
    FN(Void,0x194a10)(c);send(base,p->hud,c,"UnitRenameUnavailable");
}

static void refresh_name(u32 base,Rename *p,ptr unit,const wch *name) {
    u32 c[5];
    if (PTR(p->unit_sm,0x20)!=p->unit_state || PTR(p->player,0x35c)!=unit
        || PTR(p->player,0x364)) return;
    BYTE(p->unit_state,0x120)=1;
    FN(Void,0x194a10)(c);
    FN(Open,0x195420)(c,"UnitPanelDataObject");
    FN(Wide,0x1957f0)(c,"UnitName",name);
    FN(Void,0x190770)(c);
    FN(Call,0x194ae0)(c,"UnitRenameApplied",1);
    FN(Push,0x2c7280)(p->hud,"HUD_FloatingHeroBackground",(u8 *)c+8);
    FN(Void,0x15de20)((u8 *)c+8);
}

/* Called immediately before the original helper's EndUpdate is queued.
 * Only this root window receives the additional, opt-in UI property. */
void rename_panel(ptr helper,u32 base,ptr controller) {
    ptr hud,unit;
    int allowed;
    if (!equal(PTR(helper,8),"HUD_FloatingHeroBackground")) return;
    hud=PTR(helper,0xc);
    unit=target(base,hud);
    allowed=unit && PTR(helper,0x10)==(u8 *)unit+0x230
        && idle_machine(hud) && !RENAME->phase;
    FN(Open,0x195420)(controller,"UnitPanelDataObject");
    FN(Bool,0x195910)(controller,"CanRenameUnit",allowed);
    FN(Void,0x190770)(controller);
}

/* The existing string callback supplies a reserved UI action. Consume only
 * this exact token; all ordinary ability clicks follow the original ABI. */
int rename_click(ptr unit_state,u32 base,const char *action) {
    Rename *p=RENAME;
    ptr hud,unit,sm,unit_sm;
    if (!equal(action,"__aow3_rename_unit_v064__")) return 0;
    if (p->phase || !unit_state) return 1;
    if (!is_type(unit_state,0x472451) && !is_type(unit_state,0x472453)) return 1;
    hud=FN(Get,0x5ea5f0)(unit_state);
    if (!(sm=idle_machine(hud)) || !(unit=target(base,hud))) return 1;
    unit_sm=PTR(unit_state,0xc);
    if (!unit_sm || PTR(unit_sm,0x20)!=unit_state || PTR(unit_sm,0x34)!=hud) return 1;
    p->hud=hud;p->player=PTR(hud,8);p->world=PTR(p->player,0xf4);
    p->sm=sm;p->unit_state=unit_state;p->unit_sm=unit_sm;
    p->unit=unit;p->id=WORD(unit,0x10);p->phase=REQUESTED;
    /* Same deferred modal transition used by the city's NameClicked. */
    FN(State,0x138320)(sm,10,0);
    return 1;
}

/* Runs after the native name dialog and vignette have been shown. */
void rename_opened(ptr modal,u32 base) {
    Rename *p=RENAME;
    ptr unit;u32 name[4]={0,0,0,0},c[5];wch empty[1]={0};
    if (p->phase!=REQUESTED || !modal || WORD(modal,8)!=10
        || PTR(modal,0xc)!=p->sm || FN(Get,0x5ea5f0)(modal)!=p->hud) return;
    p->modal=modal;p->phase=EDITING;
    unit=same_unit(base,p);
    if (!unit) { unavailable(base,p);return; }
    FN(One,0x7c27c0)((u8 *)unit+0x230,name);
    FN(Void,0x194a10)(c);
    /* ShowWindow(..., false) does not give this movie the game's keyboard
     * focus. Stage.focus inside the SWF only chooses a field within it.
     * Queue the original GiveFocus command before the AS3 setup callback. */
    FN(Void,0x190570)(c);
    FN(Open,0x195420)(c,"UnitRenameData");
    FN(Wide,0x1957f0)(c,"CurrentUnitName",name[2] ? (const wch *)name[2] : empty);
    FN(Void,0x190770)(c);
    send(base,p->hud,c,"BeginUnitRename");
    if (name[2] && (int)name[3]>0) FN(Free,0x1137b0)((ptr)name[2]);
}

/* Unit input is bounded and copied before any assignment. This also rejects
 * forged UI callbacks and keeps input valid if it aliases an old name. */
static int copy_name(wch *out,const wch *s) {
    u32 n=0;
    if (!s) return 0;
    while (*s==32) ++s;
    for (;*s;++s) {
        if (*s<32 || *s==127 || n==80) return 0;
        out[n++]=*s;
    }
    while (n && out[n-1]==32) --n;
    out[n]=0;return n!=0;
}

int rename_submit(ptr modal,u32 base,ptr input) {
    Rename *p=RENAME;
    ptr unit,data;wch name[81];u32 c[5];
    if (!same_context(base,p,modal)) return 0;
    if (p->phase!=EDITING) return 1;
    unit=same_unit(base,p);
    if (!unit) { unavailable(base,p);return 1; }
    if (!input || !copy_name(name,PTR(input,8))) {
        FN(Void,0x194a10)(c);send(base,p->hud,c,"UnitRenameRejected");return 1;
    }
    p->phase=CLOSING;
    data=(u8 *)unit+0x230;
    FN(One,0x116880)((u8 *)data+0x314,0);
    FN(One,0x139250)((u8 *)data+0x320,name);
    FN(One,0x116880)((u8 *)data+0x370,0);
    FN(One,0x139250)((u8 *)data+0x37c,0);
    refresh_name(base,p,unit,name);
    FN(State,0x138320)(p->sm,0,0);
    return 1;
}

void rename_closed(ptr modal,u32 base) {
    Rename *p=RENAME;
    if (!same_context(base,p,modal)) return;
    if (PTR(p->unit_sm,0x20)==p->unit_state) BYTE(p->unit_state,0x120)=1;
    clear(p);
}

void rename_forget(ptr manager,u32 base) {
    Rename *p=RENAME;
    ptr hex=manager ? PTR(manager,0xbc) : 0;
    if (p->phase && hex && PTR(hex,0x28)==p->world) clear(p);
}
