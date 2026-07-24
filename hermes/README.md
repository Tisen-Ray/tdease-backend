# Hermes Agent Reference

> **Hermes Agent 核心 memory loop 参考副本**

来源：hermes-agent-main

## Memory 循环模式

```
┌──────────────────────────────────────────┐
│               TURN CYCLE                  │
│                                          │
│  pre-turn:                               │
│    memory_manager.prefetch_all(query)     │
│    → 注入 system prompt context          │
│                                          │
│  turn:  model call + tool dispatch       │
│    memory tool:  add/replace/remove       │
│    → MEMORY.md/USER.md 即时落盘          │
│                                          │
│  post-turn:                              │
│    memory_manager.sync_all(user, asst)   │
│    → 持久化到外部 provider                │
│    memory_manager.queue_prefetch_all()   │
│    → 后台预加载下一轮                     │
│                                          │
│  session end:                            │
│    memory_manager.on_session_end()       │
│    memory_manager.shutdown_all()          │
└──────────────────────────────────────────┘
```

## 核心文件

| 文件 | 作用 |
|------|------|
| `agent/memory_provider.py` | MemoryProvider ABC — 所有 memory backend 的接口 |
| `agent/memory_manager.py` | MemoryManager — 编排 prefetch/sync 循环 |
| `tools/memory_tool.py` | file-backed 内存工具 (MEMORY.md / USER.md) |
| `agent/curator.py` | 后台 skill 维护（inactivity-triggered） |
| `agent/learning_graph.py` | 技能-记忆关联图 |

## 关键设计

**File-backed memory (MemoryStore)** — 最实用的模式：
- `MEMORY.md` — agent 自己记的笔记
- `USER.md` — agent 对用户的了解
- Frozen snapshot 注入 system prompt（保持 prefix cache 稳定）
- 中间写操作直接落盘，但不改 system prompt
- 防注入扫描
- Bounded (char limit)

**MemoryProvider ABC 生命周期:**
```
initialize() → system_prompt_block() → prefetch() →
↻ sync_turn() → queue_prefetch() → (next turn)
→ shutdown()
```

## License

Hermes Agent 遵循项目原始许可证。
