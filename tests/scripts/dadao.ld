/* DADAO link script — standard ELF linking for E2E pipeline
 *
 * .text at BINARY_BASE (0x80000000, ADR-0004), at file offset 0 for flat binary
 * .rodata / .data / .bss follow
 * Entry point: _start (in crt0.s)
 */
ENTRY(_start)

PHDRS {
  text PT_LOAD FILEHDR PHDRS;
  data PT_LOAD;
}

SECTIONS {
  . = 0x80000000;

  .text : {
    *(.text .text.*)
  } :text

  . = ALIGN(4096);
  .rodata : {
    *(.rodata .rodata.*)
  } :text

  . = ALIGN(4096);
  .data : {
    *(.data .data.*)
  } :data

  . = ALIGN(8);
  .bss : {
    *(.bss .bss.*)
    *(COMMON)
  } :data

  /DISCARD/ : {
    *(.note.GNU-stack)
  }
}
