define i64 @shift_check(i64 %x){
  %ashr_v = ashr i64 %x, 2
  %res = add i64 %ashr_v, 50
  ret i64 %res
}
define i64 @main(){
  %r = call i64 @shift_check(i64 -16)
  ret i64 %r
}
; ashr(-16, 2) = -4; -4 + 50 = 46
; Expected exit: 46
; vs lshr(-16, 2) would give different result → discriminant
