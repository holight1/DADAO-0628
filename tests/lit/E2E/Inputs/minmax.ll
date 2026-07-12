;; min/max with negative values — must use csz+cmps, NO branches
define i64 @min(i64 %a, i64 %b){
  %c = icmp slt i64 %a, %b
  %r = select i1 %c, i64 %a, i64 %b
  ret i64 %r
}
define i64 @max(i64 %a, i64 %b){
  %c = icmp sgt i64 %a, %b
  %r = select i1 %c, i64 %a, i64 %b
  ret i64 %r
}
define i64 @main(){
  %mn = call i64 @min(i64 -5, i64 3)
  %mx = call i64 @max(i64 -5, i64 3)
  %sum = add i64 %mn, %mx
  ret i64 %sum
}
; min(-5,3) = -5, max(-5,3) = 3, sum = -2 → & 0xFF = 254
; Note: -5 unsigned = 251, 3 unsigned = 3, 251+3=254
