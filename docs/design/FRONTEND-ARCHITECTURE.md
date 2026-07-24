# TDEase-zero 前端架构

> **复用 Hanako PI 内核 + 保留 TDEase 交互看板 + 删掉工作流编辑器**

---

## 一、三层结构

```
TDEase-FrontEnd/
│
├── pi-kernel/          ← 从 Hanako 复用 (完整复制，不做胶水)
│   ├── pi-sdk/           PI SDK 适配层
│   ├── providers/        40+ LLM provider 插件
│   ├── llm/              LLM 客户端 (provider-client, cache, usage)
│   ├── permission/       safety-policy, tool-invocation
│   ├── memory/           MEMORY.md deep-memory 系统
│   ├── sandbox/          PI 沙盒环境
│   ├── tools/            browser, file, search, subagent...
│   └── skills/           技能系统
│
├── shell/               ← 已有 (不变)
│   ├── main.cjs           Electron 主进程
│   ├── preload.cjs        预加载脚本
│   └── splash.html        启动画面
│
├── ui/                  ← Vue 3 + TypeScript
│   │
│   ├── pages/
│   │   ├── dashboard.vue      主看板 (文件浏览 + 结果渲染)
│   │   ├── editor.vue         Snakefile 编辑器
│   │   ├── runs.vue           运行历史
│   │   └── settings.vue       Provider 配置等
│   │
│   ├── components/
│   │   ├── visualization/     ★ 保留 - viewer matrix 家族
│   │   ├── widgets/           ★ 保留 - 交互积木
│   │   ├── table/             ★ 保留
│   │   ├── chat/              改 - AI chat (PI 内核驱动)
│   │   ├── run/               新 - 运行状态面板
│   │   └── common/            精简
│   │
│   ├── services/
│   │   ├── backend.ts         新 - TDEase 后端 API 客户端
│   │   ├── pi-bridge.ts       新 - PI 内核 ↔ UI 桥接
│   │   └── visualization/     ★ 保留 - viewer data 服务
│   │
│   ├── stores/                精简
│   │   ├── runs.ts            新 - 运行状态
│   │   ├── workspace.ts       ★ 保留 - workspace 管理
│   │   └── settings.ts        新 - provider/backend 配置
│   │
│   └── composables/           精简

```

---

## 二、从 TDEase-FrontEnd 保留 vs 删除

### 保留

| 模块 | 原因 |
|------|------|
| `components/visualization/` | viewer matrix — 结果渲染核心 |
| `components/widgets/` | 交互积木 |
| `components/table/` | 数据表格 |
| `components/icons/` | 图标库 |
| `components/theme/` | 主题系统 |
| `services/visualization/` | viewer data 处理 |
| `stores/visualization-*.ts` | viewer 状态 |
| `stores/workspace.ts` | workspace 管理 |
| `composables/useChart*` | 图表交互 |
| `composables/useResponsive` | 响应式 |
| `electron/` 全部 | Electron 壳 |
| `locales/` | 国际化 |
| `styles/` | 样式系统 |

### 删除

| 模块 | 原来做什么 | 为什么删 |
|------|-----------|---------|
| `pages/workflow.vue` | 可视化编辑器 | AI 写 Snakefile |
| `pages/copilot.vue` | Copilot 会话 | PI 内核替代 |
| `pages/explore.vue` | 工作流浏览 | 改为 dashboard |
| `components/workflow/` | 节点编辑器 | 不再需要 |
| `components/node/` | 工作流节点 | 改为结果卡片 |
| `components/nodes/` | 节点列表 | 改为规则列表 |
| `components/ai/` | 旧 AI 面板 | PI 内核替代 |
| `composables/workflow/` | 工作流编辑 | 不再需要 |
| `composables/ai/` | 旧 AI 交互 | PI 内核替代 |
| `stores/workflow.ts` | 工作流状态 | 不再需要 |
| `stores/auth.ts` | 旧认证 | 简化版替代 |
| `stores/execution.ts` | 执行状态机 | runs.ts 替代 |
| `stores/run-session.ts` | 会话状态机 | 不再需要 |
| `services/workflow/` | 工作流 CRUD | 不再需要 |
| `services/execution/` | 执行 API | backend.ts 替代 |
| `services/ai/` | 旧 AI API | pi-bridge.ts 替代 |
| `services/auth/` | 旧认证 | 简化 |
| `services/websocket/` | 旧 WS | backend.ts 内联 |
| `types/workflow.ts` | 工作流类型 | 不再需要 |
| `types/ai/` | 旧 AI 类型 | PI 接口替代 |
| `types/tool-*.ts` | 工具类型 | 精简 |

---

## 三、从 Hanako 复用什么

```
hanako/lib/pi-sdk/         → pi-kernel/pi-sdk/        (5 files)
hanako/lib/providers/      → pi-kernel/providers/     (40 files)
hanako/lib/llm/            → pi-kernel/llm/           (9 files)
hanako/lib/permission/     → pi-kernel/permission/    (3 files)
hanako/lib/memory/         → pi-kernel/memory/        (19 files)
hanako/lib/sandbox/        → pi-kernel/sandbox/       (22 files)
hanako/lib/tools/          → pi-kernel/tools/         (40 files)
hanako/lib/skills/         → pi-kernel/skills/        (5 files)
hanako/lib/shell/          → pi-kernel/shell/         (4 files)
hanako/lib/auth/           → pi-kernel/auth/          (1 file)
hanako/shared/             → pi-kernel/shared/        (81 files)
```

Hanako 的 PI 内核是完整的独立包，**不需要修改**。我们只需要在 `services/pi-bridge.ts` 里写一个薄桥接层：

```
PI 内核 (TypeScript, 不修改)
    ↓
pi-bridge.ts (~100 行)
    ↓
Vue UI (调用 bridge)
```

---

## 四、数据流

```
┌─────────────────────────────────────────────────┐
│  UI Layer (Vue)                                  │
│                                                   │
│  dashboard.vue ←→ 编辑器.vue ←→ 运行.vue         │
│       │                │             │             │
│       ▼                ▼             ▼             │
│  ┌─────────────────────────────────────┐          │
│  │          services/                    │          │
│  │                                       │          │
│  │  backend.ts           pi-bridge.ts    │          │
│  │  (HTTP/WS to server)   (PI 内核桥接)   │          │
│  └───────┬───────────────┬───────────────┘          │
│          │               │                         │
├──────────┼───────────────┼─────────────────────────┤
│          ▼               ▼                         │
│  ┌──────────┐  ┌──────────────────────┐           │
│  │ 后端 API │  │  PI 内核 (Hanako)     │           │
│  │          │  │  ├─ providers (40)    │           │
│  │ POST run │  │  ├─ pi-sdk            │           │
│  │ GET log  │  │  ├─ llm client        │           │
│  │ WS status│  │  ├─ memory            │           │
│  │ GET files│  │  └─ sandbox/tools     │           │
│  └──────────┘  └──────────────────────┘           │
│                                                   │
│  ┌─────────────────────────────────────┐          │
│  │  stores/ (pinia)                     │          │
│  │  ├─ runs.ts      运行状态            │          │
│  │  ├─ workspace.ts  workspace 管理     │          │
│  │  └─ settings.ts  配置存储            │          │
│  └─────────────────────────────────────┘          │
└─────────────────────────────────────────────────┘
```

---

## 五、pi-bridge.ts 接口

```typescript
// services/pi-bridge.ts  ~100行

// 初始化 PI 会话
function initSession(opts: {
  provider: string;      // "anthropic" | "deepseek" | ...
  model: string;         // "claude-sonnet-5" | ...
  workspaceDir: string;  // 当前工作目录
}) → Session

// 发送消息
function sendMessage(session, message: string) → AsyncIterable<Chunk>

// 注册自定义工具 (TDEase 特有的)
function registerTool(session, tool: Tool)

// 读取 provider 列表 (用于 settings 页)
function listProviders() → ProviderPlugin[]

// 读取 provider 凭证 (API key 等)
function getCredentials(providerId: string) → Credential?
```

---

## 六、backend.ts 接口

```typescript
// services/backend.ts  ~80行

// 与 TDEase-zero 后端通信
class TDEaseClient {
  constructor(baseUrl: string)

  // Runs
  submit(workspace, snakefile, config?) → Promise<RunInfo>
  status(runId: string) → Promise<RunInfo>
  cancel(runId: string) → Promise<boolean>
  tailLog(runId: string, lines?: number) → Promise<string>
  pullFiles(runId: string, patterns?) → Promise<string[]>
  fetch(runId: string, path: string) → Promise<Blob>

  // SSE EventSource
  subscribe(runId: string, callback: (status) => void)

  // Workspace
  listRuns(workspace: string) → Promise<RunInfo[]>
}
```

---

## 七、页面设计

### Dashboard (主页面)

```
┌──────────────────────────────────────────────────┐
│  [workspace 选择]         [提交运行]  [设置]      │
├────────────┬───────────────────────┬─────────────┤
│ 文件树     │                       │  运行列表面板│
│            │   交互数据看板       │             │
│ workspace/ │   (viewer matrix)    │  run_1 ✓    │
│  ├─ raw/   │                      │  run_2 ✓    │
│  ├─ results│  ┌─ 色谱图 ───┐     │  run_3 🔄   │
│  ├─ Snake  │  │ ╱╲   ╱╲   │     │             │
│  └─ config │  │╱  ╲╱  ╲──│     │  [查看日志] │
│            │  └───────────┘     │  [拉取结果] │
│            │                      │             │
│            │  双击文件 → 渲染看板 │             │
├────────────┴───────────────────────┴─────────────┤
│  AI Chat (底部/侧边)     │ 状态: 已连接服务器    │
└──────────────────────────────────────────────────┘
```

### Editor (Snakefile 编辑)

```
┌──────────────────────────────────────────────────┐
│  Snapfile  /  config.yaml          [保存] [运行] │
├──────────────────────────────────────────────────┤
│                                                  │
│  rule process_mzml:                             │
│      input: "raw/{sample}.mzML"                 │
│      output: "results/{sample}/features.csv"    │
│      shell: "tools/process.py {input} {output}" │
│                                                  │
│                                                  │
├──────────────────────────────────────────────────┤
│  AI: "我建议把 cores 调到 8..."   [应用建议]     │
└──────────────────────────────────────────────────┘
```

### Runs (运行历史)

```
┌──────────────────────────────────────────────────┐
│  历史运行                          [刷新]        │
├──────────────────────────────────────────────────┤
│  ✅ run_a1b2  7/25 14:32  3m12s  12 files      │
│  ✅ run_c3d4  7/25 10:15  5m07s   8 files      │
│  ❌ run_e5f6  7/24 18:41  0m23s  error: OOM    │
│  🔄 run_g7h8  7/25 15:00  正在运行...           │
└──────────────────────────────────────────────────┘
```

### Settings (配置)

```
┌──────────────────────────────────────────────────┐
│  设置                                            │
├──────────────────────────────────────────────────┤
│  后端连接                                        │
│  [http://lab-server:8000]                        │
│                                                  │
│  AI Provider                                     │
│  [Anthropic ▼]  model: [claude-sonnet-5 ▼]      │
│  API Key: [••••••••••••]                         │
│                                                  │
│  默认配置                                        │
│  cores: 8    memory: 32G                         │
│                                                  │
│  模式: ○ 本地  ● 服务器  ○ 云端                  │
└──────────────────────────────────────────────────┘
```

---

## 八、store 设计

```typescript
// stores/runs.ts
interface RunsState {
  active: Map<string, RunInfo>   // 当前活跃的 run
  history: RunInfo[]              // 历史列表
  wsConnected: boolean
}

// stores/workspace.ts (保留)
interface WorkspaceState {
  root: string
  files: FileNode[]
  selectedPath: string | null
}

// stores/settings.ts
interface SettingsState {
  backendUrl: string
  provider: string
  model: string
  mode: 'local' | 'server' | 'cloud'
}
```

---

## 九、保留 vs 新增 vs 复用

| 来源 | 内容 | 用途 |
|------|------|------|
| TDEase-FrontEnd | viewer matrix, table, widgets, theme, electron | ★ 保留 |
| Hanako | pi-sdk, providers, llm, memory, sandbox, tools | ★ 复用 |
| 新写 | pi-bridge.ts, backend.ts, stores (runs/settings) | 薄胶水 |
| 改造 | dashboard.vue, editor.vue, runs.vue, settings.vue | 从旧页面改 |
| 删除 | workflow editor, copilot, old AI, state machines | ~40 files |

---

## 十、文件统计

| 层 | 文件数 | 来源 |
|----|--------|------|
| pi-kernel/ | ~230 | Hanako 完整复制 |
| shell/ | ~4 | 已有 |
| ui/ | ~60 | 精选 + 新写 + 改造 |
| **总计** | ~294 | |
| **我们的代码 (新写 + 改造)** | ~15 files | |
| **胶水比** | ~1:20 | YAGNI at its finest |

---

*文档版本: v1.0*
*上次更新: 2025-07-25*
