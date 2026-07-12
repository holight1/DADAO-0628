; Discriminating sign-extend test that ACTUALLY exercises the exts sext_inreg
; pattern at runtime (not constant-folded). Values come from function args and
; go through add -> trunc -> sext, which lowers to `exts rd, rd, 56` (i8) /
; `exts rd, rd, 48` (i16). The high byte is then extracted (lshr) so a wrong
; exts immediate (8/16 = 56/48-bit extend) shows up in the exit code:
;   correct exts 56 : sext(i8 -128)  = 0xFFFF..FF80 -> high byte 0xFF = 255
;   buggy   exts 8  : keeps low 56b  = 0x0000..0080 -> high byte 0x00 = 0
; A store-to-load through alloca gets forwarded and folded (the previous version
; did exactly that -> compile-time 254 via setzw, never running exts), so we
; keep the value in registers via runtime args instead.
define i64 @s8(i64 %a, i64 %b) {
  %x = add i64 %a, %b            ; runtime, not foldable
  %t = trunc i64 %x to i8
  %s = sext i8 %t to i64
  %h = lshr i64 %s, 56          ; high byte of the sign-extended value
  ret i64 %h
}
define i64 @s16(i64 %a, i64 %b) {
  %x = add i64 %a, %b
  %t = trunc i64 %x to i16
  %s = sext i16 %t to i64
  %h = lshr i64 %s, 48
  %m = and i64 %h, 255
  ret i64 %m
}
define i64 @main() {
  %r8  = call i64 @s8(i64 64, i64 64)        ; i8  = 128 = -128 -> 255
  %r16 = call i64 @s16(i64 16384, i64 16384) ; i16 = 32768 = -32768 -> 255
  %r   = add i64 %r8, %r16                    ; 255 + 255 = 510 -> exit 254
  ret i64 %r
}
