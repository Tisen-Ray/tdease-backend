# TDEase-zero Backend Report

> **2025-07-25 · 第一性原理重构第一阶段完成**

---

## 总览

| 指标 | 数值 |
|------|------|
| 总 Python 文件 | 92 |
| 自有代码 (app + backends + CLI) | 17 files, ~1,507 行 |
| Snakemake 内化引擎 | 75 files, ~31,921 行 |
| 胶水比 | 1:21 (每 1 行自有代码驱动 21 行引擎) |

---

## 架构

```
app/                    FastAPI — 用户/数据/队列
├── main.py             启动入口，170 行，7 routes
├── api/runs_v2.py      REST API (CRUD + SSE)
├── models/run.py       数据模型 (pydantic)
├── database/           SQLite 生命周期
└── core/               配置常量

src/
├── backends/           WorkspaceBackend 三层抽象
│   ├── local.py         Pure Desktop — subprocess 直接跑
│   ├── http_client.py   Desktop+Server — HTTP 通信
│   ├── resolver.py      自动检测用哪个 backend
│   └── base.py          统一接口
├── snakemake/          ★ 内化 Snakemake 引擎 v8+
│   │                    75 文件，精简自上游 Snakemake 源码
│   │                    删除了: remote, DB, report, linting,
│   │                    GUI, notebook, CWL, modules, container…
│   │                    只保留本地执行 + 文件持久化路径
│   ├── service.py       薄封装 — run_snakemake()
│   ├── workflow_spec.py DSL builder — AI 生成 Snakefile 的中间表示
│   └── evidence.py      证据钩子 — 每次运行的审计记录
└── domain/             质谱领域代码 (envelope fit, massql)

cli/                    ❗暂存 — 属于客户端，非后端
└── main.py             tdease CLI (216 行, 前端重构时移出)
```

---

## 不做清单 (已删除)

| 已删除 | 替代 |
|--------|------|
| `src/ai/` (150+ files) | AI 在客户端 PI 侧 |
| `src/workflow/` (39 files, 7265行) | Snakemake DAG |
| `src/execution/` (7 files, 950行) | Snakemake 执行器 |
| `src/services/runs/` 全部 | 单生命周期轴 (QUEUED→RUNNING→SUCCEEDED/FAILED/CANCELLED) |
| `app/core/engine/` + `app/core/executor/` | Snakemake API |
| `app/worker/` + `app/dispatcher/` | 40 行 worker 循环 |
| `openai, anthropic, mcp` 依赖 | 客户端 |
| `alembic` 依赖 | 直接建表 SQL |

---

## 依赖

```
Web:       fastapi, uvicorn, httpx, websockets
Data:      pydantic, pyyaml, jinja2
引擎:      snakemake-interface-* (5 个 interface 包)
Domain:    pandas, numpy, massql, pyteomics, spectrum-utils
```

不再依赖: `openai`, `anthropic`, `mcp`, `alembic`, `snakemake` 包本身

---

## API

```
POST   /api/v2/runs          提交运行
GET    /api/v2/runs          列出运行 (按 workspace 过滤)
GET    /api/v2/runs/:id      查询状态
POST   /api/v2/runs/:id/cancel  取消
GET    /api/v2/runs/:id/log  获取日志 (tail)
GET    /api/v2/runs/:id/files  列出结果文件
GET    /api/v2/runs/:id/files/:path  下载单个文件
WS     /api/v2/runs/ws       实时状态推送

GET    /                     服务信息
GET    /health               健康检查
```

---

## CLI 状态

`cli/main.py` (216 行) 目前在后端项目中，但它本质上是客户端的入口。

```
六条命令:
  tdease submit   → push Snakefile 到 backend，创建 run
  tdease status   → 查询 run 状态
  tdease pull     → 下载结果文件
  tdease log      → 查看实时日志
  tdease list     → 历史运行列表
  tdease cancel   → 取消运行

  tdease server   → 启动服务端 (uvicorn)
  tdease config   → 读写 ~/.tdease/config.yaml
```

它应该在客户端发布流中打包（与 Electron Dashboard / npm 全局包一起），
前端重构时移出。当前暂留，因为:
1. 只有 216 行
2. 开发调试时需要直接 `tdease submit` 测试后端
3. 不引入额外复杂度

---

## 下一步

- [ ] CLI 移到 `TDEase-FrontEnd/` 或独立 npm 包
- [ ] File push/pull 协议 (multipart upload, streaming download)
- [ ] SSE 细化（per-run 订阅、Last-Event-ID 断点续传；日志详情 GET 拉取）
- [ ] User 表 + 轻量认证 (Server/Cloud 模式)
- [ ] _check_view_spec.py 清理（前端相关，残留）
