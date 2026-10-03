/* Exact normal-build adapters. Offsets and custom register ABIs are recorded
 * in PORTING.md. Relative payload calls remain valid under image relocation. */
extern ptr TC n_find(ptr,int);
extern ptr TC n_hex_player(ptr);
extern u8 TC n_actions(ptr);
extern ptr TC n_hud(ptr);
extern void TC n_call(ptr,const char *,int);
extern void TC n_open(ptr,const char *);
extern void TC n_wide(ptr,const char *,const wch *);
extern void TC n_bool(ptr,const char *,int);
extern void TC n_int(ptr,const char *,int);
extern void TC n_end(ptr);
extern void TC n_focus(ptr);
extern void TC n_push(ptr,const char *,ptr);
extern void TC n_state(ptr,int,int);
extern void n_free(ptr);
extern void TC n_name(ptr,ptr);
extern void TC n_narrow(ptr,ptr);
extern void TC n_assign(ptr,ptr);
extern void TC n_refresh(ptr,ptr);
extern void TC n_list_dispose(ptr);
extern void TC n_buffer_dispose(ptr);
extern void TC n_show(ptr,const char *,int);
extern void TC n_notify(ptr,ptr,ptr);
extern void TC n_close_ac(ptr);
extern ptr TC n_tier(ptr);
extern int TC n_threshold(ptr,int);
extern void TC n_setup(ptr,const char *,ptr,ptr,int,int,int);
extern void TC n_flush(ptr,ptr);
static __attribute__((unused)) void n_controller(u32 base,ptr p) {
    u32 *v=p; v[0]=base+0xb0850c;v[1]=1;v[2]=v[3]=v[4]=0;
}
static __attribute__((unused)) void n_helper(u32 base,ptr p) {
    u32 *v=p;u32 i;for(i=0;i<15;++i)v[i]=0;
    v[0]=base+0xb59a1c;v[1]=1;v[4]=0xffffffff;
    v[5]=v[9]=base+0xae5ce4;
}
