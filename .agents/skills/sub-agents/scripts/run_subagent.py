#!/usr/bin/env python3
"""
run_subagent.py — Spawn Claude Code as a sub-agent with an agent definition as system prompt.

Usage:
    scripts/run_subagent.py --agent <name> --prompt "<task>" --cwd <path>
    scripts/run_subagent.py --list [--cwd <path>]

Agent definitions live in {cwd}/.agents/agents/*.md (or $SUB_AGENTS_DIR).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Agent loader
# ---------------------------------------------------------------------------


def parse_frontmatter(content: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not m:
        return {}, content
    fm = {}
    for line in m.group(1).split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("\"'")
    return fm, m.group(2)


def _extract_description(body: str) -> str:
    for line in body.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:100]
    return ""


_AGENT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_name(name: str) -> str:
    if not name or not _AGENT_RE.match(name):
        raise ValueError(f"Invalid agent name: {name!r}")
    return name


def _find_agent_file(agents_root: Path, name: str, ext: str) -> Path | None:
    """Look for {name}{ext} in agents_root, with path-traversal guard."""
    for sub in ["", "agents"]:
        d = agents_root / sub if sub else agents_root
        candidate = (d / f"{name}{ext}").resolve()
        if not str(candidate).startswith(str(d.resolve())):
            continue
        if candidate.exists():
            return candidate
    return None


def load_agent(agents_dir: str, name: str) -> tuple[str, str]:
    """Return (system_context, file_path)."""
    _validate_name(name)
    root = Path(agents_dir)
    for ext in [".md", ".txt"]:
        path = _find_agent_file(root, name, ext)
        if path:
            content = path.read_text(encoding="utf-8")
            _, body = parse_frontmatter(content)
            return body.strip(), str(path)
    raise FileNotFoundError(f"Agent definition not found: {name}")


def list_agents(agents_dir: str) -> list[dict]:
    root = Path(agents_dir)
    seen: set[str] = set()
    result: list[dict] = []
    for sub in ["", "agents"]:
        d = root / sub if sub else root
        if not d.is_dir():
            continue
        for ext in [".md", ".txt"]:
            for f in sorted(d.glob(f"*{ext}")):
                name = f.stem
                if name in seen:
                    continue
                seen.add(name)
                try:
                    _, body = parse_frontmatter(f.read_text(encoding="utf-8"))
                    desc = _extract_description(body)
                except Exception:
                    desc = ""
                result.append({"name": name, "description": desc})
    result.sort(key=lambda a: a["name"])
    return result


def get_agents_dir(args_dir: str | None, args_cwd: str | None) -> str:
    if args_dir:
        return args_dir
    env = os.environ.get("SUB_AGENTS_DIR")
    if env:
        return env
    if args_cwd:
        return str(Path(args_cwd) / ".agents")
    return str(Path.cwd() / ".agents")


# ---------------------------------------------------------------------------
# Claude stream-json processor
# ---------------------------------------------------------------------------


class ClaudeStreamProcessor:
    def __init__(self):
        self.result_json = None

    def feed(self, line: str) -> bool:
        """Return True when the final result is captured."""
        line = line.strip()
        if not line or self.result_json is not None:
            return False
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return False
        if data.get("type") == "result":
            self.result_json = data
            return True
        return False

    @property
    def result(self) -> dict | None:
        return self.result_json


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


def execute(system_context: str, prompt: str, cwd: str, timeout_ms: int = 600_000) -> dict:
    cmd = [
        "claude",
        "--append-system-prompt", f"cwd: {cwd}\n\n{system_context}",
        "--print", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]

    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except FileNotFoundError:
        return {"result": "", "exit_code": 127, "status": "error", "error": "claude CLI not found"}

    processor = ClaudeStreamProcessor()
    stdout_lines: list[str] = []

    if proc.stdout is None:
        proc.kill()
        return {"result": "", "exit_code": 1, "status": "error", "error": "failed to capture stdout"}

    try:
        for line in iter(proc.stdout.readline, ""):
            stdout_lines.append(line)
            if processor.feed(line):
                proc.terminate()
                break

        try:
            _, stderr = proc.communicate(timeout=timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr = proc.communicate()
            partial = processor.result.get("result", "") if processor.result else ""
            return {"result": partial, "exit_code": 124, "status": "partial" if partial else "error",
                    "error": f"Timeout after {timeout_ms}ms"}

        result = processor.result
        exit_code = proc.returncode or 0

        if result:
            status, ec = "success", exit_code  # Claude often exits 1 on success
        else:
            status, ec = "error", exit_code

        resp: dict = {
            "result": result.get("result", "") if result else "".join(stdout_lines),
            "exit_code": 0 if status == "success" else ec,
            "status": status,
        }
        if status == "success" and ec != 0:
            resp["raw_exit_code"] = ec
        if status in ("error", "partial"):
            msg = f"CLI exited with code {ec}"
            if stderr and stderr.strip():
                msg += f": {stderr.strip()}"
            resp["error"] = msg
        return resp

    except Exception as e:
        proc.kill()
        partial = processor.result.get("result", "") if processor.result else ""
        return {"result": partial, "exit_code": 1, "status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description="Spawn Claude Code as a sub-agent")
    p.add_argument("--list", action="store_true")
    p.add_argument("--agent")
    p.add_argument("--prompt")
    p.add_argument("--cwd")
    p.add_argument("--agents-dir")
    p.add_argument("--timeout", type=int, default=600_000)
    args = p.parse_args()

    agents_dir = get_agents_dir(args.agents_dir, args.cwd)

    if args.list:
        agents = list_agents(agents_dir)
        print(json.dumps({"agents": agents, "agents_dir": agents_dir}, ensure_ascii=False))
        return

    # Validation
    for required, name in [(args.agent, "--agent"), (args.prompt, "--prompt"), (args.cwd, "--cwd")]:
        if not required:
            print(json.dumps({"result": "", "exit_code": 1, "status": "error",
                              "error": f"{name} is required"}, ensure_ascii=False))
            sys.exit(1)

    if not os.path.isabs(args.cwd):
        print(json.dumps({"result": "", "exit_code": 1, "status": "error",
                          "error": "cwd must be an absolute path"}, ensure_ascii=False))
        sys.exit(1)
    if not os.path.isdir(args.cwd):
        print(json.dumps({"result": "", "exit_code": 1, "status": "error",
                          "error": f"cwd does not exist: {args.cwd}"}, ensure_ascii=False))
        sys.exit(1)

    try:
        system_context, _ = load_agent(agents_dir, args.agent)
    except FileNotFoundError as e:
        print(json.dumps({"result": "", "exit_code": 1, "status": "error",
                          "error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    result = execute(system_context, args.prompt, args.cwd, args.timeout)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
