---
title: MCP 与 Codex
description: 为基于 Codex 的本地工作流配置 OntoMCP
sidebar:
  order: 12
---

## 安装

首先安装运行时：

```bash
npx ontoskills install mcp
```

这会安装：

```text
~/.ontoskills/bin/ontomcp
```

## 快速引导

推荐设置：

```bash
npx ontoskills install mcp --codex
```

手动等效：

```bash
codex mcp add ontomcp -- ~/.ontoskills/bin/ontomcp
```

Codex 全局设置使用与其他客户端相同的本地 `stdio` 命令：

```text
~/.ontoskills/bin/ontomcp
```

## 集成模型

基于 Codex 的工作流使用与其他本地客户端相同的 MCP 约定：

- 将 `ontomcp` 作为本地 `stdio` 子进程启动
- 将其指向 `~/.ontoskills/ontologies` 中的托管本体主目录
- 让客户端调用四个公共工具（含可选的语义搜索）

要注册的稳定可执行文件是：

```text
~/.ontoskills/bin/ontomcp
```

## 推荐的运行时命令

```bash
~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

如果你的 Codex 客户端支持基于环境的配置，等效设置是：

```bash
ONTOMCP_ONTOLOGY_ROOT=~/.ontoskills/ontologies
```

## 暴露的工具

- `search` — 通过语义查询、别名或结构化过滤器搜索
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`

## 注意事项

- MCP 服务器读取已编译的 `.ttl` 本体，而不是原始 `SKILL.md`
- 如果你想要自定义技能，也要安装编译器：

```bash
npx ontoskills install core
```

- 然后编译或导入源技能。技能默认自动启用；仅当之前被手动禁用时才需要运行 `ontoskills enable <qualified-id>`
- `--codex` 仅自动化 Codex 全局设置；对于仓库级 Codex MCP 配置，`ontoskills` 目前会打印手动步骤而非强制写入非标准配置文件

## 实用规则

将 Codex 集成视为标准的本地 `stdio` MCP 注册，其命令指向：

```text
~/.ontoskills/bin/ontomcp
```

确切的 UI 或配置文件形状可能因 Codex 构建而异，但服务器命令和本体根保持不变。
