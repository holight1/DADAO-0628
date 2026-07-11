; Discriminating test for R_DADAO_RELA_LO: @pad must be NON-ZERO initialized so
; it lands in .data (a zero-init global goes to .bss and leaves @g page-aligned,
; low12=0, which does NOT exercise the low-12 relocation). With a non-zero pad
; array of 3 i64 (24 bytes) in .data, @g lands at page offset 0x18 (low12 != 0),
; so a wrong RELA_LO (e.g. PC-relative instead of absolute S&0xFFF) reads the
; wrong address and fails.
@pad = global [3 x i64] [i64 1, i64 2, i64 3]
@g = global i64 42

define i64 @main(){
  %v = load i64, ptr @g
  ret i64 %v
}
