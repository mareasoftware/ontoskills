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

OntoMCP 暴露 **1 个统一工具** `ontoskill`，集技能发现、上下文检索和知识查询于一体。

> **稀疏序列化**：响应中省略空值和空数组。仅包含有实际值的字段。这使响应保持紧凑，避免用空数据填充上下文窗口。

### `ontoskill`

按名称或自然语言查询查找技能，然后加载其完整上下文 — 全在一次调用中。

```json
{
  "q": "create a pdf document",
  "top_k": 5
}
```

| 参数 | 类型 | 描述 |
|------|------|------|
| `q` | string | **必需。** 技能 ID（如 `pdf`）或自然语言查询（如 `create a pdf document`） |
| `top_k` | integer | 查询不匹配技能 ID 时的最大搜索结果（默认 5） |

**当 `q` 匹配已知技能 ID 时** → 返回完整技能上下文：负载、依赖、知识节点、代码示例和参考表格。

**当 `q` 不匹配技能 ID 时** → 回退到搜索模式，使用 **BM25** 关键词排序（始终可用）。对于使用 `--features embeddings` 编译的大规模技能目录，当 BM25 置信度低时会使用语义回退：

```json
{
  "mode": "bm25",
  "query": "create a pdf document",
  "results": [
    {
      "skill_id": "pdf",
      "qualified_id": "obra/superpowers/test-driven-development",
      "trust_tier": "core",
      "score": 0.92,
      "matched_by": "intent",
      "intents": ["create_pdf", "export_to_pdf"]
    }
  ]
}
```

### 代理工作流

`ontoskill` 工具取代了旧的多步骤工作流：

```
之前（4 个工具）：
  search → get_skill_context → evaluate_execution_plan → query_epistemic_rules

之后（1 个工具）：
  ontoskill(q) → 返回上下文或搜索结果
```

1. 代理收到用户请求
2. 调用 `ontoskill(q: 用户请求)` — 如果查询是技能 ID，立即返回完整上下文；否则返回 BM25 排序的搜索结果
3. 代理一次获得所有需要的信息 — 负载、依赖、知识节点、代码示例

不再需要在搜索和上下文检索之间往返。无需单独的工具用于计划验证或知识查询 — 所有知识都嵌入在技能上下文中。

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
