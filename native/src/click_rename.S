.intel_syntax noprefix
.code32
.section .text
.extern rename_click, rename_panel, rename_opened, rename_closed, rename_submit
.extern rename_click_resume, rename_click_done, rename_submit_resume
.extern rename_exit_resume, iggy_call

.macro base
    call .Lbase\@
.Lbase\@:
    pop eax
    sub eax, offset .Lbase\@
.endm

.global rename_click_hook
rename_click_hook:
    pushfd
    pushad
    mov edx,eax               /* native Lua string, before TEString ctor */
    base
    push edx
    push eax
    push edi                 /* native resolved TUnitHS */
    call rename_click
    add esp,12
    test eax,eax
    jz 1f
    popad
    popfd
    add esp,0x1c             /* all seven original Lua argument words */
    jmp rename_click_done
1:  popad
    popfd
    add esp,0x10             /* leave space for original by-value TEString */
    mov ecx,esp
    jmp rename_click_resume

.global rename_panel_hook
rename_panel_hook:
    pushfd
    pushad
    mov edx,ecx              /* original Iggy controller */
    base
    push edx
    push eax
    push esi                 /* original TUnitPanelInterfaceHelper */
    call rename_panel
    add esp,12
    popad
    popfd
    jmp iggy_call            /* queue EndUpdate after the eligibility flag */

.global rename_opened_hook
rename_opened_hook:
    pushfd
    pushad
    base
    push eax
    push esi                 /* modal in original OnEntry epilogue */
    call rename_opened
    add esp,8
    popad
    popfd
    pop esi
    pop ebp
    ret 4

.global rename_exit_hook
rename_exit_hook:
    pushfd
    pushad
    base
    push eax
    push ecx
    call rename_closed
    add esp,8
    popad
    popfd
    push ebp
    mov ebp,esp
    mov eax,[ebp+8]
    jmp rename_exit_resume

.global rename_submit_hook
rename_submit_hook:
    pushfd
    pushad
    mov edx,[esp+40]          /* const TEWString& */
    base
    push edx
    push eax
    push ecx
    call rename_submit
    add esp,12
    test eax,eax
    jz 1f
    popad
    popfd
    ret 4
1:  popad
    popfd
    push ebp
    mov ebp,esp
    push -1
    jmp rename_submit_resume

.section .note.GNU-stack,"",@progbits
