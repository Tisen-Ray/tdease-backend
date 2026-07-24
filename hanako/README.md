# Hanako Reference

> **OpenHanako 核心代码参考副本** — 用于 TDEase-zero 的 provider/PI 体系参考。

来源：[openhanako-main](https://github.com/liliMozi/openhanako) (v0.416.51)

## 目录

| 目录 | 内容 | 文件数 |
|------|------|--------|
| `lib/providers/` | 40+ LLM provider 插件（OpenAI, Anthropic, DeepSeek, Ollama, 硅基流动...） | 40 |
| `lib/pi-sdk/` | PI Coding Agent SDK 适配层 | 5 |
| `lib/llm/` | LLM 客户端抽象（缓存、用量、provider-client） | 9 |
| `lib/auth/` | OAuth 认证（xAI） | 1 |
| `lib/permission/` | 权限系统（safety policy, tool invocation） | 3 |
| `lib/tools/` | 40+ 工具定义（browser, file, search, workflow, subagent...） | 41 |
| `lib/workflow/` | 工作流引擎（concurrency, journal, sandbox, structured-output） | 6 |
| `lib/` 其他 | skills, memory, sandbox, search, shell, terminal, exec-command... | ~150 |
| `shared/` | 共享工具（known-models, provider-auth, safe-fs, config-schema...） | 81 |
| `core/` | 核心引擎（provider-registry, model-manager, session-coordinator...） | 58 |
| `server/` | Hono HTTP 服务（routes: providers, auth, config, sessions...） | 32 |
| `cli/` | CLI 入口 | 10 |
| `hub/` | 插件市场 | - |
| `packages/` | 插件 SDK（plugin-sdk, plugin-protocol, plugin-runtime） | - |

## 使用方式

1. 参考 `lib/providers/` 中的插件定义模式来集成 LLM provider
2. 参考 `lib/pi-sdk/` 了解 PI Coding Agent 集成
3. 参考 `core/provider-registry.ts` 了解 provider 注册表设计
4. 参考 `server/routes/providers.ts` 了解 provider API 设计

## License

Hanako 基于 Apache-2.0 许可证。
