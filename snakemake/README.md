# Snakemake Reference

> **Snakemake v8+ 源码参考** — TDEase-zero 将 Snakemake 作为唯一 workflow 引擎

## 核心哲学

```
Snakefile (DSL) → 解析 → DAG → Scheduler → Executor → 输出
    ↓                                              ↓
  规则声明                                  持久化 (file/DB)
  输入/输出/脚本                            缓存 (provenance hash)
  conda/container                            日志
```

**TDEase-zero 不做的事：**
- ❌ 不重写 workflow DAG 引擎
- ❌ 不重写调度器
- ❌ 不重写执行器
- ❌ 不重写缓存/持久化

**TDEase-zero 做的事：**
- ✅ 程序化调用 `SnakemakeApi` → `WorkflowApi` → `DAGApi.execute_workflow()`
- ✅ AI Agent 自动生成 Snakefile
- ✅ 在 Snakemake 之上包装证据钩子 (evidence hooks)

## API 集成模式

```python
from snakemake.api import SnakemakeApi
from snakemake.settings.types import (
    ResourceSettings, ConfigSettings, ExecutionSettings,
    OutputSettings, DAGSettings,
)

with SnakemakeApi(output_settings=OutputSettings()) as api:
    workflow_api = api.workflow(
        snakefile="path/to/Snakefile",
        workdir="path/to/workdir",
        resource_settings=ResourceSettings(cores=8),
        config_settings=ConfigSettings(),
    )
    dag_api = workflow_api.dag(dag_settings=DAGSettings())
    
    # 执行
    dag_api.execute_workflow(
        executor="local",
        execution_settings=ExecutionSettings(),
    )
```

## 核心模块

| 模块 | 文件 | 作用 |
|------|------|------|
| **Workflow** | `workflow.py` | 中心类：持有 rules, DAG, settings, 文件系统映射 |
| **DAG** | `dag.py` | DAG 构建、拓扑排序、候选作业推导 |
| **Jobs** | `jobs.py` | 单个执行单元（input/output/wildcards/params） |
| **Rules** | `rules.py` | 规则定义（从 Snakefile 解析而来） |
| **Scheduler** | `scheduling/greedy.py` | 贪心调度器（默认） |
| **Scheduler** | `scheduling/job_scheduler.py` | 作业生命周期管理 |
| **Executor** | `executors/local.py` | 本地执行器（ThreadPool） |
| **Persistence** | `persistence/file.py` | 文件持久化（.snakemake/metadata/） |
| **Persistence** | `persistence/db.py` | 数据库持久化 (SQLModel) |
| **Caching** | `caching/__init__.py` | 输出缓存（provenance hash） |
| **Parser** | `parser.py` | Snakefile 解析 |
| **CLI** | `cli.py` | 命令行入口 |
| **API** | `api.py` | 程序化 API（TDEase-zero 要用的） |
| **Shell** | `shell.py` | shell 命令执行封装 |

## API 调用链

```
SnakemakeApi (上下文管理器)
  └─ .workflow(snakefile, ...) → WorkflowApi
       ├─ .lint()              — 工作流检查
       ├─ .list_rules()        — 列出规则
       └─ .dag() → DAGApi
            └─ .execute_workflow() — 执行入口
```

## Snakefile DSL 模式

```python
# 最简单的规则
rule process_mzml:
    input: "raw/{sample}.mzML"
    output: "results/{sample}/features.csv"
    shell: "process.py {input} {output}"

# 带 conda 环境
rule deconvolve:
    input: "raw/{sample}.mzML"
    output: "results/{sample}/deconv.csv"
    conda: "envs/deconv.yaml"
    script: "scripts/deconvolve.py"

# 带 config
rule all:
    input: expand("results/{sample}/report.html", sample=SAMPLES)
```

## Snakemake 天然特性（TDEase-zero 不需重造的）


| 特性 | 说明 |
|------|------|
| DAG 构建 | 自动推导依赖关系 |
| 文件时间戳检查 | 跳过已完成的 job |
| 并行执行 | ThreadPool / 集群提交 |
| 失败重试 | retry 机制 |
| Conda 环境 | 自动创建/管理 |
| Container | Singularity 集成 |
| 输出缓存 | Provenance-based |
| 持久化 | 记录每个 job 的元数据 |
| Report | 自动生成 HTML 报告 |
| 模块化 | `include` / `module` 复用 |

## TDEase-zero 集成要点

1. **AI 生成 Snakefile** → Agent 输出 `.smk` 文件到 workspace
2. **调用 API** → `python -m snakemake API` 或 `SnakemakeApi`
3. **证据钩子** → 每个 job 完成后 capture stdout/stderr + 文件校验
4. **结果渲染** → Snakemake 产生文件，viewer matrix 渲染
5. **失败处理** → Snakemake 失败 → AI Agent 修复 Snakefile 重试

## License

Snakemake 遵循 MIT License (Johannes Köster).
