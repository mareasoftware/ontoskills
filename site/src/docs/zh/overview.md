---
title: OntoSkills 是什么？
description: OntoSkills 架构、商店和运行时概述
---

**OntoSkills** 是一个面向确定性智能体的神经符号技能平台。它将 `SKILL.md` 源文件转换为经过验证的 OWL 2 本体，通过本地 MCP 运行时提供已编译的技能，并通过 OntoStore 分发已发布的包。

---

## 为什么选择 OntoSkills？

### 确定性问题

LLM 以概率方式读取技能。同样的查询，不同的结果。长技能文件对大型模型来说是昂贵的，对小型模型来说是混乱的。

- **非确定性读取** — LLM 每次解释文本的方式不同
- **Token 浪费** — 大型模型在解析长文档时消耗大量 token
- **小型模型限制** — 复杂技能对边缘模型来说不可读
- **无可验证的结构** — 技能之间的关系是隐式的

### 本体论解决方案

OntoSkills 使用 **描述逻辑 (OWL 2)** 将技能转换为形式化本体：

- **确定性查询** — SPARQL 每次都返回精确答案
- **蕴含推理** — 推断依赖关系、冲突、能力
- **民主化智能** — 小型模型查询大型模型读取的内容
- **形式语义** — 技能关系无歧义

### 性能比较

| 操作 | 读取文件 | 本体查询 |
|------|----------|----------|
| 按意图查找技能 | O(n) 文本扫描 | O(1) 索引查找 |
| 检查依赖关系 | 解析每个文件 | 沿 `dependsOn` 边遍历 |
| 检测冲突 | 比较所有配对 | 单次 SPARQL 查询 |

**对于 100 个技能：** ~500KB 文本扫描 → ~1KB 查询

---

## 工作原理

<img src="/architecture.webp" alt="OntoCore Architecture" style="max-height: 500px; width: auto; max-width: 100%; display: block; margin: 0 auto;" />

### 编译流水线

1. **提取** — Claude 读取 SKILL.md 并提取结构化知识
2. **验证** — 安全管道检查恶意内容
3. **序列化** — Pydantic 模型 → RDF 三元组
4. **校验** — SHACL 守门员确保逻辑有效性
5. **写入** — 编译后的 `.ttl` 文件到 `ontoskills/`

### 运行时

- **OntoMCP** 从 `ontoskills/` 加载已编译的 `.ttl` 文件
- 智能体通过 MCP 协议使用 SPARQL 查询
- OntoStore 默认内置
- 第三方商店可以通过 `store add-source` 显式添加

---

## 核心能力

| 能力 | 描述 |
|------|------|
| **LLM 提取** | Claude 从 SKILL.md 文件中提取结构化知识 |
| **知识架构** | 遵循 "A 是一个做了 C 的 B" 定义模式（属 + 种差）|
| **知识节点** | 10 维认知分类法（启发式、反模式、预检等）|
| **OWL 2 序列化** | 输出有效的 RDF/Turtle 格式 OWL 2 本体 |
| **SHACL 验证** | 宪法守门员在写入前确保逻辑有效性 |
| **状态机** | 技能可以定义前置条件、后置条件和失败处理器 |
| **安全管道** | 深度防御：正则表达式模式 + LLM 审查恶意内容 |
| **静态检查** | 检测死状态、循环依赖、重复意图 |
| **漂移检测** | 本体版本之间的语义差异 |

---

## 编译内容

每个技能都提取以下内容：

- **身份**：`nature`、`genus`、`differentia`（知识架构）
- **意图**：此技能解决的用户意图
- **需求**：依赖项（EnvVar、Tool、Hardware、API、Knowledge）
- **知识节点**：认知知识（每个技能 8-12 个节点）
- **执行负载**：可选的要执行的代码
- **状态转换**：`requiresState`、`yieldsState`、`handlesFailure`
- **溯源**：`generatedBy` 证明（使用的 LLM 模型）

---

## 组件

| 组件 | 语言 | 状态 | 描述 |
|------|------|------|------|
| **ontoskills** | CLI | ✅ 就绪 | 面向用户的安装器和管理器 |
| **OntoCore** | Python | ✅ 就绪 | `SKILL.md` 源文件的技能编译器 |
| **OntoMCP** | Rust | ✅ 就绪 | 具有 5 个语义工具的 MCP 服务器（含 search_intents） |
| **OntoStore** | GitHub 仓库 | ✅ 就绪 | 官方编译技能商店 |
| `skills/` | Markdown | 输入 | 人工编写的源技能 |
| `ontoskills/` | Turtle | 输出 | 编译后的本体产物 |
| `specs/` | Turtle | 宪法 | 用于验证的 SHACL 形状 |

---

## 用例

| 用例 | OntoSkills 如何帮助 |
|------|---------------------|
| **企业 AI 智能体** | 通过 SPARQL 查询进行确定性技能选择 |
| **边缘部署** | 较小的模型查询大型技能生态系统 |
| **多智能体系统** | 共享本体作为协调层 |
| **合规与审计** | 每个技能都带有证明和内容哈希 |
| **技能市场** | OntoStore 和第三方商店实现即插即用分发 |

---

## 下一步

- **[快速开始](/zh/getting-started/)** — 安装并编译你的第一个技能
- **[CLI](/zh/cli/)** — 了解托管命令界面
- **[OntoStore](/zh/ontostore/)** — 浏览可安装的商店技能
- **[OntoCore](/zh/ontocore/)** — 安装编译器以使用自定义技能
- **[商店](/zh/store/)** — 了解官方和第三方商店如何工作
- **[架构](/zh/architecture/)** — 深入了解系统设计
- **[知识提取](/zh/knowledge-extraction/)** — 理解知识节点
- **[故障排除](/zh/troubleshooting/)** — 修复常见的安装和运行时问题
- **[路线图](/zh/roadmap/)** — 查看即将推出的内容

---

## 链接

- [GitHub 仓库](https://github.com/mareasw/ontoskills)
- [OntoStore](https://github.com/mareasw/ontostore)
- [理念](https://github.com/mareasw/ontoskills/blob/main/PHILOSOPHY.md)
