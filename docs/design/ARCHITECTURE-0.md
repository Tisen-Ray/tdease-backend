# TDEase-zero 架构设计 v0

> **核心思想：文件系统即状态。命令行即接口。Snakemake 即引擎。**
> 不做状态机、不做可视化编排、不做双向同步、不做自己的 DAG。

---

## 一、系统全景

```
┌──────────────────────────────────────────────────┐
│                  本地 / PI                         │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ AI Agent │  │ CLI     │  │ Dashboard      │  │
│  │ (coding) │──│ (脚本)  │──│ (Vue/Electron) │  │
│  └──────────┘  └──────────┘  └────────────────┘  │
│       │               │              │            │
│       ▼               ▼              ▼            │
│  ┌──────────────────────────────────────────┐     │
│  │          本地文件系统 (workspace)         │     │
│  │  config.yaml / Snakefile / scripts/      │     │
│  │  results/ (缓存) / .tdease/ (元数据)     │     │
│  └──────────────────┬───────────────────────┘     │
│                     │ push / pull / fetch          │
└─────────────────────┼────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────┐
│                  云端 Server                       │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ 队列     │  │ Worker  │  │ 用户 / 数据库  │  │
│  │ queue    │──│ (轮询)  │──│ (谁跑了什么)    │  │
│  └──────────┘  └────┬─────┘  └────────────────┘  │
│                     │                             │
│                     ▼                             │
│  ┌──────────────────────────────────────────┐     │
│  │  Snakemake 执行 (容器/Slurm/本地)        │     │
│  │  .snakemake/metadata/ (证据)             │     │
│  └──────────────────────────────────────────┘     │
│                                                   │
│  ┌──────────────────────────────────────────┐     │
│  │  持久文件系统                            │     │
│  │  workspace/{id}/raw/ (mzML)              │     │
│  │  workspace/{id}/results/ (结果)          │     │
│  │  workspace/{id}/.snakemake/ (证据)       │     │
│  └──────────────────────────────────────────┘     │
│                                                   │
└──────────────────────────────────────────────────┘
```

---

## 二、文件同步：三种操作

不需要双向同步引擎。不需要冲突解决。不需要 diff/merge。

### Push（本地 → 云端）

在用户触发 run 时，将必要文件推送到云端。

```
默认推送：
  Snakefile            — 必须
  config.yaml          — 必须
  scripts/             — 必须
  *.smk                — 可选 (include 的 subworkflow)
```

上传即创建 run。同步到云端的 workspace 目录。

### Pull（云端 → 本地）

在 run 完成后拉回结果。

```
默认拉取：
  results/**           — 所有结果文件
  .snakemake/metadata/ — Snakemake 执行元数据
  .tdease/evidence/    — 自定义证据

拉取模式：
  pull           — 拉全量 results/
  pull --new     — 只拉比本地新的文件
  pull "*.csv"   — 按 pattern 拉取
```

### Fetch（按需拉取）

AI Agent 在分析时，发现需要某个原始文件：

```
场景：
  AI: "我需要对样本A的原始谱图做个检查"
  → fetch("raw/sampleA.mzML")
  → 云端传输到本地 cache
  → AI 透明使用
```

按需获取在本地是一个**透明代理**：

```
从 AI 的视角：文件就在 workspace 里。
实际上：Finder 发现文件缺失 → 自动从云端拉取 → 缓存到本地。
```

---

## 三、进程管理

### 状态模型

只有一个生命周期轴，无并行子状态机：

```
QUEUED      (排队中, 等待 worker 拾取)
RUNNING     (运行中, Snakemake 进程活跃)
  ├─ SUCCEEDED (成功)
  ├─ FAILED    (失败)
  └─ CANCELLED (用户取消)
```

### 队列表

```sql
CREATE TABLE runs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    workspace   TEXT NOT NULL,
    snakefile   TEXT NOT NULL,
    config      TEXT,          -- JSON
    status      TEXT DEFAULT 'QUEUED',  -- QUEUED | RUNNING | SUCCEEDED | FAILED | CANCELLED
    created_at  TEXT,
    started_at  TEXT,
    finished_at TEXT,
    pid         INTEGER,       -- OS 进程 ID（RUNNING 时有效）
    exit_code   INTEGER,       -- 进程退出码
    error       TEXT,          -- 致命错误消息
);
```

### Worker 守护进程

```python
# ~50 行核心循环
while True:
    run = queue.dequeue()      # 取 QUEUED → 设为 RUNNING
    if not run:
        sleep(1); continue
    
    proc = Popen(["snakemake", "-s", run.snakefile, "--cores", ...])
    run.pid = proc.pid         # 存 PID
    proc.wait()
    
    run.status = "SUCCEEDED" if proc.returncode == 0 else "FAILED"
    run.exit_code = proc.returncode
```

### 实时状态同步

```
客户端 ← SSE ← 服务端

推消息格式:
  { "run_id": "...", "status": "RUNNING", "pid": 12345 }
  { "run_id": "...", "status": "SUCCEEDED", "exit_code": 0 }
  { "run_id": "...", "log_tail": "...latest 50 lines..." }
```

详细日志：客户端直接请求 `/api/runs/:id/log`，返回 Snakemake 日志文件内容。
不需要心跳、不需要状态恢复、不需要重连状态同步。断连重连后客户端主动 pull 一次当前状态即可。

### 排队策略

FIFO 简单队列。如果将来需要优先级或资源限制，加一个 `priority` 字段即可。

```
当前版本: FIFO + 单 worker
未来版本: priority 字段 + 多 worker + 资源约束
```

---

## 四、版本管理

### 核心观点

版本管理 = 文件系统快照。

不是状态机的状态转换。不是 DAG 的版本树。不是复杂 diff 引擎。

### 做法

每个 run 创建前，自动保存**运行时的输入**快照：

```
workspaces/
  my-project/
    current/
      Snakefile
      config.yaml
      ...                     ← 用户编辑区

  my-project/
    runs/
      run_2025-07-25_01/
        Snakefile             ← 只读快照
        config.yaml
      run_2025-07-25_02/
        Snakefile
        config.yaml
```

快照必须自包含执行身份：Snakefile、config、scripts、输入 tree/blob identities、
package/environment locks。`run.json` 记录这些内容的 digest，充当不可变 Run
commit；缺少任一项都不能声称可审计重放。

### 版本回滚 = 文件复制

```
# 回滚到某个历史版本
cp workspace/runs/run_2025-07-25_01/Snakefile workspace/current/Snakefile
cp workspace/runs/run_2025-07-25_01/config.yaml workspace/current/config.yaml
```

### 版本对比 = AI diff

```
用户: "上次的参数是什么？"
AI:   diff workspace/runs/run_2025-07-25_01/config.yaml workspace/current/config.yaml
      → "参数 X 从 0.5 改成了 0.8"
```

### 只有三种版本操作

| 操作 | 实现 |
|------|------|
| 保存快照 | 运行前 `cp Snakefile runs/{id}/` |
| 查看历史 | `ls runs/`，每个目录都有人可读 |
| 回滚 | `cp runs/{id}/* current/` |

---

## 五、用户旅程

### 完整流程

```
┌─ 1. 用户编辑 ──────────────────────────┐
│  AI Agent 或用户手动编辑                │
│  Snakefile + config.yaml                │
│  全在本地 workspace/ 里                 │
└──────────────────┬─────────────────────┘
                   ▼
┌─ 2. 提交运行 ──────────────────────────┐
│  tdease run submit                      │
│  → push Snakefile + config + scripts    │
│  → server 入队 (QUEUED)                 │
│  → 返回 run_id                         │
└──────────────────┬─────────────────────┘
                   ▼
┌─ 3. 排队/执行 ────────────────────────┐
│  (可选) 本地 tail 云端日志             │
│  SSE 推送: QUEUED → RUNNING → 终态    │
│  进度 = Snakemake 自己产生的日志       │
└──────────────────┬─────────────────────┘
                   ▼
┌─ 4. 拉取结果 ──────────────────────────┐
│  tdease run pull <run_id>              │
│  → 下载 results/** 到本地缓存          │
│  → Dashboard 自动刷新看板              │
└──────────────────┬─────────────────────┘
                   ▼
┌─ 5. AI 分析 ───────────────────────────┐
│  AI Agent 读取结果文件                  │
│  需要某个 mzML → fetch("raw/x.mzML")   │
│  按需从云端拉取                         │
│  全在本地透明进行                       │
└─────────────────────────────────────────┘
```

### 典型交互

```bash
# 1. 编辑工作流（AI 或手动）
# 本地 workspace 里自由操作

# 2. 提交运行
$ tdease submit
✓ 已提交: run_a1b2c3 (QUEUED)

# 3. 查看状态
$ tdease status run_a1b2c3
RUNNING (pid: 4521) · 已运行 2m34s
→ 执行: rule deconvolve (样本A)
→ 日志: 输出 57 个特征

# 4. 查看结果
$ tdease list run_a1b2c3
results/sampleA/features.csv
results/sampleA/deconv.csv
results/sampleB/features.csv

# 5. 拉取结果
$ tdease pull run_a1b2c3
↓ results/sampleA/features.csv  (1.2 MB)
↓ results/sampleA/deconv.csv    (3.4 MB)
↓ results/sampleB/features.csv  (1.1 MB)
✓ 已拉取 3 个文件

# 6. AI 分析（本地透明）
# Dashboard 刷新，显示结果
```

---

## 六、不做清单

| 功能 | 为什么不做 |
|------|-----------|
| 可视化工作流编辑器 | AI 写 Snakemake，人不拖拽 |
| 自研 DAG 引擎 | Snakemake 是最好的 |
| 状态机 | 三个状态就够了 |
| 双向同步 | 不需要。本地是云端的子集 |
| 冲突解决 | 没有双向同步就没有冲突 |
| 版本 diff/merge | 只保存快照，diff 交给 AI |
| 实时进度条 | Snakemake 日志就是进度 |
| 工作流节点 | 不需要中间态可视化 |
| 复杂排队算法 | FIFO 够用 |
| 前端工作流配置 | 编辑 Snakefile 即可 |

---

## 七、必须做的事

| 组件 | 工作量评估 |
|------|-----------|
| `push` 操作：上传文件到云端 | ~1 天 |
| `pull` 操作：从云端下载结果 | ~1 天 |
| `fetch` 操作：按需单文件获取 | ~0.5 天 |
| 队列表 + Worker 循环 | ~1 天 |
| WS 状态推送 | ~0.5 天 |
| 版本快照 (cp Snakemake + config) | ~0.5 天 |
| Dashboard 结果浏览 | 复用 viewer matrix |
| CLI 客户端 | ~2 天 |

**总计：约 1-2 周的核心工作量。** 其他所有都是"有了上面这些就自然能工作"的产物。

---

## 八、设计的检验标准

在实现任何功能之前，问三个问题：

1. **这个功能是否增加了新的"状态"？** 如果是，说明我们在滑向状态机陷阱。
2. **这个功能能否用文件操作实现？** 如果不能，说明我们引入了不必要的抽象。
3. **AI 能否直接处理这个功能？** 如果能，应该交给 AI 而非框架代码。

```
例：版本对比 → AI diff ✓ → 不写框架代码
例：冲突解决 → 引入了"冲突状态" ✗ → 重新设计
例：进度追踪 → tail 日志文件 ✓ → 不写进度组件
```

---

*文档版本: v0.1*
*上次更新: 2025-07-25*
