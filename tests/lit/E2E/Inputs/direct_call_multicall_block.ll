; ML-021a regression test: two independent direct calls in the same basic
; block. Non-floating-point, no libcall involvement — isolates the
; ISD::CALLSEQ_START/END glue-linkage bug from the floating-point-libcall
; scenario used to originally find it (ML-020a's `cmp.c`).
define i64 @g() {
  ret i64 10
}

define i64 @h() {
  ret i64 32
}

define i64 @main() {
entry:
  %a = call i64 @g()
  %b = call i64 @h()
  %s = add i64 %a, %b
  ret i64 %s
}
