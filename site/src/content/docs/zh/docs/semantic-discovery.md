---
title: 语义意图发现
description: 通过自然语言意图和预计算的每技能嵌入查找技能
sidebar:
  order: 8
---

## 概述

语义意图发现使 LLM 智能体能够通过自然语言意图查找技能，无需知道确切的意图字符串。这打破了 O(1) 查询承诺 — 智能体现在可以发现如何查询本体。

**解决方案：** 约定 (C) + 模式摘要 (A) + 语义发现

| 组件 | 目的 |
|------|------|
| **约定** | 可预测的命名（意图用 `verb_noun`，属性用 `camelCase`）|
| **模式摘要** | MCP 资源 `ontology://schema` — 2KB 紧凑模式 |
| **search**（语义模式） | MCP 工具 — 通过预计算的嵌入进行语义匹配 |

---

## 架构

嵌入在**编译时按技能预计算**，并在安装时合并。MCP 服务器仅对查询执行 ONNX 推理，将其与预加载的意图向量进行匹配。

```
┌─────────────────────────────────────────────────────────────────┐
│                     编译时 (Python)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontocore compile                                                │
│       │                                                          │
│       ├──► ontoskill.ttl (现有)                                  │
│       │                                                          │
│       └──► intents.json          # 每技能必需文件               │
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
│                   安装时 (JS CLI)                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontoskills install <package>                                    │
│       │                                                          │
│       ├──► 下载 model.onnx + tokenizer.json（一次，缓存）       │
│       ├──► 下载每技能 intents.json                               │
│       └──► mergeEmbeddings() → system/embeddings/intents.json   │
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

## 每技能嵌入

每个技能**必须**声明至少一个意图。编译时，`ontocore compile` 会在每个 `ontoskill.ttl` 旁边生成 `intents.json`：

```text
ontoskills/
└── <skill>/
    ├── ontoskill.ttl
    └── intents.json     # 必需 — 没有意图则编译失败
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

如果技能没有声明任何意图，编译将**失败**并显示：

```text
Skill 'my-skill' has no declared intents. Every skill must declare at
least one intent for semantic search.
```

---

## 使用

### 编译（必需）

```bash
ontocore compile -i skills/ -o ontoskills/
```

这会为每个技能生成 `ontoskill.ttl` 和 `intents.json`。需要 `sentence-transformers`：

```bash
pip install sentence-transformers
```

### 导出 ONNX 模型（一次性）

```bash
ontoskills export-embeddings --ontology-root ./ontoskills --output-dir ./embeddings
```

这会创建全局模型产物（`model.onnx` + `tokenizer.json`），MCP 服务器使用它们进行查询推理。由维护者一次性发布到注册表。

### 安装 + 合并 (JS CLI)

```bash
ontoskills install mareasw/office/xlsx
```

CLI 会：
1. 下载 `model.onnx` + `tokenizer.json`（一次，缓存）
2. 下载每技能 `intents.json` 文件
3. 将所有已安装的意图合并到 `system/embeddings/intents.json`

使用 `--no-embeddings` 跳过嵌入：

```bash
ontoskills install mareasw/office/xlsx --no-embeddings
```

### MCP 工具：search（语义模式）

```json
{
  "name": "search",
  "arguments": {
    "query": "create a pdf document",
    "top_k": 5
  }
}
```

返回带混合分数（余弦相似度 × 信任层级质量乘数）的匹配意图：

```json
{
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
| `local` | 1.2 | 提升本地编译技能 |
| `trusted` | 1.2 | 提升官方/可信供应商技能 |
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
| search 延迟（语义） | < 50ms | 手动基准测试 |
| ONNX 模型大小 | ~90MB | 检查文件大小 |
| 内存占用 | < 200MB | 使用 `top` 监控 |

---

## 文件结构

```text
~/.ontoskills/
├── ontologies/
│   ├── system/
│   │   ├── index.enabled.ttl
│   │   └── embeddings/
│   │       ├── model.onnx           # 全局 ONNX 模型 (~90MB)
│   │       ├── tokenizer.json       # HuggingFace 分词器
│   │       └── intents.json         # 从所有已安装技能合并
│   └── vendor/
│       └── <vendor>/<pkg>/<skill>/
│           ├── ontoskill.ttl
│           └── intents.json         # 每技能预计算的嵌入
```

**源代码：**

```text
core/
├── src/embeddings/
│   └── exporter.py              # 每技能导出 + ONNX 模型导出

mcp/
├── src/
│   ├── embeddings.rs            # Rust 嵌入引擎（ONNX 推理）
│   ├── schema.rs                # 模式资源
│   └── main.rs                  # MCP 工具处理器

cli/
├── lib/
│   └── registry.js              # 安装时的 mergeEmbeddings()
```

---

## 依赖

### Python (core/) — 编译必需

```toml
# pyproject.toml — 必需依赖
sentence-transformers>=2.2.0

# pyproject.toml — 可选（仅用于 export-embeddings）
optimum>=1.12.0
onnx>=1.15.0
onnxruntime>=1.16.0
```

### Rust (mcp/)

```toml
ort = { version = "2.0.0-rc.12", features = ["load-dynamic"] }
tokenizers = "0.19"
ndarray = "0.17"
anyhow = "1.0"
```

### 运行时要求

ONNX Runtime 共享库必须可用。MCP 服务器使用带 `load-dynamic` 的 `ort`，它会在运行时查找 `libonnxruntime.so`。如需要，设置 `ORT_DYLIB_PATH`：

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
