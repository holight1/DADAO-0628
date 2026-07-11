; Runtime wyde-materialization check (NOT constant-folded).
; The 64-bit constant 0x0007000500030001 is added to a function argument, so
; llc must materialize it via setzw+orw inside @f (main passes 0, which cannot
; be folded away since %x is a runtime SSA value from f's view). The checksum
; sums the low nibble of each wyde (1+3+5+7=16) — any wrong wyde placement or
; truncated materialization changes the result.
define i64 @f(i64 %x) {
  %v  = add i64 %x, 1970346312007681   ; 0x0007000500030001
  %a0 = and i64 %v, 15                  ; wyde0 low nibble = 1
  %s1 = lshr i64 %v, 16
  %a1 = and i64 %s1, 15                 ; wyde1 low nibble = 3
  %s2 = lshr i64 %v, 32
  %a2 = and i64 %s2, 15                 ; wyde2 low nibble = 5
  %s3 = lshr i64 %v, 48
  %a3 = and i64 %s3, 15                 ; wyde3 low nibble = 7
  %p  = add i64 %a0, %a1
  %q  = add i64 %p, %a2
  %r  = add i64 %q, %a3
  ret i64 %r                            ; 1+3+5+7 = 16
}
define i64 @main() {
  %r = call i64 @f(i64 0)
  ret i64 %r
}
