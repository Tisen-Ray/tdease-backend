---
name: sub-agents
description: Run agent definitions as sub-agents. Use when the user names an agent or sub-agent to run, references an agent definition, or delegates a bounded task to a specialist agent.
allowed-tools: Bash, Read, Agent
---

# Sub-Agents - Task Delegation

Delegates bounded work to sub-agents. Use the native
`Agent` tool when available. For custom agents without native definitions, fall
back to `run_subagent.py` as a one-shot runner.

Use this skill to execute an already-bounded dispatch, not to replace
main-thread planning. The main thread owns routing, scope boundaries, synthesis,
and final judgment.

Load detailed references only when actively dispatching:

- `references/dispatch-contract.md` - required task contract, acceptance checks, and stop conditions.
- `references/agent-roles.md` - canonical role boundaries.
- `references/codex.md` - Codex-specific execution notes.

## Execution Routing

| Agent | Mechanism | Behavior |
|-------|-----------|----------|
| Built-in agents (`researcher`, `implementer`, etc.) | `Agent` tool | Long-running, reports results. |

## Interpreting Requests

| Parameter | Source |
|-----------|--------|
| Agent name | User request mapped to available `.claude/agents/` definitions. |
| Prompt | Task instruction with scope, context refs, acceptance checks, and stop conditions. |

## Required Dispatch Contract

Before dispatch, read `references/dispatch-contract.md` and ensure the prompt
contains:

- objective
- scope
- forbidden scope
- context refs
- acceptance checks
- stop conditions

Do not dispatch broad prompts like "look at this" or "fix everything". If the
contract cannot be written, return to main-thread planning first.

## Dispatch Via Agent Tool

For native agents:

```text
Agent(
  description: "<short 3-5 word description>",
  subagent_type: "<agent-name>",
  prompt: "<dispatch prompt with scope, refs, checks, stop conditions>",
  run_in_background: true
)
```

Parallelize only read-only tasks or tasks with disjoint write ownership.

## Agent Definition Location

All agent definitions live in `.claude/agents/`. Use the native `Agent` tool to dispatch them.

## Common Mistakes

| Mistake | Result | Fix |
|---------|--------|-----|
| Missing scope in prompt | Sub-agent drifts. | Include owned files/modules and forbidden areas. |
| Overlapping write ownership | Conflicting edits. | Parallelize only read-only work or disjoint write scopes. |
| Vague duplicate reviewers | Noisy findings. | Give each reviewer a distinct lens and output contract. |
| Long pasted context | Context overflow. | Reference files and paths instead of pasting large content. |
| Treating sub-agents as final authority | Unreconciled contradictions. | Main thread synthesizes and decides. |
