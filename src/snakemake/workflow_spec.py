"""
Snakemake workflow 规格定义。

WorkflowSpec 是 AI Agent 生成 Snakemake 的中间表示，
最终渲染为 .smk 文件或直接通过 Snakemake API 执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RuleSpec:
    """单个 Snakemake rule 的规格。"""

    name: str
    input: list[str] = field(default_factory=list)
    output: list[str] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    shell: Optional[str] = None
    script: Optional[str] = None
    run: Optional[str] = None
    conda: Optional[str] = None
    container: Optional[str] = None
    threads: int = 1
    resources: dict[str, str] = field(default_factory=dict)
    benchmark: Optional[str] = None
    wildcard_constraints: dict[str, str] = field(default_factory=dict)
    priority: int = 0


@dataclass
class WorkflowSpec:
    """完整的 workflow 规格，可直接渲染为 Snakefile。"""

    rules: list[RuleSpec] = field(default_factory=list)
    config: dict[str, object] = field(default_factory=dict)
    modules: list[str] = field(default_factory=list)
    workdir: Optional[str] = None

    def to_snakefile(self) -> str:
        """渲染为 Snakefile 内容。"""
        parts: list[str] = []

        # Config header
        if self.config:
            import yaml
            config_yaml = yaml.dump(self.config, default_flow_style=False)
            parts.append(f"config:\n{self._indent(config_yaml)}")

        # Modules
        for module in self.modules:
            parts.append(f"module {module}:")
            parts.append("")

        # Rules
        for rule in self.rules:
            parts.append(self._render_rule(rule))

        return "\n".join(parts)

    def _render_rule(self, rule: RuleSpec) -> str:
        lines = [f"rule {rule.name}:"]
        if rule.input:
            items = ",\n".join(f"    \"{i}\"" for i in rule.input)
            lines.append(f"    input:\n{items}")
        if rule.output:
            items = ",\n".join(f"    \"{o}\"" for o in rule.output)
            lines.append(f"    output:\n{items}")
        if rule.params:
            items = ",\n".join(f"    {k}={v}" for k, v in rule.params.items())
            lines.append(f"    params:\n{items}")
        if rule.log:
            items = ",\n".join(f"    \"{l}\"" for l in rule.log)
            lines.append(f"    log:\n{items}")
        if rule.conda:
            lines.append(f"    conda: \"{rule.conda}\"")
        if rule.container:
            lines.append(f"    container: \"{rule.container}\"")
        if rule.threads > 1:
            lines.append(f"    threads: {rule.threads}")
        if rule.resources:
            items = ",\n".join(f"    {k}={v}" for k, v in rule.resources.items())
            lines.append(f"    resources:\n{items}")
        if rule.benchmark:
            lines.append(f"    benchmark: \"{rule.benchmark}\"")
        if rule.shell:
            lines.append(f"    shell:")
            lines.append(f"        \"{rule.shell}\"")
        elif rule.script:
            lines.append(f"    script:")
            lines.append(f"        \"{rule.script}\"")
        elif rule.run:
            lines.append(f"    run:")
            for line in rule.run.split("\n"):
                lines.append(f"        {line}")
        return "\n".join(lines)

    @staticmethod
    def _indent(text: str, prefix: str = "    ") -> str:
        return "\n".join(prefix + line for line in text.split("\n"))
