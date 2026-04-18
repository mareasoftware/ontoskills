---
title: 意图发现
description: 通过 BM25 关键词搜索和可选语义嵌入查找技能
sidebar:
  order: 8
---

## 概述

意图发现使 LLM 智能体能够通过自然语言意图查找技能，无需知道确切的意图字符串。BM25 关键词搜索是默认引擎，始终可用。语义嵌入是可选的，推荐仅在大型技能目录中使用，因为关键词匹配可能遗漏相关结果。

**解决方案：** 约定 (C) + 模式摘要 (A) + 意图发现

| 组件 | 目的 |
|------|------|
| **约定** | 可预测的命名（意图用 `verb_noun`，属性用 `camelCase`）|
| **模式摘要** | MCP 资源 `ontology://schema` — 2KB 紧凑模式 |
| **search**（BM25 模式） | MCP 工具 — 通过内存 BM25 索引快速关键词匹配 |
| **search**（语义模式） | MCP 工具 — 可选语义匹配（通过预计算的嵌入） |

---

## BM25 关键词搜索（默认）

BM25 是默认的搜索引擎，始终可用。它在启动时从 Catalog 已加载的技能数据（意图、别名、描述）构建内存 BM25 索引，无需额外文件。

**工作流程：**

```
1. Catalog 加载 .ttl 文件 → 提取技能数据
2. Bm25Engine::from_catalog() → 构建内存 BM25 索引
3. search(query) → 关键词匹配 + 信任层级质量乘数
```

**响应示例：**

```json
{
  "mode": "bm25",
  "query": "create a pdf document",
  "results": [
    {
      "skill_id": "pdf",
      "qualified_id": "marea/office/pdf",
      "score": 0.87,
      "matched_by": "keyword",
      "intents": ["create pdf document", "export to pdf"],
      "aliases": ["pdf-generator"],
      "trust_tier": "official"
    }
  ]
}
```

---

## 语义搜索架构（可选）

嵌入在**编译时按技能预计算**，安装时可选下载。MCP 服务器在启动时扫描本体树中的每技能 `intents.json` 文件，仅对查询执行 ONNX 推理。

```
┌─────────────────────────────────────────────────────────────────┐
│                     编译时 (Python)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontocore compile                                                │
│       │                                                          │
│       ├──► ontoskill.ttl (现有)                                  │
│       │                                                          │
│       └──► intents.json          # 可选每技能文件               │
│            预计算的 384 维嵌入 (L2 归一化)                       │
│                                                                  │
│  ontocore export-embeddings      # 一次性：全局 ONNX 模型       │
│       │                                                          │
│       └──► model.onnx + tokenizer.json                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   安装时 (CLI)                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontoskills install <package>                                    │
│       │                                                          │
│       └──► 安装 ontoskill.ttl + package.json                    │
│                                                                  │
│  ontoskills install <package> --with-embeddings                  │
│       │                                                          │
│       ├──► 下载 model.onnx + tokenizer.json（一次，缓存）       │
│       └──► 下载每技能 intents.json                               │
│                                                                  │
│  MCP 服务器启动时自动扫描每技能 intents.json                    │
│  （无需集中合并步骤）                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      运行时 (Rust MCP)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  工具:                                                           │
│    search(query: str, top_k: int) → Vec<IntentMatch>           │
│       │                                                          │
│       ├── 1. 加载 tokenizer.json + model.onnx                   │
│       ├── 2. 安全截断查询（最多 512 字符）                      │
│       ├── 3. 分词查询 → input_ids, attention_mask              │
│       ├── 4. ONNX 推理 → 查询嵌入 (384 维)                     │
│       ├── 5. 余弦相似度 vs 预计算的 intents.json                │
│       └── 6. 自适应截断（最小 0.4，间隔 0.15）→ top_k          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 每技能嵌入（可选）

每个技能可以声明意图用于语义搜索。编译时，如果安装了 `ontocore[embeddings]`，`ontocore compile` 会在每个 `ontoskill.ttl` 旁边生成 `intents.json`：

```text
ontoskills/
└── <skill>/
    ├── ontoskill.ttl
    └── intents.json     # 可选 — 仅在使用语义搜索时需要
```

**intents.json 格式：**

```json
{
  "model": "sentence-transformers/all-MiniLM-L6-v2",
  "dimension": 384,
  "intents": [
    {
      "intent": "edit spreadsheet",
      "embedding": [0.12, -0.05, ...],
      "skills": ["calc-skill"]
    }
  ]
}
```

如果使用 `pip install ontocore[embeddings]` 编译且技能没有声明任何意图，编译将**警告**并跳过嵌入生成。BM25 搜索仍然可以基于技能描述和别名进行匹配。

---

## 使用

### 编译（必需）

```bash
ontocore compile -i skills/ -o ontoskills/
```

这会为每个技能生成 `ontoskill.ttl`。BM25 搜索默认可用。

如需同时生成语义嵌入（`intents.json`），安装嵌入依赖：

```bash
pip install ontocore[embeddings]
```

### 导出 ONNX 模型（一次性）

```bash
ontoskills export-embeddings --ontology-root ./ontoskills --output-dir ./embeddings
```

这会创建全局模型产物（`model.onnx` + `tokenizer.json`），MCP 服务器使用它们进行查询推理。由维护者一次性发布到注册表。

### 安装 + 可选嵌入

```bash
ontoskills install obra/superpowers
```

默认仅安装 `ontoskill.ttl` + `package.json`（不包含嵌入）。如需包含每技能嵌入文件用于语义搜索：

```bash
ontoskills install obra/superpowers --with-embeddings
```

CLI 会下载每技能 `intents.json` 文件到技能目录。MCP 服务器启动时自动扫描本体树发现它们 — 无需集中合并步骤。

### MCP 工具：search（BM25 默认模式）

```json
{
  "name": "search",
  "arguments": {
    "query": "create a pdf document",
    "top_k": 5
  }
}
```

返回匹配的技能及 BM25 分数（含信任层级质量乘数）：

```json
{
  "mode": "bm25",
  "query": "create a pdf document",
  "results": [
    {
      "skill_id": "pdf",
      "qualified_id": "marea/office/pdf",
      "score": 0.87,
      "matched_by": "keyword",
      "intents": ["create pdf document", "export to pdf"],
      "aliases": ["pdf-generator"],
      "trust_tier": "official"
    }
  ]
}
```

当 BM25 置信度较低且嵌入可用时，自动回退到语义搜索：

```json
{
  "mode": "semantic",
  "query": "create a pdf document",
  "matches": [
    {"intent": "create_pdf", "score": 0.92, "skills": ["pdf"]},
    {"intent": "export_document", "score": 0.78, "skills": ["pdf", "document-export"]}
  ]
}
```

### 混合评分

结果按**混合分数**排名 — 余弦相似度乘以信任层级的质量乘数。这确保了高信任技能在原始相似度略低的情况下也能排在社区技能之上。

| 信任层级 | 乘数 | 效果 |
|----------|------|------|
| `local` | 1.0 | 本地编译技能中性 |
| `official` | 1.2 | 提升官方/可信作者技能 |
| `verified` | 1.0 | 中性（基线） |
| `community` | 0.8 | 抑制社区贡献 |

示例：余弦相似度为 0.80 的已验证技能（混合分：0.80）排名高于余弦相似度为 0.90 的社区技能（混合分：0.72）。

### MCP 资源：ontology://schema

描述可用类和属性的紧凑 JSON 模式：

```json
{
  "version": "0.1.0",
  "base_uri": "https://ontoskills.sh/ontology#",
  "prefix": "oc",
  "classes": { ... },
  "properties": { ... },
  "example_queries": [ ... ]
}
```

---

## 智能体工作流

```
1. 智能体启动 → 读取 ontology://schema (2KB)
   → 知道所有属性和约定

2. 用户："我需要创建一个 PDF"
   → 智能体调用：search(query: "create a pdf", top_k: 3)
   → 返回：[{intent: "create_pdf", score: 0.92, skills: ["pdf"]}]

3. 智能体现在知道 intent = "create_pdf"
   → 智能体查询：SELECT ?skill WHERE { ?skill oc:resolvesIntent "create_pdf" }
   → 返回：oc:pdf

4. 智能体调用：get_skill_context("pdf")
   → 返回：完整的技能上下文，包含负载、依赖项和知识节点
```

---

## 性能目标

| 指标 | 目标 | 验证 |
|------|------|------|
| 模式资源大小 | < 4KB | `test_schema_size` |
| search 延迟（BM25） | < 5ms | 手动基准测试 |
| search 延迟（语义，可选） | < 50ms | 手动基准测试 |
| ONNX 模型大小 | ~90MB | 检查文件大小 |
| 内存占用（无嵌入） | < 50MB | 使用 `top` 监控 |

---

## 文件结构

```text
~/.ontoskills/
├── ontologies/
│   ├── system/
│   │   ├── index.enabled.ttl
│   │   └── embeddings/
│   │       ├── model.onnx           # 全局 ONNX 模型 (~90MB)
│   │       └── tokenizer.json       # HuggingFace 分词器
│   └── author/
│       └── <author>/<pkg>/<skill>/
│           ├── ontoskill.ttl
│           └── intents.json         # 每技能嵌入（可选，使用 --with-embeddings）
```

**源代码：**

```text
core/
├── src/embeddings/
│   └── exporter.py              # 每技能导出 + ONNX 模型导出

mcp/
├── src/
│   ├── embeddings.rs            # Rust 嵌入引擎（ONNX 推理 + 每技能扫描）
│   ├── bm25_engine.rs           # BM25 关键词搜索（始终可用）
│   ├── catalog.rs               # 带信任层级质量乘数的目录
│   ├── schema.rs                # 模式资源
│   └── main.rs                  # MCP 工具处理器
```

---

## 依赖

### Python (core/) — 编译

```toml
# pyproject.toml — 默认依赖（无需 sentence-transformers）

# pyproject.toml — 可选嵌入依赖（用于语义搜索）
# pip install ontocore[embeddings]
sentence-transformers>=2.2.0
optimum>=1.12.0
onnx>=1.15.0
onnxruntime>=1.16.0
```

### Rust (mcp/)

```toml
# 必需 — BM25 关键词搜索
bm25 = "1"
anyhow = "1.0"

# 可选 — 语义搜索（--features embeddings）
ort = { version = "2.0.0-rc.12", features = ["load-dynamic"], optional = true }
tokenizers = { version = "0.19", optional = true }
ndarray = { version = "0.17", optional = true }
```

### 运行时要求

BM25 搜索始终可用，无需额外运行时依赖。

ONNX Runtime 共享库仅在语义搜索时需要。MCP 服务器使用带 `load-dynamic` 的 `ort`，它会在运行时查找 `libonnxruntime.so`。如需要，设置 `ORT_DYLIB_PATH`：

```bash
export ORT_DYLIB_PATH=/path/to/libonnxruntime.so
```

---

## 测试

### Python 测试

```bash
cd core && python -m pytest tests/test_embeddings.py -v
```

### Rust 测试

```bash
cd mcp && cargo test
```

### 端到端测试

```bash
bash mcp/tests/e2e_search.sh
```

---

## 相关

- [OntoCore 编译器](/zh/docs/ontocore/) — 编译参考
- [MCP 运行时](/zh/docs/mcp/) — 工具参考
- [CLI 参考](/zh/docs/cli/) — 安装和合并命令
