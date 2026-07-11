define i64 @f(i64 %x){
  %q = sdiv i64 42, %x
  ret i64 %q
}
define i64 @main(){
  %r = call i64 @f(i64 0)
  ret i64 %r
}
; sdiv 42/0 → ILLI (exit 130 = 0x82)
