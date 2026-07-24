# TDEase-zero

> **零范式架构 — Snakemake + CLI Agent + 自由文件系统**

从第一性原理重构：不再做可视化工作流编辑器。AI 时代的 Ease —— 最简约，最容易管理的质谱分析工程体系。

## 架构

```
┌─ PI (本地 Agent) ───────────────────────┐
│  Claude Code / coding agent              │
│  ├─ 写 Snakemake DSL                      │
│  ├─ 跑脚本                                │
│  ├─ hook/tool → evidence runtime          │
│  └─ prompt 规则 = 唯一约束                │
│                                           │
│  Interactive Dashboard (Electron + Vue)   │
│  ├─ 可视化节点积木 → 结果渲染             │
│  └─ 交互数据看板                          │
└──────────────────┬────────────────────────┘
                    │ 上传脚本 / 下载结果
┌─ Server ─────────────────────────────────┐
│  Snakemake 执行引擎                      │
│  ├─ DAG / 调度 / 缓存 / 重入             │
│  └─ 只管运行脚本                         │
│                                          │
│  Knowledge Base                          │
│  ├─ AI 知识库 (RAG)                      │
│  └─ 实验室数据库                         │
└──────────────────────────────────────────┘
```

## 核心原则

| 原则 | 说明 |
|------|------|
| 🚫 无工作流编辑器 | AI 写 Snakemake DSL，人不拖拽连线 |
| 🚫 无状态机 | 文件存在 = 完成，文件缺失 = 需运行 |
| 🚫 无框架约束 | 约束只在 prompt 层，代码只做该做的事 |
| ✅ 自由文件系统 | workspace = 目录，脚本随便写 |
| ✅ 命令行优先 | 能走 CLI 就不封装 API |
| ✅ 结果可视化 | viewer matrix 渲染数据看板 |

## 设计来源

三个参考项目被完整复制过来作为设计参考：

| 参考 | 目录 | 内容 | 文件数 |
|------|------|------|--------|
| **OpenHanako** | `hanako/` | 40+ LLM provider 插件、PI SDK、provider-registry、permission、auth | ~490 |
| **Hermes Agent** | `hermes/` | Memory 循环模式（MEMORY.md/USER.md + MemoryProvider ABC） | ~47 |
| **Snakemake** | `snakemake/` | 完整的 workflow 引擎源码（DAG/scheduler/executor/persistence） | ~132 |

### Hanako — Provider + PI 体系

- `hanako/lib/providers/` — 40 个声明式 LLM provider 定义
- `hanako/lib/pi-sdk/` — PI Coding Agent SDK 适配
- `hanako/lib/permission/` — safety policy, tool invocation
- `hanako/core/` — provider-registry, model-manager, agent-manager
- `hanako/server/routes/` — providers, auth, config, sessions API

### Hermes — Memory 循环

最值得参考的记忆循环模式：

```
pre-turn:   prefetch(query)       → 注入 system prompt
turn:       memory tool 交互        → 直接读写 MEMORY.md/USER.md
post-turn:  sync_turn(user, asst)  → 持久化到外部 provider
            queue_prefetch()       → 后台预加载下一轮
session结束: shutdown()             → 清理
```

### Snakemake — Workflow 引擎

唯一的 workflow 引擎，TDEase-zero 不重写它，而是通过 API 调用：

```python
with SnakemakeApi(output_settings=...) as api:
    dag_api.execute_workflow(executor="local")
```

## 目录结构

```
src/              Python 后端（AI, tools, services, domain, …）
TDEase-FrontEnd/  Electron + Vue 交互数据看板
app/              FastAPI 后端入口
scripts/          工具脚本
docs/             文档 / 架构 / 决策记录
tests/            测试
data/             数据 / 工作空间 / 数据库
hanako/           OpenHanako 参考副本
hermes/           Hermes Agent 参考副本
snakemake/        Snakemake 参考副本
```

## 快速开始

```bash
# 本地开发
cd TDEase-FrontEnd && pnpm install && pnpm run dev

# 后端
uv run python main.py

# 运行 workflow
snakemake -s workflow.smk --cores all
```

## 设计溯源

参见 `docs/ARCHITECTURE.md` 和 `docs/specs/` 了解详细设计决策。
