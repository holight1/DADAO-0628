# §6 机器内存映射与异常协议

**来源**：DL-013a, DL-016a, DL-019a review（2026-07-02）  
**交叉验证**：docs/adr/0004-test-machine.md

---

## §6.1 内存映射（dadao-m1 机器）

| 起始地址 | 结束地址 | 大小 | 属性 | 描述 |
|---------|---------|------|------|------|
| 0x00000000 | 0x000FFFFF | — | unmapped | 访问 → exit 0x8F |
| 0x00100000 | 0x0010FFFF | 64 KB | ROM（只读） | 启动 trampoline，写入静默丢弃 |
| 0x10000000 | 0x10000007 | 8 B | MMIO（只写） | Exit port |
| 0x80000000 | 0x87FFFFFF | 128 MB | RAM | 测试代码/栈/数据 |
| 其他 | — | — | unmapped | 访问 → exit 0x8F |

## §6.2 复位值

| 寄存器 | 复位值 |
|--------|-------|
| rb0（PC） | 0x00100000（ROM 入口） |
| rd0–rd63 | 0（rd0 硬连接零） |
| rb1–rb63 | 0 |
| ra0–ra63 | 0（所有条目无效，匹配 process-entry init） |
| rf0 | 0x07F87F8000000000（QNaN） |
| rf1–rf63 | 0 |

## §6.3 Exit Port 协议（0x10000000）

- 8 字节写（sto）→ 低字节作为 exit code → `qemu_system_shutdown`
- 非 8 字节写 → UNDI
- 读 → 返回 0
- PASS = write 0x00, FAIL = write 0x01–0x7F

## §6.4 TLB Identity Mapping

M1 bare-metal 无 MMU：TLB identity flat-map。物理地址 = 虚拟地址。
`tcg_gen_qemu_ld/st` 的 `ctx->mem_idx` 指向 flat mapping。

## §6.5 测试加载流程

1. `-bios trampoline.bin` → ROM @ 0x00100000
2. `-kernel test.bin` → RAM @ 0x80000000
3. CPU reset → rb0 = 0x00100000 → trampoline init → jump to 0x80000000
4. Test 执行 → halt/exit port → QEMU exit

## §6.6 精确异常保证

所有 ISA 异常（ILLI/UNDI/MALIGN/IALIGN/RASOF/RASUF）均精确：
- 目标寄存器不写入
- 内存不写入
- PC 指向 faulting 指令（rb0 在 handler 中保持 faulting 地址）
