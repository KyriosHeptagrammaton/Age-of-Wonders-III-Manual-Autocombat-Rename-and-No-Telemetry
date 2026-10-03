/* Hooks for normal AoW3.exe SHA-256 9fd625d4... . No absolute VA operands. */
.intel_syntax noprefix
.code32
.section .text
.macro base
    call .Lbase\@
.Lbase\@:
    pop eax
    sub eax,offset .Lbase\@
.endm
.macro save
    pushfd
    pushad
.endm
.macro restore
    popad
    popfd
.endm
.macro probe operation,reg
    save
    mov edx,\reg
    base
    push \operation
    push eax
    push edx
    call native_modal
    add esp,12
    test eax,eax
.endm
.global retry_entry
retry_entry:
    save
    base
    mov ebx,eax
    push eax
    push esi
    call retry_decide
    add esp,8
    mov [ebx+state_rva+0xc0],eax
    mov [ebx+state_rva+0xc4],esi
    cmp eax,2
    je 1f
    cmp eax,3
    je 2f
    test eax,eax
    jnz 3f
    restore
    mov edx,[esi+0xa0]
    jmp close_ac_resume
1:  restore
    jmp close_ac_epilogue
2:  restore
    mov eax,[esi+0x84]
    mov eax,[eax+0x16c]
    mov edi,[eax+0x3414]
    jmp close_ac_commit
3:  restore
    jmp close_ac_cleanup
.global retry_finish
retry_finish:
    base
    xor edx,edx
    cmp [eax+state_rva+0xc4],esi
    jne 1f
    cmp dword ptr [eax+state_rva+0xc0],1
    jne 1f
    mov ecx,[esi+0x94]
    mov byte ptr [ecx+0xc],0
    mov byte ptr [esi+0xfc],1
    mov edx,1
1:  mov dword ptr [eax+state_rva+0xc0],0
    mov dword ptr [eax+state_rva+0xc4],0
    push edx
    mov ecx,esi
    call battle_set_state
    jmp close_ac_epilogue
.global ui_entry_hook
ui_entry_hook:
    probe 0,ecx
    jz 1f
    restore
    ret 4
1:  restore
    push ebx
    push edi
    mov edi,ecx
    mov ecx,[edi+0xc]
    jmp ui_entry_resume
.global ui_exit_hook
ui_exit_hook:
    probe 1,ecx
    jz 1f
    restore
    ret 4
1:  restore
    push esi
    mov esi,ecx
    mov eax,[esi+0xc]
    jmp ui_exit_resume
.global ui_refresh_hook
ui_refresh_hook:
    probe 2,ecx
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
    probe 4,eax
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
    probe 5,eax
    jz 1f
    restore
    ret
1:  restore
    push ebp
    mov ebp,esp
    sub esp,12
    jmp auto_resume
.global retreat_hook
retreat_hook:
    probe 5,eax
    jz 1f
    restore
    ret
1:  restore
    push esi
    mov esi,eax
    mov eax,[esi+0xc]
    jmp retreat_resume
.global ready_hook
ready_hook:
    probe 3,edi
    jz 1f
    restore
    jmp ready_done
1:  restore
    mov ecx,[edi+0x12c]
    jmp ready_resume
.global world_tick_hook
world_tick_hook:
    save
    mov edx,eax
    base
    push eax
    push edx
    call native_tick
    add esp,8
    restore
    jmp engine_battle_update
.global manager_dtor_hook
manager_dtor_hook:
    save
    mov edx,[esp+40]
    base
    push eax
    push edx
    call native_forget
    add esp,8
    restore
    push ebp
    mov ebp,esp
    push -1
    jmp manager_dtor_resume
.global result_units_hook
result_units_hook:
    save
    mov edx,[esp+40]
    base
    push eax
    push edx
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
    save
    base
    push dword ptr [ebp-0x14]
    push dword ptr [ebp+12]
    push eax
    push dword ptr [ebp+8]
    call native_unit
    add esp,16
    restore
    mov eax,[ebx+4]
    mov ecx,[ebx+8]
    jmp unit_resume
.global combat_report_hook
combat_report_hook:
    save
    base
    /* Seven stdcall arguments: event manager, results, setup, list,
       winner, loser, AutoOpen. Only the participant call is hooked. */
    lea edx,[esp+40]
    push dword ptr [edx+8]
    push dword ptr [edx+4]
    push ebx
    push eax
    push dword ptr [ebp+8]
    call native_skip_report
    add esp,20
    test eax,eax
    jz 1f
    mov dword ptr [esp+64],0
1:  restore
    jmp combat_complete
.global rename_click_hook
rename_click_hook:
    save
    mov edx,[esp+40]
    base
    push edx
    push eax
    push ecx
    call rename_click
    add esp,12
    test eax,eax
    jz 1f
    /* Consume the by-value TEString and release its owned allocation using
       exactly the same capacity/ownership conditions as native AbilityClicked. */
    cmp dword ptr [esp+44],0
    je 2f
    cmp byte ptr [esp+48],0
    je 2f
    mov edi,[esp+40]
    call engine_free
2:  restore
    ret 12
1:  restore
    push ebp
    mov ebp,esp
    push -1
    jmp rename_click_resume
.global rename_panel_hook
rename_panel_hook:
    save
    mov edx,eax
    base
    push edx
    push eax
    push ebx
    call rename_panel
    add esp,12
    restore
    jmp engine_call
.global rename_opened_hook
rename_opened_hook:
    save
    base
    push eax
    push ebx
    call rename_opened
    add esp,8
    restore
    pop edi
    pop esi
    pop ebx
    ret 4
.global rename_exit_hook
rename_exit_hook:
    save
    base
    push eax
    push ecx
    call rename_closed
    add esp,8
    restore
    push esi
    mov esi,ecx
    mov eax,[esi+0xc]
    jmp rename_exit_resume
.global rename_submit_hook
rename_submit_hook:
    save
    lea edx,[esp+40]
    base
    push dword ptr [edx+4]
    push eax
    push dword ptr [edx]
    call rename_submit
    add esp,12
    test eax,eax
    jz 1f
    restore
    ret 8
1:  restore
    push ebp
    mov ebp,esp
    push -1
    jmp rename_submit_resume
.global telemetry_disabled
telemetry_disabled:
    mov eax,[esp+4]
    mov byte ptr [eax+8],0
    mov eax,0x80004005
    ret 8
.global tooltip_health_hook
tooltip_health_hook:
    /* Original tooltip: EBX=live UnitData, EAX=max HP, ECX=current HP. */
    mov eax,[ebx+0x28]
    mov ecx,[ebx+0x1e8]
    save
    mov edx,esp
    base
    lea ecx,[edx+24]
    push ecx
    lea ecx,[edx+28]
    push ecx
    push eax
    push ebx
    call native_tooltip_health
    add esp,16
    restore
    jmp tooltip_health_resume
.section .note.GNU-stack,"",@progbits
