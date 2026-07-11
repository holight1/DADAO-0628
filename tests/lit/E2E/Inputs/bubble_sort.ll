define i64 @main(){
entry:
  %arr = alloca [5 x i64]
  ; Initialize: arr = {5, 3, 4, 1, 2}
  %p0 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 0
  store i64 5, i64* %p0
  %p1 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 1
  store i64 3, i64* %p1
  %p2 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 2
  store i64 4, i64* %p2
  %p3 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 3
  store i64 1, i64* %p3
  %p4 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 4
  store i64 2, i64* %p4

  ; Bubble sort — outer loop i=0 to 3
  br label %outer
outer:
  %i = phi i64 [ 0, %entry ], [ %ni, %outer_inc ]
  %ii = add i64 %i, 1
  br label %inner
inner:
  %j = phi i64 [ 0, %outer ], [ %nj, %inner_inc ]
  %jj = add i64 %j, 1
  ; arr[j]
  %pa = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 %j
  %va = load i64, i64* %pa
  ; arr[j+1]
  %pb = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 %jj
  %vb = load i64, i64* %pb
  %swap = icmp sgt i64 %va, %vb
  br i1 %swap, label %do_swap, label %inner_inc
do_swap:
  store i64 %vb, i64* %pa
  store i64 %va, i64* %pb
  br label %inner_inc
inner_inc:
  %nj = add i64 %j, 1
  ; inner loop bound: 5 - 1 - i = 4 - i
  %limit = sub i64 4, %i
  %inner_cond = icmp slt i64 %nj, %limit
  br i1 %inner_cond, label %inner, label %outer_inc
outer_inc:
  %ni = add i64 %i, 1
  %outer_cond = icmp slt i64 %ni, 4
  br i1 %outer_cond, label %outer, label %verify

verify:
  ; Check arr[0] == 1
  %q0 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 0
  %v0 = load i64, i64* %q0
  ; Check arr[4] == 5
  %q4 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 4
  %v4 = load i64, i64* %q4
  ; Sum of min+max = 1+5 = 6 — only correct if sorted
  %sum = add i64 %v0, %v4
  ; Also check that adjacent elements are sorted (ascending pairs count = 4)
  %q1 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 1
  %v1 = load i64, i64* %q1
  %q2 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 2
  %v2 = load i64, i64* %q2
  %q3 = getelementptr [5 x i64], [5 x i64]* %arr, i64 0, i64 3
  %v3 = load i64, i64* %q3
  %c01 = icmp slt i64 %v0, %v1
  %v01 = zext i1 %c01 to i64
  %c12 = icmp slt i64 %v1, %v2
  %v12 = zext i1 %c12 to i64
  %c23 = icmp slt i64 %v2, %v3
  %v23 = zext i1 %c23 to i64
  %c34 = icmp slt i64 %v3, %v4
  %v34 = zext i1 %c34 to i64
  %pairs = add i64 %v01, %v12
  %pairs2 = add i64 %pairs, %v23
  %pairs3 = add i64 %pairs2, %v34                  ; should be 4

  ; Result: (min+max)*10 + pairs = 6*10 + 4 = 64
  %result = mul i64 %sum, 10
  %result2 = add i64 %result, %pairs3
  ret i64 %result2
}
