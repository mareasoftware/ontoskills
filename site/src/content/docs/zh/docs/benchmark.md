---
title: 基准测试结果
description: OntoSkills MCP 与传统技能的对比 — SkillsBench 确定性评估结果
sidebar:
  order: 15.5
---

通过 MCP 工具传递的结构化知识是否真的能帮助 AI 代理比原始 Markdown 文件更好地完成任务？我们进行了一项对照实验来验证。

---

import BenchmarkApp from '../../../components/benchmark/BenchmarkApp.astro';

## 核心问题

像 Claude Code 这样的 AI 编程代理依赖技能文档来完成专业任务——生成 DOCX 文件、处理 PDF、分析金融数据。如今，这些技能以纯 Markdown 文件（`SKILL.md`）的形式提供。代理必须阅读原始文本并自行提取指令、启发式规则和反模式。

**OntoSkills** 采用了不同的方法：技能知识被编译成结构化的 OWL 2 本体，通过 MCP 工具传递。代理使用 `search`、`get_skill_context`、`evaluate_execution_plan` 和 `query_epistemic_rules` 四个工具——接收带有严重性评级、认知规则和执行计划评估的类型化知识节点。

哪种方法效果更好？

## SkillsBench：确定性代码生成评估

我们使用 [SkillsBench](https://github.com/benchflow-ai/skillsbench) 对两种方法进行了评估，该基准测试衡量代理为真实任务生成可用代码的能力。

### 评估方式

1. 代理接收任务描述和相关的技能文档
2. 生成一个 Python 解决方案脚本
3. 脚本在任务的 **Docker 容器**中运行（通过 podman）
4. **pytest 测试套件**验证输出文件——完全确定性，无需人工判断
5. 分数 = `通过测试数 / 总测试数`

这不是 LLM 评审。评估完全确定且可重复。

### 实验设置

| 参数 | 值 |
|------|-----|
| 代理 | Claude Code CLI（`--print --bare` 模式）|
| 模型 | glm-5.1（通过 API 代理）|
| 任务数 | 10（seed=7），来自 70+ 个可用任务池 |
| 评分 | Docker + pytest CTRF 报告 |

### 代理模式

**传统模式** — 技能文档以 SKILL.md 文件形式放置在 `.claude/skills/` 中。代理使用 Claude Code 的原生文件读取功能发现和加载技能——与生产环境中的工作方式完全一致。

**OntoSkills MCP 模式** — 技能编译为 OWL 2 本体，通过 OntoMCP 提供。代理通过 MCP 工具（`search`、`get_skill_context`）发现技能。`ontomcp-driver` 技能教导代理查询本体的最佳工作流程。

两种模式使用相同的 Claude Code 代理、相同的模型、相同的提示。唯一的区别是**技能知识的传递方式**。

## 结果

<BenchmarkApp />

### 主要发现

- **OntoSkills MCP 通过更多任务**：总体 50% vs 40%，技能知识任务 83% vs 67%（排除基础设施故障）
- **OntoSkills 使用更少 token**：输入 token 减少 15%，输出 token 减少 35%——结构化知识更紧凑
- **OntoSkills 成本更低**：总计 $2.92 vs $3.97（-26%），因为 token 使用量更低
- **最大优势**：paper-anonymizer（PDF 处理）——传统模式完全失败，OntoSkills 通过全部 6 项测试

### 基础设施故障

10 个任务中有 4 个因与技能质量无关的**基础设施问题**而在两种模式下都失败了：
- `gh-repo-analytics` — Docker 容器内 GitHub CLI 未认证
- `flood-risk-analysis` — 外部 HTTP 端点返回 404
- `lab-unit-harmonization` / `fix-visual-stability` — 代理超时

这些已从技能知识对比中排除。

## 为什么结构化知识胜出

传统 SKILL.md 文件将指令、示例、注意事项和反模式混合在非结构化文本中。代理必须一次性解析所有内容，无法区分关键信息和可选信息。

OntoSkills 以**带有严重性评级的类型化节点**传递知识：
- `CRITICAL`（关键）规则优先突出显示
- 反模式附带明确的 `rationale`（原因），解释*为什么*要避免
- 执行计划评估在编码前捕获常见错误
- 代理获得经过筛选、优先排序的知识视图，而非一整面文本墙

这对于 PDF 处理（paper-anonymizer）等复杂领域尤其有价值，正确与错误输出之间的差异取决于细微的配置细节。

## 局限性

- **样本量**：10 个任务来自 70+ 个任务池。结果应通过更大规模的运行来确认。
- **单一模型**：所有结果使用 glm-5.1 通过 API 代理。其他模型的表现可能不同。
- **单一基准**：SkillsBench 测试代码生成。其他基准（GAIA 问答、SWE-bench 代码库修补）已计划中。
- **种子依赖**：任务选择因种子而异。我们报告 seed=7 以确保可重复性。

## 后续计划

- **25 任务运行**正在进行中，以获得更强的统计显著性
- **GAIA** 评估（带文件附件的问答）— 需要 HuggingFace 认证
- **SWE-bench** 评估（代码库修补）— 已计划使用更新模型

---

> 所有基准测试代码均为开源。您可以自行运行：`python benchmark/run.py --benchmark skillsbench --mode claudecode --max-tasks 25 --model glm-5.1 --seed 7`
