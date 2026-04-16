---
title: 商店
description: OntoStore、第三方商店和包生命周期
sidebar:
  order: 14
---

OntoSkills 使用简单的分发模型：

- **OntoStore** — 默认内置
- **第三方商店** — 显式添加
- **源导入** — 本地克隆并编译

---

## 商店类型

### OntoStore（内置）

OntoStore 随产品提供。无需配置。

```bash
ontoskills search hello
ontoskills install mareasw/greeting/hello
```

技能安装后自动启用。

**包 ID 格式：** `author/package/skill`

支持多层级安装：

```bash
# 安装单个技能
ontoskills install obra/superpowers/test-driven-development

# 安装整个包中的所有技能
ontoskills install obra/superpowers

# 安装某作者的所有包
ontoskills install mareasw
```

示例：`obra/superpowers/test-driven-development`

### 第三方商店

由其他团队或社区维护的可选商店。

```bash
# 添加商店
ontoskills store add-source acme https://example.com/index.json

# 列出已配置的商店
ontoskills store list
```

第三方包使用相同的 ID 格式和安装流程。

### 源导入

包含 `SKILL.md` 文件的原始仓库，本地编译。

```bash
ontoskills import-source https://github.com/user/skill-repo
```

- 克隆到 `~/.ontoskills/skills/author/`
- 编译到 `~/.ontoskills/ontologies/author/`
- 需要安装 OntoCore 编译器

---

## 包生命周期

### 安装

```bash
ontoskills install obra/superpowers/test-driven-development
```

从商店下载已编译的 `.ttl` 并放入 `~/.ontoskills/ontologies/`。

要同时下载语义搜索嵌入文件，使用 `--with-embeddings`：

```bash
ontoskills install obra/superpowers/test-driven-development --with-embeddings
```

### 启用 / 禁用

```bash
ontoskills disable obra/superpowers/test-driven-development
ontoskills enable obra/superpowers/test-driven-development
```

技能安装后默认启用。使用 `disable` 可以从 OntoMCP 隐藏技能而不删除它。使用 `enable` 重新启用。

### 更新

```bash
ontoskills update obra/superpowers/test-driven-development
```

从商店获取最新版本。

### 移除

```bash
ontoskills remove obra/superpowers/test-driven-development
```

从本地存储删除包。

### 重建索引

```bash
ontoskills rebuild-index
```

从所有已启用的技能重新生成 `~/.ontoskills/ontologies/system/index.enabled.ttl`。如果手动修改了 `.ttl` 文件，运行此命令。

---

## CLI 命令参考

| 命令 | 描述 |
|------|------|
| `search <query>` | 跨所有商店搜索技能 |
| `install <package-id>` | 安装已编译的包 |
| `enable <package-id>` | 为 MCP 运行时启用 |
| `disable <package-id>` | 从 MCP 运行时禁用 |
| `remove <package-id>` | 卸载包 |
| `update <package-id>` | 更新到最新版本 |
| `list-installed` | 列出所有已安装的包 |
| `store list` | 列出已配置的商店 |
| `store add-source <name> <url>` | 添加第三方商店 |
| `import-source <url>` | 导入并编译源仓库 |
| `rebuild-index` | 重新生成已启用索引 |
| `uninstall --all` | 删除整个托管主目录 |

---

## 本地布局

```text
~/.ontoskills/
├── bin/                    # 托管二进制文件
│   └── ontomcp
├── core/                   # 编译器运行时（可选）
├── ontologies/             # 已编译的本体
│   ├── core.ttl
│   ├── index.ttl
│   ├── system/             # 系统级文件
│   │   └── index.enabled.ttl  # 已启用技能清单
│   └── */ontoskill.ttl
├── skills/                 # 源技能
│   └── author/             # 导入的仓库
└── state/                  # 元数据和锁
    ├── registry.sources.json
    └── registry.lock.json
```

---

## 故障排除

### "找不到包"

- 检查包 ID 拼写
- 运行 `ontoskills search <query>` 发现可用包
- 如果使用第三方商店，验证已配置：`ontoskills store list`

### "技能在 MCP 中不可见"

如果技能被禁用了，重新启用它：

```bash
ontoskills enable obra/superpowers/test-driven-development
ontoskills rebuild-index
```

### "源导入失败"

确保已安装 OntoCore：

```bash
ontoskills install core
```

然后重试导入。

### "索引损坏"

从头重建：

```bash
ontoskills rebuild-index
```

### "嵌入生成失败"

如果 `ontocore[embeddings]` 使用 ONNX Runtime 时出错，设置动态库路径：

```bash
export ORT_DYLIB_PATH=/path/to/onnxruntime/libonnxruntime.so
```

或者要同时下载语义搜索嵌入文件，使用 `--with-embeddings`：

```bash
ontoskills install obra/superpowers/test-driven-development --with-embeddings
```

---

## 实用规则

| 命令 | 作用 |
|------|------|
| `install mcp` | 安装 MCP 运行时 |
| `install core` | 安装编译器 |
| `install <id>` | 安装已编译的包 |
| `import-source <url>` | 克隆并编译源 |
| `enable` / `disable` | 控制 MCP 可见性 |
| OntoStore | 内置，永远不需要 `store add-source` |
