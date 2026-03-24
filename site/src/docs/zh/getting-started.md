---
title: 快速开始
description: 安装 OntoSkills 并查询你的第一个技能
---

在本教程中，你将安装 OntoSkills 并对已编译的技能本体运行你的第一个 SPARQL 查询。

**完成后你将拥有：**
- 一个可用的 OntoSkills 安装
- 一个从 OntoStore 安装的技能
- 一个成功的 SPARQL 查询结果

预计时间：~5 分钟

---

## 前置条件

开始之前，确保你有：

- **Node.js** 18+（[安装](https://nodejs.org/)）
- **Git**（[安装](https://git-scm.com/)）
- **Anthropic API key**（从 [console.anthropic.com](https://console.anthropic.com/) 获取）

---

## 第一步：安装 CLI

打开终端并运行：

```bash
npx ontoskills install mcp
```

这将在 `~/.ontoskills/` 下创建一个托管主目录，包含：

- `bin/ontomcp` — MCP 运行时
- `ontologies/` — 已编译的本体包
- `state/` — 锁定文件和元数据

**预期输出：**
```
✓ 已安装 ontomcp 到 ~/.ontoskills/bin/ontomcp
✓ 已创建 ~/.ontoskills/ontologies/
✓ 已创建 ~/.ontoskills/state/
```

---

## 第二步：从 OntoStore 安装技能

OntoStore 已内置。让我们安装一个问候技能：

```bash
ontoskills search hello
```

**预期输出：**
```
找到 1 个技能：
  mareasw/greeting/hello - 简单的问候技能
```

安装它（安装后自动启用）：

```bash
ontoskills install mareasw/greeting/hello
```

**预期输出：**
```
✓ 已安装 mareasw/greeting/hello
```

---

## 第三步：查询技能

现在让我们用 SPARQL 查询已安装的技能：

```bash
ontoskills query "SELECT ?skill ?intent WHERE { ?skill a oc:Skill . ?skill oc:resolvesIntent ?intent }"
```

**预期输出：**
```text
?skill                    ?intent
─────────────────────────────────────
skill:hello               "say_hello"
```

你刚刚查询了一个已编译的本体。结果是确定性的 — 相同的查询，相同的结果，每次都是。

---

## 第四步：（可选）安装编译器

如果你想从源文件编写自定义技能，安装编译器：

```bash
ontoskills install core
```

系统要求：
- **Python** 3.10+
- 设置 `ANTHROPIC_API_KEY` 环境变量

```bash
export ANTHROPIC_API_KEY="你的-key"
ontoskills init-core
```

这会创建 `ontoskills-core.ttl` — 包含类和属性的基础本体。

---

## 第五步：（可选）编写你的第一个技能

创建一个简单的技能：

```bash
mkdir -p skills/my-first-skill
```

创建 `skills/my-first-skill/SKILL.md`：

```markdown
# 我的第一个技能

一个简单的演示技能。

## 功能

这个技能按名字问候用户。

## 何时使用

当用户想要友好的问候时使用。

## 如何使用

1. 询问用户的名字
2. 说"你好，{名字}！"
```

编译它：

```bash
ontoskills compile my-first-skill
```

**预期输出：**
```
✓ 已编译 my-first-skill
  性质: 一个简单的演示技能
  意图: greet_user
```

查询你的技能：

```bash
ontoskills query "SELECT ?intent WHERE { skill:my_first_skill oc:resolvesIntent ?intent }"
```

---

## 你学到了什么

- 如何安装 OntoSkills CLI 和 MCP 运行时
- 如何从 OntoStore 安装技能
- 如何用 SPARQL 查询技能
- （可选）如何编写和编译自己的技能

---

## 下一步

现在你已经设置好了：

| 目标 | 阅读 |
|------|------|
| 学习所有 CLI 命令 | [CLI 参考](/zh/cli/) |
| 浏览可用技能 | [OntoStore](/zh/ontostore/) |
| 编写自定义技能 | [技能创作](/zh/authoring/) |
| 理解工作原理 | [架构](/zh/architecture/) |
| 连接到你的 AI 客户端 | [MCP 设置](/zh/mcp/) |
| 修复问题 | [故障排除](/zh/troubleshooting/) |

---

## 常见问题

### "命令未找到：ontoskills"

确保你运行了 `npx ontoskills install mcp`，并且 `~/.ontoskills/bin` 目录在你的 PATH 中，或者使用 `npx ontoskills` 作为命令。

### "ANTHROPIC_API_KEY 未设置"

```bash
export ANTHROPIC_API_KEY="你的-key"
```

将此添加到你的 shell 配置文件（`~/.bashrc`、`~/.zshrc`）以持久化。

### "未找到技能"

技能安装后默认启用。如果之前禁用了，重新启用：

```bash
ontoskills enable mareasw/greeting/hello
```

### "SHACL 验证失败"

你的技能缺少必需字段。检查：
- 至少一个 `resolvesIntent`
- 技能有清晰的结构

使用 `-v` 查看详细信息：

```bash
ontoskills compile my-skill -v
```
