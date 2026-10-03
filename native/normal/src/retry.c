/* Exact-build, single-player autocombat preview. No CRT or writable globals.
 * Every game address below is an RVA, verified against the supplied EXE.
 * This runs BEFORE any strategic result processing. No save format changes.
 */
typedef unsigned int u32;
typedef unsigned char u8;
typedef unsigned short wch;
typedef void *ptr;
#define TC __attribute__((thiscall))
#define WC __attribute__((stdcall))
#define WORD(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define BYTE(p,o) (*(u8 *)((u8 *)(p)+(o)))
#define PTR(p,o) (*(ptr *)((u8 *)(p)+(o)))
#include "engine.h"
#define IMP(type,rva) (*(type *)(base+(rva)))

typedef ptr (TC *Find)(ptr, int);
typedef u8 (TC *IsType)(ptr, int);
typedef void (TC *GetName)(ptr, ptr);
typedef void (TC *Notify)(ptr, ptr, ptr);
typedef void (*Free)(ptr);
typedef ptr (WC *GetModule)(const char *);
typedef ptr (WC *GetProc)(ptr, const char *);
typedef int (WC *Message)(ptr, const wch *, const wch *, u32);
extern int native_begin(ptr,u32,ptr,ptr,ptr,ptr);

/* Keep the dialog bounded even for large armies / unusually long mod names.
 * The local frame is < 4 KiB; no stack-probe or runtime support is needed. */
typedef struct { wch text[1400]; u32 n; } Text;
static void ch(Text *t, wch c) {
    if (t->n < 1399) t->text[t->n++] = c;
    t->text[t->n] = 0;
}
static void ascii(Text *t, const char *s) {
    while (*s) ch(t, (u8)*s++);
}
static void number(Text *t, u32 n) {
    char b[10]; u32 i=0;
    do { b[i++] = '0'+n%10; n/=10; } while (n);
    while (i) ch(t,b[--i]);
}
static void wide_name(Text *t, const wch *s) {
    u32 i=0;
    if (!s || !*s) { ascii(t,"Unnamed unit"); return; }
    for (; s[i] && i<80; ++i) ch(t, s[i]<32 ? ' ' : s[i]);
    if (s[i]) ascii(t,"...");
}
static int list_ok(ptr list, u32 limit) {
    u32 count=WORD(list,0x0c);
    return count<=limit && (!count || PTR(list,8));
}
static ptr item(ptr list, u32 n) { return PTR(PTR(list,8), n*8+4); }

static ptr strategic_unit(u32 base __attribute__((unused)), ptr world, u32 id) {
    ptr unit=n_find((u8 *)world+0x31dc,
                             (int)id);
    if (!unit) return 0;
    IsType is_type=(IsType)PTR(PTR(unit,0),0x24);
    return is_type(unit,0x471429) ? unit : 0;
}

/* The native result has ordinary dead IDs plus separate resurrection
 * snapshots. Include both in the fallback's reported-casualty summary. */
static ptr dead_unit(u32 base __attribute__((unused)),ptr world,ptr results,u32 n) {
    u32 count=WORD(results,0x14);
    if (n<count) return strategic_unit(base,world,WORD(PTR(results,0x18),4*n));
    ptr r=item((u8 *)results+0x30,n-count);
    return r ? strategic_unit(base,world,WORD(r,0x3d8)) : 0;
}

/* cdecl: called from retry.S with all original registers saved. */
int retry_decide(ptr manager, u32 base __attribute__((unused))) {
    ptr hex,world,players,setup,simulation,tactical,results,sp=0,rp=0;
    u32 id,i,own_dead=0,shown=0,total_dead;
    Text t;
    t.n=0; t.text[0]=0;
    if (!manager || WORD(manager,8)!=5) return 0;
    hex=PTR(manager,0xa0);
    if (!hex || !(BYTE(hex,0x2cdc)&8)) return 0;
    world=PTR(hex,0x28);
    if (!world) return 0;
    players=PTR(world,0x408);
    if (!players || WORD(players,0x50)!=0) return 0; /* single-player */
    setup=PTR(manager,0x94);
    if (!setup || BYTE(setup,0x0c)!=1 || WORD(setup,0x190)!=0) return 0;
    if (!list_ok((u8 *)setup+0x14,256)) return 0;
    id=BYTE(hex,0x3c);
    for (i=0;i<WORD(setup,0x20);++i) {
        ptr p=item((u8 *)setup+0x14,i);
        if (p && BYTE(p,0x4c)==id) { sp=p; break; }
    }
    if (!sp || WORD(sp,0x78)!=0 || !BYTE(sp,0x181) || !WORD(sp,0x24)) return 0;
    simulation=PTR(manager,0x84);
    if (!simulation || !(tactical=PTR(simulation,0x16c))) return 0;
    tactical=PTR(tactical,0x3414);
    if (!tactical || !(results=PTR(tactical,0x2e20))) return 0;
    if (!list_ok((u8 *)results+0x44,256)
        || !list_ok((u8 *)results+0x30,16384)
        || !list_ok((u8 *)results+0x1c,16384)
        || WORD(results,0x14)>16384
        || (WORD(results,0x14) && !PTR(results,0x18))) return 0;
    for (i=0;i<WORD(results,0x50);++i) {
        ptr p=item((u8 *)results+0x44,i);
        if (p && BYTE(p,8)==id) { rp=p; break; }
    }
    if (!rp || !BYTE(rp,0x2a)) return 0; /* actual combat participant */

    int native=native_begin(manager,base,world,setup,results,rp);
    if (native>=0) return native;
    /* A timed-out native preview has already delivered its completion sound.
     * Keep that fact on this call's stack, including failed dialog APIs. */
    int accept=native==-2 ? 3 : 0;

    /* Resolve W API before doing any UI or mutation. No DLL is installed. */
    ptr user=IMP(GetModule,0xad803c)("user32.dll");
    if (!user) return accept;
    Message message=(Message)IMP(GetProc,0xad8044)(user,"MessageBoxW");
    if (!message) return accept;

    ascii(&t,BYTE(rp,0x28) ? "Autocombat: VICTORY\r\n" : "Autocombat: NO VICTORY\r\n");
    total_dead=WORD(results,0x14)+WORD(results,0x3c);
    for (i=0;i<total_dead;++i) {
        ptr unit=dead_unit(base,world,results,i);
        if (unit && BYTE(unit,0x60c)==id) ++own_dead;
    }
    ascii(&t,"Your units in the dead-unit report: "); number(&t,own_dead);
    ascii(&t,"\r\nAll sides: "); number(&t,total_dead);
    ascii(&t," reported dead, "); number(&t,WORD(results,0x28));
    ascii(&t," reported surviving.\r\n");
    if (own_dead) {
        ascii(&t,"\r\nYour reported casualties:\r\n");
        for (i=0;i<total_dead && shown<8;++i) {
            ptr unit=dead_unit(base,world,results,i);
            if (!unit || BYTE(unit,0x60c)!=id) continue;
            u32 name[4]={0,0,0,0};
            n_name((u8 *)unit+0x230,name);
            ascii(&t,"  - "); wide_name(&t,(const wch *)name[2]); ascii(&t,"\r\n");
            /* Same free routine used by TEWString::SetCapacity(0). */
            if (name[2] && (int)name[3]>0) n_free((ptr)name[2]);
            ++shown;
        }
        if (own_dead>shown) {
            ascii(&t,"  ... plus "); number(&t,own_dead-shown); ascii(&t," more\r\n");
        }
    }
    ascii(&t,"\r\nThese are simulation reports; post-battle resurrection and other\r\neffects are applied only if you accept.\r\n\r\nRetry this battle manually?\r\n\r\nRETRY = discard this result and FIGHT MANUALLY.\r\nCANCEL = ACCEPT this result and continue.");
    static const wch title[]={'A','o','W','3',' ','-',' ','A','u','t','o','c','o','m','b','a','t',' ','r','e','t','r','y',0};
    /* MB_RETRYCANCEL | MB_ICONQUESTION | MB_DEFBUTTON2 |
     * MB_SETFOREGROUND | MB_TASKMODAL. Cancel/X/Esc/failure accepts. */
    int answer=message(0,t.text,title,0x12125);
    int choice=answer==4 ? 1 : 0; /* IDRETRY: manual only; never reroll. */
    if (!choice) return accept;
    /* With a null result, this exact native method only hides the combat
     * indicator for each HUD; it does not play a victory/defeat sound.
     * Verified C01080 -> A36930 -> 983900 -> 98399D. */
    n_notify(world,0,0);
    return choice;
}
