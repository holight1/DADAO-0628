define i64 @abs(i64 %x){
  %c = icmp slt i64 %x, 0
  br i1 %c, label %neg, label %done
neg:
  %nx = sub i64 0, %x
  ret i64 %nx
done:
  ret i64 %x
}
define i64 @main(){
  %r = call i64 @abs(i64 -5)
  ret i64 %r
}
