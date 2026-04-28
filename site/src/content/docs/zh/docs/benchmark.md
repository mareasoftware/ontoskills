---
title: 基准测试结果
description: OntoSkills MCP 与传统技能的对比 — 确定性评估结果
sidebar:
  order: 15.5
---

基准测试衡量通过 MCP 工具传递的结构化知识是否能比原始 Markdown 技能文件更好地改善代理任务完成率。

---

## SkillsBench

基于 Docker 的确定性代码生成任务评估。

### 方法论

- 代理：Claude Code CLI（`--print --bare` 模式）
- 代理生成 Python 解决方案脚本
- 脚本在任务的 Docker 容器中运行（通过 podman）
- 任务的 pytest 测试套件验证输出文件（确定性评分）
- 跳过 9 个任务（未编译技能），6 个任务（特殊基础镜像 + BuildKit 不兼容）
- 模型：glm-5.1，seed=7，每种模式 10 个任务

### 结果（seed=7, glm-5.1, Claude Code, 10 个任务）

| 任务 | 传统模式 | OntoSkills MCP |
|------|---------|----------------|
| reserves-at-risk-calc（金融） | 0/5 失败 | **1/5 部分通过** |
| offer-letter-generator（docx） | 4/4 通过 | 4/4 通过 |
| lab-unit-harmonization（医疗） | 0/8 失败 | 0/8 失败 |
| travel-planning（旅行） | 11/11 通过 | 11/11 通过 |
| paper-anonymizer（PDF） | 0/6 失败 | **6/6 通过** |
| flood-risk-analysis（数据） | 0/2 失败 | 0/2 失败 |
| 3d-scan-calc（工程） | 2/2 通过 | 2/2 通过 |
| exceltable-in-ppt（Office） | 8/8 通过 | 8/8 通过 |
| fix-visual-stability（Web） | 0/2 失败 | 0/2 失败 |
| gh-repo-analytics（DevOps） | 0/8 失败 | 0/8 失败 |

| 指标 | 传统模式 | OntoSkills MCP | 差异 |
|------|---------|----------------|------|
| 通过率 | 40% | **50%** | +25% |
| 平均奖励 | 0.40 | **0.52** | +30% |

### 工作原理

**传统模式** — 代理接收放置在 `.claude/skills/` 中的 `SKILL.md` 文件。它读取原始 Markdown，并需要从非结构化文本中解析指令、启发式规则和反模式。所有知识通过文件读取获取。

**OntoSkills MCP 模式** — 代理可使用 OntoMCP 工具（`search`、`get_skill_context`、`evaluate_execution_plan`、`query_epistemic_rules`）。它查询结构化的 OWL 2 本体，获取知识节点、认知规则和执行计划评估。`ontomcp-driver` 技能教导代理如何有效使用 MCP 工具。

---

## GAIA

带文件附件的问答（PDF、DOCX、XLSX 等）。

> API 代理的结果已存在。Claude Code 模式结果即将推出。

---

## SWE-bench

代码库补丁 — 代理生成 git diff 来修复真实的 GitHub 问题。

> API 代理的结果已存在。Claude Code 模式结果即将推出。
