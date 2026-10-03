.intel_syntax noprefix
.code32
.section .text
/* thiscall adapters around the normal build's LTCG register conventions. */
.macro eax_this name,target
.global \name
\name:
    mov eax,ecx
    jmp \target
.endm
.macro esi_this name,target
.global \name
\name:
    push esi
    mov esi,ecx
    call \target
    pop esi
    ret
.endm
eax_this n_call,engine_call
eax_this n_open,engine_open
eax_this n_wide,engine_wide
eax_this n_bool,engine_bool
eax_this n_int,engine_int
eax_this n_assign,engine_assign
eax_this n_hex_player,engine_hex_player
eax_this n_tier,engine_tier
esi_this n_end,engine_end
esi_this n_focus,engine_focus
esi_this n_close_ac,engine_close_ac
.global n_hud
n_hud: jmp engine_hud
.global n_actions
n_actions:
    push ecx
    call engine_actions
    ret
.global n_state
n_state:
    push esi
    mov esi,ecx
    mov edx,[esp+8]
    push dword ptr [esp+12]
    call engine_state
    pop esi
    ret 8
.global n_free
n_free:
    push edi
    mov edi,[esp+8]
    call engine_free
    pop edi
    ret
.global n_name
n_name:
    mov eax,[esp+4]
    call engine_name
    ret 4
.global n_narrow
n_narrow:
    /* This port only calls assignment with null to clear localization tags.
       Equivalent to the original TEString null branch, retaining capacity. */
    cmp dword ptr [ecx+4],0
    jle 1f
    mov eax,[ecx]
    mov byte ptr [eax],0
1:  mov eax,ecx
    ret 4
.global n_push
n_push:
    mov eax,[ecx+0xd4]
    test eax,eax
    jz 1f
    jmp engine_push
1:  ret 8
.global n_show
n_show:
    push ebp
    mov ebp,esp
    push esi
    push edi
    mov esi,ecx
    mov edi,[ebp+8]
    lea ecx,[esi+0xdc]
    mov eax,[ecx]
    push edi
    call dword ptr [eax+0x28]
    cmp eax,-1
    jne 1f
    mov eax,[esi+0xdc]
    push 0
    push edi
    lea ecx,[esi+0xdc]
    call dword ptr [eax+4]
1:  cmp byte ptr [esi+0xd8],0
    je 2f
    cmp dword ptr [esi+0xd0],0
    je 2f
    push dword ptr [ebp+12]
    push edi
    push esi
    call engine_show
2:  pop edi
    pop esi
    pop ebp
    ret 8
.global n_notify
n_notify:
    mov eax,ecx
    push dword ptr [esp+4]
    call engine_notify
    ret 8
.global n_refresh
n_refresh:
    mov eax,ecx
    mov ecx,[esp+4]
    push eax
    call engine_refresh
    ret 4
.global n_flush
n_flush:
    mov eax,[esp+4]
    add eax,8
    push eax
    push dword ptr [ecx+8]
    mov ecx,[ecx+12]
    call n_push
    ret 4
.global n_setup
n_setup:
    mov eax,[esp+4]
    mov [ecx+8],eax
    mov eax,[esp+8]
    mov [ecx+12],eax
    mov eax,[esp+12]
    mov [ecx+0x34],eax
    mov al,[esp+16]
    mov [ecx+0x38],al
    mov al,[esp+20]
    mov [ecx+0x39],al
    mov al,[esp+24]
    mov [ecx+0x3a],al
    ret 24
.global n_list_dispose
n_list_dispose:
    push esi
    xor esi,esi
    push ecx
    call engine_list_resize
    pop esi
    ret
.global n_buffer_dispose
n_buffer_dispose:
    push esi
    push edi
    mov esi,ecx
    cmp dword ptr [esi+8],0
    je 1f
    xor edi,edi
    push dword ptr [esi]
    call engine_realloc
    add esp,4
1:  mov dword ptr [esi],0
    mov dword ptr [esi+4],0
    mov dword ptr [esi+8],0
    pop edi
    pop esi
    ret
.global n_threshold
n_threshold:
    mov eax,[esp+4]
    cmp eax,6
    jge 1f
    mov eax,[ecx+eax*4+0x9c]
    ret 4
1:  sub eax,5
    imul eax,[ecx+0xb4]
    add eax,[ecx+0xb0]
    ret 4
.global n_find
n_find:
    push ebp
    mov ebp,esp
    sub esp,4
    push ebx
    push esi
    push edi
    mov esi,ecx
    call 1f
1:  pop ebx
    sub ebx,offset 1b
    lea eax,[esi+8]
    push eax
    call dword ptr [ebx+enter_cs_iat]
    lea eax,[ebp+8]
    push eax
    lea eax,[ebp-4]
    push eax
    lea eax,[esi+0x20]
    call engine_tree_find
    mov eax,[ebp-4]
    xor edi,edi
    cmp eax,[esi+0x24]
    je 2f
    mov edi,[eax+0xc]
2:  lea eax,[esi+8]
    push eax
    call dword ptr [ebx+leave_cs_iat]
    mov eax,edi
    pop edi
    pop esi
    pop ebx
    mov esp,ebp
    pop ebp
    ret 4
.section .note.GNU-stack,"",@progbits
