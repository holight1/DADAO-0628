define i64 @usum(i64 %n){
entry:
  br label %loop
loop:
  %i = phi i64 [ 1, %entry ], [ %i2, %loop ]
  %s = phi i64 [ 0, %entry ], [ %s2, %loop ]
  %s2 = add i64 %s, %i
  %i2 = add i64 %i, 1
  %c = icmp ule i64 %i2, %n
  br i1 %c, label %loop, label %done
done:
  ret i64 %s2
}
define i64 @main(){
  %r = call i64 @usum(i64 10)
  ret i64 %r
}
