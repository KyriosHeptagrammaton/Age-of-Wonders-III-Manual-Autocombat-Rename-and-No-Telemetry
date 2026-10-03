ENTRY(patch_entry)
SECTIONS {
  . = 0x00fc2000;
  .text : { *(.text) *(.text.*) *(.rodata*) *(.got*) }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
