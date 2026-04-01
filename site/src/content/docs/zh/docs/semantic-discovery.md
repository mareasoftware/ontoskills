---
title: 语义意图发现
description: 通过自然语言意图查找技能，无需知道确切的意图字符串
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
| **search_intents** | MCP 工具 — 通过嵌入进行语义匹配 |

---

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     编译时 (Python)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontoskills export-embeddings                                   │
│       │                                                          │
│       ├──► ontoskill.ttl (现有)                                 │
│       │                                                          │
│       └──► ontoskills/system/embeddings/                        │
│                ├── model.onnx          # 导出的模型 (~45MB)     │
│                ├── tokenizer.json      # HuggingFace 分词器     │
│                └── intents.json         # 预计算的嵌入          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      运行时 (Rust MCP)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  资源:                                                           │
│    ontology://schema → JSON 模式（类、属性）                     │
│                                                                  │
│  工具:                                                           │
│    search_intents(query: str, top_k: int) → Vec<IntentMatch>   │
│       │                                                          │
│       ├── 1. 加载 tokenizer.json                                │
│       ├── 2. 分词查询 → input_ids, attention_mask              │
│       ├── 3. ONNX 推理 → 嵌入 (384 维)                          │
│       ├── 4. 余弦相似度 vs intents.json                         │
│       └── 5. 返回 top_k 匹配                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 使用

### 导出嵌入

```bash
ontoskills export-embeddings --ontology-root ./ontoskills
```

这会创建 `ontoskills/system/embeddings/`，包含：
- `model.onnx` - ONNX 嵌入模型 (~45MB)
- `tokenizer.json` - HuggingFace 分词器
- `intents.json` - 预计算的意图嵌入

### MCP 工具：search_intents

导出嵌入后，MCP 服务器提供：

```json
{
  "name": "search_intents",
  "arguments": {
    "query": "create a pdf document",
    "top_k": 5
  }
}
```

返回带相似度分数的匹配意图：
```json
{
  "query": "create a pdf document",
  "matches": [
    {"intent": "create_pdf", "score": 0.92, "skills": ["pdf"]},
    {"intent": "export_document", "score": 0.78, "skills": ["pdf", "document-export"]}
  ]
}
```

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
   → 智能体调用：search_intents("create a pdf", top_k: 3)
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
| search_intents 延迟 | < 50ms | 手动基准测试 |
| ONNX 模型大小 | < 50MB | 检查文件大小 |
| 内存占用 | < 100MB | 使用 `top` 监控 |

---

## 文件结构

```
ontoskills/
└── system/
    └── embeddings/
        ├── model.onnx           # ~45MB
        ├── tokenizer.json       # ~500KB
        ├── tokenizer_config.json
        ├── special_tokens_map.json
        └── intents.json         # 可变

core/
├── embeddings/
│   ├── __init__.py
│   └── exporter.py              # Python 导出脚本

mcp/
├── src/
│   ├── embeddings.rs            # Rust 嵌入引擎
│   ├── schema.rs                # 模式资源
│   └── main.rs                  # MCP 工具处理器
```
