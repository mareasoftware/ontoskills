---
title: 基准测试方法论与结果
description: OntoSkills MCP 与传统技能的对比 — 100% 与 BenchFlow 对齐的 SkillsBench 确定性评估
sidebar:
  order: 15.5
---

通过 MCP 工具传递的结构化知识是否真的能帮助 AI 代理比原始 Markdown 文件更好地完成任务？我们进行了一项对照实验来验证——并在每次迭代中持续改进知识传递方式。

---

import BenchmarkApp from '../../../components/benchmark/BenchmarkApp.astro';

## 核心问题

像 Claude Code 这样的 AI 编程代理依赖技能文档来完成专业任务——生成 DOCX 文件、处理 PDF、分析金融数据。如今，这些技能以纯 Markdown 文件（`SKILL.md`）的形式提供。代理必须阅读原始文本并自行提取指令、启发式规则和反模式。

**OntoSkills** 采用了不同的方法：技能知识被编译成结构化的 OWL 2 本体，通过 **OntoMCP** 传递。代理通过单一的 `ontoskill` 工具调用发现和加载技能知识——接收带有严重性评级、反模式原因说明、精选代码示例以及**技能内链接**的类型化知识节点，这些链接将反模式连接到正确替代方案，将约束连接到其适用的工作流步骤。

哪种方法效果更好？

## SkillsBench：确定性代码生成评估

我们使用 [SkillsBench](https://github.com/benchflow-ai/skillsbench) 对两种方法进行了评估，该基准测试是 [BenchFlow](https://github.com/benchflow-ai/benchflow) 评估套件的一部分。评估**100% 与 SkillsBench 对齐**——代理通过 ACP（代理通信协议）在 Docker 容器内运行，完全遵循官方 SkillsBench 方法论。

### 评估方式

1. 代理通过 BenchFlow ACP（代理通信协议）在**任务的 Docker 容器内**运行
2. 代理接收任务描述和技能提示，然后生成 Python 解决方案脚本
3. [Harbor Verifier](https://github.com/benchflow-ai/harbor) 运行任务的 pytest 测试套件——完全确定性，无需人工判断
4. 分数 = `通过测试数 / 总测试数`（CTRF 报告）
5. 指数退避重试——取最佳奖励

这不是 LLM 评审。评估完全确定且可重复。两种模式使用相同的容器管理（BenchFlow Trial）和相同的验证（Harbor Verifier）。唯一的区别是**技能知识的传递方式**。

### 实验设置

| 参数 | 值 |
|------|-----|
| 代理 | claude-agent-acp（通过 BenchFlow ACP）|
| 模型 | glm-5.1（通过 API 代理）|
| 基础设施 | [BenchFlow](https://github.com/benchflow-ai/benchflow) Trial + [Harbor](https://github.com/benchflow-ai/harbor) Verifier |
| 评分 | Harbor Verifier + pytest CTRF 报告 |
| 重试 | 每任务 5 次（BenchFlow RetryConfig，干净重试，取最佳）|
| 工作线程 | 2 个并行 Docker 容器 |

### 代理模式

**传统模式（`acp`）** — SKILL.md 文件通过 BenchFlow 的 `_inject_skills_into_dockerfile()` 注入到 Docker 镜像中。代理使用原生文件读取功能发现和加载技能——与生产环境中的工作方式完全一致。100% 与 SkillsBench 对齐。

**OntoSkills MCP 模式（`acp-mcp`）** — 技能编译为 OWL 2 本体，通过容器内的 **OntoMCP** 提供。`ontomcp` 二进制文件、TTL 包和 `.mcp_config.json` 在容器启动和代理安装之间注入。代理通过单一的 `ontoskill` 工具调用发现和加载技能知识，接收经过优先级排序的结构化上下文，知识元素之间相互关联。100% 与 SkillsBench 对齐。

**基线模式（`baseline`）** — 无技能、无提示。原始代理仅在容器内接收任务描述。这测量模型的零样本能力。

ACP 和 ACP-MCP 模式在容器内运行相同的代理，使用相同的模型和相同的 BenchFlow 基础设施。对比是公平的——唯一的变量是技能的传递方式。

## 五组对照实验设计

我们运行五组受控实验，分别隔离技能传递的不同维度：

| 实验 | 模式 | 技能 | 提示 | 测试维度 |
|------|------|------|------|----------|
| 1 | baseline | 无 | 无 | **基线** — 无技能的原始代理 |
| 2 | acp | SKILL.md | 有 | **知识质量** — 传统传递 |
| 3 | acp-mcp | ontomcp | 有 | **知识质量** — 结构化传递 |
| 4 | acp | SKILL.md | 无 | **发现能力** — 代理需自行查找技能 |
| 5 | acp-mcp | ontomcp | 无 | **发现能力** — 代理需自行查询 MCP 工具 |

- **基线（实验 1）**：无技能、无提示的原始代理。这确立了能力下限——模型在没有任何领域知识时能做什么。
- **知识质量（实验 2-3）**：技能名称在提示中明确给出（`skill_nudge="name"`）。这隔离了每种传递方法将知识传递给代理的效果。
- **发现能力（实验 4-5）**：提示中不包含技能名称（`skill_nudge=""`）。这测试代理能否自主发现和使用可用技能。

### 关键对比

- **实验 2 vs 实验 3**：有提示的知识质量——当代理知道使用哪些技能时，传统传递 vs 结构化传递
- **实验 4 vs 实验 5**：无提示的发现能力——当代理必须自主查找技能时，传统传递 vs 结构化传递
- **实验 1 vs 实验 2**：技能增量（传统）——技能帮助了多少？
- **实验 1 vs 实验 3**：技能增量（结构化）——技能帮助了多少？
- **实验 2 vs 实验 4**：发现惩罚（传统）——移除提示后损失了多少？
- **实验 3 vs 实验 5**：发现惩罚（结构化）——MCP 处理自主发现的效果如何？

## 运行基准测试

### 前提条件

```bash
# 克隆 SkillsBench 任务
git clone --depth 1 https://github.com/benchflow-ai/skillsbench /tmp/skillsbench_full

# 安装 benchflow（需要 0.3.3.dev0 以支持 glm-5.1 代理）
pip install git+https://github.com/benchflow-ai/benchflow.git

# 设置 API 密钥
export ANTHROPIC_API_KEY="your-key"
```

### 运行全部 5 组实验

```bash
python benchmark/run.py \
  --benchmark skillsbench \
  --mode all5 \
  --max-tasks 25 \
  --model glm-5.1 \
  --attempts 5 \
  --workers 2 \
  --skillsbench-repo ~/.ontoskills/skillsbench \
  --output-dir benchmark/results \
  --force-restart -v
```

### 运行单个实验

```bash
# 仅基线
python benchmark/run.py --benchmark skillsbench --mode baseline --max-tasks 25 -v

# 传统模式（带提示）
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 -v

# MCP 模式（带提示）
python benchmark/run.py --benchmark skillsbench --mode acp-mcp --max-tasks 25 -v

# MCP 模式（无提示——发现能力）
python benchmark/run.py --benchmark skillsbench --mode acp-mcp --no-skill-hints --max-tasks 25 -v
```

### 增量执行

先运行 15 个任务，之后扩展到 25 个，无需重新运行已完成的任务：

```bash
# 首次运行：15 个任务
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 15 -v

# 扩展到 25 个（从保存的状态恢复）
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 --resume -v
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--mode` | `both` | `acp`、`acp-mcp`、`baseline`、`both`、`all5` |
| `--attempts` | 5 | 每任务干净重试次数（与 SkillsBench 一致）|
| `--workers` | 2 | 并行 Docker 工作线程 |
| `--resume` | True | 从之前的状态文件恢复 |
| `--force-restart` | False | 忽略现有状态，从头开始 |
| `--no-skill-hints` | False | 从提示中省略技能名称 |
| `--only-tasks id1,id2` | — | 仅运行指定任务 ID |
| `--skip-first N` | 0 | 跳过前 N 个任务 |

## 结果

结果即将发布——五组对照实验正在运行中，25 个任务 x 5 次尝试，完全与 BenchFlow 对齐。

<BenchmarkApp />

### 为什么结构化知识更胜一筹

传统 SKILL.md 文件将指令、示例、注意事项和反模式混合在非结构化文本中。代理必须一次性解析所有内容，无法区分关键信息。

OntoSkills 以**带有严重性评级和互联关系的类型化节点**传递知识：
- `CRITICAL` 规则优先展示
- 反模式附带明确的 `rationale`，解释*为什么*要避免特定方法——加上 `→ Correct:` 链接指向正确方法
- 约束链接到其适用的工作流步骤（`→ Applies to:`）
- 经过筛选的优先视图，而非大段文本
- 紧凑的结构化格式，自动去重已由知识节点捕获的内容

token 效率优势会产生复合效应：代理花更少的轮次阅读文档，花更多的轮次编写正确的代码。

## 方法论细节

### 12 个跳过的任务

以下任务因基础设施原因被跳过（与技能无关）：
- 特殊基础镜像（gcr.io、bugswarm 缓存镜像）
- 多容器 docker-compose 配置
- BuildKit heredoc 语法与 Podman 不兼容

### 状态持久化

基准测试状态在每次尝试后保存（不仅是已完成任务）。如果进程崩溃，所有进度都会保留。恢复从确切的状态位置继续。

### 工作线程池

两个异步工作线程共享一个 `asyncio.Queue`。每个工作线程选择一个任务，运行完整的试验生命周期（Docker 构建 → 代理执行 → 验证），然后标记完成或使用指数退避重新入队重试。

## 局限性

- **样本量**：结果来自 70+ 可用任务池（部分因基础设施限制被跳过）。
- **单一模型**：所有结果使用 glm-5.1 通过 API 代理。其他模型的表现可能不同。
- **单一基准**：SkillsBench 测试代码生成。其他基准测试（GAIA 问答、SWE-bench 代码库修补）将测试不同能力。

## 后续计划

- **五组对照结果** — 包含基线、知识质量和发现能力三个维度的完整基准测试
- **技能内链接评估** — 测量 derivedFromSection、correctAlternative 和 appliesToStep 链接对代理性能的影响
- **GAIA** 评估（带文件附件的问答）
- **SWE-bench** 评估（代码库修补）

---

> 所有基准测试代码均为开源。您可以自行运行：`python benchmark/run.py --benchmark skillsbench --mode all5 --max-tasks 25 --model glm-5.1 --attempts 5 --workers 2`
