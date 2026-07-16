/* Adapted from llvm-test-suite SingleSource/UnitTests/HashRecognize/crc16.be.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Same accumulator-instead-of-printf technique as Inputs/crc8_le.c/divrem.c;
 * crc_loop stays a real noinline call per sample (codegen-call-clobbers-gprb-
 * not-declared shape, fixed by ML-004c). Expected value from host gcc -O0
 * (acc=232). stdint.h swapped for `unsigned short` (see crc8_le.c header). */
#define GENPOLY 4129
static unsigned short crc_loop(unsigned short crc_initval, unsigned short data) __attribute__((noinline));
static unsigned short crc_loop(unsigned short crc_initval, unsigned short data) {
  unsigned short crc = crc_initval;
  for (int i = 0; i < 16; ++i) {
    unsigned short x = crc ^ data;
    unsigned short crc_shl = crc << 1;
    crc = (x & 0x8000) ? (crc_shl ^ GENPOLY) : crc_shl;
    data <<= 1;
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
