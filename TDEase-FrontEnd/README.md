# TDEase FrontEnd

前端负责工作流编辑、结果可视化与轻量交互计算。重型数据处理仍由后端或本地计算节点完成，前端不承担核心批处理计算。

## 1. 项目定位

- 工作流定义和执行状态由后端持久化，前端负责渲染和交互。
- TSV 等结果文件在前端进行可视化处理（表格、图谱、联动分析）。
- 氨基酸序列编辑、局部重算等轻量能力在前端完成。
- 支持“纯可视化工作流”模式，不触发后端重计算也可浏览数据。
- 支持两种封装方式：
  - 纯 web
  - Electron 桌面壳

## 2. 开发与运行模式

### 纯 web 开发

- 默认 Vite 端口为 `1420`
- `1420` 是唯一允许的 dev server 端口；如果被占用，Vite 应直接失败，而不是漂移到 `1421`
- 开发模式下 `/api` 通过 `vite.config.ts` 代理到 `http://127.0.0.1:8000`

常用命令：

```bash
pnpm install
pnpm run dev
pnpm run build
pnpm run preview
```

### Electron 桌面开发

Electron 仅替换桌面窗口封装层，不改变 Vue 前端主逻辑。

常用命令：

```bash
pnpm run desktop:dev
pnpm run desktop:build
pnpm run desktop:dist
```

说明：

- `desktop:dev` 会先启动 Vite dev server，再用 Electron 打开它
- `desktop:build` / `desktop:dist` 依赖已有的 `dist/` 产物
- 后端仍然是独立服务，不由前端业务代码接管

## 3. 前后端连接配置

当前代码中 `src/services/api/client.ts` 使用以下规则：

- `VITE_API_BASE_URL` 未设置时，使用相对路径
- 若 `VITE_API_BASE_URL` 误指向 HMR 端口 `1421`，会被自动重置为空，避免请求打到前端 HMR 服务

推荐环境变量：

```env
VITE_API_BASE_URL=
VITE_WS_URL=ws://localhost:8000
VITE_TUS_UPLOAD_ENDPOINT=
```

说明：

- 开发环境通常保持 `VITE_API_BASE_URL` 为空，由代理处理
- 生产环境可设置为反向代理地址，例如 `https://api.example.com`
- 文件上传默认使用 Uppy；配置 `VITE_TUS_UPLOAD_ENDPOINT` 后切换为 Tus

## 4. 认证与多用户访问

对齐当前后端约定：

- `TDEASE_AUTH_MODE=off`：主分支默认，不校验 API Key
- `TDEASE_AUTH_MODE=api_key`：必须传 API Key，并执行用户作用域校验
- `TDEASE_DEPLOYMENT_MODE=personal`：主分支默认，偏本地单用户
- `TDEASE_DEPLOYMENT_MODE=lab`：实验室共享部署，要求 API Key

多用户场景下，前端调用应遵守：

- `/api/users/{user_id}/...` 路径中的 `user_id` 必须与认证身份一致（非管理员）
- 执行接口在认证模式下必须提供 `user_id + workspace_id + sample_ids`
- `workspace` 上下文统一从 `useWorkspaceStore()` 读取，避免不同页面传入不一致用户

## 5. 批量执行请求

批量执行接口：

- `POST /api/workflows/{workflow_id}/execute-batch`

请求最少应保证传入：

- `user_id`
- `workspace_id`
- `sample_ids`

否则在 `api_key` 模式下会被拒绝。

## 6. 排障

后端会为每个请求生成或透传 `X-Request-ID`，并写入 access log。

建议：

1. 请求时附带 `X-Request-ID`
2. 若收到 `500` 且响应包含 `correlation_id`，在 UI 错误提示中展示该 ID
3. 支持侧使用 `X-Request-ID` 或 `correlation_id` 检索后端日志

常见错误：

- `401 Missing/Invalid API key`
- `403 Access denied for user_id`
- `400 Authenticated mode requires user_id, workspace_id and sample_ids`

## 7. 安全建议

- 不要把 API Key 写死在源码或提交到仓库
- 浏览器场景优先通过反向代理注入认证头
- 桌面端如需保存凭据，后续再接系统凭据库
- 前端日志中避免打印原始密钥、完整文件绝对路径与敏感参数
