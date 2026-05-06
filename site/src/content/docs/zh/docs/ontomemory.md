---
title: OntoMemory
description: 面向图感知智能体的持久化运行时记忆
sidebar:
  order: 7
---

`OntoMemory` 将项目和全局知识保存为可编辑的图节点。记忆不是旁路备注：它们是 `oc:Memory` 节点，也是 `oc:KnowledgeNode` 的子类，并会和已编译技能一起加载到同一个 OntoMCP 运行时图中。

---

## 保存什么

每条记忆包含结构化字段：

| 字段 | 用途 |
|------|------|
| `content` | 被记住的指令、事实、流程、修正、偏好或反模式 |
| `scope` | 写入范围为 `project` 或 `global`；搜索/list 可使用 `both` |
| `memory_type` | `procedure`、`correction`、`anti_pattern`、`preference` 或 `fact` |
| `related_skill_ids` | 适用的技能 |
| `related_intents` | 适用的意图字符串 |
| `related_topic_ids` | 确定性主题聚类 |
| `related_memory_ids` | 主题相似的记忆 |
| `depends_on_memory_ids` | 支撑或前置记忆 |
| `supersedes_memory_ids` | 被此记忆替代的旧记忆 |

运行时记忆以 `.ttl` 数据持久化，并随其他本体图一起加载。

---

## 图关系

OntoMemory 使用显式图关系，而不是扁平备注列表。

| 关系 | 含义 |
|------|------|
| `related_to_skill` | 此记忆与某个已编译技能相关。 |
| `related_to_intent` | 此记忆与某个意图字符串相关。 |
| `related_to_topic` | 此记忆属于某个主题聚类。一条记忆可以属于多个主题，并作为跨聚类桥接记忆。 |
| `related_to_memory` | 此记忆与另一条记忆主题相似，但不表示顺序。 |
| `depends_on_memory` | 此记忆依赖另一条记忆；用于操作链。 |
| `supersedes_memory` | 此记忆替代、修正或版本化一条旧记忆。 |

主要 RDF 谓词包括 `oc:memoryId`、`oc:memoryScope`、`oc:directiveContent`、`oc:relatedToSkill`、`oc:relatedIntent`、`oc:relatedTopic`、`oc:relatedToMemory`、`oc:dependsOnMemory` 和 `oc:supersedesMemory`。

---

## MCP 动作

使用 `ontomemory` MCP 工具：

```json
{
  "action": "remember",
  "content": "发布说明依赖 changelog，并替代旧的草稿摘要。",
  "memory_type": "procedure",
  "related_intents": ["write_release_notes"],
  "depends_on_memory_ids": ["mem_changelog_source"],
  "supersedes_memory_ids": ["mem_old_release_summary"]
}
```

| 动作 | 用途 |
|------|------|
| `remember` | 保存一个或多个记忆。默认会拆分复合想法、自动关联图链接、合并重复项并避免孤立节点。 |
| `associate` | 预览拆分和图关联，不写入。 |
| `search` / `list` | 按查询、范围、技能、置信度、归档状态或数量限制检索记忆。 |
| `get` | 加载一条记忆，可选择包含依赖和被替代记录。 |
| `update` | 替换可编辑字段和关系数组。 |
| `link` / `unlink` | 添加或移除一条显式图关系。 |
| `forget` | 归档记忆，或使用 `hard_delete=true` 硬删除。 |
| `recluster` | 重新计算既有记忆的主题聚类和通用记忆链接。 |

---

## 聚类与质量

记忆聚类 v1 是确定性且本地的。嵌入可用于技能发现，但 OntoMemory 聚类不需要嵌入。

- `dedupe_policy=merge` 默认合并相似记忆；`reject` 在重复时失败；`allow` 保留重复项。
- `isolation_policy=auto_link` 通过关联技能、意图、主题或邻近记忆把记忆放入图中；`reject` 拒绝孤立记忆；`inbox` 分配未分类主题。
- `auto_link_related=true` 会分配主题聚类，并根据主题/上下文/意图信号连接非重复记忆。
- `recluster` 会回填已保存记忆。用 `{"action":"recluster","dry_run":true}` 预览，用 `{"action":"recluster","apply":true}` 持久化。

---

## OntoGraph

OntoGraph 是运行时图的本地 3D 查看器/编辑器。它显示技能、知识节点、状态、记忆、意图、主题和关系。

从 MCP 二进制启动：

```bash
cargo run --manifest-path mcp/Cargo.toml -- graph --ontology-root ./ontoskills
```

或调用 MCP 工具：

```json
{ "action": "start" }
```

记忆编辑器可以创建、编辑、归档、硬删除和关联记忆。图视图会高亮记忆链、主题聚类、桥接记忆，以及所选节点的入站/出站关系。
