# TDEase-zero Agent 体系

## 核心代理

| Agent | 用途 |
|-------|------|
| implementer | 代码实现，遵循第一性原理 |
| researcher | 代码调研、对比、证据合成 |
| checker | 正确性/回归验证 |
| doc-writer | 架构/方案/决策记录 |
| architect-reviewer | 架构评审 |

## 工作流 Agent（来自 .claude/agents/）

参见 `.claude/agents/` 中 40+ 个 specialist agent：
- `ce-correctness-reviewer` — 逻辑正确性
- `ce-maintainability-reviewer` — 可维护性
- `ce-security-reviewer` — 安全
- `ce-performance-reviewer` — 性能
- `ce-adversarial-reviewer` — 对抗性破坏测试
- 其他...

## 使用方式

```bash
# 在 Claude Code 中直接调用
/agent implementer "任务描述"
/agent checker "验证文件"
```

## 约束

- 所有 agent 遵循 CLAUDE.md 中定义的第一性原理架构
- 不做可视化工作流编辑
- 不引入新的抽象层或状态机
- 优先使用命令行/Snakemake 而非 API 封装
