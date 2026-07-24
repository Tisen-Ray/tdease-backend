# TDEase-zero 服务器运行设计：雨天路径

> **ARCHITECTURE-0 描述了晴天路径。本文档覆盖服务器化的全部"雨天路径"：**
> 崩溃恢复、多用户归属、上传安全、实时跟踪、错误处理、排队与资源、
> 多到一聚合、按需传输 UX。
>
> **总原则：服务器只做对账和准入，真相留给文件系统和 Snakemake。**
> 本文档中没有任何一条需要引入状态机。

关联文档：`ARCHITECTURE-0.md`（晴天路径）、`DEPLOYMENT-MODES.md`（三种部署模式）、`SERVER-PRODUCTION.md`（生产化：安全/磁盘/队列/运维）、`FIRST-PRINCIPLES-AUDIT.md`（终审：轮子替换，冲突时以终审为准）。

---

## 一、崩溃恢复：Snakemake 自己就是恢复引擎

### 核心洞察

文件系统即状态的原则在崩溃恢复上是最强的：

```
服务器断电重启：
  1. 扫 runs 表：status=RUNNING 但 PID 已死 → 重置回 QUEUED
  2. worker 重新拾取 → 再次执行 snakemake
  3. Snakemake 检查 .snakemake/metadata/ 和输出文件完整性
     → 自动只重跑未完成的 job (--rerun-incomplete)
```

服务器侧只需要一段 ~10 行的**启动对账**代码。不需要任务级状态机，
不需要 checkpoint 数据库，不需要心跳协议。

### 三种断电场景

| 场景 | 后果 | 恢复方式 |
|------|------|----------|
| 服务器断电 | RUNNING 记录变孤儿 | 启动对账 → 回 QUEUED → Snakemake 增量重跑 |
| 本地客户端断电 | 无后果（run 在服务器上继续） | 客户端重连后 pull 一次当前状态 |
| Worker 进程被杀 | 同上，PID 死亡可检测 | 同上 |

### 已知坑：stale lock

Snakemake 崩溃会留下 `.snakemake/locks/`。worker 重跑前必须处理：

```bash
snakemake --unlock          # 清理 stale lock
snakemake --rerun-incomplete --keep-going
```

检测方式：lock 文件存在但持有进程已死 → 可安全 unlock。

### 对照旧系统

旧系统用 `lost` 状态 + lease 过期做 recovery。新系统把同一件事表达为
"启动对账 + 文件真相"。语义等价，代码量差一个数量级。

---

## 二、多用户与归属：run_id = 目录，握手即物化

### 让歧义不可能出现

"哪个 Snakemake 进程对应哪个用户"不应该靠查询来回答，应该在设计上不可能歧义：

```
POST /runs  (带 auth token)
  → 服务器生成 run_id
  → 物化目录: workspaces/{user_id}/{ws_id}/runs/{run_id}/
      ├─ Snakefile      ← push 的快照，只读
      ├─ config.yaml
      └─ scripts/
  → 入队 (run_id, QUEUED)

worker: cd runs/{run_id}/ && snakemake --cores N
```

- run_id 由**服务器**生成，路径由**认证后的 user_id** 推导。
  客户端永远不提供服务器侧路径 → "传到别人 workspace"在协议上不可能。
- run 目录是不可变快照。用户本地继续编辑不影响正在跑的 run。
  版本管理（ARCHITECTURE-0 §四）免费获得这个性质。
- 多用户隔离 = 目录隔离 + token 鉴权。无共享工作目录，无跨用户串扰。

### 归属表（已在 ARCHITECTURE-0 的 runs 表）

runs 表的 `user_id + workspace + run_id` 三元组就是全部归属信息。
"谁跑了什么、在哪、什么状态"是单表查询，不是分布式追踪问题。

---

## 三、上传安全：白名单 + manifest 两步握手

质谱场景最致命的误传是**把几百 GB 的 mzML 当脚本推上去**。三道防线：

### 防线 1：白名单推送

```
submit 只推:  Snakefile / config.yaml / scripts/ / *.smk
raw 数据走另一个显式命令: tdease push-data（默认带大小确认）
```

上传清单是**枚举出来的**，不是"目录里有什么推什么"。

### 防线 2：manifest 先行

```
client → server: 文件清单 [{path, size, sha256}, ...]
server → client: 我已有哪些（按 hash 去重）
client → server: 只传缺失的文件
```

- 重复传输在去重层消失（同一 mzML 两个 run 引用 → 只传一次）。
- 误传在第一个 RTT 就暴露（清单返回时用户/AI 能看到总量）。

### 防线 3：dry-run

```bash
$ tdease submit --dry-run
将上传:
  Snakefile          2.1 KB
  config.yaml        0.8 KB
  scripts/deconv.py  4.3 KB
  ─────────────────────────
  合计 3 个文件, 7.2 KB
```

AI agent 提交前也必须走这一步——**把"确认"做成协议的一部分，而不是靠人小心**。

### 传错了怎么办

- run 快照是廉价文本文件：cancel + delete，无清理负担。
- raw 数据 content-addressed 存储：无引用时可 GC。
- 不存在"传错位置"——位置由服务器从认证身份推导（见 §二）。

---

## 四、实时跟踪与"稳定用户心态"

质谱一跑几小时，用户焦虑的来源不是慢，是**不知道它还活着没有**。

### 进度信号几乎不用自己造

Snakemake 日志就是进度：

```
启动时打印 DAG 汇总:  "Job stats: 40 jobs"
运行中每个 job 完成都有日志行
tail 日志 + 解析 "x of 40 jobs finished"  → 进度条
```

WS 推送"心态三件套"，全部可从日志 + 文件推导，不需要进度组件：

| 信号 | 来源 |
|------|------|
| 已运行时长 | `started_at` |
| 当前在跑什么 rule | 日志最后一行 |
| 完成度 x/y | 解析日志计数行 |

### per-sample 进度靠 Snakefile 约定

约定 AI 生成的 Snakefile 用 wildcard **每样本一个 job**（见 §七），
则 `3/40 jobs` 天然就是 `3/40 个样本`。不需要建进度数据库。

### ETA 从历史来

同 workspace 历史 run 的耗时在 runs 表里（`started_at/finished_at`）。
第一次跑没有 ETA；第二次跑同管线就能显示"上次跑了 3h12m"。
这是查询，不是预测引擎。

### 断连语义

断连重连后客户端主动 pull 一次当前状态（ARCHITECTURE-0 已确认）。
不需要心跳、不需要状态恢复协议、不需要重连补偿。

---

## 五、运行错误：诊断是 AI 的活，不是框架的活

### 失败语义

```
exit_code != 0 → status=FAILED, 存 exit_code + 日志路径
Snakemake 日志自带: 哪个 rule / 哪个样本失败, 失败 job 的 log 路径
```

### 诊断路径

```
FAILED
  → AI agent 读失败 job 的 log
  → 判断: 参数问题? 数据问题? 环境问题?
  → 改 config / 改脚本 → 重新 submit
```

旧系统在状态机里给每种错误建分支；新系统里这是 prompt/技能问题。
这是零范式真正赢的地方：**错误的分类是无限的，状态机装不下，AI 装得下**。

### 重跑是幂等的

同一 run 目录再跑一次 snakemake：已完成的输出文件还在 → 只补失败的。
40 个样本挂 1 个（`--keep-going` 默认带上，见 §七）→ 39 个照样跑完，
缺的那个从缺失的输出文件一眼看出。文件即状态再次生效。

---

## 六、排队与资源分配

### 准入控制（服务器负责）

```
FIFO 队列表 + per-user 并发上限（如每人最多 2 个 RUNNING）
优先级 = 加 priority 字段，取出时排序（未来）
```

服务器只做三件事：**准入、归属、生命周期**。不做细粒度调度。

### 资源分配（Snakemake 负责）

别自造调度器。Snakemake 原生就有：

```
rule 级:  resources: mem_mb=8000, threads=4, gpu=1
全局级:  snakemake --cores N --resources mem_mb=M
```

worker 领取 run 时按机器剩余配额决定 `--cores/--resources`，
多 worker 瓜分机箱。

### 未来：集群规模

换 Snakemake executor 到 Slurm/k8s，细粒度调度交给专业调度器。
队列表保留"准入 + 归属 + 生命周期"，其余删除。

---

## 七、执行粒度：per-run 模型与 wildcard-per-sample 约定

### 警惕：粒度退化

旧系统的执行粒度是 **per-row**（一个样本失败不影响其余 39 个）。
新模型"server 只管跑脚本"，粒度退化为 **per-run**——整个 Snakefile
是一个黑盒进程。如果 Snakefile 组织得不好：

```
一个样本坏 → 整个 run FAILED → 无法只重跑那行
```

### 解法不是回去做 per-row 队列，而是约定

AI 生成的 Snakefile **必须**遵守三条约定：

```
1. wildcard-per-sample: 每样本独立 job
   rule process:
       input:  "raw/{sample}.mzML"
       output: "results/{sample}/features.csv"

2. --keep-going 默认开启: 独立分支互不受失败影响

3. 输出路径即状态: 哪个样本失败 = 哪个输出缺失
```

这三条写进生成 Snakefile 的 **skill/prompt**，不写进框架代码——
完全符合"约束只在 prompt 层"的原则。

效果：失败粒度自然落到文件层，重跑自动增量，per-row 的好处全部保留，
但队列和恢复代码一行都不用写。

---

## 八、多到一聚合：Snakemake 的母语

### 问题形态

```
N 个样本各自走一遍管线（路径只写一遍）
  → 最后一个脚本把 N 个结果汇总成一张表（merge / 全局归一化 / QC 报告）
```

### Snakemake 原生处理：wildcard + expand

```python
SAMPLES = ["A", "B", "C", ...]

# 每样本规则只写一遍 —— wildcard 自动实例化 N 次，互相并行
rule process_sample:
    input:  "raw/{sample}.mzML"
    output: "results/{sample}/features.csv"
    shell:  "python scripts/deconv.py {input} {output}"

# 聚合规则：input 声明依赖全部样本输出
# → DAG 自动形成同步屏障（所有样本完成才运行）
rule aggregate:
    input:  expand("results/{sample}/features.csv", sample=SAMPLES)
    output: "results/summary/merged.csv"
    shell:  "python scripts/merge.py {input} {output}"
```

这正是 `2026-07-24-execution-model-analysis.md` 里设想的
"Map 层 + 同步屏障 + Reduce 层"，Snakemake 的 DAG 天然就是 MapReduce：

```
sample_A: deconv → id ─┐
sample_B: deconv → id ─┼─→ aggregate (merge)
sample_C: deconv → id ─┘
   (并行)                 (等全部完成)
```

### 动态样本集：checkpoint

如果样本集要到管线中途才知道（例如 QC 过滤后只剩合格样本），
用 `checkpoint` 在运行中重新计算 DAG：

```python
checkpoint qc_filter:
    output: "results/qc/passed_samples.txt"

def aggregate_input(wildcards):
    ckpt = checkpoints.qc_filter.get()
    passed = read_samples(ckpt.output[0])
    return expand("results/{sample}/features.csv", sample=passed)

rule aggregate:
    input: aggregate_input
```

checkpoint 完成后 Snakemake 重读下游依赖——动态扇入扇出无需任何框架代码。

### 部分失败语义

- 某样本失败 + `--keep-going` → 其余样本跑完，aggregate 因缺输入**不运行**。
- 缺失的输出文件直接指出坏样本；修好重跑同一目录 → 只补该样本 + aggregate。
- 若业务允许"部分汇总"（N-1 个样本也出报告），用 checkpoint 读
  `passed_samples.txt` 时只枚举实际存在的输出——这是 Snakefile 层的策略，
  服务器无感知。

---

## 九、按需传输 UX：本地是云端的稀疏视图

### 分工回顾

```
云端:  重度计算 + 全部数据（raw + results + 证据）
本地:  AI 分析 + 可视化 + 编辑
```

矛盾点：AI 和看板在本地，数据在云端。质谱数据太大，
不可能全量镜像，也不应该让用户手动管传输。

### 用户心智模型

```
本地 workspace = 云端 workspace 的稀疏视图

用户只需要理解一件事：
  "文件名字我都能看到，需要的时候才下载。"
```

不是同步（无双向、无冲突），不是挂载（无内核驱动），
是**按需物化**——语义接近 git-annex / VFS，实现只需一个 Finder 层。

### 三个动词，其余全是策略

| 动词 | 方向 | 触发者 |
|------|------|--------|
| push | 本地 → 云 | 用户提交 run / 显式 push-data |
| pull | 云 → 本地 | 用户拉取 / run 完成自动触发 |
| fetch | 云 → 本地（单文件） | AI/看板读缺失文件时透明触发 |

策略层（不写新机制，只组合三动词）：

```
1. 自动 pull:  run DONE → 自动拉 results/**（小，KB-MB 级）
               raw 不自动拉（大，GB 级）

2. 懒 fetch:   AI 读 raw/sampleA.mzML → 本地缺失
               → Finder 自动 fetch → 缓存 → 透明返回
               从 AI 视角文件"一直在本地"

3. 预取:       Dashboard 打开某 run 的结果页
               → 后台预拉该 run 的 viewer 常用文件
               （用户大概率马上要看）
```

### 传输层要求（大文件的现实）

- **分块 + 断点续传**：mzML 动辄 GB，网络中断是常态不是异常。
  分块上传/下载，每块带 hash，中断后续传。
- **content-addressed 去重**：hash 命中即秒传（manifest 握手已实现）。
- **进度可见**：大文件传输在 Dashboard 显示进度条。
  这是"稳定心态"在传输层的延伸——GB 级文件下载必须让用户看到它在动。

### 可见性：文件树徽章

Dashboard 文件树标注每个文件的位置：

```
workspace/
  ├─ raw/
  │   ├─ sampleA.mzML   ☁️      (在云端, 未下载)
  │   └─ sampleB.mzML   💾      (已缓存本地)
  ├─ results/
  │   └─ merged.csv     💾      (run 完成时自动拉取)
  └─ Snakefile          💾☁️    (两端都有)
```

点击 ☁️ 文件 → 后台 fetch → 完成变 💾。
AI 读 ☁️ 文件 → 同一机制自动触发，AI 无感知。

### 优雅性的检验

回到 ARCHITECTURE-0 的三个问题：

```
1. 增加了新的"状态"吗？  → 只有 "在不在本地" 一个布尔，且可实时推导（文件存在性）
2. 能用文件操作实现吗？  → 是，fetch = HTTP GET 写文件，缓存 = 文件存在
3. AI 能直接处理吗？    → 是，AI 照常 open()，Finder 层兜底
```

传输是管道，UX 只暴露"文件在不在本地 + 下载进度"两个信号。

---

## 十、汇总：要写的代码清单

| 组件 | 实质 | 量级 |
|------|------|------|
| 启动对账 | 扫表 + PID 存活检查 + 回 QUEUED | ~10 行 |
| manifest 握手 | 清单交换 + hash 去重 | ~1 天 |
| 白名单上传 | 枚举式 push + dry-run | ~0.5 天 |
| stale lock 处理 | worker 重跑前 --unlock | ~10 行 |
| 日志解析推送 | tail + 解析 x/y jobs → WS | ~0.5 天 |
| per-user 配额 | 取出时按 user 计数过滤 | ~10 行 |
| 断点续传 | 分块 + hash 校验 | ~2 天 |
| Finder 懒加载层 | 读缺失 → fetch → 缓存 | ~1 天 |
| Snakefile 生成约定 | wildcard-per-sample + keep-going + 聚合模式 | 0 行代码，写进 skill |

**没有任何一项引入新状态轴。** 服务器始终只做对账和准入，
真相始终在文件系统和 `.snakemake/metadata/` 里。

---

*文档版本: v0.1*
*上次更新: 2025-07-24*
