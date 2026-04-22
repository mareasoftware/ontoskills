---
title: MCP 与 Claude Code
description: 在 Claude Code 中注册和验证 OntoMCP
sidebar:
  order: 11
---

## 安装

首先安装运行时：

```bash
npx ontoskills install mcp
```

这会安装托管运行时二进制文件：

```text
~/.ontoskills/bin/ontomcp
```

## 注册服务器

最快引导：

```bash
npx ontoskills install mcp --claude
```

手动等效：

```bash
claude mcp add --scope user ontomcp -- \
  ~/.ontoskills/bin/ontomcp
```

项目本地设置：

```bash
npx ontoskills install mcp --claude --project
```

如果你想手动指定本体根目录：

```bash
claude mcp add --scope user ontomcp -- \
  ~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

## 验证

```bash
claude mcp get ontomcp
claude mcp list
```

预期状态：

```text
Status: ✓ Connected
```

## Claude Code 可用的工具

连接后，Claude Code 可以调用：

- `search` — 通过语义查询、别名或结构化过滤器搜索
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`

## 故障排除

### 连接失败

检查：
- `~/.ontoskills/bin/ontomcp` 存在
- `~/.ontoskills/ontologies/` 存在
- `index.enabled.ttl` 或已编译的 `.ttl` 文件存在

### 找不到本体

使用显式根目录运行：

```bash
~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

### 重建二进制后 Claude 行为异常

移除并重新添加 MCP 服务器，或重启 Claude Code。过期的后台进程可能仍在使用旧二进制。
