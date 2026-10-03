ENTRY(retry_entry)
SECTIONS {
  . = 0x00f22000;
  .text : { *(.text) *(.text.*) *(.rodata*) *(.got*) }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
