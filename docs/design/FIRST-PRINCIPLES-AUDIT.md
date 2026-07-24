# TDEase-zero 第一性原理审计：删轮子，抄轮子

> **对前四份设计文档的终审。方法：对每个组件问两个问题——**
> **1. 它引入了新的状态吗？ 2. 有没有已经生产打磨多年的轮子可以直接抄？**
> 结论先行：自研清单砍掉约一半；文件真相收敛为 Blob、Tree manifest、
> Run commit 三层，运行只有一个生命周期轴。

关联文档：`ARCHITECTURE-0.md`、`SERVER-OPERATIONS.md`、`SERVER-PRODUCTION.md`、`AGENT-UX-AND-PERMISSIONS.md`。
本文档与上述文档冲突时，**以本文档为准**。

---

## 一、真相原则终审：文件 = 唯一真相，DB = 可重建索引

用户问题：workspace 系统是否和前作一样，坚守本地文件是唯一真相，
DB 索引只负责业务逻辑与加速？

**是。并且这个原则有充分的工业先例：**

```
Git:        objects/ 是真相, index 是可重建的加速结构
Snakemake:  输出文件 + .snakemake/metadata/ 是真相, 无数据库
DVC:        数据文件 + content store 是真相, .dvc 元文件只是指针
TDEase-zero: Blob + Tree manifest + Run commit 是真相, SQLite 是协调索引
```

### DB 里允许放什么（白名单）

```
✅ 队列与归属:    runs 表 (谁、什么、排队顺序、worker 领取)
✅ 配额计数:      用量求和的物化（可从目录 du 重算）
✅ 幂等键投影:    UNIQUE(user, idempotency_key)，原值必须写入 run.json
✅ 加速索引:      run 列表页查询

❌ 任何"结果状态"    —— 结果在文件里
❌ 任何不可重建的信息 —— 发现即设计错误
```

### 重建测试（定期在 CI 里跑）

```
删掉 SQLite → 扫 runs/*/run.json + events.jsonl
→ 重建 runs 表 → 与删库前对比, 除加速字段外必须等价

这个测试通过 = 原则没有被偷渡破坏
```

---

## 二、状态机普查：全套系统的全部"状态位"

逐文件枚举四份设计中所有带状态的实体：

| 实体 | 状态内容 | 判定 |
|------|---------|------|
| `runs.status` | QUEUED / RUNNING / SUCCEEDED / FAILED / CANCELLED | **保留。唯一的生命周期轴。** 可从 events.jsonl 推导重建 |
| 上传 session 状态 | 已收块清单 | **删除**（换成 S3 multipart，状态托管给 S3，见 §三） |
| 软删除 | "已删除"标记 | 不是状态——是文件位置（`.trash/` 目录），`ls` 即可推导 |
| 配额 | 用量数字 | 不是状态——是求和查询 |
| token scope | agent 级 / user 级 | 不是状态——静态配置 |
| 权限规则 | allow/ask/deny | 不是状态——静态 `.tdease/permissions.yaml` |
| push 乐观锁 | expected_revision | 一个整数版本号，不是状态机 |
| workspace 身份 | workspace_id | 不可变 UUID，无转换，不是状态机 |

**终审结论：整个系统有且仅有一个生命周期字段——`runs.status`，
无子状态、无状态转换图、转换由进程生命周期驱动而非业务代码驱动。**
对照旧体系（status × freeze_state × epoch × 9 个终态写入点），
这就是"只保留必要的状态机"的字面含义。

---

## 三、抄轮子清单：直接复制替换自研设计

### 3.1 大文件传输 → S3 multipart + presigned URL（砍掉 ~2 天自研）

SERVER-PRODUCTION §六 设计的"分块续传协议"是一个已解决 15 年的问题：

```
S3 multipart upload:
  - 分块独立上传、任意顺序、可并行、可续传（5MB–5TB）
  - 每块带 SHA-256 校验, ETag 整体校验
  - presigned URL → 客户端直传存储, 不经过 API 服务器
  - 未完成的 multipart 由 lifecycle 规则自动清理
    → 我们设计的 "tmp/ 24h 清理" 也不用写了

自托管 = MinIO (单二进制, S3 兼容)
```

服务器只发 presigned URL，传输流量完全不经过应用服务器——
架构还顺带升级了。参考：[S3 multipart + presigned 实践](https://sandyghai.github.io/AWS-S3-Multipart-Upload-Using-Presigned-Url/)、[MinIO 自建](https://vsoch.github.io/2020/s3-minio-multipart-presigned-upload/)。

### 3.2 content store 与去重 → key = sha256 的 S3 bucket

```
tree manifest 里的 blob hash → 直接作为 S3 object key
已存在 = HEAD 请求 200 → 秒传（天然去重）
tree manifest 是 path→blob 的不可丢失真相，不能从裸 bucket 反推。
GC 的引用可达性扫描保留自研（这是业务逻辑），存储与传输机制全删
```

### 3.3 稀疏视图 / 懒加载 → rclone mount（砍掉自研 Finder 的大部分）

SERVER-OPERATIONS §九 的"本地是云端的稀疏视图"，
[rclone mount](https://rclone.org/commands/rclone_mount/) 就是这个东西本身，
生产打磨多年，Windows 经 WinFsp 支持：

```bash
rclone mount tdease:materialized-workspace ~/ws --vfs-cache-mode full \
       --vfs-cache-max-size 50G    # 本地缓存上限+LRU 也内置了
```

- rclone 只能挂载按逻辑路径物化的 workspace 前缀，不能直接挂载 hash-only bucket
- open() 缺失文件 → 自动拉取 → 缓存 = `--vfs-cache-mode full` 的定义行为
- 本地缓存上限 + LRU 淘汰 = `--vfs-cache-max-size`，我们不用写
- AI、脚本、看板全部透明

自研 Finder 降级为"无 mount 环境下的兜底"（如纯 HTTP 部署），
P2 再做。原始数据层可选 rclone mount；服务端必须先依据 tree manifest
暴露逻辑路径。

### 3.4 脚本沙箱 → 轻量文本审查为主，apptainer 备选

**当前决策（用户拍板）：不上重沙箱。** 可信内网模型下，防线 =
双级 token + 快照审计 + submit 时 Snakefile 文本审查（危险模式规则表，
~0.5 天自研，见 §五）。已知限制：防呆不防高手。

云模式/不可信租户时启用备选——Snakemake 原生容器集成，几乎零成本：

```bash
snakemake --containerize > Dockerfile     # 从 workflow 自动生成镜像定义
snakemake --use-apptainer                 # 每个 rule 在容器里跑
```

Apptainer/Singularity 本就是 HPC 质谱社区的标准（BioContainers 生态），
无需 root、天然 cgroup 隔离。集群化时 [executor 插件目录](https://snakemake.readthedocs.io/en/latest/executing/executors.html)
有现成的 slurm/k8s 插件。自研容器编排计划删除。

### 3.5 进程管理三件套 → systemd（砍掉自研包装）

```
守护/崩溃重启:    systemd unit, Restart=always
cgroup 资源硬限:  systemd-run --scope -p MemoryMax=32G -p CPUQuota=400% \
                  -p TasksMax=512 snakemake ...
进程组杀伤:       cgroup 边界 → systemctl kill, 无孤儿
tmp 清理:         systemd-tmpfiles（或 S3 lifecycle, 见 3.1）
```

worker 循环保持 50 行，但"不死"这件事交给 systemd，不交给自己。

### 3.6 SQLite 备份 → Litestream

DB 虽然只是索引，但队列/归属重建有成本。
Litestream 把 SQLite WAL 持续流式复制到 S3，单二进制，零自研。

### 3.7 实时推送 → SSE 替代 WebSocket（简化）

我们的推送全是**单向**（服务器 → 客户端），SSE 严格更合适：

```
✅ 浏览器/客户端原生自动重连（EventSource）
✅ 纯 HTTP, 过代理/防火墙无坑
✅ Last-Event-ID 断点续传 → 重连补发丢失事件
❌ WS 的双向能力我们用不到（日志详情本来就是 GET 拉取）
```

### 3.8 监控 → 不自研

```
磁盘/CPU/内存:  node_exporter（一个二进制）
业务指标:       /metrics 文本端点 (~20 行, 保留)
可视化:         Grafana（后置, 需要时再接）
告警:           先不接, readyz + 日志够小团队用
```

### 3.9 版本与 diff → git

workspace 纳入 git（Snakefile/config/scripts 都是文本）：
版本历史、diff、回滚、Agent 误改恢复——全部免费。
run 快照仍是文件复制（ARCHITECTURE-0 §四），两者互补不冲突。

---

## 四、明确不抄的清单（同样重要）

| 轮子 | 为什么不抄 |
|------|-----------|
| Airflow / Prefect / Dagster | 状态机地狱本狱。DAG 抽象 + 任务状态数据库 + Web UI 全家桶，正是我们逃离的东西 |
| Nextflow | 换一个引擎 = 推翻已选定的 Snakemake 轮子，DSL 生态（nf-core）虽强但锁定更重 |
| DVC / git-annex | 产品不直接引入其命令体系；但采用同类成熟的 blob + tree/commit 分层，避免假设裸 CAS 可以恢复路径。 |
| syncthing / 双向同步 | 双向 = 冲突 = 新状态。设计文档已拒绝，维持 |
| Redis + RQ/Celery | 多一个有状态服务来管理一个四值字段，SQLite 队列表 50 行已够。单机不需要消息队列中间件 |
| Kubernetes | 5-50 人团队自托管 k8s 是负资产。要集群时走 Snakemake slurm executor |
| OAuth 全家桶（现在） | 课题组模式 API key 够了。云模式再抄 Supabase/Keycloak，不自研 |

---

## 五、保留自研的清单（这些就是业务本身）

第一性原理判断：以下组件没有现成轮子，因为它们**是** TDEase 的业务规则：

| 组件 | 为什么必须自研 | 量级 |
|------|--------------|------|
| runs 表 + 原子 dequeue + per-user 公平轮转 | 业务准入规则 | SQL + ~50 行 |
| 启动对账（孤儿 run 回 QUEUED） | 业务恢复语义 | ~10 行 |
| manifest 白名单 + 配额校验 + presigned URL 发放 | 业务规则（传输机制已外包 S3） | ~0.5 天 |
| 路径穿越校验 | 安全边界 | ~30 行 |
| tdease CLI（submit/pull/fetch/wait/log） | 薄壳：调 S3 SDK + API，人/Agent 共用 | ~2 天 |
| Snakefile 生成约定（wildcard-per-sample 等） | prompt/skill，0 行代码 | — |
| SSE 事件流（events.jsonl → SSE） | 格式转换 | ~0.5 天 |
| 前端文件位置徽章（☁️/💾） | UX 展示 | ~0.5 天 |
| 双级 token + permissions.yaml | 权限是业务策略 | ~1 天 |
| Snakefile 文本审查（audit-rules.yaml） | 轻量防线的业务规则 | ~0.5 天 |

**自研总量：约 1 周核心 + 1 周打磨。其余全部是成熟轮子的配置与胶水。**

---

## 六、最终系统公式

```
TDEase-zero server =
    Snakemake          (执行引擎, 恢复引擎, 进度来源)
  + MinIO / S3         (存储, 传输, 去重, multipart, lifecycle)
  + rclone             (客户端传输 + mount 稀疏视图)
  + SQLite             (队列/归属索引, 可重建, Litestream 备份)
  + systemd            (守护, cgroup, 进程组杀伤, tmp 清理)
  + SSE                (单向状态推送)
  + git                (workspace 版本, diff, 回滚)
  + ~1 周胶水代码       (§五清单, 含 Snakefile 文本审查)
  [ 备选: Apptainer    (脚本沙箱, 云模式/不可信租户时一行开启) ]
```

九个组件，七个是别人的生产级轮子，一个是 SQLite，
一个是业务本身。**没有第十个。**

---

## 七、终审检验（每次想加组件时过一遍）

```
1. 新状态轴?    → 停。runs.status 之外不该有第二个生命周期轴；
                  Blob/tree/run commit 是不可约事实，不以“无状态”为由删除。
2. 有轮子吗?    → 先查 rclone / S3 / systemd / snakemake 插件目录 / git
                  能不能配置出来。能配置就不写代码。
3. 是业务吗?    → 队列准入/配额/权限/白名单是业务, 允许自研, 但保持薄。
4. 重建测试     → 删掉 SQLite 能重建吗? 删掉本地缓存能用吗?
                  服务器换机器目录搬走能活吗? 三个都必须能。
5. Agent 检验   → 新组件 Agent 能直接用 CLI 操作吗?
                  不能 → 接口设计错了, 不是 Agent 错了。
```

---

*文档版本: v1.0*
*上次更新: 2025-07-24*
