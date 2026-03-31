---
title: OntoCore 编译器
description: 安装和使用 OntoCore 处理自定义源技能
sidebar:
  order: 5
---

`ontocore` 是可选的编译器，将 `SKILL.md` 源文件转换为已验证的 OWL 2 本体模块。

大多数用户不需要它 — 只有在以下情况才需要 OntoCore：
- 从源文件编写自定义技能
- 导入和编译原始技能仓库
- 本地开发和测试技能

---

## 安装

```bash
ontoskills install core
```

这将在以下位置创建托管的编译器运行时：

```text
~/.ontoskills/core/
```

系统要求：
- **Python** 3.10+
- **Anthropic API key**（设置 `ANTHROPIC_API_KEY` 环境变量）

---

## 编译流水线

```
SKILL.md → [提取] → [安全检查] → [序列化] → [SHACL] → ontoskill.ttl
```

| 阶段 | 发生什么 |
|------|----------|
| **提取** | Claude 读取 SKILL.md 并提取结构化知识 |
| **安全检查** | 正则表达式 + LLM 审查恶意内容 |
| **序列化** | Pydantic 模型 → RDF 三元组 |
| **验证** | SHACL 形状检查逻辑有效性 |
| **写入** | 带备份的原子写入 |

如果任何阶段失败，技能**不会被写入**。SHACL 守门员强制执行宪法规则。

---

## 文件处理规则

OntoCore 根据文件类型进行处理：

| 规则 | 输入 | 输出 | 处理方式 |
|------|------|------|----------|
| **A** | `SKILL.md` | `ontoskill.ttl` | LLM 编译 |
| **B** | `*.md`（辅助文件）| `*.ttl` | 作为子技能进行 LLM 编译 |
| **C** | 其他文件 | 直接复制 | 资产（图片等）|

### 目录镜像

输出结构镜像输入：

```text
skills/                          →    ontoskills/
├── office/                      →    ├── office/
│   ├── SKILL.md                 →    │   ├── ontoskill.ttl
│   ├── planning.md              →    │   ├── planning.ttl
│   └── review.md                →    │   └── review.ttl
└── pdf/                         →    └── pdf/
    ├── SKILL.md                 →        ├── ontoskill.ttl
    └── diagram.png              →        └── diagram.png
```

### 子技能

技能目录中的辅助 `.md` 文件成为**子技能**：

- 它们自动 `extend` 父技能
- 在提取过程中继承父级上下文
- 获得限定 ID：`package/parent/child`

---

## CLI 命令

### 初始化核心本体

```bash
ontoskills init-core
```

创建 `core.ttl`，包含基础 TBox 本体（类、属性、状态定义）。

### 编译技能

```bash
# 编译 skills/ 中的所有技能
ontoskills compile

# 编译特定技能
ontoskills compile office

# 带选项编译
ontoskills compile --force          # 跳过缓存
ontoskills compile --dry-run        # 预览但不保存
ontoskills compile --skip-security  # 跳过 LLM 安全审查
ontoskills compile -v               # 详细日志
```

| 选项 | 描述 |
|------|------|
| `-i, --input` | 输入目录（默认：`skills/`）|
| `-o, --output` | 输出目录（默认：`ontoskills/`）|
| `--dry-run` | 预览但不保存 |
| `--skip-security` | 跳过 LLM 安全审查（正则检查仍运行）|
| `-f, --force` | 强制重新编译（跳过缓存）|
| `-y, --yes` | 跳过确认提示 |
| `-v, --verbose` | 启用调试日志 |
| `-q, --quiet` | 抑制进度输出 |

### 查询图谱

```bash
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
```

对编译后的本体运行 SPARQL 查询。

### 检查质量

```bash
# 列出所有已编译的技能
ontoskills list-skills

# 运行安全审计
ontoskills security-audit
```

---

## 输出结构

编译后：

```text
ontoskills/
├── core.ttl      # 核心 TBox（共享类/属性）
├── index.ttl                # 带 owl:imports 的清单
├── system/
│   └── index.enabled.ttl    # 为 MCP 启用的技能
└── <skill-path>/
    └── ontoskill.ttl        # 单个技能模块
```

### 核心本体

核心本体（`core.ttl`）是所有技能模块通过 `owl:imports` 引用的共享 TBox。它：

- **在线服务**于 `https://ontoskills.sh/ontology/core.ttl`
- **由 `ontoskills install mcp` 自动下载**到 `~/.ontoskills/ontologies/core.ttl`
- 在开发时由 `ontoskills init-core` 或 `ontoskills compile` **本地重新生成**

已编译的技能模块通过 `owl:imports <https://ontoskills.sh/ontology/core.ttl>` 引用核心本体。MCP 将此解析为本体根目录中的本地副本。

`core.ttl` 定义：

- `oc:Skill`、`oc:ExecutableSkill`、`oc:DeclarativeSkill`
- 属性：`dependsOn`、`extends`、`contradicts`、`resolvesIntent` 等
- 知识节点类：`oc:Heuristic`、`oc:AntiPattern` 等
- 前置条件/后置条件的状态类

### 索引

`index.ttl` 是一个清单，它：
- 列出所有已编译的技能
- 通过 `owl:imports <https://ontoskills.sh/ontology/core.ttl>` 引用核心本体
- 被 OntoMCP 用于发现可用技能

---

## 缓存

OntoCore 是**缓存感知**的：

- 每个技能都有存储在 `oc:contentHash` 中的内容哈希
- 未更改的技能在重新编译时会被跳过
- 使用 `--force` 跳过缓存

---

## 安全流水线

编译器运行深度防御安全检查：

1. **Unicode 规范化** — NFC 规范化，零宽字符移除
2. **正则模式** — 检测提示注入、命令注入、路径遍历、凭据暴露
3. **LLM 审查** — Claude 审查标记内容的细微威胁

检测到的威胁类型：
- 提示注入（`ignore instructions`、`system:`、`you are now`）
- 命令注入（`; rm`、`| bash`、命令替换）
- 数据泄露（带凭据的 `curl -d`、`wget --data`）
- 路径遍历（`../../../`、`/etc/passwd`）
- 凭据暴露（硬编码的 `api_key=`、`password=`）

使用 `--skip-security` 跳过 LLM 审查（正则检查仍运行）。

---

## SHACL 验证

每个技能在写入前必须通过 SHACL 验证。宪法形状定义在 `core/specs/ontoskills.shacl.ttl` 中，跨 6 个节点形状强制执行约束。

**必需字段（阻止）：**

| 约束 | 规则 |
|------|------|
| `resolvesIntent` | 必需（至少 1 个）|
| `generatedBy` | 必需（恰好 1 个）|
| `requiresState` | 必须是有效的 IRI |
| `yieldsState` | 必须是有效的 IRI |
| `handlesFailure` | 必须是有效的 IRI |

**类型特定规则：**
- `ExecutableSkill` 必须恰好有 1 个 `hasPayload`（带 `code` 或 `executionPath`）
- `DeclarativeSkill` 不能有 `hasPayload`

如果验证失败，技能**不会被写入**并显示错误。

参见[技能创作](/zh/authoring/)获取通过验证的实用指南。

---

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `SkillNotFoundError` | 技能目录不存在 | 检查路径拼写 |
| `OrphanSubSkillsError` | `.md` 文件没有父级 `SKILL.md` | 在目录中创建 SKILL.md |
| `SecurityError` | 内容被安全流水线阻止 | 审查内容，如果安全使用 `--skip-security` |
| `OntologyValidationError` | SHACL 验证失败 | 修复报告的约束违规 |
| `ExtractionError` | LLM 提取失败 | 检查 ANTHROPIC_API_KEY，重试 |

---

## 环境变量

| 变量 | 描述 | 默认值 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API key | 必需 |
| `ANTHROPIC_BASE_URL` | API 基础 URL | `https://api.anthropic.com` |
| `SECURITY_MODEL` | 安全审查模型 | `claude-opus-4-6` |

---

## 下一步

- [快速开始](/zh/getting-started/) — 安装和第一步
- [架构](/zh/architecture/) — 系统如何工作
- [知识提取](/zh/knowledge-extraction/) — 理解知识节点
- [技能创作](/zh/authoring/) — 编写自己的技能
