# ML-014ag：mallocng/libc bring-up 知识图谱沉淀

**执行者**：主 agent（架构师）；按用户约束不交给 subagent

**状态**：Completed（30-task run：13/30）

## 沉淀内容

在确认 ML-014af 双大块 contract 已闭合后，更新了 `/home/holight/knowledge-graph`：

- `compiler-backend/03-lld-target-integration.md`：新增“页地址重定位必须与
  signed-low 立即数协同舍入”，提炼 page relocation、signed low、`S+A-P`、`P+4`
  语义及 `0x7ff/0x800` 边界测试要求。
- `compiler-backend/08-libc-bringup-novel-isa.md`：新增“用分阶段运行契约隔离
  libc bring-up 的故障边界”，提炼 startup→main、单块、双块、双后端、raw
  sidecar 的通用验证阶梯。
- 运行 `scripts/gen_index.py` 和 `scripts/check_links.py`：索引更新为 94 文件、
  132 个规范模式节点；链接检查 `0` 悬空。

知识图谱 commit：`c4827c1`。

## Scope audit

仅提交上述两份知识节点及自动生成的 `INDEX.md`。知识图谱中原有的用户未提交修改
`compiler-backend/04-isel-calling-convention.md`、
`isa-design/04-multi-implementation-differential.md` 保持未触碰、未纳入本次 commit。
未向 subagent 暴露或要求查阅 `~/toolchain`、`~/knowledge-graph`。

## 依据

主要事实来自 ML-014ab、ML-014ac、ML-014ae、ML-014af 任务记录及其 task-owned
QEMU/gem5/ELF sidecar；本记录不把知识图谱当作项目运行时证据。
