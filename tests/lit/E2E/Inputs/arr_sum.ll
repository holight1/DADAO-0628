define i64 @main(){
entry:
  %arr = alloca [5 x i64]
  br label %init
init:
  %i = phi i64 [ 0, %entry ], [ %i2, %init ]
  %p = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 %i
  store i64 %i, i64* %p
  %i2 = add i64 %i, 1
  %c = icmp slt i64 %i2, 5
  br i1 %c, label %init, label %sum
sum:
  %j = phi i64 [ 0, %init ], [ %j2, %sum ]
  %acc = phi i64 [ 0, %init ], [ %acc2, %sum ]
  %q = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 %j
  %v = load i64, i64* %q
  %acc2 = add i64 %acc, %v
  %j2 = add i64 %j, 1
  %d = icmp slt i64 %j2, 5
  br i1 %d, label %sum, label %done
done:
  ret i64 %acc2
}
