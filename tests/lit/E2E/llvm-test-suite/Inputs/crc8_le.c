/* Adapted from llvm-test-suite SingleSource/UnitTests/HashRecognize/crc8.le.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream PRINT_RESULTS(crc_loop) printf's crc_loop() over 8 sample pairs;
 * this freestanding slice has no libc I/O, so each printed value is folded
 * into one running checksum (acc = acc*131 + value) asserted via exit code
 * instead, same technique as Inputs/divrem.c. crc_loop stays a real
 * noinline function call per sample, preserving the shape that triggered
 * codegen-call-clobbers-gprb-not-declared (MALIGN 0x81 before ML-004c;
 * fixed by ML-004c's CALL RegMask attach + GPRB spill/reload fix). Expected
 * value derived by running this file under host gcc -O0 (acc=104). stdint.h
 * swapped for `unsigned char` — the cross target's stdint.h chain pulls in
 * host glibc bits headers that don't resolve for -nostdlib dadao-unknown-elf. */
#define GENPOLY 0x1D
static unsigned char crc_loop(unsigned char crc_initval, unsigned char data) __attribute__((noinline));
static unsigned char crc_loop(unsigned char crc_initval, unsigned char data) {
  unsigned char crc = crc_initval;
  for (int i = 0; i < 8; ++i) {
    unsigned char x = crc ^ data;
    unsigned char crc_lshr = crc >> 1;
    crc = (x & 1) ? (crc_lshr ^ GENPOLY) : crc_lshr;
    data >>= 1;
  }
  return crc;
}
int main(void) {
  static const unsigned sample[] = {0,1,11,16,129,142,196,255};
  unsigned acc = 0;
  for (unsigned i = 0; i < 8; ++i)
    acc = acc*131 + crc_loop(sample[i], sample[7-i]);
  return acc & 0xFF;
}
