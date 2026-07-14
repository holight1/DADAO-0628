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

  /* Static heap region consumed by picolibc's libos/fallback/sbrk.c
   * (__fallback_sbrk / weak-referenced sbrk()) — required whenever that
   * archive member is pulled into the link (ADR-0014 D3). */
  . = ALIGN(4096);
  __heap_start = .;
  __heap_end = 0x87E00000;

  /DISCARD/ : {
    *(.note.GNU-stack)
  }
}
