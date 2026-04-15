---
title: 技能编写
description: 编写有效的 SKILL.md 文件，编译为 Claude 可发现和使用的本体
sidebar:
  order: 4
---

OntoSkills 将自然语言的 `SKILL.md` 文件编译为正式的 RDF 本体。本指南介绍如何编写简洁、结构良好且有效的技能。

---

## 核心原则

### 简洁是关键

上下文窗口与 Claude 需要的所有其他内容共享。挑战每一条信息：

- "Claude 真的需要这个解释吗？"
- "我可以假设 Claude 知道这个吗？"
- "这段内容值得它的 token 成本吗？"

**好** (~50 tokens):
```markdown
## 提取 PDF 文本

使用 pdfplumber 提取文本：

\`\`\`python
import pdfplumber

with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
\`\`\`
```

**不好** (~150 tokens):
```markdown
## 提取 PDF 文本

PDF（便携式文档格式）文件是一种常见的文件格式，包含
文本、图像和其他内容。要从 PDF 中提取文本，你需要
使用一个库。有很多用于 PDF 处理的库可用，但
推荐使用 pdfplumber，因为它易于使用且能很好地处理大多数情况。
首先，你需要使用 pip 安装它。然后你可以使用下面的代码...
```

### 设置适当的自由度

根据任务的脆弱性匹配具体程度：

| 自由度 | 何时使用 | 示例 |
|--------|----------|------|
| **高** | 多种有效方法 | "审查代码中的 bug 并建议改进" |
| **中** | 存在首选模式 | "使用此模板并根据需要自定义" |
| **低** | 需要精确序列 | "精确运行：`python migrate.py --verify`" |

### 使用所有模型测试

技能在不同模型上表现不同：

- **Haiku**：技能是否提供足够的指导？
- **Sonnet**：技能是否清晰高效？
- **Opus**：技能是否避免了过度解释？

---

## SKILL.md 结构

### YAML 前置元数据

```yaml
---
name: pdf-processing
description: 从 PDF 文件中提取文本和表格。用于处理 PDF、表单或文档提取时。
category: document-processing
is_user_invocable: true
aliases: [pdf, pdf-extract]
argument_hint: "<file_path>"
allowed_tools: [read, write, execute]
---
```

**名称要求：**
- 最多 64 个字符
- 仅限小写字母、数字、连字符
- 无保留词（"anthropic"、"claude"）

**描述要求：**
- 最多 1024 个字符
- 使用第三人称
- 包含做什么和何时使用

**可选字段：**
- `category` — 技能分类（如 `document-processing`、`data-analysis`）
- `is_user_invocable` — 用户是否可以直接调用（默认 `true`）
- `aliases` — 技能别名列表
- `argument_hint` — 参数提示，说明技能接受的输入
- `allowed_tools` — 技能允许使用的工具列表

### 正文部分

一个结构良好的 SKILL.md：

```markdown
# 技能标题

简短的一句话性质声明。

## 功能

能力的简明描述。

## 使用场景

技能激活的触发条件。

## 使用方法

分步说明或代码示例。

## 知识

指南、启发式规则、反模式（可选但推荐）。
```

---

## 编写有效的描述

`description` 字段对技能发现至关重要。Claude 使用它从可能 100+ 个技能中进行选择。

**好例子：**

```yaml
description: 从 PDF 文件提取文本和表格，填写表单，合并文档。用于处理 PDF 文件或用户提到 PDF、表单、文档提取时。
```

```yaml
description: 分析 Excel 电子表格，创建数据透视表，生成图表。用于分析 .xlsx 文件、电子表格或表格数据。
```

**避免：**

```yaml
description: 帮助处理文档
```

```yaml
description: 处理数据
```

---

## 渐进式披露

保持 SKILL.md 在 500 行以内。接近此限制时拆分内容。

### 模式：带引用的高级指南

```
pdf/
├── SKILL.md          # 主要指令（触发时加载）
├── FORMS.md          # 表单填写指南（按需加载）
├── reference.md      # API 参考（按需加载）
└── scripts/
    └── analyze.py    # 实用脚本
```

SKILL.md:
```markdown
# PDF 处理

## 快速开始
[简要说明在此]

## 高级功能
- **表单填写**：参见 [FORMS.md](FORMS.md)
- **API 参考**：参见 [reference.md](reference.md)
```

### 保持引用只有一层深度

```markdown
# 不好：太深
SKILL.md → advanced.md → details.md → actual-info.md

# 好：一层
SKILL.md → advanced.md
SKILL.md → reference.md
SKILL.md → examples.md
```

---

## 工作流和反馈循环

### 对复杂任务使用工作流

```markdown
## PDF 表单填写工作流

复制此清单并跟踪进度：

- [ ] 步骤 1：分析表单
- [ ] 步骤 2：创建字段映射
- [ ] 步骤 3：验证映射
- [ ] 步骤 4：填写表单
- [ ] 步骤 5：验证输出

**步骤 1：分析表单**
运行：`python scripts/analyze_form.py input.pdf`

**步骤 2：创建字段映射**
编辑 `fields.json` 添加值...

[继续清晰的步骤]
```

### 实现验证循环

```markdown
## 文档编辑流程

1. 编辑 `word/document.xml`
2. **立即验证**：`python scripts/validate.py`
3. 如果验证失败：
   - 查看错误消息
   - 修复问题
   - 重新运行验证
4. 只有验证通过才继续
```

---

## 技能组件

OntoSkills 支持用于渐进式披露的结构化组件：

### 参考文件

按用途组织支持文档：

```text
pdf-skill/
├── SKILL.md
└── reference/
    ├── api.md      # api-reference
    ├── examples.md # examples
    └── guide.md    # guide
```

编译器识别参考文件及其用途：
- `api-reference`：API 文档、方法参考
- `examples`：代码示例、使用模式
- `guide`：教程、操作指南
- `domain-specific`：领域知识
- `other`：其他

### 可执行脚本

捆绑具有明确意图的实用脚本：

```text
pdf-skill/
├── SKILL.md
└── scripts/
    ├── extract.py   # execution_intent: "execute"
    └── validate.py  # execution_intent: "execute"
```

脚本的序列化包括：
- `executor`：python、bash、node、other
- `execution_intent`："execute" 或 "read_only"
- `requirements`：所需工具（如 ["pypdf"]）

### 工作流

定义多步骤流程：

```markdown
## PDF 表单填写工作流

**步骤 1：分析**
运行：`python scripts/analyze_form.py input.pdf`

**步骤 2：填写**
编辑 `fields.json` 添加值

**步骤 3：验证**
运行：`python scripts/verify.py output.pdf`
```

### 示例

提供用于模式匹配的输入/输出对：

```markdown
## 提交消息示例

**示例 1：**
- 输入：Added JWT auth
- 输出：`feat(auth): implement JWT authentication`

**示例 2：**
- 输入：Fixed date bug
- 输出：`fix(reports): correct timezone handling`
```

---

## 知识节点

OntoSkills 从你的 SKILL.md 中提取结构化知识。编写清晰的部分以映射到节点类型：

### PreFlightCheck

```markdown
## 开始之前

验证 wkhtmltopdf 已安装：
\`\`\`bash
which wkhtmltopdf || brew install wkhtmltopdf
\`\`\`

这可以防止 PDF 生成期间出现 "command not found" 错误。
```

### AntiPattern

```markdown
## 常见错误

**不要**接受来自不可信输入的文件路径。这会启用路径遍历攻击。

相反，根据允许目录的白名单进行验证。
```

### Heuristic

```markdown
## 提示

对于大型电子表格（>10k 行），以 1000 为块处理以避免内存问题。
```

参见 [知识提取](/zh/docs/knowledge-extraction/) 了解所有 26 种节点类型。

---

## 常见模式

### 模板模式

```markdown
## 报告结构

始终使用此确切格式：

\`\`\`markdown
# [分析标题]

## 执行摘要
[一段话]

## 关键发现
- 发现 1
- 发现 2

## 建议
1. 行动项
\`\`\`
```

### 示例模式

```markdown
## 提交消息格式

**示例 1：**
输入：Added JWT authentication
输出：
\`\`\`
feat(auth): implement JWT authentication

Add login endpoint and token validation
\`\`\`

**示例 2：**
输入：Fixed date bug in reports
输出：
\`\`\`
fix(reports): correct timezone handling

Use UTC consistently in date formatting
\`\`\`
```

---

## 需要避免的反模式

### Windows 风格路径

```markdown
# 不好
scripts\\helper.py
reference\\guide.md

# 好
scripts/helper.py
reference/guide.md
```

### 太多选项

```markdown
# 不好：令人瘫痪的选择
"你可以使用 pypdf，或 pdfplumber，或 PyMuPDF，或 pdf2image..."

# 好：明确的默认选项和逃生舱
"使用 pdfplumber 提取文本。对于需要 OCR 的扫描 PDF，使用 pdf2image 配合 pytesseract。"
```

### 假设工具已安装

```markdown
# 不好
"使用 pdf 库处理文件。"

# 好
"安装：`pip install pypdf`

然后：
\`\`\`python
from pypdf import PdfReader
reader = PdfReader("file.pdf")
\`\`\`"
```

---

## 编译

编写 SKILL.md 后，编译它：

```bash
ontoskills install core
ontoskills init-core
ontoskills compile my-skill
```

> **注意：** 嵌入生成是可选的。安装 `pip install ontocore[embeddings]` 可在编译时生成语义搜索向量。未安装时编译正常完成，但跳过嵌入生成。

### 编译期间发生什么

1. **解析**：从 markdown 提取结构
2. **LLM 提取**：使用 Claude 识别知识节点
3. **SHACL 验证**：验证必需字段存在
4. **嵌入生成**：为语义搜索生成向量嵌入（可选）
5. **RDF 生成**：生成 `ontoskill.ttl`

### 常见验证错误

| 错误 | 修复 |
|------|------|
| "Missing resolvesIntent" | 添加清晰的 "使用场景" 部分 |
| "Nature not extracted" | 在顶部添加一句话摘要 |
| "SHACL violation" | 确保技能有清晰的结构 |

使用 `-v` 查看详情：
```bash
ontoskills compile my-skill -v
```

### SHACL 验证规则

编译器根据 `core/specs/ontoskills.shacl.ttl` 中定义的宪法 SHACL 形状验证技能。这些规则确保每个编译的技能逻辑有效。

**每个技能必须具有：**
- 至少一个 `resolvesIntent` — 此技能解决什么用户意图
- 可选 `generatedBy` — 哪个 LLM 生成了此技能（自动填充）

**状态字段必须是有效的 IRI：**
- `requiresState` — 前置条件（如 `oc:FileExists`）
- `yieldsState` — 成功后的后置条件
- `handlesFailure` — 失败时的状态

**技能类型规则（自动）：**
- 可执行技能必须恰好有一个负载（`oc:code` 或 `oc:executionPath`）
- 声明式技能不能有负载

**知识节点必须具有：**
- `directiveContent` — 实际的知识内容
- `appliesToContext` — 此知识何时适用
- `hasRationale` — 为什么这很重要

**警告（非阻止）：**
- 没有 `impartsKnowledge` 的技能会收到警告 — 考虑添加启发式规则、反模式或最佳实践

大多数字段在提取过程中自动填充。你主要需要确保 SKILL.md 有清晰的意图、结构和知识部分。

---

## 检查清单

发布技能前：

**核心质量**
- [ ] 描述包含做什么和何时使用
- [ ] SKILL.md 在 500 行以内
- [ ] 无时间敏感信息
- [ ] 全文术语一致
- [ ] 示例具体，不抽象

**结构**
- [ ] 引用只有一层深度
- [ ] 使用了渐进式披露
- [ ] 工作流有清晰的步骤
- [ ] 包含验证循环

**代码**
- [ ] 脚本显式处理错误
- [ ] 列出必需的包
- [ ] 路径使用正斜杠
- [ ] 无魔术数字

**测试**
- [ ] 编译无错误
- [ ] 用真实场景测试
- [ ] 知识节点正确提取

---

## 下一步

- [知识提取](/zh/docs/knowledge-extraction/) — 了解所有 26 种节点类型
- [OntoCore](/zh/docs/ontocore/) — 编译器参考
- [快速开始](/zh/docs/getting-started/) — 编译你的第一个技能
