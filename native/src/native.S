.intel_syntax noprefix
.code32
.section .text
.extern native_begin, native_modal, native_tick, native_forget
.extern native_result_units, native_unit
.extern native_skip_report, combat_complete
.extern ui_entry_resume, ui_exit_resume, ui_refresh_resume
.extern manual_resume, auto_resume, ready_resume, ready_done
.extern retreat_resume, retreat_done, get_hud
.extern world_tick_resume, manager_dtor_resume
.extern result_units_resume, setup_units, iggy_call

.macro base
    call .Lbase\@
.Lbase\@:
    pop eax
    sub eax, offset .Lbase\@
.endm

/* All interception probes preserve native flags, registers and ABI. */
.macro probe operation
    pushfd
    pushad
    base
    push \operation
    push eax
    push ecx
    call native_modal
    add esp,12
    test eax,eax
.endm
.macro restore
    popad
    popfd
.endm

.global combat_report_hook
combat_report_hook:
    /* Called at TriggerPlayerEvents RVA 6d65ec. EDI is battle manager, ESI
     * strategic player; seven native stack arguments must survive intact
     * except AutoOpen at entry ESP+24 when the exact acceptance scope matches. */
    pushfd
    pushad
    base
    lea edx,[esp+40]            /* original first argument: results */
    push dword ptr [edx+4]      /* setup */
    push dword ptr [edx]        /* results */
    push esi                   /* strategic player */
    push eax                   /* image base */
    push edi                   /* battle manager */
    call native_skip_report
    add esp,20
    test eax,eax
    jz 1f
    mov dword ptr [esp+60],0    /* AutoOpen only */
1:  restore
    jmp combat_complete        /* original constructor and history insertion */

.global ui_entry_hook
ui_entry_hook:
    probe 0
    jz 1f
    restore
    ret 4
1:  restore
    push ebp
    mov ebp,esp
    mov eax,[ebp+8]
    jmp ui_entry_resume

.global ui_exit_hook
ui_exit_hook:
    probe 1
    jz 1f
    restore
    ret 4
1:  restore
    push ebp
    mov ebp,esp
    push esi
    mov esi,ecx
    jmp ui_exit_resume

.global ui_refresh_hook
ui_refresh_hook:
    probe 2
    jz 1f
    restore
    ret
1:  restore
    push ebp
    mov ebp,esp
    push -1
    jmp ui_refresh_resume

.global manual_hook
manual_hook:
    probe 4
    jz 1f
    restore
    ret
1:  restore
    push ebp
    mov ebp,esp
    sub esp,8
    jmp manual_resume

.global auto_hook
auto_hook:
    probe 5
    jz 1f
    restore
    ret
1:  restore
    push ebp
    mov ebp,esp
    sub esp,12
    jmp auto_resume

.global ready_hook
ready_hook:
    pushfd
    pushad
    base
    push 3
    push eax
    push esi
    call native_modal
    add esp,12
    test eax,eax
    jz 1f
    restore
    add esp,0x1c          /* original Lua argument cleanup */
    jmp ready_done
1:  restore
    mov ecx,[esi+0x154]
    jmp ready_resume

.global retreat_hook
retreat_hook:
    pushfd
    pushad
    base
    push 5
    push eax
    push esi
    call native_modal
    add esp,12
    test eax,eax
    jz 1f
    restore
    jmp retreat_done
1:  restore
    mov ecx,esi
    call get_hud
    jmp retreat_resume

.global world_tick_hook
world_tick_hook:
    pushfd
    pushad
    base
    push eax
    lea ecx,[esi+0x2eb0]
    push ecx
    call native_tick
    add esp,8
    restore
    mov eax,[esi+0x2eb8]
    jmp world_tick_resume

.global manager_dtor_hook
manager_dtor_hook:
    pushfd
    pushad
    base
    push eax
    push ecx
    call native_forget
    add esp,8
    restore
    push ebp
    mov ebp,esp
    push -1
    jmp manager_dtor_resume

.global result_units_hook
result_units_hook:
    pushfd
    pushad
    base
    push eax
    push ecx
    call native_result_units
    add esp,8
    test eax,eax
    jz 1f
    restore
    jmp setup_units
1:  restore
    push ebp
    mov ebp,esp
    push -1
    jmp result_units_resume

.global unit_hook
unit_hook:
    pushfd
    pushad
    base
    push dword ptr [ebp-0x44]  /* unit; EDI may now contain its level */
    push esi                  /* controller */
    push eax
    push dword ptr [ebp-0x10]  /* helper */
    call native_unit
    add esp,16
    restore
    jmp iggy_call              /* keep native CallFunction return/arguments */

.global tooltip_health_hook
tooltip_health_hook:
    /* Original tooltip: ESI=live UnitData, ECX=max HP, EDX=current HP.
       Only the two saved argument registers may be changed by the probe. */
    mov ecx,[esi+0x28]
    mov edx,[esi+0x1e8]
    pushfd
    pushad
    mov edx,esp
    base
    lea ecx,[edx+20]
    push ecx
    lea ecx,[edx+24]
    push ecx
    push eax
    push esi
    call native_tooltip_health
    add esp,16
    restore
    jmp tooltip_health_resume

.section .note.GNU-stack,"",@progbits
