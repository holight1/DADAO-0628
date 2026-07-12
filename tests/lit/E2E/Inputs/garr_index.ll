; Global array variable-index via standalone PCREL_HI (address materialized into
; a GPRB register, then + i*8). @pad is NON-ZERO initialized so it occupies .data
; and pushes @arr to a page offset with low12 != 0 — this exercises the RELA_LO
; relocation on the addi_rb that carries the low bits of the standalone address
; (a page-aligned @arr, low12=0, would not test it — same blind spot as the
; global_align case in DL-061c).
@pad = global [3 x i64] [i64 1, i64 2, i64 3]
@arr = global [4 x i64] [i64 10, i64 20, i64 30, i64 40]

define i64 @f(i64 %i){
  %p = getelementptr [4 x i64], ptr @arr, i64 0, i64 %i
  %v = load i64, ptr %p
  ret i64 %v
}
define i64 @main(){
  %r2 = call i64 @f(i64 2)   ; 30
  %r0 = call i64 @f(i64 0)   ; 10
  %r3 = call i64 @f(i64 3)   ; 40
  %sum = add i64 %r2, %r0
  %sum2 = add i64 %sum, %r3
  ret i64 %sum2              ; 30 + 10 + 40 = 80
}
