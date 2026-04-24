---
title: 知识提取
description: OntoCore 如何从技能中提取结构化知识
sidebar:
  order: 9
---

技能不仅仅是代码 — 它是**结构化知识**。OntoCore 提取这些知识并将其编译为可查询的本体。

---

## 提取什么

每个技能都编译有：

| 元素 | 属性 | 描述 |
|------|------|------|
| **身份** | `oc:nature`、`oc:genus`、`oc:differentia` | "A 是一个做了 C 的 B" 定义 |
| **意图** | `oc:resolvesIntent` | 此技能解决的用户意图 |
| **需求** | `oc:hasRequirement` | 依赖项（EnvVar、Tool、Hardware、API、Knowledge）|
| **知识节点** | `oc:impartsKnowledge` | 认知 + 操作知识（每个技能 8-15 个）|
| **状态转换** | `oc:requiresState`、`oc:yieldsState`、`oc:handlesFailure` | 前置条件、结果、错误处理 |
| **执行负载** | `oc:hasPayload` | 可选的要执行的代码 |
| **溯源** | `oc:generatedBy` | 证明（哪个 LLM 编译的，可选）|

### 组件

| 元素 | 属性 | 描述 |
|------|------|------|
| **参考文件** | `oc:hasReferenceFile` | 支持 `purpose`（api-reference、examples、guide、domain-specific、other）的文档 |
| **工作流** | `oc:hasWorkflow` | 带有 `hasStep` 依赖的多步骤流程 |
| **示例** | `oc:hasExample` | 用于模式匹配的输入/输出对 |

---

## 知识节点

知识提取的核心。每个技能包含 8-15 个**知识节点** — 结构化的认知规则和操作指令。

### 认知节点

OntoCore 将知识组织为 **10 个维度**，共 **26 种认知节点类型**：

#### 维度 1：NormativeRule（规范性规则）
定义什么是正确的、错误的或受限制的规则。

| 类型 | 描述 | 示例 |
|------|------|------|
| **Standard** | 正确的做法 | "使用 SPARQL 查询本体" |
| **AntiPattern** | 要避免的模式 | "不要将 >100MB 的文件读入内存" |
| **Constraint** | 明确的限制 | "仅在 Unix 上工作" |

#### 维度 2：StrategicInsight（战略洞察）
有效决策的战略洞察。

| 类型 | 描述 | 示例 |
|------|------|------|
| **Heuristic** | 经验法则 | "大文件优先使用流式传输" |
| **DesignPrinciple** | 架构原则 | "一个技能 = 一个职责" |
| **WorkflowStrategy** | 流程策略 | "先编译依赖项" |

#### 维度 3：ResilienceTactic（弹性策略）
如何处理问题并恢复。

| 类型 | 描述 | 示例 |
|------|------|------|
| **KnownIssue** | 已知问题 | "慢速网络会超时" |
| **RecoveryTactic** | 恢复策略 | "使用指数退避重试" |

#### 维度 4：ExecutionPhysics（执行物理）
执行的物理特征。

| 类型 | 描述 | 示例 |
|------|------|------|
| **Idempotency** | 是否可以安全重复 | "编译是幂等的" |
| **SideEffect** | 副作用 | "写入文件到 ontoskills/" |
| **PerformanceProfile** | 性能特征 | "O(n) 基于技能数量" |

#### 维度 5：Observability（可观测性）
如何观察和测量。

| 类型 | 描述 | 示例 |
|------|------|------|
| **SuccessIndicator** | 成功信号 | "生成 .ttl 文件且无 SHACL 错误" |
| **TelemetryPattern** | 遥测模式 | "记录每个技能的提取时间" |

#### 维度 6：SecurityGuardrail（安全护栏）
安全相关的护栏。

| 类型 | 描述 | 示例 |
|------|------|------|
| **SecurityImplication** | 安全影响 | "需要在环境变量中设置 API key" |
| **DestructivePotential** | 破坏潜力 | "可能覆盖现有文件" |
| **FallbackStrategy** | 回退策略 | "离线时使用缓存" |

#### 维度 7：CognitiveBoundary（认知边界）
认知限制和模糊性。

| 类型 | 描述 | 示例 |
|------|------|------|
| **RequiresHumanClarification** | 需要人工确认 | "意图模糊 → 请求确认" |
| **AssumptionBoundary** | 所做假设 | "假设 UTF-8 编码" |
| **AmbiguityTolerance** | 模糊容忍度 | "接受 .md 和 .MD" |

#### 维度 8：ResourceProfile（资源概况）
资源使用概况。

| 类型 | 描述 | 示例 |
|------|------|------|
| **TokenEconomy** | Token 使用 | "SPARQL 查询：~100 tokens vs 50KB 技能文件" |
| **ComputeCost** | 计算成本 | "LLM 提取：每个技能约 2 秒" |

#### 维度 9：TrustMetric（信任指标）
信任相关指标。

| 类型 | 描述 | 示例 |
|------|------|------|
| **ExecutionDeterminism** | 执行确定性 | "SPARQL：100% 确定性" |
| **DataProvenance** | 数据来源 | "由 Claude 4 编译，哈希已验证" |

#### 维度 10：LifecycleHook（生命周期钩子）
生命周期中的钩子。

| 类型 | 描述 | 示例 |
|------|------|------|
| **PreFlightCheck** | 执行前检查 | "验证 ANTHROPIC_API_KEY 已设置" |
| **PostFlightValidation** | 执行后验证 | "使用 SHACL 验证 .ttl" |
| **RollbackProcedure** | 回滚流程 | "验证失败时从 .bak 恢复" |

---

### 操作节点

除了认知知识，OntoCore 还提取**操作节点** — 紧凑的、可操作的指令，告诉代理要*做什么*。这些将冗长的技能文档压缩为可直接执行的指令。

| 类型 | 描述 | 特殊字段 | 示例 |
|------|------|----------|------|
| **Procedure** | 有序步骤序列 | `step_order`（整数）| "1. 写失败测试 → 2. 运行 → 3. 最小代码 → 4. 重构" |
| **CodePattern** | 可复用代码片段 | `code_language` | `def test_add(): assert add(1,2) == 3` |
| **OutputFormat** | 预期输出模板 | `template_variables` | "## 总结\n- 发现\n- 建议" |
| **Command** | 精确的 CLI 命令 | — | `pytest tests/ -v --tb=short` |
| **Prerequisite** | 必需的前置条件 | — | "必须安装 Python 3.10+" |

每个技能生成 3-8 个操作节点。编译器积极压缩多行指令 — 去除填充词、解释和激励文本，只保留代理*需要做*的内容。

#### 操作节点的价值

| 没有操作节点 | 有操作节点 |
|---|---|
| 代理读取完整 SKILL.md（5-20KB）| 代理查询特定指令（~200 字节）|
| 指令埋藏在叙述中 | 编号步骤、精确命令 |
| 代码示例混在解释中 | 最小片段带语言上下文 |
| 输出格式不明确 | 带变量的显式模板 |
| 前置条件分散 | 单一前置条件检查列表 |

---

### 知识节点结构

每个知识节点都有：

**认知节点**（关于技能的推理）：

```turtle
oc:kn_a1b2c3d4
  a oc:Heuristic ;
  oc:directiveContent "大文件优先使用流式传输" ;
  oc:appliesToContext "处理大文件时" ;
  oc:hasRationale "避免内存不足错误" ;
  oc:severityLevel "HIGH" .
```

**操作节点**（要做什么）：

```turtle
oc:kn_e5f6g7h8
  a oc:Procedure ;
  oc:directiveContent "1. 写失败测试 2. 运行测试 3. 写最小代码 4. 重构" ;
  oc:stepOrder 1 ;
  oc:appliesToContext "实现新功能时" .
```

| 字段 | 描述 |
|------|------|
| `directiveContent` | 规则、见解或指令 |
| `appliesToContext` | 何时适用 |
| `hasRationale` | 为什么存在此规则（仅认知节点）|
| `severityLevel` | 重要性：`CRITICAL`、`HIGH`、`MEDIUM`、`LOW` |
| `stepOrder` | Procedure 节点的步骤位置 |
| `codeLanguage` | CodePattern 节点的编程语言 |
| `templateVariables` | OutputFormat 节点的占位符名称 |

---

## 模块化本体架构

### 单个技能作为模块

每个已编译的技能是一个**自包含的 `.ttl` 文件**：

```
ontoskills/
├── core.ttl      # 核心 TBox（共享）
├── index.ttl                # 带 owl:imports 的清单
├── pdf/
│   └── ontoskill.ttl        # PDF 技能模块
├── markdown/
│   └── ontoskill.ttl        # Markdown 技能模块
└── email/
    └── ontoskill.ttl        # Email 技能模块
```

### 可插拔知识

- **添加**技能 → 放入 `.ttl` 文件
- **移除**技能 → 删除 `.ttl` 文件
- **更新**技能 → 替换 `.ttl` 文件

全局本体通过**添加**而非修改来增长。

---

## 嵌入生成（可选）

编译期间，OntoCore 可以为技能描述和意图生成向量嵌入（**可选步骤**），用于语义搜索（`search` 工具的语义模式）。嵌入生成需要安装 `ontocore[embeddings]` 额外包：

```bash
pip install ontocore[embeddings]
```

如果未安装，编译将跳过嵌入生成并显示警告。BM25 关键词搜索在 MCP 运行时始终可用。

---

## 查询知识

### 按意图查找技能

```sparql
SELECT ?skill WHERE {
  ?skill oc:resolvesIntent "create_pdf"
}
```

### 获取技能的知识节点

```sparql
SELECT ?content ?type WHERE {
  <skill:pdf> oc:impartsKnowledge ?node .
  ?node oc:directiveContent ?content .
  ?node a ?type .
}
```

### 查找所有反模式

```sparql
SELECT ?skill ?content WHERE {
  ?skill oc:impartsKnowledge ?node .
  ?node a oc:AntiPattern .
  ?node oc:directiveContent ?content .
}
```

### 查找所有 PreFlightCheck

```sparql
SELECT ?skill ?content WHERE {
  ?skill oc:impartsKnowledge ?node .
  ?node a oc:PreFlightCheck .
  ?node oc:directiveContent ?content .
}
```

---

## 价值主张

| 之前（读取文件）| 之后（查询本体）|
|----------------|-----------------|
| 解析 50 个 SKILL.md 文件 | 单次 SPARQL 查询 |
| ~500KB 文本扫描 | ~1KB 查询 |
| 非确定性 | 精确结果 |
| 上下文溢出 | 只查询需要的 |
| LLM 解释 | 图返回 |

**知识变得可查询。智能变得民主化。**
