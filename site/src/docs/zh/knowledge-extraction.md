---
title: 知识提取
description: OntoCore 如何从技能中提取结构化知识
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
| **知识节点** | `oc:impartsKnowledge` | 认知知识（每个技能 8-12 个）|
| **状态转换** | `oc:requiresState`、`oc:yieldsState`、`oc:handlesFailure` | 前置条件、结果、错误处理 |
| **执行负载** | `oc:hasPayload` | 可选的要执行的代码 |
| **溯源** | `oc:generatedBy` | 证明（哪个 LLM 编译的）|

---

## 知识节点

知识提取的核心。每个技能包含 8-12 个**知识节点** — 结构化的认知规则。

### 10 个认知维度

OntoCore 将知识组织为 **10 个维度**，共 **26 种**节点类型：

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

### 知识节点结构

每个知识节点都有：

```turtle
oc:kn_a1b2c3d4
  a oc:Heuristic ;
  oc:directiveContent "大文件优先使用流式传输" ;
  oc:appliesToContext "处理大文件时" ;
  oc:hasRationale "避免内存不足错误" ;
  oc:severityLevel "HIGH" .
```

| 字段 | 描述 |
|------|------|
| `directiveContent` | 规则或见解 |
| `appliesToContext` | 何时适用 |
| `hasRationale` | 为什么存在此规则 |
| `severityLevel` | 重要性：`CRITICAL`、`HIGH`、`MEDIUM`、`LOW` |

---

## 模块化本体架构

### 单个技能作为模块

每个已编译的技能是一个**自包含的 `.ttl` 文件**：

```
ontoskills/
├── ontoskills-core.ttl      # 核心 TBox（共享）
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
