---
title: MCP 运行时
description: OntoMCP 运行时指南和工具参考
sidebar:
  order: 6
---

`OntoMCP` 是 OntoSkills 的运行时层。它从托管本地主目录加载已编译的本体，并通过 `stdio` 上的模型上下文协议暴露它们。

---

## 安装

```bash
npx ontoskills install mcp
npx ontoskills install mcp --claude
npx ontoskills install mcp --cursor --project
```

这将在以下位置安装运行时二进制文件：

```text
~/.ontoskills/bin/ontomcp
```

有关一条命令客户端引导，请参见 [MCP 引导](/zh/docs/mcp-bootstrap/)。

---

## OntoMCP 加载什么

**主要来源：**

```text
~/.ontoskills/ontologies/system/index.enabled.ttl
```

**回退（按顺序）：**

1. `~/.ontoskills/ontologies/index.ttl`
2. 当前目录的 `index.ttl`
3. `*/ontoskill.ttl` 模式

**覆盖本体根目录：**

```bash
# 环境变量
ONTOMCP_ONTOLOGY_ROOT=~/.ontoskills/ontologies

# 或命令行标志
~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

---

## 工具参考

OntoMCP 暴露 **4 个工具** 用于技能发现、上下文检索和推理。

> **稀疏序列化**：响应中省略空值和空数组。仅包含有实际值的字段。这使响应保持紧凑，避免用空数据填充上下文窗口。

### `search`

通过语义查询、别名或结构化过滤器搜索技能。工具根据提供的参数进行分派：

- 提供了 **`query`** → BM25 关键词搜索（可选语义回退，用于大规模技能目录）
- 提供了 **`alias`** → 别名解析
- 否则 → 结构化技能搜索（带过滤器）

#### 结构化技能搜索

```json
{
  "intent": "create_pdf",
  "requires_state": "oc:DocumentCreated",
  "yields_state": "oc:PdfGenerated",
  "skill_type": "executable",
  "category": "document",
  "is_user_invocable": true,
  "limit": 25
}
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `intent` | string | 按已解决的意图过滤 |
| `requires_state` | string | 按所需状态过滤（URI 或 `oc:StateName`）|
| `yields_state` | string | 按产出状态过滤（URI 或 `oc:StateName`）|
| `skill_type` | string | `executable` 或 `declarative` |
| `category` | string | 按技能类别过滤（如 `automation`、`document`、`marketing`）|
| `is_user_invocable` | boolean | 按技能是否可由用户直接调用过滤 |
| `limit` | integer | 最大结果数（1-100，默认 25）|

**示例响应：**

```json
{
  "skills": [
    {
      "id": "pdf",
      "qualified_id": "obra/superpowers/test-driven-development",
      "package_id": "superpowers",
      "trust_tier": "core",
      "nature": "创建 PDF 文档的技能",
      "intents": ["create_pdf", "export_pdf"],
      "requires_state": ["oc:ContentReady"],
      "yields_state": ["oc:PdfGenerated"]
    }
  ],
  "total": 1
}
```

#### 意图搜索

当提供 `query` 参数时，搜索工具使用 **BM25** 作为默认搜索引擎。BM25 是一种内存关键词排序算法，直接在 Catalog 数据上运行 — 始终可用，无需额外依赖。

```json
{
  "query": "创建 pdf 文档",
  "top_k": 5
}
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `query` | string | **必需。** 自然语言查询 |
| `top_k` | integer | 返回结果数（默认 5）|

**BM25 响应示例**（默认模式）：

```json
{
  "query": "创建 pdf 文档",
  "mode": "bm25",
  "results": [
    {
      "skill_id": "pdf",
      "qualified_id": "obra/superpowers/test-driven-development",
      "package_id": "superpowers",
      "trust_tier": "core",
      "score": 0.92,
      "matched_by": "intent",
      "intents": ["create_pdf", "export_pdf"],
      "aliases": ["pdf"]
    }
  ]
}
```

**语义回退**（可选，用于大规模技能目录）：

语义搜索是大规模技能目录的可选增强功能，仅靠关键词匹配可能无法捕获细微的查询意图。需使用 `--features embeddings` 编译并提供嵌入文件（`ontoskills export-embeddings`）。

当 BM25 置信度低于回退阈值（0.4）且嵌入可用时，服务器自动回退到语义搜索：

```json
{
  "query": "生成带图表的报告并导出",
  "mode": "semantic",
  "results": [
    {
      "skill_id": "pdf",
      "qualified_id": "obra/superpowers/test-driven-development",
      "package_id": "superpowers",
      "trust_tier": "core",
      "score": 0.88,
      "matched_by": "embedding_similarity",
      "intents": ["create_pdf", "export_pdf"],
      "aliases": ["pdf"]
    }
  ]
}
```

语义结果使用**混合评分**（余弦相似度 x 信任层级质量乘数），使高信任技能在原始相似度略低的情况下也能排在社区贡献之上。

#### 别名解析

```json
{
  "alias": "pdf"
}
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `alias` | string | **必需。** 要解析的别名（不区分大小写）|

**示例响应：**

```json
{
  "alias": "pdf",
  "skills": [
    {
      "id": "pdf",
      "qualified_id": "obra/superpowers/test-driven-development",
      "nature": "创建 PDF 文档的技能",
      "intents": ["create_pdf", "export_pdf"]
    }
  ]
}
```

---

### `get_skill_context`

获取技能的完整执行上下文，包括需求、转换、负载、依赖和知识节点。

```json
{
  "skill_id": "pdf",
  "include_inherited_knowledge": true
}
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `skill_id` | string | **必需。** 短 id（`pdf`）或限定 id（`obra/superpowers/test-driven-development`）|
| `include_inherited_knowledge` | boolean | 包含扩展技能的知识（默认 true）|

**示例响应：**

```json
{
  "id": "pdf",
  "qualified_id": "obra/superpowers/test-driven-development",
  "nature": "从内容创建 PDF 文档的技能",
  "genus": "DocumentGenerator",
  "differentia": "输出 PDF 格式",
  "intents": ["create_pdf", "export_pdf"],
  "requires_state": ["oc:ContentReady"],
  "yields_state": ["oc:PdfGenerated"],
  "handles_failure": ["oc:PdfGenerationFailed"],
  "requirements": [
    {"type": "Tool", "value": "wkhtmltopdf", "optional": false}
  ],
  "depends_on": ["content-processor"],
  "extends": ["document-base"],
  "execution_payload": {
    "executor": "shell",
    "code": "wkhtmltopdf $INPUT $OUTPUT.pdf",
    "timeout": 30000
  },
  "knowledge_nodes": [
    {
      "node_type": "PreFlightCheck",
      "directive_content": "验证 wkhtmltopdf 已安装",
      "applies_to_context": "PDF 生成之前",
      "has_rationale": "避免运行时失败",
      "severity_level": "HIGH"
    }
  ]
}
```

> `payload` 部分仅在技能具有可执行负载（`available: true`）时出现。大多数声明式技能完全省略此部分。

---

### 代理工作流

4 个工具构成完整的工作流，替代读取原始 SKILL.md 文件：

```
search → get_skill_context → evaluate_execution_plan → query_epistemic_rules
发现       理解需求             计划验证                 合规检查
```

1. **`search`** — 通过意图、关键词或别名找到正确的技能
2. **`get_skill_context`** — 获取完整上下文，包括知识节点、需求、依赖和执行负载
3. **`evaluate_execution_plan`** — 验证计划是否可行（状态、依赖）
4. **`query_epistemic_rules`** — 在执行期间检查特定规则和约束

每个工具仅加载所需的数据。代理从不读取完整的 SKILL.md — 它通过 SPARQL 查询本体存储，并在亚毫秒时间内获得确定性的结构化结果。

---

### `evaluate_execution_plan`

评估意图或技能是否可以从当前状态执行。返回完整的执行计划和警告。

```json
{
  "intent": "create_pdf",
  "current_states": ["oc:ContentReady", "oc:UserAuthenticated"],
  "max_depth": 10
}
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `intent` | string | 目标意图（使用 `intent` 或 `skill_id`）|
| `skill_id` | string | 目标技能（使用 `intent` 或 `skill_id`）|
| `current_states` | array | 当前状态 URI 或紧凑值 |
| `max_depth` | integer | 最大计划深度（1-10，默认 10）|

**示例响应：**

```json
{
  "executable": true,
  "plan": [
    {
      "skill_id": "content-processor",
      "step": 1,
      "satisfies": ["oc:ContentReady"]
    },
    {
      "skill_id": "pdf",
      "step": 2,
      "requires": ["oc:ContentReady"],
      "yields": ["oc:PdfGenerated"]
    }
  ],
  "missing_states": [],
  "warnings": [
    "技能 'pdf' 有可选依赖 'fonts-installer' 不在计划中"
  ]
}
```

**当 `executable: false`：**

```json
{
  "executable": false,
  "plan": [],
  "missing_states": ["oc:ApiKeyConfigured"],
  "warnings": ["没有 API key 配置无法继续"]
}
```

---

### `query_epistemic_rules`

使用引导过滤器查询规范化的知识节点。

```json
{
  "skill_id": "pdf",
  "kind": "AntiPattern",
  "dimension": "SecurityGuardrail",
  "severity_level": "CRITICAL",
  "applies_to_context": "文件处理",
  "include_inherited": true,
  "limit": 25
}
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `skill_id` | string | 按技能过滤 |
| `kind` | string | 节点类型（Heuristic、AntiPattern、PreFlightCheck 等）|
| `dimension` | string | 认识维度（NormativeRule、ResilienceTactic 等）|
| `severity_level` | string | CRITICAL、HIGH、MEDIUM、LOW |
| `applies_to_context` | string | 上下文过滤器 |
| `include_inherited` | boolean | 包含扩展技能（默认 true）|
| `limit` | integer | 最大结果数（1-100，默认 25）|

**示例响应：**

```json
{
  "rules": [
    {
      "skill_id": "pdf",
      "node_type": "AntiPattern",
      "dimension": "SecurityGuardrail",
      "directive_content": "不要接受来自不可信输入的文件路径",
      "applies_to_context": "处理用户提供的文件名时",
      "has_rationale": "防止路径遍历攻击",
      "severity_level": "CRITICAL"
    }
  ],
  "total": 1
}
```

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                        AI 客户端                              │
│                   (Claude Code, Codex)                       │
└─────────────────────────┬───────────────────────────────────┘
                          │ MCP 协议 (stdio)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       OntoMCP                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   目录       │  │  BM25 引擎  │  │   SPARQL 引擎       │  │
│  │   (Rust)    │  │  (内存)     │  │   (Oxigraph)        │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         └─────────┐      │                    │             │
│                   ▼      │                    │             │
│          ┌─────────────┐ │                    │             │
│          │   嵌入      │ │                    │             │
│          │ (ONNX/Intents│ │                   │             │
│          │  可选，      │ │                    │             │
│          │ 大规模目录)  │ │                    │             │
│          └─────────────┘ │                    │             │
└─────────────────────────┼────────────────────┼─────────────┘
                          │                    │
                          ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    ontologies/                               │
│  ├── index.ttl                                              │
│  ├── system/                                                │
│  │   ├── index.enabled.ttl                                  │
│  │   └── embeddings/                                        │
│  └── */ontoskill.ttl                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 本地开发

从仓库根目录：

```bash
# 使用本地本体运行
cargo run --manifest-path mcp/Cargo.toml -- --ontology-root ./ontoskills

# 运行测试
cargo test --manifest-path mcp/Cargo.toml

# 构建发布二进制
cargo build --release --manifest-path mcp/Cargo.toml
```

---

## 客户端指南

- [Claude Code](./claude-code-mcp.md) — Claude Code CLI 设置
- [Codex](./codex-mcp.md) — Codex 工作流设置

---

## 故障排除

### "Ontology root not found"

确保已编译的 `.ttl` 文件存在：

```bash
ls ~/.ontoskills/ontologies/
# 应该显示：index.ttl、system/ 等

ls ~/.ontoskills/ontologies/system/
# 应该显示：index.enabled.ttl、embeddings/ 等
```

如果缺失，先编译技能：

```bash
ontoskills compile
```

### "Embeddings not available"

搜索始终使用 **BM25**（关键词搜索）。语义搜索是可选的，仅在使用 `--features embeddings` 编译且嵌入文件存在时可用。

如果需要语义搜索且 ONNX Runtime 共享库缺失，设置 `ORT_DYLIB_PATH`：

```bash
export ORT_DYLIB_PATH=/path/to/libonnxruntime.so
```

生成嵌入文件：

```bash
ontoskills export-embeddings
```

### "Server not initialized"

MCP 客户端必须在调用工具之前发送 `initialize`。合规客户端会自动处理。

### 连接静默断开

检查日志中的错误：

```bash
# 手动运行以查看 stderr
~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

---

## 环境变量

| 变量 | 描述 | 默认值 |
|------|------|--------|
| `ONTOMCP_ONTOLOGY_ROOT` | 本体目录 | `~/.ontoskills/ontologies` |
| `ORT_DYLIB_PATH` | ONNX Runtime 共享库路径（可选 — 仅用于语义搜索/大规模技能目录） | 自动检测 |
