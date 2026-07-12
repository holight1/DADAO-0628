@.str = constant [3 x i8] c"AB\00"

define i64 @main(){
  %p0 = getelementptr [3 x i8], ptr @.str, i64 0, i64 0
  %c0 = load i8, ptr %p0
  %z0 = zext i8 %c0 to i64
  %p1 = getelementptr [3 x i8], ptr @.str, i64 0, i64 1
  %c1 = load i8, ptr %p1
  %z1 = zext i8 %c1 to i64
  %sum = add i64 %z0, %z1
  ret i64 %sum
}
; 'A'=65 + 'B'=66 = 131
