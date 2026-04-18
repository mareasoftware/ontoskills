---
title: 路线图
description: 从核心到自主智能体 — OntoSkills 生态系统
sidebar:
  order: 15
---

> 此路线图随项目发展而演变。

## 阶段 1：OntoCore

**状态：** 完成

基础。OntoCore 是我们的神经符号核心，将自然语言技能定义转换为经过验证的 OWL 2 DL 本体。

- [x] 使用 Claude 进行自然语言解析
- [x] OWL 2 DL 序列化（RDF/Turtle）
- [x] SHACL 验证守门员
- [x] 安全审计管道
- [x] 156+ 测试

## 阶段 2：OntoSkills

**状态：** 完成

知识库。OntoSkills 是从 OntoCore 发布的已编译、已验证技能 — 准备好被智能体查询。

- [x] 核心技能库编译
- [x] 公共技能商店
- [x] 技能版本控制和更新
- [x] 依赖管理

## 阶段 3：OntoMCP

**状态：** 完成

接口。OntoMCP 通过模型上下文协议暴露 OntoSkills，使任何 MCP 兼容的智能体能够通过亚毫秒级 SPARQL 查询即时访问结构化知识。

- [x] 具有 stdio 传输的 Rust MCP 服务器
- [x] Oxigraph 内存图存储
- [x] SPARQL 1.1 查询接口
- [x] 4 个工具（search、get_skill_context、evaluate_execution_plan、query_epistemic_rules）
- [x] 每技能预计算的嵌入（可选，需要 ontocore[embeddings]）
- [x] 安装时下载嵌入（--with-embeddings 标志）
- [x] 类别和 is_user_invocable 搜索过滤器
- [x] Claude Code 集成

## 阶段 4：OntoStore

**状态：** 开发中

市场。OntoStore 是一个集中式仓库，团队可以在其中发布、发现和共享本体。

- [x] 带嵌入文件引用的每包清单
- [x] 带全局嵌入模型声明的注册表索引
- [x] 具有实时市场的本体商店
- [x] 3D 知识图谱可视化
- [ ] 版本管理
- [ ] 团队协作功能
- [ ] 社区贡献

## 阶段 5：OntoClaw

**状态：** 计划中

智能体。由结构化知识驱动的自主智能体 — 以精确而非幻觉进行推理。

- [ ] 智能体架构设计
- [ ] 多智能体协作
- [ ] 知识图谱推理
- [ ] 生产部署

---

## 跟踪进度

在 [GitHub](https://github.com/mareasw/ontoskills) 上关注开发。

有想法？[提出问题](https://github.com/mareasw/ontoskills/issues)。
