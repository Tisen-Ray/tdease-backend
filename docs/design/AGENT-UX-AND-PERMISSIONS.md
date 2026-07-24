# TDEase-zero Agent 集成与权限设计

> **核心立场：Agent 的 UX 不是"给 Agent 一堆工具"，而是"给 Agent 一个世界和一道边界"。**
> 旧体系用工具白名单保安全 → 限制了 Agent 的智力。
> 新体系给全部自由，把安全放在**效果边界**上：能做什么不限，能影响什么有界。

关联文档：`ARCHITECTURE-0.md`、`SERVER-OPERATIONS.md`、`SERVER-PRODUCTION.md`、`FIRST-PRINCIPLES-AUDIT.md`（终审：轮子替换，冲突时以终审为准）。

---

## 一、workflow 全生命周期 = Agent 的能力，但不等于 Agent 的工具

### 关键区分

```
运行、监管、数据处理、拉取 —— 这些都必须 Agent 可做。
但"可做"不等于"包成一个个 bespoke tool"。
```

Agent 是一个 coding agent（Claude Code 类）。它**自带**一套久经考验的工具：

```
Bash / Read / Write / Edit / Glob / Grep / WebFetch ...
```

workflow 全生命周期通过 **tdease CLI** 暴露，Agent 用它已有的 Bash 工具调用：

| 生命周期动作 | Agent 的做法 | 新代码 |
|--------------|-------------|--------|
| 运行 workflow | `tdease submit` | 0（CLI 已有） |
| 监管运行 | `tdease status` / `tdease log --tail` | 0 |
| 等完成 | `tdease wait <run_id>`（阻塞至终态） | ~20 行 |
| 数据处理 | 直接写 Python/R 脚本跑（本地结果文件） | 0 |
| 拉取结果 | `tdease pull` | 0 |
| 按需取原始文件 | `tdease fetch raw/x.mzML`，或直接 open() 由 Finder 兜底 | 0 |
| 诊断失败 | 读日志 → 改 config → 重新 submit | 0 |

**Agent 的工具面 = 它原生的工具 + 一个 CLI 的 `--help`。**
不包 MCP tool，不包 function schema，不维护"AI 专用 API"。
CLI 是给人和 Agent 共用的同一个接口——这正是"命令行优先"原则的兑现：
多一个 API 封装就是多一个要同步、要测试、要文档化的轮子。

### 什么时候才值得包 tool

只有一种情况：需要**结构化双向交互**且 CLI 文本来回解析明显笨拙时。
目前的清单里没有一个动作满足这个条件。将来若出现，再加单个 tool，
而不是预先包一层。

---

## 二、按需拉取：Agent 是最好的预取器

两层机制（SERVER-OPERATIONS §九的细化）：

```
第 1 层 — Finder 兜底（哑的，自动的）:
  Agent open("raw/sampleA.mzML") → 本地缺失 → 自动 fetch → 缓存 → 返回
  Agent 无感知。保证"不会错"。

第 2 层 — Agent 显式规划（聪明的）:
  Agent 在动手前先想："我要做 40 个样本的 QC 对比，
  需要这 40 个 features.csv" → tdease pull "results/*/features.csv"
  一把拉齐，再开始分析。保证"不会慢"。
```

框架做不了第 2 层——预取策略需要理解"接下来要分析什么"，
这个知识只在 Agent 的推理里。这是把按需拉取交给 Agent 决定的根本原因：
**它不是在执行传输，它是在做计划。**

Finder 层依然必要：Agent 也会判断失误，直接 open() 一个没拉的文件时
不能崩，兜底层保证正确性与聪明程度无关。

---

## 三、Agent 与前端的关系：共享真相，不互相监视

### Agent 不需要"监控前端"

```
错误模型:  Agent ←(监视)— 前端 UI 状态
正确模型:  Agent ─┐
                 ├─→ 同一份真相 ←─ 前端
            文件系统 + 服务器状态
```

- 前端渲染的是文件和 run 状态；Agent 读的也是文件和 run 状态。
  两者天然一致，不需要同步通道。
- Agent pull 了结果 → 文件出现在本地 → 前端的 file watcher 刷新看板。
  **Agent 影响前端的媒介是文件，不是 UI 指令。**

### 反向：前端给 Agent 的一点点上下文

用户在看什么，对 Agent 有帮助（"帮我解释这张图"）：

```
前端 → Agent: 一条轻量 context push
  { "viewing": "results/summary/merged.csv",
    "viewer": "heatmap", "selection": ["sample_3"] }

原则: 单向、可忽略、非结构化也无妨。
Agent 拿它当提示，不当状态源。丢了对正确性零影响。
```

### Agent 活动的可见性

用户需要知道 Agent 在干嘛（稳定心态的 Agent 版）：

```
Dashboard 侧栏显示 Agent 的动作流:
  "提交了 run_a1b2c3"  "正在拉取 40 个结果文件"  "正在读 qc_report.csv"

来源: tdease CLI 的每次调用写一条 events（复用 runs 事件流机制）
     前端读事件文件渲染。Agent 不需要主动"汇报"。
```

---

## 四、权限哲学：从能力限制到边界遏制

### 旧体系的问题

```
"只给 Agent 给定的工具" → 安全来自能力缺失
  → 遇到工具清单外的合理需求, Agent 变蠢或卡住
  → 工具清单永远追不上真实任务的长尾
```

质谱分析的长尾是无限的：今天要比对两个 csv，明天要调一个 R 包，
后天要编译一个小工具。白名单模式等于要求设计者预知全部科学计算需求。

### 新体系的三道边界

安全不来自"Agent 没有什么工具"，来自"Agent 的效果落在哪"：

```
┌─ 边界 1: 本地文件系统 ──────────────────────────────┐
│  Agent 可读写执行的范围 = workspace 目录             │
│  workspace 内: 完全自由 (ls/cat/rm/跑脚本/装包)      │
│  workspace 外: 只读 (系统库、参考数据), 写 = 拒绝    │
│  实现: OS 级沙箱 (sandbox-exec / bubblewrap /        │
│        容器), 或 Agent 框架自带的 permission 层      │
│        → hanako/lib/permission/ 就是现成参考         │
└─────────────────────────────────────────────────────┘
┌─ 边界 2: 网络 ──────────────────────────────────────┐
│  Agent 不直接持有服务器凭据，不直接发 HTTP           │
│  所有服务器交互 = tdease CLI (持 agent 级 token)     │
│  出站网络可选白名单 (装包/查文献放行, 其余询问)      │
└─────────────────────────────────────────────────────┘
┌─ 边界 3: 服务器 API ────────────────────────────────┐
│  agent token 的 scope:                               │
│    ✅ submit / status / log / pull / fetch           │
│    ✅ push (白名单文件) / push-data (带大小确认)     │
│    ❌ delete workspace / gc / admin / 改配额         │
│       → 这些要 user 级 token, Agent 碰不到           │
│  配额/限速/背压对 Agent 流量同样生效                 │
│    (SERVER-PRODUCTION §三/§五)                      │
└─────────────────────────────────────────────────────┘
```

### 为什么这就够了：Agent 攻击面 = 用户攻击面

```
Agent 对服务器能做的最坏的事
  = 用户拿着 CLI 能做的最坏的事
  = 提交一堆 run (配额挡住), 传一堆数据 (配额挡住),
    拉自己的文件 (本来就是他的)

服务器不需要"防 Agent"，只需要防"任何客户端"——
这套防线 SERVER-PRODUCTION 已经建完。
Agent 没有引入新的攻击面, 因为 Agent 的服务器访问
被约束在 CLI + 受限 token 之内。
```

### 错误可能性：失误的爆炸半径是受限的

Agent 会犯错。设计目标是让每个错误都可恢复、有界：

| Agent 失误 | 遏制机制 | 最坏后果 |
|-----------|---------|---------|
| 删了 workspace 里重要文件 | 本地 git/快照（workspace 建议纳入 git） | 可恢复 |
| 提交了错的 workflow | run 快照独立 + cancel | 浪费一次算力 |
| 重复提交 | 幂等键（SERVER-PRODUCTION §五） | 无 |
| 拉了一堆大文件塞满本地磁盘 | 本地缓存上限 + LRU 清理 | 清缓存 |
| 想删服务器上的 workspace | token scope 拒绝 | 无 |
| 改坏了 Snakefile | git diff + AI 自己 diff 回滚 | 可恢复 |

**零范式在这里再次帮忙：一切真相是文件，文件可快照、可 diff、可恢复，
所以"给 Agent 自由"的代价有天花板。**

---

## 五、确认层：少数动作要问过人

自由不等于无确认。按**不可逆性/成本**分级（复用 coding agent
框架的 permission 模式：allow / ask / deny 规则表）：

```
auto-allow (默认放行):
  workspace 内一切文件操作
  tdease status / log / pull / fetch / submit(脚本类)
  本地跑脚本、装包

ask (首次询问, 记住选择):
  push-data 超过 N GB
  tdease submit 且队列已满/预估算力大
  写 workspace 外的路径（原则上 deny, 破例需明示）
  出站网络到新域名

deny (规则拒绝, 无询问):
  使用 user 级 token 的操作 (delete/gc/admin)
  修改 .tdease/identity 文件
```

规则表本身是一个文件（`.tdease/permissions.yaml`），
用户可改，AI 可解释。**权限策略是数据，不是代码。**

---

## 六、审计：自由的前提是可追溯

```
Agent 的每个动作都可重建:

本地:  workspace 在 git 下 → 文件变更全历史
       .tdease/events.jsonl → CLI 动作流水
云端:  runs 表 + run 快照 → 谁提交了什么代码、结果如何
       (SERVER-PRODUCTION §二, 免费获得)

出问题时: "Agent 干了什么" 是一次 git log + 一次单表查询。
```

可追溯性是让"高自由度"在组织层面可被接受的真正筹码：
不是事前限制智力，而是事后能看清一切。

---

## 七、不做清单（Agent 维度）

| 不做 | 为什么 |
|------|--------|
| 为每个服务器操作包 MCP tool | CLI 就是接口，封装是重复轮子 |
| Agent 专用 API 面 | 人和 Agent 共用 CLI，双份接口必然腐化 |
| 工具白名单 | 限制智力，追不上科学计算长尾 |
| Agent 监视前端 UI | 共享文件真相，无需监视通道 |
| 前端渲染指令通道 | Agent 写文件，file watcher 刷新，够了 |
| Agent 专用配额体系 | 复用用户配额，Agent 不是新主体 |
| 新的权限状态机 | allow/ask/deny 规则表 + 两个 token 级别 |

---

## 八、要写的代码清单

| 组件 | 量级 |
|------|------|
| `tdease wait`（阻塞至 run 终态） | ~20 行 |
| agent 级 / user 级双 token + scope 校验 | ~0.5 天 |
| `.tdease/permissions.yaml` 规则表 + CLI 接入 | ~0.5 天 |
| workspace 沙箱配置（复用 agent 框架/hanako permission） | 配置为主，~0.5 天 |
| CLI 调用写 events.jsonl | ~10 行 |
| 前端 context push（当前视图 → Agent） | ~0.5 天 |
| 前端 Agent 动作流面板（读 events 渲染） | ~0.5 天 |
| 本地缓存上限 + LRU | ~0.5 天 |

**合计约 3 天，且没有一项是新的抽象层。**

### 零范式检验

```
1. 新增状态轴？ → 没有。权限是静态规则文件，token 是两个枚举值。
2. 文件操作能实现？ → 规则表/events/快照/git 全是文件。
3. AI 能直接处理？ → 整个设计的目的就是让 AI 直接处理一切。
```

---

*文档版本: v0.1*
*上次更新: 2025-07-24*
