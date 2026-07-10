/* Prototypes for the Sail<->C platform primitives the DADAO model calls.
 * Passed to `sail -c` via --c-include so the generated model C sees correct
 * signatures. bits(n<=64) is Sail's fbits == uint64_t; unit is Sail's int. */
#pragma once
#include <stdint.h>
#include "sail.h"   /* unit, UNIT */

/* big-endian memory bytes (spec §2.1) — implemented in dadao_harness.c */
uint64_t read_ram_byte(uint64_t addr);
unit     write_ram_byte(uint64_t addr, uint64_t value);

/* run-result sink: kind 0=halt, 1=fault, 2=unimpl; code = exit/fault code */
unit     set_result(uint64_t kind, uint64_t code);
