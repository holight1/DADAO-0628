@g = global i64 42

define i64 @main(){
  %a = load i64, ptr @g
  %b = add i64 %a, 2
  store i64 %b, ptr @g
  %c = load i64, ptr @g
  ret i64 %c
}
