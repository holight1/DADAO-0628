;; Plain select: c ? a : b — BOTH branches discriminated at runtime.
;; f is a separate function so the condition/values arrive in registers (not
;; constant-folded). c=1 must pick a (true), c=0 must pick b (false); using
;; distinct value pairs so a wrong operand order changes the sum:
;;   f(1, 11, 22) = 11   (true branch)
;;   f(0, 33, 44) = 44   (false branch)
;;   11 + 44 = 55  -> exit 55
define i64 @f(i64 %c, i64 %a, i64 %b){
  %cond = trunc i64 %c to i1
  %r = select i1 %cond, i64 %a, i64 %b
  ret i64 %r
}
define i64 @main(){
  %t = call i64 @f(i64 1, i64 11, i64 22)   ; true  -> 11
  %f = call i64 @f(i64 0, i64 33, i64 44)   ; false -> 44
  %sum = add i64 %t, %f                      ; 11 + 44 = 55
  ret i64 %sum
}
