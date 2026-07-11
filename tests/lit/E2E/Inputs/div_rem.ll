; Strong runtime div/rem discriminator (operands are function args -> not
; constant-foldable, so the DADAO divs/divu really execute on both backends).
; sdiv/udiv must return the QUOTIENT (rdhb), not the remainder (rdha) — the
; gem5-divs-quotient-swap bug returned the remainder when rem=rd0.
define i64 @f(i64 %a, i64 %b, i64 %c, i64 %d) {
  %qs = sdiv i64 %a, %b   ; sdiv(-7, 2)  = -3  (trunc toward zero; NOT rem -1)
  %rs = srem i64 %a, %b   ; srem(-7, 2)  = -1  (rem sign = dividend)
  %qu = udiv i64 %c, %d   ; udiv(100, 7) = 14  (NOT rem 2)
  %ru = urem i64 %c, %d   ; urem(100, 7) = 2
  %t1 = add i64 %qs, %rs
  %t2 = add i64 %t1, %qu
  %t3 = add i64 %t2, %ru
  %t4 = add i64 %t3, 60
  ret i64 %t4             ; -3 + -1 + 14 + 2 + 60 = 72  (buggy gem5 gave 62)
}
define i64 @main() {
  %r = call i64 @f(i64 -7, i64 2, i64 100, i64 7)
  ret i64 %r
}
