/* Disable this exact build's built-in telemetry client. Both native methods
 * take one stack argument (thiscall) and return a status. Constructors and
 * destructors remain untouched. No socket or event object is created here. */
.intel_syntax noprefix
.code32
.section .text
.global telemetry_disabled
telemetry_disabled:
    mov byte ptr [ecx + 8], 0    /* Native client active flag */
    mov eax, 0x80004005          /* Same disabled status as native submission */
    ret 4
.section .note.GNU-stack,"",@progbits
