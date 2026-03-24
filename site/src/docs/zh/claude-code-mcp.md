---
title: MCP 与 Claude Code
description: 为 Claude Code 配置 OntoMCP
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

## Claude Code 配置

在 Claude Code 中注册 MCP 服务器。编辑 `~/.claude/settings.json`：

```json
{
  "mcpServers": {
    "ontoskills": {
      "command": "/Users/你的用户名/.ontoskills/bin/ontomcp",
      "args": ["--ontology-root", "/Users/你的用户名/.ontoskills/ontologies"]
    }
  }
}
```

或者使用环境变量：

```json
{
  "mcpServers": {
    "ontoskills": {
      "command": "/Users/你的用户名/.ontoskills/bin/ontomcp",
      "env": {
        "ONTOMCP_ONTOLOGY_ROOT": "/Users/你的用户名/.ontoskills/ontologies"
      }
    }
  }
}
```

## 暴露的工具

- `search_skills`
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`
- `search_intents`（可选，需先运行 `ontoskills export-embeddings`）

## 验证

重启 Claude Code 后，检查工具是否可用：

```bash
claude --mcp-debug
```

## 注意事项

- MCP 服务器读取已编译的 `.ttl` 本体，而不是原始 `SKILL.md`
- 如果你想要自定义技能，也要安装编译器：

```bash
npx ontoskills install core
```

- 然后编译或导入源技能。技能默认自动启用；仅当之前被手动禁用时才需要运行 `ontoskills enable <qualified-id>`
