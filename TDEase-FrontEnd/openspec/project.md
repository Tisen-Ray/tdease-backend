# Project Context

## Purpose
TDEase 是一个面向质谱数据分析的可视化工作流平台，旨在为生物信息学研究人员提供：
- 可视化工作流编辑器（类似ComfyUI的节点式编辑）
- 集成CLI工具、Python脚本、Docker容器的统一执行环境
- AI辅助的工作流设计和参数优化
- 跨平台桌面应用（Electron打包）

## Tech Stack

### 前端
- Vue 3 + TypeScript + Vite
- Vue Flow - 工作流编辑器
- Element Plus - UI组件库
- plotly - 数据可视化
- AG-Grid - 数据表格
- Pinia - 状态管理
- Tauri - 桌面应用框架

### 后端
- FastAPI + Python 3.11+
- Pydantic v2 - 数据验证
- SQLite - 本地数据库
- WebSocket - 实时通信
- conda - Python环境管理

## Project Conventions

### Code Style
- 前端使用 TypeScript 严格模式
- Vue 组件使用 `<script setup>` 语法
- 后端遵循 PEP 8 规范
- 使用中文注释和文档

### Architecture Patterns
- 前端驱动工作流控制，后端负责执行
- 节点间通过文件路径传递数据，避免大数据内存传输
- 配置驱动的节点系统，支持动态加载
- 事件驱动架构支持异步处理

### Testing Strategy
- 单元测试覆盖核心功能
- API集成测试验证前后端通信
- 端到端测试验证完整工作流

### Git Workflow
- main 分支保持稳定
- feature/* 分支开发新功能
- 使用 OpenSpec 管理变更提案

## Domain Context
- 质谱数据处理（Mass Spectrometry）
- 蛋白质组学（Proteomics）
- 生物信息学工作流
- 支持 msconvert、OpenMS、pyOpenMS 等工具
- 之后会在后端加入pbfgen进一步更新加入工具!

## Important Constraints
- 单体应用架构，简化部署
- 支持离线工作流编辑
- 大文件流式处理，避免内存溢出
- 跨平台兼容（Windows/Linux/macOS）

## External Dependencies
- CLI工具：msconvert, OpenMS等
- Python库：pyOpenMS, pandas等
- 可选Docker容器支持
- 可选云端计算服务集成

## 文档结构
- `doc/核心需求.md` - 核心功能需求
- `doc/架构设计.md` - 整体架构设计
- `doc/节点设计.md` - 节点系统架构
- `doc/可视化节点设计.md` - 可视化节点设计
- `doc/功能需求.md` - 功能需求
- `doc/其他需求.md` - 其他需求
- `doc/tdeaseapi.md` - 后端API实现记录（Phase 2完成）
