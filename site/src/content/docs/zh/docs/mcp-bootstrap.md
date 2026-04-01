---
title: MCP 引导
description: 一条命令完成全局和项目级 AI 客户端的 MCP 设置
sidebar:
  order: 7
---

`ontoskills` 可以在一条命令中安装 `ontomcp` 并将其接入支持的 MCP 客户端。

## 快速开始

```bash
# 默认全局
npx ontoskills install mcp --claude
npx ontoskills install mcp --codex --cursor

# 仅项目级
npx ontoskills install mcp --cursor --vscode --project
```

## 作用域模型

- `--global`：配置当前用户或机器
- `--project`：仅配置当前仓库/工作区

如果省略两个标志，`ontoskills` 使用 `--global`。

## 支持的客户端

| 客户端 | 全局 | 项目 | 引导方式 |
|--------|------|------|----------|
| Claude Code | 是 | 是 | 原生 CLI 命令 |
| Codex | 是 | 手动 | 原生 CLI 命令 |
| Qwen Code | 是 | 是 | 原生 CLI 或 `settings.json` 回退 |
| Cursor | 是 | 是 | JSON 文件 |
| VS Code | 是 | 是 | CLI（全局）、JSON 文件（项目）|
| Windsurf | 是 | 手动 | JSON 文件 |
| Antigravity | 尽力 | 手动 | 配置检测或手动回退 |
| OpenCode | 是 | 是 | JSON 文件 |

## 注册内容

每个客户端都配置为使用同一个托管运行时：

```text
~/.ontoskills/bin/ontomcp
```

默认情况下，`ontomcp` 从以下位置读取已编译的本体：

```text
~/.ontoskills/ontologies
```

## 常用命令

```bash
# Claude Code，全局
ontoskills install mcp --claude

# Claude Code + Codex + Cursor 全局
ontoskills install mcp --claude --codex --cursor

# Cursor 和 VS Code 仅限此仓库
ontoskills install mcp --cursor --vscode --project

# 仅安装运行时，不触碰任何客户端
ontoskills install mcp
```

## 手动回退

某些客户端不提供稳定的项目级引导流程。在这种情况下，`ontoskills` 会：

1. 安装 `ontomcp`
2. 尝试最安全的自动化路径
3. 如果客户端仍需用户操作，则打印确切的手动步骤

这是有意为之：命令不应因为一个客户端需要手动最终步骤而阻塞 MCP 安装。
