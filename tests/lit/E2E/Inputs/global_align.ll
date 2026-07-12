@pad = global i64 1
@g = global i64 42

define i64 @main(){
  %v = load i64, ptr @g
  ret i64 %v
}
