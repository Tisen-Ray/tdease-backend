# Hanako vs Hermes Agent 架构评估

> **2025-07-25 · 决定 TDEase-zero 前端 PI 内核的策略**

---

## 一、总体判断

| | Hanako | Hermes |
|------|------|------|
| 语言 | TypeScript (Node.js) | Python |
| 定位 | 个人 AI Agent (PI) | 个人 AI Agent (CLI) |
| 规模 | ~230 核心文件 | ~150 核心文件 |
| **结论** | ★★★★ 主选 — PI 内核 | ★★★ 记忆循环参考 |

**两者互补，不是竞争。** Hanako 提供 PI 运行时的完整骨架；Hermes 提供记忆和异步委托的最佳实现。

---

## 二、Subagent 体系

### Hanako — subagent-tool.ts

```
模式: 非阻塞派发 → DeferredResultStore 持久化 → 结果以 steer 消息注入对话

能力:
  delegate("任务", { agent: "coder" })   指定 agent
  delegate("任务", { background: true })  后台运行
  agent="?"                               列出所有可用 agent
  SubagentAccessDeniedError               权限拦截
  SUBAGENT_TIMEOUT = 30min                超时保护
```

**评价：** 够用。支持非阻塞、agent 路由、权限控制。但缺少原生并行批量派发（需要调用方自己 `Promise.all`）。

### Hermes — delegate_tool.py + async_delegation.py

```
模式: 同步或异步子进程 → ThreadPoolExecutor → completion_queue 通知

能力:
  delegate_task(goal, context)            单任务
  delegate_task(goals=[...], parallel=4)  批量并行
  delegate_task(background=true)          异步后台
  结果通过 completion_queue 在 agent 空闲时注入
  DaemonThreadPoolExecutor                daemon 线程池
```

**评价：** 更成熟。原生支持批量并行 + 后台异步。completion_queue 的 "agent 空闲时才注入结果" 设计很精巧 — 不打断正在进行的对话轮次。

### 结论

| 需求 | 选谁 |
|------|------|
| 即时 subagent 调用 | 都用得到 |
| 批量并行派发 | Hermes delegate_tool |
| 非阻塞后台 | 两者都可以 |
| Agent 路由 | Hanako agent="name" |

---

## 三、Dynamic Workflow

### Hanako — workflow/ (★ 关键优势)

Hanako 有一套完整的 **Workflow Script Runtime**：

```
lib/workflow/
├── meta.ts              提取 export const meta = { name, description, phases }
├── sandbox.ts           在 node:vm 沙箱里执行 workflow 脚本
├── host-api.ts          提供 agent(), parallel(), pipeline(), log(), phase(),
│                        workflow() (嵌套), budget, args
├── journal.ts           JSONL 断点日志 — 按 nodeSeq 匹配 key 做 resume
├── concurrency.ts       并发控制
└── structured-output.ts  schema-based 结构化输出
```

**这就是 Claude Code Workflow API 的等价物！**

```javascript
// AI 生成的 workflow 脚本
export const meta = {
  name: 'ptm-analysis',
  description: 'Run PTM discovery across 8 samples',
  phases: [{ title: 'Process' }, { title: 'Analyze' }, { title: 'Report' }],
};

phase('Process')
const results = await pipeline(
  SAMPLES,
  sample => agent(`处理 ${sample}`, { access: 'read' }),
  output => agent(`验证 ${output}`, { schema: VALIDATION_SCHEMA }),
);

phase('Report')
await agent(`汇总结果: ${JSON.stringify(results)}`);
```

**关键设计亮点：**
1. **Checkpoint/Resume** — journal 按 `nodeSeq + computeKey(prompt, opts)` 匹配，同位置同 key → 缓存命中，首不同 → 该位置及之后全部重跑
2. **Sandbox** — `node:vm` 执行，禁止 `require/process/fs/net`，禁止 `Math.random/Date.now`（确定性）
3. **Budget/Abort** — token 预算 + AbortSignal
4. **嵌套 workflow** — 限一层，共享 limiter/signal/budget
5. **Pipeline vs Parallel** — `pipeline(items, stage1, stage2)` 流式无屏障，`parallel(thunks)` 屏障等待全部

### Hermes

**没有 workflow DSL。** Hermes 的"工作流"概念是 cron jobs + delegate 组合，没有脚本运行时。

### 结论

| 需求 | 选谁 |
|------|------|
| Workflow 脚本执行 | **Hanako — 完整实现** |
| AI 生成编排逻辑 | Hanako host-api.ts |
| Checkpoint/Resume | Hanako journal.ts |
| 并行执行模式 | Hanako pipeline/parallel |
| 结构化输出验证 | Hanako structured-output.ts |

**Hanako 的 workflow runtime 恰好是 TDEase "AI 全量写工作流" 愿景的运行时基础。** 不需要 Snakemake 级别的 DAG 编排（那归 Snakemake），但需要 agent 级的编排（subagent 并行、pipeline、结果汇总）。

---

## 四、Provider 体系

### Hanako

```
lib/providers/ — 40 个声明式 ProviderPlugin

每个插件 ~10-50 行:
  export const deepseekPlugin = {
    id: "deepseek",
    displayName: "DeepSeek",
    authType: "api-key",
    defaultBaseUrl: "https://api.deepseek.com",
    defaultApi: "openai-completions",
  };
```

支持的 provider: OpenAI, Anthropic, DeepSeek, Ollama, 硅基流动, xAI, Gemini, Groq, 百川, 百度云, DashScope, 混元, Kimi, 月之暗面, Mistral, 火山引擎, 智谱...

### Hermes

Providers 在配置文件中定义（YAML），不通过插件系统。

### 结论

Hanako 的 provider 插件体系明显更灵活。40 个声明式插件可以直接用，而且添加新 provider 只需 ~10 行。

---

## 五、Memory 系统

### Hanako

```
lib/memory/
├── fact-store.ts        FactStore — 键值记忆
├── deep-memory.ts       深度记忆
├── memory-search.ts     语义搜索
├── memory-ticker.ts     定期触发回忆
├── memory-reflection-runner.ts  反思
├── config-loader.ts     配置加载
├── session-summary.ts   会话摘要
├── rolling-summary-format.ts  滚动摘要
└── prompts/             记忆提示词
```

### Hermes

```
tools/memory_tool.py:
  MEMORY.md — agent 的个人笔记 (文件存储)
  USER.md   — agent 对用户的了解
  Frozen snapshot 注入 system prompt
  即时落盘, mid-session 不改 prompt

plugins/memory/:
  holographic/ — HRR 向量符号架构
  mem0/        — Mem0 后端
  honcho/      — Honcho 后端
  hindsight/   — Hindsight 后端
```

### 结论

| 维度 | Hanako | Hermes |
|------|------|------|
| 简单性 | 复杂 fact-store | **极简 — 两个 .md 文件** |
| 可审计 | 需要工具读 | **直接 cat MEMORY.md** |
| 外部存储 | 无 | 多后端插件 (mem0/honcho/...) |
| 语义搜索 | 内置 | 依赖外部 provider |

**Hermes 的文件存储模式更好。** 两个 .md 文件，人可读、AI 可写、git 可跟踪。这完全匹配"文件系统即状态"的哲学。Hanako 的 fact-store 引入了不必要的抽象。

---

## 六、综合结论

### 直接用（不改）

| 来源 | 模块 | 原因 |
|------|------|------|
| Hanako | `providers/` (40 plugins) | 完整的 provider 生态 |
| Hanako | `pi-sdk/` | PI Coding Agent 适配 |
| Hanako | `llm/` | LLM 客户端抽象 |
| Hanako | `permission/` | 安全策略 |
| Hanako | `workflow/` ★ | **完整的 agent 级编排运行时** |
| Hanako | `sandbox/` | node:vm 隔离执行 |
| Hanako | `skills/` | 技能加载系统 |
| Hanako | `shell/` | shell 执行 |

### 参考设计（自己重写）

| 来源 | 功能 | 原因 |
|------|------|------|
| Hermes | MEMORY.md 文件存储 | 更简单、更符合哲学 |
| Hermes | async_delegation 批量并行 | 比 Hanako 的成熟 |
| Hermes | completion_queue 注入 | 不打断对话的设计精巧 |
| Hermes | MemoryProvider ABC | 插件化 memory 接口 |

### 不需要的

| 来源 | 模块 | 原因 |
|------|------|------|
| Hanako | `desk/` | 桌面自动化 (用不到) |
| Hanako | `channels/` | Telegram/Discord (用不到) |
| Hanako | `notifications/` | 推送通知 (用不到) |
| Hanako | `bridge/` | 跨平台桥接 (用不到) |
| Hanako | `character-cards/` | 角色卡片 (用不到) |
| Hanako | `conversations/` | 语音通话 (用不到) |
| Hanako | `diary/` | 日记 (用不到) |
| Hermes | `run_agent.py` (686KB) | 整套 agent 太重 |
| Hermes | `hermes_cli/` | 自己的 CLI (用不到) |

---

## 七、TDEase-zero PI 内核组合

```
pi-kernel/
├── providers/     ← Hanako (40 files, 不改)
├── pi-sdk/        ← Hanako (5 files, 不改)
├── llm/           ← Hanako (9 files, 不改)
├── permission/    ← Hanako (3 files, 不改)
├── workflow/      ← Hanako (6 files, 不改) ★ agent 级编排运行时
├── sandbox/       ← Hanako (22 files, 不改)
├── skills/        ← Hanako (5 files, 不改)
├── shell/         ← Hanako (4 files, 不改)
├── tools/         ← Hanako (40 files, 不改)
├── memory/        ← 自己写 (~200行) — MEMORY.md + USER.md 文件模式
├── subagent.ts    ← 自己写 (~150行) — 融合 Hermes async_delegation 设计
└── shared/        ← Hanako (81 files, 不改)

总计: ~230 不改 + ~350 行新写 = 薄胶水
```

---

*文档版本: v1.0*
*上次更新: 2025-07-25*
