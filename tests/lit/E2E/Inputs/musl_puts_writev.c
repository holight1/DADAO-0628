/* ML-019a: exercises musl's real buffered stdio write path.
   puts() -> fputs() -> __stdio_write() -> syscall(SYS_writev, fd, iov, 2)
   (src/stdio/__stdio_write.c) -- unlike a direct write() call, this is the
   path that was silently broken before the cfx_smon SYS_writev(66)
   responder existed in QEMU/gem5 (ML-017d puts_return_bypass/PUTS_RC_ERR
   finding: puts() returned a negative value, errno was set, no output
   appeared). This program must actually print the marker string below on
   stdout, not just exit 42. */
#include <stdio.h>

int main(void) {
    puts("DADAO_WRITEV_PUTS_OK");
    return 42;
}
