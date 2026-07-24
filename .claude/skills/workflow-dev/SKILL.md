---
name: workflow-dev
description: TDEase workflow/node/run 开发 — 系统节点扩展、workflow 设计、API 运行、后端执行、冻结核验、进程泄露、参数传递。完整开发闭环，含所有硬核调试经验。
version: 1.0.0
---

# Workflow 开发 Skill

## 何时使用

- 新增系统 node
- 设计/扩展 workflow
- 通过 API 创建并执行 run
- 启动本地后端
- 调试 run 冻结/丢失/执行失败/子进程泄露

## 架构速查

```
D:/TDEase/system/nodes/<id>/                     ← 系统 node (node.json + entry script)
D:/TDEase/workspaces/test_workspace/runs/<id>/   ← Run 文件 (run.json, workflow.json, inputs.json, events.jsonl)
D:/TDEase/database/tdease.db                     ← SQLite 数据库
src/tools/ptm/<tool>.py                          ← 共享实现（AI tool + node 共用）
src/services/runs/                               ← Run 状态机/输入/执行
src/workflow/execution/                          ← Workflow 引擎
app/api/runs.py                                  ← Run CRUD + execute API
app/core/executor/                               ← LocalExecutor + CommandPipeline
```

### 核心原则

- **单实现源**: AI tool 和 system node 共享 `src/tools/ptm/` 下的函数
- **直接验证优先**: 开发 node pipeline 时先用 `uv run python` 直接跑，再走 API/Workflow
- **freeze = lock config, not lock execution**: freeze 应该阻止修改 inputs/workflow，但永远允许重新执行（当前有 bug，见下文）

---

## 1. 创建系统 Node

```
D:/TDEase/system/nodes/<node_id>/
├── node.json          ← schema: tdease.node/v1, ports/params/runtime
├── <entry>.cmd        ← Windows launcher (sets PYTHONPATH, uv run)
└── <pipeline>.py      ← 实际逻辑
```

### node.json 模板

```json
{
  "schema": "tdease.node/v1",
  "id": "my_node",
  "label": "My Node",
  "category": "quantification",
  "description": "...",
  "runtime": { "kind": "cli", "entry": "run.cmd" },
  "ports": {
    "inputs": [
      { "id": "data_in", "dataType": "tsv", "required": true,
        "positional": true, "positionalOrder": 0 }
    ],
    "outputs": [
      { "id": "result", "dataType": "tsv", "pattern": "{row}_my_output.tsv",
        "handle": "result", "provides": ["tsv"] }
    ]
  },
  "params": {
    "my_param": { "type": "value", "flag": "--my-flag", "group": "basic", "required": true }
  },
  "resources": { "cpus": 1, "memory_mb": 512 },
  "sandbox": { "read_paths": ["workspace/data/", "runs/"], "write_paths": ["runs/{run_id}/artifacts/"] }
}
```

### ⚠️ 两个容易出错的点

**1. input port 必须有 `positional: true` + `positionalOrder`**
否则 CommandPipeline 不生成输入文件路径参数，argparse 报 `required: prsm_tsv, ms2_msalign`。

**2. workflow node 的 params 必须在顶层**
```json
// ✅ 正确
{ "id": "my_node", "params": { "my_param": "value" } }
// ❌ 错误 — CommandPipeline 拿不到
{ "id": "my_node", "data": { "params": { "my_param": "value" } } }
```

### Pipeline 脚本骨架

```python
#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, io, json, os, sys
from pathlib import Path

# -- Project root
for _root in [Path("C:/Users/ray/Desktop/TDEaseNext")]:
    if _root.exists() and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
        break

# -- Settings (required by resolve_workspace_path etc.)
from src.infrastructure.settings import set_settings

class _NodeSettings:
    def get_workspace_root(self, wid): return Path("D:/TDEase/workspaces") / wid
    def get_database_path(self): return Path("D:/TDEase/database/tdease.db")
    def get_data_root(self): return Path("D:/TDEase")
    def get_system_root(self): return Path("D:/TDEase/system")
    def get_workspaces_root(self): return Path("D:/TDEase/workspaces")
    def get_deployment_mode(self): return "personal"
    def get_max_batch_samples(self): return 10
    def get_batch_parameter_limit(self): return 5
    def get_ai_provider_config(self, pid): return {}
    def get_ai_default_config(self): return {}
    data_dir_name = "data"
set_settings(_NodeSettings())

# -- TopPIC PrSM reader (skips parameter header block)
def _read_prsm(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.readlines()
    data_start = next(i for i, line in enumerate(raw) if line.startswith("Data file name\t"))
    return list(csv.DictReader(io.StringIO("".join(raw[data_start:])), delimiter="\t"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prsm_tsv")
    parser.add_argument("ms2_msalign")
    parser.add_argument("--accession", required=True)
    parser.add_argument("--mod-mass", type=float, required=True)
    # ... other params
    parser.add_argument("--output", "-o", default=None)
    args = parser.parse_args()

    print(f"[node_log] {{'message': 'Pipeline start', 'level': 'info'}}")
    # ... pipeline logic ...
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

### 绕过 Workflow Executor 直接验证

开发 node 时不创建 run，直接用 CLI 验证：

```bash
uv run python D:/TDEase/system/nodes/<node>/<pipeline>.py \
  "D:/TDEase/workspaces/test_workspace/runs/r11/5_ms2_toppic_prsm.tsv" \
  "D:/TDEase/workspaces/test_workspace/runs/r11/5_ms2.msalign" \
  --accession "sp|P50566|H4_CHLRE" \
  --mod-mass 42.0106 --mod-name Acetyl --positions "5,8,12,16" \
  --mod-count 1 --ion-group c --ppm 10 \
  --output "D:/TDEase/workspaces/test_workspace/runs/r11"
```

---

## 2. Workflow 设计

### Edge portHandle 规则
- source: `output-<port_id>`
- target: `input-<port_id>`

### 常见错误速查

| 症状 | 原因 | 修复 |
|------|------|------|
| `msconvert Unknown wrapper` | filters 传了 JSON object | 改为字符串 `"peakPicking true 1-"` |
| `TopFD profile data` | 没做 centroid | 确保 msconvert peakPicking |
| `revision_conflict` | expected_revision 过期 | 先 GET inputs → 用返回 revision PUT |
| `frozen_run` | freeze 语义 bug | 手动 unfreeze 三步法 |
| node params 没传到 CLI | params 在 `data.params` | 移到 `node["params"]` 顶层 |
| input positional args missing | port 缺 `positional: true` | 加 `positional` + `positionalOrder` |

---

## 3. 后端启动

```powershell
uv run python scripts/run_backend.py --port 8000 --log-level warning
```

**不要**用 `start_prod_like_backend.py`（copytree workspace 数据，因文件锁定失败）。

### node.json 热加载

当前修改 node.json 后需要重启后端。system node 从文件系统扫描，但 `ToolRegistry`/`CommandPipeline` 缓存了工具定义。改进方向：文件 watch auto-invalidate。

---

## 4. API 创建并执行 Run

```powershell
$h = @{"X-TDEASE-User-Id"="test-user"; "X-TDEASE-User-Admin"="true"}
$base = "http://127.0.0.1:8000/api"

# 1. 创建 run → rid = r<N>
$run = Invoke-RestMethod "$base/runs" -Method Post -Body (@{
    name="my-run"; workspace_id="test_workspace"; description="..."
}|ConvertTo-Json) -Headers $h -ContentType "application/json"

# 2. 上传 workflow
$wf = Get-Content "path/to/workflow.json" -Raw | ConvertFrom-Json
Invoke-RestMethod "$base/runs/$($run.id)/workflow-revisions" -Method Post -Body (@{
    document=$wf; source_type="api"
}|ConvertTo-Json -Depth 10) -Headers $h -ContentType "application/json"

# 3. 绑定输入（先 GET 拿 revision）
$inp = Invoke-RestMethod "$base/runs/$($run.id)/inputs" -Method Get -Headers $h
Invoke-RestMethod "$base/runs/$($run.id)/inputs" -Method Put -Body (@{
    inputs = @{rows = @(@{rowId="r1"; label="r1"
        bindings = @{
            data_loader_1 = @{source = @{kind="workspace-file"; path="data/raw/my.raw"}}
            fasta_loader_1 = @{source = @{kind="workspace-file"; path="data/fasta/my.fasta"}}
        }
    }); sharedBindings = @{}}
    expected_revision = $inp.revision
}|ConvertTo-Json -Depth 6) -Headers $h -ContentType "application/json"

# 4. 执行
Invoke-RestMethod "$base/runs/$($run.id)/preflight" -Method Post -Headers $h
Invoke-RestMethod "$base/runs/$($run.id)/execute" -Method Post -Body "{}" -Headers $h -ContentType "application/json"

# 5. 轮询
Invoke-RestMethod "$base/runs/$($run.id)" -Method Get -Headers $h
Invoke-RestMethod "$base/runs/$($run.id)/node-executions" -Method Get -Headers $h
```

---

## 5. Run 状态管理 & 调试

### 三种真相源

| 源 | 路径 | 控制什么 |
|---|---|---|
| `run.json` | `runs/<id>/run.json` | `status`, `freeze_state` — **API 以此为准** |
| `inputs.json` | `runs/<id>/inputs.json` | `frozenAt` 字段（存在=冻结） |
| DB | `D:/TDEase/database/tdease.db` → `runs` | 列表查询/审计，会滞后 |

### Freeze 语义 bug（当前，待修）

**当前行为（错误）:** `freeze_and_plan()` 将 run 设为 `freezing` → `frozen` → 非 `editable` 状态无法重新执行。

**期望行为:** freeze 只锁 inputs/workflow 不可修改，但 run **永远可重新执行**。

### 手动 unfreeze

```python
import json, sqlite3

run_id = "r11"
# 1. run.json
rj = json.load(open(f"D:/TDEase/workspaces/test_workspace/runs/{run_id}/run.json"))
rj["status"] = "draft"; rj["freeze_state"] = "editable"
json.dump(rj, open(f"D:/TDEase/workspaces/test_workspace/runs/{run_id}/run.json", "w"), indent=2)

# 2. inputs.json — 删除 frozenAt
inp = json.load(open(f"D:/TDEase/workspaces/test_workspace/runs/{run_id}/inputs.json"))
inp.pop("frozenAt", None)
json.dump(inp, open(f"D:/TDEase/workspaces/test_workspace/runs/{run_id}/inputs.json", "w"), indent=2)

# 3. DB
db = sqlite3.connect("D:/TDEase/database/tdease.db")
db.execute(f"UPDATE runs SET status='draft', freeze_state='editable' WHERE id='{run_id}'")
db.execute(f"UPDATE run_node_executions SET status='pending', progress=0, error_message=NULL WHERE run_id='{run_id}' AND node_id='isoforma_1'")
db.commit(); db.close()
```

**不要创建新 run** — unfreeze 保留已完成节点输出，resume 只跑未完成部分。

### Resume

`POST /api/runs/{id}/execute` body `{"resume": true}`：
- `completed` 节点跳过
- `blocked` 节点不重试（需先改回 `pending`）
- 已产出文件保留，不覆盖

### 子进程泄露

**现象:** 杀 backend python 后 TopPIC/TopFD exe 仍在运行。

**原因:** `LocalExecutor` 用 `ThreadPoolExecutor` + subprocess — `cancel()` 只取消排队 task，不杀正在运行的 exe。

**后果:** run → `lost`；子进程可能继续写文件；内存泄露。

**处理:**
```bash
tasklist | grep toppic           # 检查残留
taskkill //F //PID <pid>         # 清理
# 检查文件时间戳判断哪个节点已完成
# 修 DB run_node_executions: running → completed
# unfreeze + resume
```

---

## 6. 数据库速查

```sql
-- 位置: D:/TDEase/database/tdease.db

SELECT id, run_name, status, freeze_state FROM runs ORDER BY created_at DESC LIMIT 10;
SELECT node_id, status, progress, error_message FROM run_node_executions WHERE run_id = 'r11';
SELECT event_type, json_extract(payload, '$.phase') FROM run_events WHERE run_id = 'r11';

-- 修复冻结
UPDATE runs SET status = 'draft', freeze_state = 'editable' WHERE id = 'r11';
UPDATE run_node_executions SET status = 'completed', progress = 100 WHERE run_id = 'r11' AND node_id = 'toppic_1';
```

---

## 7. 性能优化

32 核机器，当前 TopPIC/TopFD workflow 配置：

| 节点 | thread_number | 实际耗时 | 优化 |
|------|--------------|---------|------|
| MSConvert | N/A | ~2 min | 跳过，用预转换 mzML 绑定 |
| TopFD | 30 | ~18 min | `skip_html_folder: true`（改模板，不动正在运行的 run） |
| TopPIC | 30 | ~15 min | `skip_html_folder: true` |
| IsoForma | N/A (Python) | ~2 min | 保持串行（非瓶颈） |

---

## 8. 架构边界：Built-in → PEP723 → 可视化

```
                         ┌─────────────────────────────────┐
                         │   Case-specific PEP723 scripts  │
                         │   (scan selection, filtering,    │
                         │    sample aggregation)           │
                         │   e.g. scan-manifest subcommand  │
                         └────────────┬────────────────────┘
                                      │ produces scan_manifest.tsv
                                      ▼
┌──────────────────────────────────────────────────────────────┐
│             Built-in AI tools  (universal)                    │
│  sum_ms2_spectra    merge_multi_sample_ms2                   │
│  generate_modified_proteoforms                                │
│  build_abundance_matrix    estimate_beta_proportions          │
│                                                              │
│  System nodes: isoforma (single-sample | --scan-manifest)    │
└─────────────────────────┬────────────────────────────────────┘
                          │ produces result tables (.tsv)
                          ▼
┌──────────────────────────────────────────────────────────────┐
│           render_visualization  (Plotly DSL)                  │
│           → PlotlyViewer.vue renders in frontend              │
└──────────────────────────────────────────────────────────────┘
```

**三层分工：**
| 层 | 是什么 | 例子 |
|----|--------|------|
| **Built-in tools** | 通用、可组合的质谱操作 | `merge_multi_sample_ms2`（msalign+feature 双源）|
| **PEP723 scripts** | 案例特化的数据整合，不具普适性 | `scan-manifest` 子命令：读多 PrSM → 过滤 accession → 提取 scan → 输出 manifest TSV |
| **render_visualization** | Plotly DSL 声明式渲染 | `render_visualization(viewer="plotly", viewSpec={chart: {traces: [{type: "pie", ...}]}})` |

**Workflow 模式**：isoforma node 支持两种输入路径：
- **Single-sample**（原位）：`prsm_tsv` + `ms2_msalign` 位置参数
- **Multi-sample batch**（`--scan-manifest`）：上游 PEP723 脚本产出的 manifest TSV

## 9. PEP723 独立脚本

TDEase 系统节点可以同时提供 PEP723 独立脚本，证明插件的零依赖可运行性：

```
D:/TDEase/system/nodes/isoforma/standalone/
└── isoforma_tools.py    ← PEP723 脚本（# /// script 元数据）
```

```bash
# 无需 TDEase 后端，直接用 uv 运行
uv run isoforma_tools.py generate --seq ... --mass ... --positions ... -o vars.tsv
uv run isoforma_tools.py sum-ms2 data.msalign --scans 4403,4409 -o summed.tsv
uv run isoforma_tools.py merge-ms2 --sample "data.msalign|4403|labA" --sample "data.msalign|4409|labB" -o merged.tsv
uv run isoforma_tools.py scan-manifest \
    --pair prsm1.tsv msalign1.msalign label1 \
    --pair prsm2.tsv msalign2.msalign label2 \
    --accession "H4_CHLRE" -o scan_manifest.tsv
uv run isoforma_tools.py build-matrix frag_matches.json --ion c -o matrix.tsv
uv run isoforma_tools.py estimate matrix.tsv --pie pie_spec.json -o props.tsv
```

**merge-ms2 支持两种数据源**：
- `kind=msalign`（默认）：从 TopFD msalign 文件中按 scan number 提取 peak list
- `kind=feature`：从 feature table（ProMex/MSPathFinder 输出）中按 feature ID 提取 monoisotopic mass + intensity

**scan-manifest** 是 PEP723 层的案例特化工具：
- 输入：多对 `--pair PRSM MSALIGN LABEL` + `--accession` + `--evalue` 过滤
- 输出：`scan_manifest.tsv`（msalign_path, scan_number, sample_label）
- 下游：`merge-ms2 --samples-file` 或 isoforma node `--scan-manifest`

**原始输出 + transform_table 清洗**：工具产出 raw TSV，Agent 用 `transform_table` 过滤/重排/限制行数后再给 `render_visualization`。

---

## 关键文件

| 文件 | 说明 |
|------|------|
| `scripts/run_backend.py` | 后端启动 |
| `D:/TDEase/system/nodes/` | 系统 node 目录 |
| `D:/TDEase/workspaces/test_workspace/` | 工作空间根 |
| `D:/TDEase/database/tdease.db` | SQLite |
| `app/api/runs.py` | Run CRUD + execute |
| `app/core/executor/local.py` | `LocalExecutor` |
| `app/core/executor/command_pipeline.py` | params → CLI flags |
| `src/services/runs/run_inputs.py` | `RunInputModule`, `freeze_and_plan` |
| `src/services/runs/commands/execute_run_service.py` | `execute_run_service` |
| `src/workflow/execution/service.py` | `WorkflowService` |
| `src/infrastructure/settings.py` | `SettingsProvider`, `set_settings()` |
| `src/infrastructure/workspace_paths.py` | `resolve_workspace_path()` |
| `src/domain/proteomics/neutral_fragment_matcher.py` | msalign 读取 + fragment matching |
