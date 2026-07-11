define i64 @main(){ %r=call i64 @callee(i64 41)  ret i64 %r }
define i64 @callee(i64 %a){ %s=add i64 %a,1  ret i64 %s }
