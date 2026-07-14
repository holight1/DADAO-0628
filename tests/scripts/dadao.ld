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
   * archive member is pulled into the link (ADR-0014 D3).
   *
   * This must live inside a real output section covered by a PHDRS
   * PT_LOAD entry: gem5 SE builds its page table strictly from ELF
   * segment memsz (see issue gem5-se-heap-not-covered-by-elf-segment),
   * so a bare location-counter symbol assignment here (with no section)
   * left the heap unmapped and page-faulted on first malloc(). Using
   * NOLOAD gives it SHT_NOBITS semantics like .bss: it contributes to
   * :data's memsz (so gem5 maps and zero-fills it) but not to filesz,
   * so QEMU's flat `llvm-objcopy -O binary` output is unchanged. */
  . = ALIGN(4096);
  .heap (NOLOAD) : {
    __heap_start = .;
    . = 0x87E00000;
    __heap_end = .;
  } :data

  /DISCARD/ : {
    *(.note.GNU-stack)
  }
}
