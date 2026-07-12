;; Narrow store no-clobber: arr[0]=5, arr[1]=9 → return arr[0] = 5
define i64 @main(){
  %arr = alloca [4 x i8]
  %p0 = getelementptr [4 x i8], ptr %arr, i64 0, i64 0
  store i8 5, ptr %p0
  %p1 = getelementptr [4 x i8], ptr %arr, i64 0, i64 1
  store i8 9, ptr %p1
  %v = load i8, ptr %p0
  %z = zext i8 %v to i64
  ret i64 %z
}
