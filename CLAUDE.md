# TDEase-zero — First-Principles Architecture

## 核心哲学

```
┌─ PI (本地) ─────────────────────────────┐
│  CLI Agent (Claude Code / coding agent)  │
│  ├─ 写 Snakemake DSL                     │
│  ├─ 跑脚本                               │
│  ├─ hook/tool → evidence runtime         │
│  └─ prompt 规则 = 唯一约束               │
│                                          │
│  Interactive Dashboard                   │
│  ├─ 可视化节点积木 (来自 viewer matrix)  │
│  ├─ 交互数据看板 (非工作流编辑)          │
│  └─ 自由组装 → 自定义结果渲染            │
└──────────────┬───────────────────────────┘
               │ 上传脚本 / 下载结果
               ▼
┌─ Server / 后端 ─────────────────────────┐
│  app/  FastAPI 用户/数据库/谁跑了什么     │
│  src/  核心: 节点/转换/Snakemake 执行    │
│                                          │
│  Knowledge Base                          │
│  ├─ AI 知识库 (嵌入/检索)                │
│  └─ 实验室数据库                         │
└──────────────────────────────────────────┘
```

## 不做什么（YAGNI）

| 不做 | 替代方案 |
|------|---------|
| 可视化工作流编辑器 | AI 写 Snakemake DSL |
| 自研 workflow DAG 引擎 | TDEase Execution Runtime (selectively migrated from Snakemake) |
| 状态机 / state-machine.ts | 文件系统 = 状态 |
| 流程编排节点 | AI 直接写脚本 |
| 前端配置工作流 | prompt 约束全量交给 AI |

## 做什么

| 做 | 原因 |
|----|------|
| 交互数据看板 | 结果可视化是刚需，但由 viewer matrix 渲染 |
| 可视化节点积木 | 提供可组合的渲染块，非流程编排 |
| hook/tool evidence runtime | 可审计性 |
| workspace 权限分派 | 安全性 |
| Knowledge Base | AI 需要上下文 |
| Prompt 规则体系 | 唯一约束层 |

## 项目结构

```
app/              FastAPI 后端
  ├── api/         路由 (admin, ai, files, runs, workspace...)
  ├── core/        auth, config, 数据库工具
  ├── database/    DB lifecycle + migrations
  ├── models/      SQLModel 数据模型
  ├── schemas/     Pydantic 请求/响应模式
  └── main.py     入口

src/              核心代码
  ├── contracts/    类型真相 — 前后端/CLI/Agent 共享
  ├── execution_runtime/  TDEase 执行引擎 (selectively migrated from Snakemake)
  │   ├── storage.py     唯一文件写入原语
  │   ├── events.py      从引擎内部直接发出 TDEase typed event
  │   ├── errors.py      ExecError → ErrorCode
  │   └── runtime.py     preflight / execute / cancel
  ├── snakemake/    向后兼容封装 → 委托给 execution_runtime
  ├── services/     文件/证据/worker 服务
  ├── ai/          Agent 系统
  ├── domain/      领域模型 (proteomics, identity...)
  ├── tools/       原子工具
  └── infrastructure/ 基础设施
  └── main.py     入口

src/              核心代码
  ├── ai/          Agent 系统 (session, prompts, tools, eval, harness...)
  ├── domain/      领域模型 (proteomics, workflow, identity...)
  ├── nodes/       内置特殊节点 (database, deconvolution, feature, massql...)
  ├── tools/       原子工具 (ptm...)
  ├── services/    服务层 (runs, workspace, permissions)
  ├── snakemake/   Snakemake 封装层 ★
  │   ├── __init__.py     公开 API
  │   ├── service.py      程序化调用 SnakemakeApi
  │   ├── workflow_spec.py WorkflowSpec → Snakefile 渲染
  │   └── evidence.py     证据收集钩子
  ├── contracts/   契约定义
  ├── capabilities/能力系统
  ├── storage/     存储抽象
  ├── infrastructure/ 基础设施
  ├── workspace/   workspace 管理
  └── mcp_server/  MCP 服务

TDEase-FrontEnd/  Electron + Vue 交互看板
参考副本:
  hanako/          OpenHanako provider/PI 体系
  hermes/          Hermes Agent memory loop
  snakemake/       Snakemake 源码参考
```

## 硬规则

1. **文件系统即状态。** 文件存在 = 完成，文件缺失 = 需运行。无状态机。
2. **能走命令行就走命令行。** Snakemake、Python 脚本、CLI tool。不要封装成 API 再调。
3. **约束在 prompt 层，不在框架层。** 不在代码里做"流程校验"之类的事。
4. **绝对自由的文件系统。** workspace 就是目录，脚本随便写，works 就行。
5. **单点真理。** 一个功能一个实现。无 shim、无死代码、无注释掉的代码。

## 工作流（Workflow = Snakemake）

```
# 示例 workflow (Snakefile)
rule process_mzml:
    input: "raw/sample.mzML"
    output: "results/features.csv"
    shell: "tools/process.py {input} {output}"
```

- Workflow 是 Snakemake 文件，不是 UI 上的节点。
- AI Agent 负责生成、调试、优化 Snakemake。
- 前端不渲染 DAG，只渲染结果。
- 后端通过 `src/snakemake/service.py` 调用 SnakemakeApi。

## Snakemake / Workflow DSL

Agent 直接写 Snakemake DSL。TDEase Execution Runtime 解析并执行。
```python
# 例：Agent 生成的 Snakefile
# rule process_mzml:
#     input: "raw/{sample}.mzML"
#     output: "results/{sample}/features.csv"
#     shell: "process.py {input} {output}"
```

无中间 DSL、无 WorkflowSpec、无代码生成。Snakefile 是用户 workspace 中的
普通文件。Execution Runtime 直接从内部执行，不 shell out 到 `snakemake` 命令。

## TDEase Execution Runtime

```python
from src.execution_runtime import preflight, execute, cancel

# 校验
pf = preflight(commit)  # -> PreflightResult (临时 view model, 不持久化)

# 执行
result = execute(commit)  # -> ExecutionResult
# 内部直接发出 TDEase typed events → events.jsonl
# 内部只通过 Storage Layout 写入文件
```

- 无 `import snakemake`
- 无运行时 `snakemake` 命令
- 无 `.snakemake/` 目录
- 上游名称仅存于 `THIRD_PARTY.md` 和 `provenance/source-ledger.json`

## 设计参考（完整副本）

| 来源 | 路径 | 关键内容 |
|------|------|----------|
| OpenHanako | `hanako/lib/providers/` | 40 个 LLM provider 声明式插件 |
| OpenHanako | `hanako/lib/pi-sdk/` | PI Coding Agent SDK 适配 |
| OpenHanako | `hanako/lib/permission/` | 安全策略、工具调用权限 |
| OpenHanako | `hanako/core/provider-registry.ts` | provider 注册表设计 |
| OpenHanako | `hanako/server/routes/providers.ts` | provider API 路由 |
| Hermes | `hermes/agent/memory_manager.py` | 记忆循环编排 |
| Hermes | `hermes/agent/memory_provider.py` | MemoryProvider ABC |
| Hermes | `hermes/agent/curator.py` | 后台技能维护 |
| Hermes | `hermes/tools/memory_tool.py` | MEMORY.md/USER.md 文件存储 |
| Snakemake | `snakemake/src/snakemake/api.py` | 程序化 API 入口 |
| Snakemake | `snakemake/src/snakemake/dag.py` | DAG 构建 |
| Snakemake | `snakemake/src/snakemake/executors/local.py` | 本地执行器 |
| Snakemake | `snakemake/src/snakemake/persistence/` | 作业持久化 |
