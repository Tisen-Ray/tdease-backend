---
name: ai-tool-dev
description: TDEase AI 扩展开发 — 新增 AI 工具、技能系统、测试脚手架、eval suite 运行。覆盖原子工具设计、中间表协议、工具验证、子代理调度、前后端 AI 链路。
version: 1.0.0
---

# AI 工具 & 技能扩展开发

## 何时使用

- 新增原子 AI 工具（`src/ai/tool_manifests/`）
- 新增 AI Skill（`.claude/skills/` 或 `.codex/skills/`）
- 运行 AI eval suite
- 调试 tool 注册/调用/返回链路
- 验证 Agent 能发现并使用新工具
- 写 AI 测试脚本

## 与 workflow-dev 的分工

| 场景 | 用哪个 skill |
|------|-------------|
| 加 node、改 workflow、启动后端、调 freeze | `workflow-dev` |
| 加 AI tool、写 skill、跑 eval、调 agent 链路 | **`ai-tool-dev`** |

---

## 1. 新增 AI Tool

### Manifest (`src/ai/tool_manifests/<id>.json`)

```json
{
  "schema": "tdease.ai-tool/v2",
  "id": "my_tool",
  "description": "What it does and when to use it. One clear sentence.",
  "runtime": { "kind": "in_process", "entry": "src.tools.ptm.my_module:my_function" },
  "params": {
    "my_arg": { "type": "string", "required": true, "description": "..." }
  },
  "permission_level": "sidecar",
  "tool_type": "analysis",
  "output_contract": ["text"],
  "persist_result": true
}
```

**参数类型:** `string`, `integer`, `number`, `boolean`, `array`, `object`。
**`workspace_path: true`** 标记路径参数，会被 `resolve_workspace_path()` 解析。

### 共享实现 (`src/tools/ptm/<module>.py`)

```python
from src.tools.ptm.serialization import tool_result, DisplayHint

def my_function(arg1: str, workspace_id: str = "") -> dict:
    """每个工具产出可检查的中间表。"""
    rows = [...]   # list[dict]
    columns = [{"name": "col1", "type": "string"}, ...]
    result_data = {"summary": "..."}
    return tool_result(
        result_data,
        tables=[{"id": "t1", "name": "my_table", "kind": "table",
                 "columns": columns, "rows": rows}],
        display_hint=DisplayHint(visualizationType="table", semanticType="proteomics/..."),
    )
```

**关键约定:**
- 函数签名必须含 `workspace_id: str = ""` 参数
- 使用 `tool_result()` 包装返回，含 `tables[]` 供可视化
- `display_hint` 标记语义类型，前端按此渲染
- `in_process` tool 通过 `src/ai/builtin_tools.py` → `load_builtin_tool_specs()` 自动加载，无需额外注册

### 验证工具注册

```python
import os; os.environ.setdefault("TDEASE_ENV", "development")
from src.ai.tool_registry import get_tool_registry
from pathlib import Path

reg = get_tool_registry()
reg.load_system_tools(Path("D:/TDEase/system"))
spec = reg.get("my_tool")
print(f"Tool: {spec.name} source={spec.source}" if spec else "MISSING")
# 检查 load errors
for err in reg.get_load_errors():
    print(f"  ERROR: {err}")
```

---

## 2. 工具设计原则

### 原子工具 > 大工具

| ❌ 不要 | ✅ 要 |
|---------|-----|
| 一个大工具做全部 6 步 | 4 个原子工具，每个产出一个中间表 |
| `quantify_positional_isomers` | `generate_modified_proteoforms` → `sum_ms2_spectra` → `build_abundance_matrix` → `estimate_beta_proportions` |

**原因:** Agent 可以自由组合、跳过、重排；每个中间表可被 `render_visualization` 独立检查。

### 通用参数 > 硬编码

```python
# ✅ 通用
generate_modified_proteoforms(sequence=..., modification_mass=..., target_positions=[5,8,12,16])

# ❌ 特化
generate_h4_acetyl_isomers()  # 硬编码 H4 + Acetyl + [5,8,12,16]
```

### 单实现源

AI tool 和 system node 共享 `src/tools/ptm/` 下的同一份函数。Tool 用 `in_process` 直接调用，node 用 `uv run` 脚本调用。

### 中间表协议

每个 tool 返回 `tables[]`：
```python
{
    "id": "proteoform_variants",
    "name": "proteoform_variants",
    "kind": "table",
    "columns": [{"name": "proteoform_id", "type": "string"}, ...],
    "rows": [{"proteoform_id": "isoform_0", ...}, ...]
}
```

Agent 可以在 tool 之间传递表引用。

---

## 3. 现有工具矩阵 (参考)

### 数据访问 (8)
`read_run`, `read_table`, `read_file`, `read_directory`, `read_nodes`, `read_workflows`, `view_tool_history`, `Skill`

### 质谱分析 (10)
`match_fragments`, `analyze_envelope`, `analyze_table_patterns`, `find_family_ladder`, `find_feature_window`, `massql_check`, `massql_extract`, `search_ptms`, `unimod`, `uniprot`

### 数据处理 (2)
`transform_table`, `render_visualization`

### 证据 (3)
`classify_ptm_evidence`, `record_inference`, `review_evidence`

### IsoForma 位置异构体 (5)
`generate_modified_proteoforms`, `sum_ms2_spectra`, `merge_multi_sample_ms2`, `build_abundance_matrix`, `estimate_beta_proportions`

### 编辑 (3)
`write_file`, `edit_file`, `run_shell`

### 编排 (3)
`run`, `configure_run`, `formalize_workflow`

---

## 4. AI Skill 系统

### Skill 位置

| 目录 | 用途 |
|------|------|
| `.claude/skills/` | Claude Code CLI 用 — 开发工具链 |
| `.codex/skills/` | Codex / TDEase 产品用 — 科学流程 + 开发 |

### Skill 格式

```markdown
---
name: my-skill
description: One-line description for skill discovery
version: 1.0.0
---

# Skill Title

## 何时使用
- Scenario 1
- Scenario 2

## 流程
...
```

### Agent 如何调用 Skill

Agent 通过 `Skill` 工具按名称调用。Skill 的 markdown 内容被注入到 agent prompt 中作为指令。

---

## 5. 测试脚手架

### Eval Suite

```bash
# 运行完整 eval suite
uv run python scripts/eval/run_eval_suite.py paper-cases-v1 --model deepseek-chat --repetitions 3 --workspace-id test_workspace

# 输出: .scratch/ eval run report JSON
```

### 单 Case AI 测试

```bash
# 干跑 (只生成 payload，不执行 LLM)
uv run python scripts/paper_case_ai_runner.py --case soybean --run-name soy

# 执行 (POST 到真实 API)
uv run python scripts/paper_case_ai_runner.py --case chlamy_h4 --execute --run-id c064aa288bce
```

### AI 基础设施检查

```bash
# 基础设施（不耗 LLM tokens）
uv run python scripts/ai_test_pipeline.py

# 含 LLM
uv run python scripts/ai_test_pipeline.py --live --provider deepseek --model deepseek-chat
```

### 直接调用 Tool 函数

```python
import os; os.environ.setdefault("TDEASE_ENV", "development")
from src.tools.ptm.isoforma import generate_modified_proteoforms

result = generate_modified_proteoforms(
    sequence="SGRGKGGKGLGKGGAKR...",
    modification_mass=42.0106,
    modification_name="Acetyl",
    target_positions=[5, 8, 12, 16],
    count=1,
)
print(result["data"]["total_variants"])
for v in result["data"]["variants"]:
    print(f"  {v['proteoform_id']}: {v['modification_sites']}")
```

---

## 6. 常用调试

### Tool 未注册

```python
from src.ai.tool_registry import get_tool_registry
reg = get_tool_registry()
reg.load_system_tools(Path("D:/TDEase/system"))
for err in reg.get_load_errors():
    print(f"[{err['id']}] {err['error']}")
```

### Agent 不调用新工具

1. 检查 `tool_registry.list_specs()` 是否包含该 tool
2. 检查 tool manifest 的 `description` 是否足够清晰（Agent 靠 description 做 tool selection）
3. 检查 `permission_level` — `sidecar` 对所有 agent 级别可见，`manager` 仅 manager 可见

### Tool 调用失败

- `SettingsProvider not configured` → tool 未初始化 settings，见 `workflow-dev` 
- `workspace_path` 解析失败 → path 不是 workspace-relative
- `FragmentMatch` object has no attribute `get` → 需同时支持 dataclass 和 dict

### Session JSONL 检查

```python
import json
with open("path/to/session.jsonl", encoding="utf-8") as f:
    for line in f:
        entry = json.loads(line.strip())
        # entry["role"], entry["content"], entry.get("tool_calls")
```

---

## 关键文件

| 文件 | 说明 |
|------|------|
| `src/ai/tool_manifests/` | 所有 builtin tool manifest |
| `src/ai/builtin_tools.py` | Builtin tool 加载 + 注册 |
| `src/ai/tool_registry.py` | ToolRegistry 单例 |
| `src/tools/ptm/serialization.py` | `tool_result()`, `DisplayHint` |
| `src/tools/ptm/isoforma.py` | IsoForma 4-tool 参考实现 |
| `src/ai/eval/suites/paper_cases_v1.py` | Paper cases eval suite |
| `scripts/eval/run_eval_suite.py` | Eval runner |
| `scripts/paper_case_ai_runner.py` | 单 case AI runner |
| `scripts/ai_test_pipeline.py` | AI 基础设施检查 |
| `.codex/skills/` | 产品技能目录 |
| `.claude/skills/` | 开发技能目录 |
