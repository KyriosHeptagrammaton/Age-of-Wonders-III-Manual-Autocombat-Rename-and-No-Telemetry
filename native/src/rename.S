/* Experimental AoW3_Debug.exe unit-name command. GNU as, x86, Intel syntax.
 * All external values are RVAs, not preferred or runtime addresses.
 * Link .text at 0x00fc2000. Relative calls move with the game's ASLR base.
 * No new Windows imports, runtime, writable globals, or PE relocations.
 */
.intel_syntax noprefix
.code32
.section .text
.global patch_entry, handle_command
.extern original_resume, get_hud, can_generate_actions, strategic_cheats
.extern assign_narrow, assign_wide, close_window, message_box_iat
.extern stack_get_unit

patch_entry:
    pushfd
    pushad
    mov ecx, [esp + 24]           /* original this */
    mov edx, [esp + 40]           /* original TEWString& argument */
    push edx
    push ecx
    call handle_command
    add esp, 8
    test eax, eax
    jz pass_through
    popad
    popfd
    ret 4
pass_through:
    popad
    popfd
    /* Exactly the five bytes displaced from TCheatWindowMHS::EnterCheat. */
    push ebp
    mov ebp, esp
    push -1
    jmp original_resume

/* cdecl int handle_command(TCheatWindowMHS*, const TEWString*).
 * Return zero for ordinary commands; one if our command was consumed.
 */
handle_command:
    push ebp
    mov ebp, esp
    push ebx
    push esi
    push edi
    sub esp, 8                    /* [ebp-16]: player; [ebp-20]: unit index */
    call get_base
get_base:
    pop ebx
    sub ebx, offset get_base      /* actual loaded image base */
    mov esi, [ebp + 12]
    test esi, esi
    jz not_ours
    mov esi, [esi + 8]            /* TEWString wchar_t* */
    test esi, esi
    jz not_ours
    xor eax, eax
match_keyword:
    movzx ecx, word ptr [esi + eax*2]
    or ecx, 0x20                 /* ASCII case-insensitive keyword only */
    movzx edx, byte ptr [ebx + command + eax]
    cmp ecx, edx
    jne not_ours
    inc eax
    cmp eax, 10
    jb match_keyword
    movzx ecx, word ptr [esi + 20]
    test ecx, ecx
    jz usage_error
    cmp ecx, 32
    jne not_ours                  /* do not consume 'renameunits', etc. */
    add esi, 20
skip_slot_space:
    add esi, 2
    cmp word ptr [esi], 32
    je skip_slot_space
    /* A required 1-based army position removes the dependency on the
     * individual detail panel, which prevents opening the cheat window.
     * Bound the result to signed int, then check the live army's length.
     */
    xor eax, eax
parse_slot:
    movzx edx, word ptr [esi]
    cmp edx, '0'
    jb usage_error
    cmp edx, '9'
    ja usage_error
    imul eax, eax, 10
    jo usage_error
    sub edx, '0'
    add eax, edx
    jo usage_error
    add esi, 2
    cmp word ptr [esi], 32
    jne parse_slot
    test eax, eax
    jz usage_error
    dec eax
    mov [ebp - 20], eax
skip_name_space:
    add esi, 2
    cmp word ptr [esi], 32
    je skip_name_space
    xor eax, eax
check_name:
    movzx ecx, word ptr [esi + eax*2]
    test ecx, ecx
    jz end_name
    cmp ecx, 32
    jb usage_error
    cmp ecx, 127
    je usage_error
    inc eax
    cmp eax, 80
    ja usage_error
    jmp check_name
end_name:
    test eax, eax
    jz usage_error

    mov ecx, [ebp + 8]
    test ecx, ecx
    jz context_error
    call get_hud
    test eax, eax
    jz context_error
    mov edi, [eax + 8]            /* THUD::player */
    test edi, edi
    jz context_error
    mov eax, [edi]
    lea edx, [ebx + strategic_cheats]
    cmp [eax + 0x108], edx        /* require this build's TPlayerS */
    jne context_error
    mov [ebp - 16], edi
    mov eax, [edi + 0xf8]         /* TPlayer::manager */
    test eax, eax
    jz context_error
    cmp dword ptr [eax + 0x50], 0 /* local single-player connection */
    jne network_error
    mov ecx, edi
    call can_generate_actions
    test al, al
    jz context_error
    mov eax, [ebp - 16]
    mov edi, [eax + 0x238]        /* selected army, as used by HAUER */
    test edi, edi
    jz selection_error
    mov eax, [edi]
    mov ecx, edi
    push 0x0047142c               /* TStackE class ID */
    call dword ptr [eax + 0x24]
    test al, al
    jz selection_error
    mov eax, [ebp - 20]
    cmp eax, [edi + 0x254]        /* live army unit count */
    jge slot_error
    push eax
    mov ecx, edi
    call stack_get_unit          /* engine resolves the indexed reference */
    mov edi, eax
    test edi, edi
    jz selection_error
    mov eax, [edi]
    mov ecx, edi
    push 0x00471429               /* TUnitE class ID; allows subclasses */
    call dword ptr [eax + 0x24]   /* IsOfType */
    test al, al
    jz selection_error
    add edi, 0x230                /* embedded TUnitData */

    /* Use the engine allocator/string methods. Clear localization tags so
     * loading cannot replace a custom name with its old localized text.
     * Whole requested name goes in first-name; last-name becomes empty.
     */
    push 0
    lea ecx, [edi + 0x314]
    call assign_narrow
    push esi
    lea ecx, [edi + 0x320]
    call assign_wide
    push 0
    lea ecx, [edi + 0x370]
    call assign_narrow
    push 0
    lea ecx, [edi + 0x37c]
    call assign_wide
    lea eax, [ebx + success_message]
    jmp report
usage_error:
    lea eax, [ebx + usage_message]
    jmp report
context_error:
    lea eax, [ebx + context_message]
    jmp report
network_error:
    lea eax, [ebx + network_message]
    jmp report
selection_error:
    lea eax, [ebx + selection_message]
    jmp report
slot_error:
    lea eax, [ebx + slot_message]
report:
    push 0x40                    /* MB_OK | MB_ICONINFORMATION */
    lea edx, [ebx + title]
    push edx
    push eax
    push 0
    call dword ptr [ebx + message_box_iat]
    mov ecx, [ebp + 8]
    test ecx, ecx
    jz consumed
    mov ecx, [ecx + 12]
    test ecx, ecx
    jz consumed
    push 1
    push 0
    call close_window            /* same closure as original EnterCheat */
consumed:
    mov eax, 1
    jmp done
not_ours:
    xor eax, eax
done:
    add esp, 8
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret

command: .asciz "renameunit"
title: .asciz "AoW3 unit-name prototype v0.2"
success_message:
    .asciz "Unit name changed. Reselect the unit to refresh its panel.\nSave to a new slot, then reload to check that the name persists."
usage_message:
    .asciz "Select an army on the strategic map. Keep unit details closed.\nEnter: renameunit 2 Your Chosen Name\n\n2 selects the second portrait (count from 1).\nUse 1-80 UTF-16 code units for the name; no control characters."
context_message:
    .asciz "Use renameunit on the strategic map during your active turn."
network_message:
    .asciz "This experimental command supports local single-player games only."
selection_message:
    .asciz "Select an army on the strategic map, then enter:\nrenameunit 1 Your Chosen Name\n\nKeep the individual unit-details panel closed."
slot_message:
    .asciz "That unit position is outside the selected army.\nCount its portraits from 1 and use:\nrenameunit 2 Your Chosen Name"

.section .note.GNU-stack,"",@progbits
