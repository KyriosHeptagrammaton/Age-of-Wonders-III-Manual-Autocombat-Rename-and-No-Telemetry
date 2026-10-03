/* Hooks inside this build's EnterCloseAC. Reuse the attack-position local
 * only while it is not needed; clear it after the native accepted-result
 * branch. The original stack frame, SEH and security cookie stay intact. */
.intel_syntax noprefix
.code32
.section .text
.global retry_entry, retry_finish, retry_accept_done
.extern retry_decide, close_ac_resume, close_ac_cleanup, close_ac_epilogue
.extern close_ac_commit
.extern battle_set_state, set_current_heap

retry_entry:
    pushfd
    pushad
    call retry_base
retry_base:
    pop eax
    sub eax, offset retry_base
    push eax                    /* runtime module base */
    push ecx                    /* original battle manager */
    call retry_decide
    add esp, 8
    mov [ebp - 0x1c], eax        /* 0 accept, 1 manual, 2 pending, 3 already notified */
    popad
    popfd
    mov esi, ecx                /* displaced instructions */
    mov ecx, [esi + 0xbc]
    cmp dword ptr [ebp - 0x1c], 2
    je close_ac_epilogue        /* keep setup/simulation/results alive */
    cmp dword ptr [ebp - 0x1c], 3
    je retry_notified_accept
    cmp dword ptr [ebp - 0x1c], 0
    jne close_ac_cleanup        /* omit notification/result commit */
    jmp close_ac_resume

retry_notified_accept:
    /* Same tactical-world lookup as original RVA 6dc24d..6dc25f. The preview
     * already delivered the HUD-only finish notification. Resume directly
     * at the unchanged heap-selection/result-commit block; EDI is its sole
     * live input besides ESI (manager). No RNG or battle setup is touched. */
    mov eax, [esi + 0xa0]
    mov eax, [eax + 0x188]
    mov edi, [eax + 0x34fc]
    jmp close_ac_commit

retry_accept_done:
    /* Called in place of the final heap restore on the accept branch.
     * Its original cdecl argument/return address remain on the stack. */
    mov dword ptr [ebp - 0x1c], 0
    jmp set_current_heap

retry_finish:
    mov eax, [ebp - 0x1c]
    cmp eax, 1
    jne retry_accept
    mov edx, [esi + 0xb0]        /* retained TTacticalSetupData */
    mov byte ptr [edx + 0x0c], 0 /* FAutoCombat -> manual */
    mov byte ptr [esi + 0x118], 1 /* native manual-combat telemetry flag */
    jmp retry_transition
retry_accept:
    xor eax, eax
retry_transition:
    push eax
    mov ecx, esi
    call battle_set_state       /* 1 opens TC, 0 clears setup; seed unchanged */
    jmp close_ac_epilogue

.section .note.GNU-stack,"",@progbits
