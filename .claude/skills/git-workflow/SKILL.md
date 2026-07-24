---
name: git-workflow
description: Git 提交规范与代码审查工作流 — 标准化 commit message、分批策略、review 流程
version: 1.0.0
---

# Git Workflow Skill

## Commit Message 规范

遵循本项目历史风格，采用 `[prefix] message` 格式：

```
[prefix] 简短标题（不超过 72 字符）

可选详细说明（空一行后写），每行不超过 72 字符
- 用列表说明关键变更点
- 说明为什么改、改了什么
```

### Prefix 对照表

| Prefix | 适用场景 |
|--------|----------|
| `[feat]` | 新功能、新接口、新组件 |
| `[refactor]` | 重构、架构调整、模块拆分/合并 |
| `[fix]` | 修复 bug、运行时错误、行为异常 |
| `[clean]` | 删除 dead code、清理遗留文件、移除废弃模块 |
| `[chore]` | 更新配置、文档、测试、依赖（非功能变更） |
| `[docs]` | 纯文档变更（与 `[chore]` 的区别：只动 docs/ 目录） |
| `[ux]` | 前端 UI/UX 改进 | 
| `[perf]` | 性能优化 |
| `[test]` | 增改测试（与 `[chore]` 的区别：只动 tests/） |
| `[wip]` | 工作在进行中，不稳定 |
| `[revert]` | 回滚之前的提交 |
| `[codex]` | Codex 工具生成的提交 |

### 历史示例

```
[refactor] ai harness — consolidate skills, add navigation/session/evidence modules
[feat] workflow runtime progress dedup & storage upgrades
[feat] artifact entries API, msalign parser & backend improvements
[ux] node data service
[clean] clean the legacy codes
fix: websocket传输
refactor: 收紧 run_logs 写入职责，前端日志面板按分类展示
```

### 详细说明的格式

当需要补充细节时，空一行后写：

```
[refactor] ai harness — consolidate skills, add navigation/session/evidence modules

- Remove legacy exploration system (collector, proof, ptm_models, ptm_state, session, storage)
- Add navigation module (engine, models, store) for subagent state routing
- Consolidate PTM skills: discovery, evidence, ingestion, reporting + common
```

## 分批提交策略

当工作区包含多个领域的变更时，按逻辑分组提交：

### 典型分组

```
# 1. AI 引擎变更
git add src/ai/ src/tools/ src/plugins/

# 2. 后端核心变更
git add app/ src/domain/ src/storage/ src/execution/

# 3. 前端变更
git add TDEase-FrontEnd/src/

# 4. 配置与文档
git add config/ docs/

# 5. 测试
git add tests/

# 6. 清理（删除残留文件）
git rm <file>
git add -A <dir>    # 删除整个目录
```

### 提交顺序建议

1. 底层基础设施先提交（AI 引擎、storage 层）
2. 后端 API 和 domain 逻辑
3. 前端 UI 变更
4. 配置、文档、测试
5. 清理残留文件

### 撤回误暂存

```bash
git reset HEAD -- .         # 撤回全部暂存
git reset HEAD -- <path>    # 撤回单个文件
```

## Code Review 工作流

### Review 范围

- **本地变更**: 审查 `git diff` 中未提交的修改
- **PR review**: 审查 GitHub PR 的变更

### Review Checklist

```
□ 架构一致性 — 变更是否遵循现有架构分层？
  违规表现：前端直接操作 DB、后端组件在前端项目中
□ 多真相源 — 同一逻辑是否有两处实现？
  违规表现：新写了一份已存在的数据转换函数
□ 旧链路残留 — 更新时是否删除了旧链路？
  如果新逻辑替换了旧逻辑，旧代码应移除而非注释
□ 错误处理 — 边界情况是否考虑了？
  - API 调用失败是否有 try/catch？
  - 空状态/undefined 是否有防卫？
  - 外部输入是否做校验？
□ 命名一致性 — 名称是否与项目中同类概念一致？
  - 变量名是否反映了业务含义？
  - 函数名是动词开头吗？
  - TypeScript 类型名是 PascalCase 吗？
□ 副作用 — 变更是否无意中修改了不属于本职责的代码？
□ 日志 — 关键路径是否有适量日志（非过度）？
□ 类型安全 — TypeScript 类型是否正确，是否有 any 滥用？
```

### Review 执行流程

```
1. git status → 了解变更范围
2. git diff --stat → 了解每个文件的影响量
3. git diff [file] → 逐文件审查
4. 对每个文件执行 checklist
5. 汇总问题，分类：
   - blocking: 必须修复后才能合并
   - warning: 建议修复
   - nitpick: 小问题，可忽略
```

### 报告格式

```
## Review: <分支名或变更范围>

### Blocking
- [file:line] 问题描述

### Warnings  
- [file:line] 问题描述

### Nitpicks
- [file:line] 问题描述

### 总结
变更整体质量/主要风险/建议
```

## Commit 后复利提示

当提交包含 `[fix]` 或 `[refactor]` 且变更涉及非显而易见的根因时，提示：

> "这个修复涉及非显而易见的根因，值得记录到 `docs/solutions/` 吗？
> 运行 `/compound` 可以在 2 分钟内完成文档复利。"

触发条件：
- commit prefix 为 `[fix]`，且修复涉及隐藏约束、微妙不变式或多轮尝试
- commit prefix 为 `[refactor]`，且重构解决了架构摩擦（如多真相源、旧链路残留）
- 不触发：`[chore]`、`[docs]`、`[clean]`、`[wip]` — 这些不是需要复利的修复

## 常用命令速查

```bash
# 状态
git status --short
git diff --stat
git diff --cached --stat

# 暂存
git add <path>
git add -p <file>       # 交互式部分暂存

# 提交
git commit -m "$(cat <<'EOF'
[prefix] title
EOF
)"

# 撤销
git reset HEAD -- <file>                # 取消暂存
git checkout -- <file>                  # 放弃工作区修改（谨慎）
git log --oneline -10                   # 看最近提交
```
