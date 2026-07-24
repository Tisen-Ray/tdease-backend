# TDEase-zero 部署模式与用户体验设计 v1

> **核心观点：三种部署模式使用同一套文件系统抽象，UX 完全统一。**
> 区别只在"workspace 存在哪里"，用户感知不到。

---

## 一、三种模式

```
┌─────────────────────────────────────────────────────────────────┐
│ 模式              │ 场景                   │ 计算         │ 数据 │
├───────────────────┼────────────────────────┼──────────────┼─────┤
│ Pure Desktop      │ 单机本地               │ 本机 CPU/GPU │ 本地 │
│ Desktop + Server  │ 本地客户端 + 自建服务器 │ 服务器       │ 两端 │
│ Desktop + Cloud   │ 本地客户端 + 云服务     │ 云           │ 两端 │
└─────────────────────────────────────────────────────────────────┘
```

### Pure Desktop

```
┌─────────────────────────────────────┐
│  一台电脑 = 一切                    │
│                                     │
│  Dashboard (Electron)              │
│     │                               │
│     ├─ AI Agent (本地 Claude/etc)   │
│     ├─ Snakemake (本地进程)         │
│     └─ 文件系统 (本地目录)          │
│                                     │
│  无网络，无登录，无队列。           │
│  一用户，一台机，直接跑。           │
└─────────────────────────────────────┘
```

- 所有东西在本地，不需要任何网络调用
- Snakemake 直接 `subprocess.run()`
- 结果立即可见，Dashboard 直接读本地目录
- **没有 push/pull，因为都在本地**

### Desktop + Server

```
┌─ 桌面 (PI) ────────────────┐     LAN     ┌─ 自建服务器 ────────────────┐
│                             │              │                             │
│  Dashboard                  │   push/pull  │  Worker                     │
│  AI Agent                   │  ─────────→  │  Snakemake                  │
│  本地 workspace (编辑)      │              │  大型 workspace (执行)      │
│  结果缓存                   │              │                             │
└─────────────────────────────┘              └─────────────────────────────┘
    我编辑完，提交给服务器跑。                    跑完，拉结果回来分析。
    本地只管 AI 和看板。                         服务器只管算。
```

- 用户有自建服务器（实验室里带 GPU 的工控机，或课题组服务器）
- 桌面用于编辑和看板
- 服务器跑 Snakemake
- 身份简单：就是"我自己"或者"课题组三人"
- `tdease server start` 在服务器上一键启动

### Desktop + Cloud

```
┌─ 桌面 (PI) ────────────────┐   互联网     ┌─ 云端 ──────────────────────┐
│                             │              │                             │
│  Dashboard                  │   push/pull  │  队列 + Worker              │
│  AI Agent                   │  ─────────→  │  Snakemake                  │
│                             │              │  多租户 workspace           │
└─────────────────────────────┘              └─────────────────────────────┘
    和自建服务器完全一样的 UX。              需要用户系统和按需 fetch。
```

- 多租户，需要认证
- 需要队列和资源管理
- **UX 和 Server 模式完全一致**——用户只看"提交 → 等待 → 拉取"三个动作

---

## 二、统一抽象

三种模式共享同一个核心接口：

```python
class WorkspaceBackend:
    """workspace 的存储后端。本地、服务器、云端用不同实现。"""

    async def submit(self, workspace: str, files: list[str]) -> str:
        """提交运行，返回 run_id。"""

    async def status(self, run_id: str) -> RunStatus:
        """查询运行状态。"""

    async def pull(self, run_id: str, patterns: list[str]) -> list[str]:
        """拉取结果文件到本地。"""

    async def fetch(self, run_id: str, path: str) -> Path:
        """按需获取单个文件。"""

    async def tail_log(self, run_id: str, lines: int = 50) -> str:
        """读取最新日志行。"""

    async def list_runs(self, workspace: str) -> list[RunSummary]:
        """列出历史运行记录。"""
```

### 三种实现

```python
class LocalBackend(WorkspaceBackend):
    """Pure Desktop：一切都在本地。"""
    # submit → subprocess.Popen(["snakemake", ...]) 直接跑
    # status → psutil 查 PID 是否还活着
    # pull   → 本地 cp（一步到位，直接可见）
    # fetch  → 本地 open（一步到位）
    # 无需 push，文件就在本地

class ServerBackend(WorkspaceBackend):
    """Desktop + Server：通过 HTTP 与自建服务器通信。"""
    # submit → POST /api/runs (上传 Snakefile + 文件 → 服务器)
    # status → GET /api/runs/:id
    # pull   → GET /api/runs/:id/files (下载)
    # fetch  → GET /api/runs/:id/files/:path (单文件)
    # 需要: 服务器地址配置

class CloudBackend(WorkspaceBackend):
    """Desktop + Cloud：和 ServerBackend 完全一样的协议。"""
    # 区别仅在于认证机制（多租户 OAuth/ApiKey）
    # 和按需 fetch 机制（云存储文件可能不在 worker 节点上）
```

**关键：** Dashboard 和 AI Agent 不关心用的是哪个 backend。它们只调用抽象接口。

---

## 三、用户体验

### 桌面端的角色

桌面端（Electron + Vue Dashboard）只负责四件事：

```
┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ 编辑       │  │ 提交     │  │ 看结果   │  │ AI 分析  │
│            │  │          │  │          │  │          │
│ Snakefile  │  │ 一键 run │  │ 结果浏览 │  │ AI 读    │
│ config     │  │ → 排队   │  │ 拉取     │  │ 可视化   │
│ scripts    │  │ → 监控   │  │ Dashboard│  │ 诊断     │
│            │  │ → 完成   │  │ 交互看板 │  │ 优化     │
└────────────┘  └──────────┘  └──────────┘  └──────────┘
    本地文件      三个按钮       viewer        AI agent
```

### Pure Desktop 模式下的完整旅程

```
用户打开 TDEase Desktop
  │
  ├─ 新 workspace 或 打开已有
  │   → 本地目录，自由编辑 Snakefile
  │
  ├─ AI Chat: "帮我写一个处理这批 mzML 的 workflow"
  │   → AI 生成 Snakefile 到 workspace/
  │   → 用户审查、微调
  │
  ├─ 点击【运行】
  │   → LocalBackend.submit()
  │   → Snakemake 开始跑
  │   → Dashboard 实时显示 Snakemake 日志
  │   → 不需要网络、不需要登录、不需要队列
  │
  ├─ 运行完成
  │   → Dashboard 自动显示结果文件列表
  │   → viewer matrix 渲染结果
  │
  └─ AI: "分析这些结果"
      → AI 直接读本地文件
      → 所有分析在本机完成
```

### Desktop + Server 模式下的旅程

```
用户打开 TDEase Desktop
  │
  ├─ 配置服务器地址（一次性）
  │   → tdease config set server http://lab-server:8000
  │
  ├─ 编辑 Snakefile（和 Desktop 一样）
  │
  ├─ 点击【提交】
  │   → ServerBackend.submit()
  │   → 上传 Snakefile + config
  │   → 服务器入队
  │   → WS 实时推送状态
  │
  ├─ 排队/运行中
  │   → Dashboard 显示状态 + PID
  │   → 实时日志流
  │   → 可以关掉桌面，过会儿再开
  │
  ├─ 完成
  │   → 系统通知/WS 推送
  │   → 点击【拉取】
  │   → 下载 results/ 到本地
  │
  └─ AI 分析（和 Desktop 一样）
```

### Desktop + Cloud 模式下的旅程

```
用户打开 TDEase Desktop
  │
  ├─ 登录（一次性或 session 持久）
  │   → tdease login
  │
  ├─ 编辑（和 Desktop 一样）
  │
  ├─ 点击【提交】
  │   → CloudBackend.submit()
  │   → 和 Server 模式一模一样
  │
  ├─ 按需 fetch
  │   → AI 需要某个 mzML → 自动从云拉取
  │   → 对用户透明
  │
  └─ 其余所有流程和 Server 模式相同
```

### UX 一致性原则

```
三种模式下的用户操作：
┌─────────────┬──────────┬──────────┬──────────┐
│ 操作        │ Desktop  │ Server   │ Cloud    │
├─────────────┼──────────┼──────────┼──────────┤
│ 编辑工作流  │ 本地文件 │ 本地文件 │ 本地文件 │
│ 提交运行    │ 本地运行 │ 上传提交 │ 上传提交 │
│ 查看状态    │ 本地查询 │ WS 推送  │ WS 推送  │
│ 查看日志    │ tail 文件│ 远程 tail│ 远程 tail│
│ 拉取结果    │ 本地 cp  │ 下载     │ 下载     │
│ AI 分析     │ 本地 AI  │ 本地 AI  │ 本地 AI  │
│ 按需 fetch  │ 本地打开 │ HTTP GET │ HTTP GET │
└─────────────┴──────────┴──────────┴──────────┘
```

---

## 四、用户管理

### 设计原则

```
用户管理 ≠ 复杂的权限系统
用户管理 = 知道谁提交了什么，以及他的 workspace 在哪
```

### Pure Desktop：无用户管理

```
没有"用户"概念。
一个人用一台电脑，不需要登录。
状态存在本地 SQLite。
```

### Desktop + Server：轻量身份

```
场景：课题组内部的 3-5 人共用一台服务器。

不需要：
  ❌ OAuth 流程        ❌ 邮箱验证       ❌ 权限角色
  ❌ 邀请机制          ❌ 组织管理

只需要：
  ✅ 知道谁提交的 run
  ✅ 谁的 workspace 在哪个目录
```

两种选择：

```
方案 A — 配置文件指定身份：
  # ~/.tdease/config.yaml
  user:
    name: "张三"
    email: "zhang@lab.edu"

方案 B — Server 自动生成 token：
  $ tdease server token create --name 张三
  Token: tde_xxxxx  → 发给张三使用
```

### Desktop + Cloud：多租户

```
需要标准的认证流程（OAuth, API Key, Session Token）。
但设计保持简单——本质上和 Server 模式是一样的 API。
仅有：
  ✅ 注册/登录
  ✅ 查看自己的 runs
  ✅ 管理自己的 workspace
```

### 数据模型

```sql
-- 用户 (Cloud 模式需要, Desktop 模式不需要)
CREATE TABLE users (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT,
    created_at TEXT
);

-- 运行记录 (所有模式共享)
CREATE TABLE runs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,          -- Desktop 可为 NULL
    workspace   TEXT NOT NULL,
    snakefile   TEXT NOT NULL,
    config      TEXT,
    status      TEXT DEFAULT 'QUEUED',
    mode        TEXT,          -- 'local' | 'server' | 'cloud'
    created_at  TEXT,
    started_at  TEXT,
    finished_at TEXT,
    pid         INTEGER,
    exit_code   INTEGER,
    error       TEXT
);
```

---

## 五、服务器管理

### 启动方式

```bash
# 自建服务器一键启动
$ tdease server start
TDEase Server 已启动: http://0.0.0.0:8000
工作目录: /data/tdease
队列状态: 空闲

# 守护进程模式
$ tdease server start --daemon
$ tdease server status
TDEase Server 0.1.0
运行时间: 3天 2小时
活跃队列: 1 个任务
已完成: 47 个任务
```

### 服务器做什么

```
┌─ Server ───────────────────────────────┐
│                                         │
│  1. 接收 push 请求                      │
│     → 存储收到的文件到 workspace/        │
│                                         │
│  2. 管理队列                            │
│     → FIFO 入队                         │
│     → worker 按顺序取出执行              │
│                                         │
│  3. 执行 Snakemake                       │
│     → 单个 subprocess 跑                 │
│     → 日志写入 .snakemake/               │
│                                         │
│  4. 提供 pull 接口                       │
│     → 列出结果文件                       │
│     → 流式传输文件                       │
│                                         │
│  5. 推送状态                            │
│     → WebSocket 实时状态                 │
│     → 可选的通知 (完成时)                │
│                                         │
│  6. 存储历史记录                         │
│     → runs 表                            │
│     → 版本快照                           │
│                                         │
│  7. 定期清理（可选）                     │
│     → 清理旧 raw 文件                    │
│     → 清理旧 runs                        │
│                                         │
└─────────────────────────────────────────┘
```

---

## 六、配置层级

```
系统级:  ~/.tdease/config.yaml
          ├─ server: http://lab-server:8000  (Server/Cloud 模式)
          ├─ user.name: 张三
          ├─ default_cores: 8
          └─ backend: auto  (自动检测: 无 server → local)

项目级:  workspace/.tdease/config.yaml
          ├─ resources.cores: 16              (覆盖系统级)
          └─ resources.memory: 64G

运行级:  Snakefile 中的 config 块
          ├─ raw_dir: "raw/"
          └─ output_dir: "results/"
```

优先级: `运行级 > 项目级 > 系统级`

---

## 七、前端/桌面端结构

```
Electron App
  ├─ 启动画面
  │   → 自动检测: 上次连的是本地还是远程
  │   → Pure Desktop 模式: 直接进入，显示本地 workspace
  │   → Server 模式: 检查服务器连通性
  │   → Cloud 模式: 检查登录状态
  │
  ├─ 主界面（三个面板）
  │   ├─ 左侧面板    — workspace 浏览 (文件树)
  │   ├─ 中央面板    — 编辑器 (Snakefile) 或 看板 (results)
  │   │   ├─ 模式 1: 编辑 — 打开 Snakefile/config
  │   │   └─ 模式 2: 看板 — 渲染结果文件
  │   └─ 右侧面板    — AI Chat 或 运行状态
  │
  ├─ 底部状态栏
  │   └─ 模式图标 (💻桌面 / 🖥️服务器 / ☁️云) + 运行状态
  │
  └─ 用户菜单
      └─ Pure Desktop: 无
         Server: 身份配置
         Cloud: 账户管理
```

### 关键界面状态

```
Edit 状态 (编辑工作流):
┌──────────────────────────────────────────────┐
│ [文件树]  │  [Snakefile 编辑器]  │  [AI Chat]│
│           │                      │           │
│ workspace/│  rule process_mzml:   │  AI: 我帮 │
│  ├─ raw/  │      input: "..."     │  你优化   │
│  ├─ Snake │      output: "..."    │  这段规则 │
│  └─ config│                      │           │
│           │  [提交运行]           │           │
└──────────────────────────────────────────────┘

Run 状态 (运行中):
┌──────────────────────────────────────────────┐
│ [运行列表]│  [运行中: run_a1b2c3]  │ [状态]  │
│           │                      │         │
│ run_1 ✓   │  ⏳ running 2m34s    │ 日志:   │
│ run_2 ✗   │  ███████████░░░░░    │  ← tail │
│ run_3 ✓   │                      │         │
│           │  进度: 3/8 rules     │         │
└──────────────────────────────────────────────┘

View 状态 (看板):
┌──────────────────────────────────────────────┐
│ [结果列表]│  [交互数据看板]        │ [AI Chat]│
│           │                      │           │
│ features  │  ┌─ 色谱图 ──────┐   │  AI: 样本 │
│ deconv    │  │ ╱╲   ╱╲      │   │  A 丰度   │
│ heatmap   │  │╱  ╲╱  ╲─────│   │  异常高   │
│           │  └──────────────┘   │           │
│           │                      │           │
└──────────────────────────────────────────────┘
```

---

## 八、设计检验（对每种模式的三个问题）

```
Pure Desktop:
  1. 增加了新的"状态"吗？          → 没有，三个状态 + 本地 PID
  2. 能用文件操作实现吗？          → 是，subprocess + tail
  3. AI 能直接处理吗？             → 是，AI 操作本地文件系统

Desktop + Server:
  1. 增加了新的"状态"吗？          → 没有，HTTP 转发相同状态
  2. 能用文件操作实现吗？          → push/pull = 文件传输
  3. AI 能直接处理吗？             → 是，AI 看不到网络层

Desktop + Cloud:
  1. 增加了新的"状态"吗？          → 没有，多了一个 fetch 操作
  2. 能用文件操作实现吗？          → 是，文件按需下载
  3. AI 能直接处理吗？             → 是，fetch 对 AI 透明
```

---

*文档版本: v1.0*
*上次更新: 2025-07-25*
