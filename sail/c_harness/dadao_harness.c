/* DADAO Sail rehearsal slice — C harness (SL-002a / ADR-0011 M2b).
 *
 * Drives the sail-generated model: loads a flat big-endian test image, runs the
 * fetch-decode-execute loop (zdadao_step) to halt/fault, and reports terminal
 * state in the same DADAO_REGDUMP / DADAO_MEMDUMP format as the gem5 leg
 * (arch/dadao/decoder.cc), so run_sail_test.py can reuse run_gem5_test's
 * parsers/comparators. This file owns only I/O and byte storage; ALL
 * architectural semantics live in the .sail model.
 *
 * CLI:  dadao_sail_sim <code.bin> [<window.bin>]
 *   <code.bin>    flat .text loaded big-endian at 0x80000000 (BINARY_BASE)
 *   <window.bin>  optional RW data window loaded at 0x87FEF000 (MEM_WINDOW_BASE)
 * Exit: 0 on halt (+ dumps), fault SE code on fault (0x81/0x82/0x83), 0x7F for
 *   a valid opcode outside the rehearsal slice.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "dadao_model.h"     /* zRD, zRB, zdadao_init, zdadao_step, model_init */
#include "dadao_externs.h"

/* Memory map — must match build_test_binary.BINARY_BASE / run_gem5_test window
 * constants so the same flat image runs identically on all four legs. */
#define CODE_BASE 0x80000000ULL
#define CODE_SIZE 0x01000000ULL          /* 16 MiB: .text + scratch pages     */
#define WIN_BASE  0x87FEF000ULL
#define WIN_SIZE  0x00003000ULL          /* memory-test window (RW)           */

static uint8_t code_mem[CODE_SIZE];
static uint8_t win_mem[WIN_SIZE];
static int     win_mapped = 0;

/* run result, set by set_result() from the model */
static int      g_have_result = 0;
static uint64_t g_kind = 0;              /* 0 halt, 1 fault, 2 unimpl */
static uint64_t g_code = 0;

/* ---- Sail platform primitives ------------------------------------------- */
uint64_t read_ram_byte(uint64_t addr)
{
  if (addr >= CODE_BASE && addr < CODE_BASE + CODE_SIZE)
    return (uint64_t) code_mem[addr - CODE_BASE];
  if (addr >= WIN_BASE && addr < WIN_BASE + WIN_SIZE)
    return (uint64_t) win_mem[addr - WIN_BASE];
  return 0;                              /* unmapped reads as 0 */
}

unit write_ram_byte(uint64_t addr, uint64_t value)
{
  uint8_t b = (uint8_t) (value & 0xFF);
  if (addr >= CODE_BASE && addr < CODE_BASE + CODE_SIZE)
    code_mem[addr - CODE_BASE] = b;
  else if (addr >= WIN_BASE && addr < WIN_BASE + WIN_SIZE)
    win_mem[addr - WIN_BASE] = b;
  return UNIT;
}

unit set_result(uint64_t kind, uint64_t code)
{
  g_have_result = 1;
  g_kind = kind;
  g_code = code;
  return UNIT;
}

/* ---- image loading ------------------------------------------------------- */
static long load_file(const char *path, uint8_t *dst, size_t cap)
{
  FILE *f = fopen(path, "rb");
  if (!f) { perror(path); return -1; }
  size_t n = fread(dst, 1, cap, f);
  fclose(f);
  return (long) n;
}

/* ---- terminal-state dump (matches gem5 decoder.cc format) ---------------- */
static void dump_regs(void)
{
  printf("DADAO_REGDUMP");
  for (int i = 0; i < 64; i++)
    printf(" rd%d=%016llX", i, (unsigned long long) zRD.data[i]);
  for (int i = 0; i < 64; i++)
    printf(" rb%d=%016llX", i, (unsigned long long) zRB.data[i]);
  printf("\n");
}

static void dump_mem(void)
{
  printf("DADAO_MEMDUMP base=%llX size=%llX data=",
         (unsigned long long) WIN_BASE, (unsigned long long) WIN_SIZE);
  for (size_t i = 0; i < WIN_SIZE; i++)
    printf("%02X", win_mem[i]);
  printf("\n");
}

int main(int argc, char *argv[])
{
  if (argc < 2 || argc > 3) {
    fprintf(stderr, "usage: %s <code.bin> [<window.bin>]\n", argv[0]);
    return 2;
  }

  long clen = load_file(argv[1], code_mem, CODE_SIZE);
  if (clen < 0) return 2;
  if (argc == 3) {
    long wlen = load_file(argv[2], win_mem, WIN_SIZE);
    if (wlen < 0) return 2;
    win_mapped = 1;
  }

  model_init();          /* allocates + zero-inits the sail register vectors  */
  zdadao_init(UNIT);     /* zero regs, PC = 0x80000000 (spec §1.5 / harness)  */

  /* fetch-decode-execute until halt/fault/unimpl (sail-riscv style C loop). */
  const long MAX_STEPS = 20000000L;
  long steps = 0;
  while (zdadao_step(UNIT)) {
    if (++steps > MAX_STEPS) {
      fprintf(stderr, "step limit exceeded (runaway program?)\n");
      return 3;
    }
  }

  if (!g_have_result) {
    fprintf(stderr, "model stopped without a result\n");
    return 3;
  }

  int rc;
  if (g_kind == 0) {                     /* halt: dump terminal state */
    dump_regs();                         /* read zRD/zRB BEFORE model_fini */
    if (win_mapped) dump_mem();
    rc = (int) (g_code & 0xFF);
  } else if (g_kind == 1) {              /* fault (precise) */
    rc = (int) (g_code & 0xFF);
  } else {
    rc = 0x7F;                           /* unimpl: opcode outside slice */
  }
  model_fini();
  return rc;
}
