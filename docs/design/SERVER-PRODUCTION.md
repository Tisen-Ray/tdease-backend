# TDEase-zero 服务器生产化设计

> **SERVER-OPERATIONS 覆盖了单机晴雨天。本文档回答一个问题：**
> **这套系统被真实用户、真实脚本、真实磁盘真实使用时，会怎样死？怎么不死？**
>
> 前提认知：TDEase server 本质上是一个 **远程代码执行服务**。
> 用户上传任意 Snakefile，服务器执行任意 shell。生产化设计必须从这个事实出发。

关联文档：`ARCHITECTURE-0.md`、`DEPLOYMENT-MODES.md`、`SERVER-OPERATIONS.md`、`AGENT-UX-AND-PERMISSIONS.md`（Agent 权限与双级 token）、`FIRST-PRINCIPLES-AUDIT.md`（终审：轮子替换，冲突时以终审为准）。

---

## 一、身份与路径解耦：整文件夹迁移

### 攻击场景

```
- 用户把本地 workspace 文件夹从 D:\ 挪到 E:\，或重命名
- 实验室换服务器，整个 data-root 迁移到新机器
- 用户换电脑，想在新机器上接着用同一个 workspace
- 两个用户撞了 workspace 名字
```

如果身份 = 路径，以上每一条都是灾难。**身份必须是一个不随物理位置变化的 ID。**

### 设计

```
workspace 身份 = UUID，写在 .tdease/workspace.json
  { "workspace_id": "ws_a1b2c3", "name": "liver-proteomics" }

服务器侧: workspaces/{user_id}/{workspace_id}/    ← 用 ID，不用名字
本地侧:   任意路径/.tdease/workspace.json          ← 位置无关
```

- **本地移动/重命名**：客户端启动时读 `.tdease/workspace.json`，
  ID 不变 → 什么都不用做。名字只是展示层元数据。
- **换电脑**：新机器上 `tdease attach <path>` 写入同一个 workspace_id →
  该目录立即成为云端的本地视图（稀疏的，按需 fetch）。
- **服务器迁移**：data-root 整体 rsync + runs 表导出导入。
  因为 run 目录内部全是相对路径，物理搬家不改变任何语义。
- **payload 内所有路径必须是 workspace 相对路径**，且服务器校验
  拒绝 `..` 和绝对路径——这同时是路径穿越攻击的防线（见 §二）。

### 检验

身份不来自路径、不来自名字、不来自 mtime。物理世界怎么折腾，
逻辑世界纹丝不动。这是"文件系统即状态"的前提条件，必须写死。

---

## 二、安全边界：这是一个 RCE 服务

### 威胁模型

用户提交的 Snakefile 可以 `shell: "任何东西"`。在多用户服务器上：

```
- 失控脚本: 死循环吃满 CPU / fork 炸弹 / 写满磁盘
- 越界脚本: rm -rf 别人的 workspace / 读服务器敏感文件
- 恶意脚本: 挖矿 / 外联 C2 / 扫内网
- 路径攻击: 上传文件名含 ../../etc/cron.d (zip-slip 类)
```

课题组服务器（Server 模式）威胁低，但云端模式必须按恶意输入设防。
**一套设计，按最严的来，低成本模式只是少配置几行。**

### 防线（v0.2 修订：轻量防线为主，容器降级为备选）

**当前决策：暂不上重沙箱。** 信任模型 = 课题组/可信内网用户。
防线 = 权限审计 + 文本审查，够用为止：

| 层 | 措施 | 成本 |
|----|------|------|
| 1. 双级 token | agent 级 / user 级 scope（AGENT-UX-AND-PERMISSIONS §四） | ~0.5 天 |
| 2. Snakefile 文本审查 | submit 入队前静态扫描危险模式：`rm -rf`、`curl\|sh` 类管道执行、output 路径穿越、fork 炸弹模式 → 拒绝并说明。纯文本规则表（`.tdease/audit-rules.yaml`），可配置可扩展 | ~0.5 天 |
| 3. 快照审计链 | 谁/何时/提交了什么代码/结果如何（见下节，免费获得） | 0 |
| 4. 路径校验 | 上传/下载的所有相对路径拒绝 `..`、绝对路径、符号链接逃逸 | ~30 行 |
| 5. 进程组杀伤 + 超时 | cancel/超时时 kill 整个进程组，不留孤儿进程（防失控，不防恶意） | ~10 行 |
| 6. 秘密隔离 | 服务器的 token/数据库凭据不注入 run 进程环境 | 默认做到 |

**文本审查的已知限制（必须明示）**：防呆不防高手——混淆后的恶意脚本
可以绕过静态模式匹配。在可信用户模型下可接受；**一旦开放给不可信租户
（云模式），必须升级到下面的容器方案**，不能只靠文本审查。

### 备选：容器隔离（云模式/不可信租户时启用）

```
snakemake --containerize > Dockerfile   # 从 workflow 自动生成镜像定义
snakemake --use-apptainer               # 每个 rule 在容器里跑
```

Snakemake 原生集成，届时一行开启，架构不变。
配套：cgroup 资源硬限、容器内默认无外网/egress 白名单。
Apptainer 本就是 HPC 质谱社区标准（BioContainers 生态），无需 root。

### 免费获得的审计

```
谁 (runs.user_id) 在什么时间 (created_at)
提交了什么代码 (run 目录里的 Snakefile 快照)
跑出了什么 (exit_code + 日志 + .snakemake/metadata)
```

run 快照不可变 → 审计链不可篡改。出问题回溯"谁提交的挖矿脚本"
是一次单表查询。这是零范式的副产品，不用专门建审计系统。

---

## 三、磁盘生命周期：生产环境头号杀手

服务器死于磁盘满的次数会多于其他所有原因之和。质谱数据放大了这个问题。

### 分层保留策略

```
raw/           用户 pin 的数据        → 不自动清，用户显式删
results/       run 产物               → 保留，体积小（相对 raw）
.snakemake/    元数据 + 锁            → 可压缩归档，老 run 可清
logs/          运行日志               → 轮转，保留最近 N 份
tmp/           传输中的分块           → 24h 未完成即清
```

### 配额与背压

```
per-user 磁盘配额 (如 500GB)
per-workspace 配额

manifest 握手时检查:
  本次上传 + 当前用量 > 配额?
    → 拒绝，返回清晰错误:
      "配额不足: 已有 480GB/500GB, 本次需 60GB。
       建议: tdease gc --workspace X 或删除旧 raw"
```

**背压发生在传输前（manifest 阶段），不是传到 90% 才 ENOSPC。**

### GC

```
content-addressed 存储 → 引用计数来自 run 目录
无引用对象 → 宽限期 (7天) → 清除

软删除: 用户删 workspace/raw → 移入 .trash/ → 宽限期后真删
        (误删恢复 = mv 回来, 又是文件操作)
```

### 磁盘将满时的行为

```
磁盘使用率 > 90% → worker 暂停 dequeue（新 run 保持 QUEUED）
                 → health 端点报 not ready
                 → 正在跑的 run 继续（不主动杀）
磁盘真满导致 run 失败 → FAILED + error="ENOSPC"，错误信息人话可读
```

---

## 四、取消与超时：不新增状态轴

### 取消语义

```
用户点取消:
  1. SIGTERM → 进程组 (Snakemake 收到后等运行中 job 收尾)
  2. 宽限 30s → SIGKILL 进程组
  3. status = FAILED, error = "cancelled_by_user"
```

**不加 CANCELLED 状态。** 理由：

- 文件真相不变：半成品输出留在 run 目录，重跑自动续。
- 状态轴保持 QUEUED/RUNNING/DONE/FAILED 四个。
- 前端用 `error == "cancelled_by_user"` 区分显示"已取消"和"失败"，
  这是展示层策略，不是协议层状态。

### 超时

```
每 run 最大墙钟时间 (默认 72h, config 可调)
超时 → 等同取消流程, error = "timeout_exceeded"
```

### 进程泄漏防线

shell rule 可以 fork 出 Snakemake 不管的子进程。cancel/超时/正常结束时
都必须 kill **进程组**而非单 PID。容器执行则免费获得（容器即边界）。

---

## 五、队列生产化

### 原子领取

```sql
-- 多 worker 不能领到同一个 run
UPDATE runs SET status='RUNNING', worker_id=?, started_at=?
WHERE id = (SELECT id FROM runs WHERE status='QUEUED'
            ORDER BY priority DESC, created_at ASC LIMIT 1)
  AND status='QUEUED'
RETURNING id;
-- SQLite: BEGIN IMMEDIATE 包裹; 无行返回 = 被别的 worker 抢走, 重试
```

### 公平性：全局 FIFO 是不够的

```
攻击场景: 用户 A 一口气提交 100 个 run, 用户 B 的 1 个 run 排到天荒地老

解法: per-user 轮转
  dequeue 时按 user 分组, 优先取"当前 RUNNING 数最少"的用户的队首
  + per-user 并发上限 (SERVER-OPERATIONS §六)
  
实现: 一条 SQL 的事, 不是调度器
```

### 背压

```
队列深度 > 上限 (如 1000) → submit 返回 429:
  "队列已满, 请稍后提交。当前排队 1000 个 run"
不让队列无限膨胀——排队记录也是状态, 也有成本
```

### 幂等提交

```
攻击场景: 用户双击提交 / 网络重试 / AI agent 重试
→ 同一个 run 被创建两次, 算两遍

解法: 客户端生成 idempotency_key (= 本地内容 hash)
     server: UNIQUE(user_id, idempotency_key)
     重复提交 → 返回已存在的 run_id, 不新建
```

---

## 六、传输生产化

### 断点续传的具体形态

```
上传:
  1. manifest 握手 → 拿到 upload_session_id
  2. 分块 POST (如 8MB/块), 每块带 sha256
  3. 服务器记录 session → 已收块清单
  4. 中断重连 → 查询 session 已收块 → 只补缺的
  5. 最后一块到 → 拼合 + 整体 hash 校验 → 物化到 content store
  6. session 24h 未完成 → tmp 清除 (见 §三)

下载: 同一套分块协议, 客户端记录已收块
服务器重启 mid-transfer: session 状态在磁盘上, 无感恢复
```

### 并发与限速

```
per-user 并发传输数上限 (如 4)
全局限速可选 (课题组服务器共享带宽场景)
大文件传输进度在 Dashboard 可见 (SERVER-OPERATIONS §九)
```

---

## 七、可观测性：生产化 = 能运维

### 事件流（不加状态轴，只加记录）

```
每 run 追加 events.jsonl (就在 run 目录里, 文件即状态):
  {"t": "...", "event": "enqueued"}
  {"t": "...", "event": "acquired", "worker": "w2"}
  {"t": "...", "event": "started", "pid": 4521}
  {"t": "...", "event": "finished", "exit_code": 0}

服务器排障 = 读这个文件, 不是查分布式追踪系统
```

### 指标与健康

```
GET /healthz  → 进程活着
GET /readyz   → 能接受新 run: 磁盘 ok + db ok + worker 活着

指标 ( Prometheus 或简陋的 /metrics 文本端点):
  queue_depth, running_count, per_user_usage,
  disk_usage_bytes, run_duration 直方图, failed_rate
```

### 管理面

```bash
tdease server admin list-runs --status RUNNING
tdease server admin kill <run_id>        # 等同取消流程
tdease server admin pause-queue          # 停止 dequeue, 维护模式
tdease server admin drain                # 等 RUNNING 跑完, 不取新的
tdease server admin gc --dry-run         # 预览可回收空间
```

---

## 八、升级、迁移与真相重建

### 服务器升级（有 run 在跑）

```
1. admin drain          → 停止取新 run
2. 等 RUNNING 归零 (或 admin kill 长跑的)
3. 升级二进制
4. 启动对账 (SERVER-OPERATIONS §一) → 孤儿回 QUEUED
5. 恢复服务

run 目录在磁盘上, 升级不碰它们 → 零数据风险
```

### 数据库损坏/重建

**DB 是可重建的索引，文件才是真相**（与旧架构 §10 原则一致）：

```
runs 表损坏 → 扫 workspaces/*/runs/*/ 目录:
  每个 run 目录的 events.jsonl + run.json → 重建表记录
  状态推导: 有 finished 事件 → DONE/FAILED
            有 started 无 finished → 孤儿 → QUEUED (对账逻辑复用)

恢复 = 同一个启动对账代码路径, 不是另一套系统
```

### 时钟问题

Snakemake 依赖 mtime 判断新旧。服务器 NTP 跳变可能让它误判。
缓解：Snakemake 的 metadata 里存了校验和，`--rerun-incomplete`
按元数据而非纯 mtime 判断。运维层面：容器/主机时钟同步是基础要求。

### 迁移的幂等要求

DB schema 迁移只做**加列/加表**，不改旧列语义。
队列里可能有旧版本写入的 QUEUED 行，新代码必须能消费。

---

## 九、UX 雨天攻击清单（服务器侧答案汇总）

从用户会做的蠢事/坏事出发，每条对应上面哪节：

| 用户行为 | 服务器答案 |
|----------|-----------|
| 移动/重命名本地文件夹 | §一 身份文件，无感 |
| 换电脑继续用 | §一 attach 同一 workspace_id |
| 两台电脑同时编辑同一 Snakefile 并提交 | push 带 `expected_revision`，不匹配 → 拒绝 + diff，AI 辅助合并（乐观锁，一个版本号字段，不是同步引擎） |
| run 还在跑又点提交 | 合法行为——新 run_id，独立快照，互不干扰（设计免费正确） |
| 双击/重试提交 | §五 幂等键 |
| 提交后立刻关机 | 无影响，run 在服务器 |
| 一口气提交 100 个 | §五 公平轮转 + 配额 |
| 上传 500GB raw | §三 manifest 阶段配额拒绝 |
| 传到一半拔网线 | §六 分块续传 |
| 脚本写死循环/挖矿 | §二 cgroup + 超时 + 网络隔离 |
| 脚本 `rm -rf ../` | §二 容器/低权用户 + 路径校验 |
| 取消正在跑的 run | §四 SIGTERM→SIGKILL 进程组 |
| 误删服务器上 workspace | §三 软删除 + 宽限期 |
| token 泄露 | revoke token，审计链定位影响面 (§二) |
| 服务器磁盘满 | §三 暂停 dequeue + 清晰报错 |
| 服务器进程崩溃 | SERVER-OPERATIONS §一 启动对账 |
| 服务器换机器 | §一 目录搬家 + 表导出，相对路径无感 |

---

## 十、生产化新增代码清单（在 SERVER-OPERATIONS §十 之上）

| 组件 | 量级 |
|------|------|
| workspace 身份文件 + attach 命令 | ~1 天 |
| 路径穿越校验（上传/下载入口） | ~30 行 |
| cgroup/超时/进程组杀伤（systemd-run 包装） | ~1 天 |
| 容器执行（--use-apptainer 路径） | ~2 天（可后置） |
| 配额检查（manifest 握手扩展） | ~0.5 天 |
| 分块续传协议（双向） | ~2 天（与之前估计合并） |
| 原子 dequeue + per-user 公平轮转 | ~0.5 天 |
| 幂等键 | ~10 行 |
| events.jsonl 追加 | ~0.5 天 |
| /healthz /readyz /metrics | ~0.5 天 |
| admin CLI（kill/pause/drain/gc） | ~1 天 |
| 软删除 + GC + tmp 清理 | ~1 天 |
| push 乐观锁（expected_revision） | ~0.5 天 |

### 分期建议

```
P0 (多用户上线前必须):
  路径校验、配额、超时+进程组杀伤、原子 dequeue、
  幂等键、events.jsonl、health 端点、tmp 清理、Snakefile 文本审查

P1 (真实用户跑起来后):
  per-user 公平轮转、软删除+GC、断点续传、admin CLI、乐观锁

P2 (云模式/不可信用户):
  容器隔离、网络隔离、metrics、跨机迁移工具
```

### 零范式检验

```
1. 新增状态轴了吗？ → 没有。CANCELLED 都没加。
   配额/会话/宽限期全是"带 TTL 的文件 + 单表字段"。
2. 能用文件操作实现吗？ → events.jsonl、身份文件、软删除(mv)、
   content store、GC(引用计数+rm) 全是文件操作。
3. AI 能直接处理吗？ → 冲突合并、配额清理建议、排障读 events
   都是 AI 的主场。
```

---

*文档版本: v0.1*
*上次更新: 2025-07-24*
