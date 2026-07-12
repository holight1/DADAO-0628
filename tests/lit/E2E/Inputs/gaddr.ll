@g = global i64 42

define i64 @main(){
  %p = ptrtoint ptr @g to i64
  %v = inttoptr i64 %p to ptr
  %r = load i64, ptr %v
  ret i64 %r
}
