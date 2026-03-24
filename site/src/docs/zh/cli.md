---
title: CLI 参考
description: ontoskills CLI 完整命令参考
---

`ontoskills` 是产品入口点。它在 `~/.ontoskills/` 下安装和管理运行时、编译器、商店技能和本地状态。

---

## 快速开始

```bash
# 首次设置
npx ontoskills install mcp

# 引导后，直接使用
ontoskills --help
```

---

## 安装命令

### `install mcp`

安装 MCP 运行时。

```bash
ontoskills install mcp
```

创建：
- `~/.ontoskills/bin/ontomcp` — MCP 服务器二进制文件
- `~/.ontoskills/ontologies/` — 已编译的本体包
- `~/.ontoskills/state/` — 锁定文件和元数据

### `install core`

安装 OntoCore 编译器（可选）。

```bash
ontoskills install core
```

需要 Python 3.10+。创建 `~/.ontoskills/core/` 作为编译器运行时。

---

## 商店命令

### `search <query>`

在 OntoStore 中搜索技能。

```bash
ontoskills search hello
ontoskills search pdf
ontoskills search "office document"
```

### `install <package-id>`

从 OntoStore 安装技能。

```bash
ontoskills install mareasw/greeting/hello
ontoskills install mareasw/office/xlsx
```

包 ID 格式：`owner/repo/skill`

### `enable <package-id>`

为 MCP 运行时重新启用已禁用的技能。

```bash
ontoskills enable mareasw/greeting/hello
```

技能安装后默认启用。使用此命令重新启用之前禁用的技能。

### `disable <package-id>`

禁用技能但不删除。

```bash
ontoskills disable mareasw/greeting/hello
```

### `remove <package-id>`

移除已安装的技能。

```bash
ontoskills remove mareasw/greeting/hello
```

### `store list`

列出配置的技能商店。

```bash
ontoskills store list
```

### `store add-source <name> <url>`

添加第三方技能商店。

```bash
ontoskills store add-source acme https://example.com/index.json
```

---

## 编译器命令

### `init-core`

初始化核心本体。

```bash
ontoskills init-core
```

创建 `ontoskills-core.ttl`，包含基础 TBox 本体（类、属性、状态定义）。

### `compile [skill]`

编译技能。

```bash
# 编译 skills/ 中的所有技能
ontoskills compile

# 编译特定技能
ontoskills compile office

# 带选项编译
ontoskills compile --force          # 跳过缓存
ontoskills compile --dry-run        # 预览但不保存
ontoskills compile --skip-security  # 跳过 LLM 安全审查
ontoskills compile -v               # 详细日志
```

| 选项 | 描述 |
|------|------|
| `-i, --input` | 输入目录（默认：`skills/`）|
| `-o, --output` | 输出目录（默认：`ontoskills/`）|
| `--dry-run` | 预览但不保存 |
| `--skip-security` | 跳过 LLM 安全审查 |
| `-f, --force` | 强制重新编译 |
| `-y, --yes` | 跳过确认提示 |
| `-v, --verbose` | 调试日志 |
| `-q, --quiet` | 抑制进度输出 |

### `query <sparql>`

对已编译的本体运行 SPARQL 查询。

```bash
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
ontoskills query "SELECT ?intent WHERE { ?skill oc:resolvesIntent ?intent }"
```

### `list-skills`

列出所有已编译的技能。

```bash
ontoskills list-skills
```

### `security-audit`

对所有技能运行安全审计。

```bash
ontoskills security-audit
```

---

## 管理命令

### `update [target]`

更新组件或技能。

```bash
ontoskills update mcp
ontoskills update core
ontoskills update mareasw/office/xlsx
```

### `rebuild-index`

重建本体索引。

```bash
ontoskills rebuild-index
```

### `doctor`

诊断安装问题。

```bash
ontoskills doctor
```

检查：
- MCP 二进制文件存在且可执行
- 核心本体有效
- 环境变量已设置
- 索引一致

---

## 卸载

### `uninstall --all`

删除整个托管主目录。

```bash
ontoskills uninstall --all
```

**警告：** 这会删除 `~/.ontoskills/` 下的所有内容。

---

## 托管主目录结构

```text
~/.ontoskills/
├── bin/
│   └── ontomcp           # MCP 服务器二进制文件
├── core/                  # 编译器运行时（如果已安装）
├── ontologies/            # 已编译的本体包
│   ├── ontoskills-core.ttl
│   ├── index.ttl
│   ├── system/            # 系统级文件
│   │   └── index.enabled.ttl  # 已启用技能清单
│   └── */ontoskill.ttl
├── skills/                # 源技能
│   └── vendor/            # 导入的仓库
└── state/                 # 锁定文件和元数据
    ├── registry.sources.json
    └── registry.lock.json
```

---

## 环境变量

| 变量 | 描述 | 默认值 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | API key | 必需 |
| `ANTHROPIC_BASE_URL` | API 基础 URL | `https://api.anthropic.com` |
| `ONTOSKILLS_HOME` | 托管主目录 | `~/.ontoskills` |

---

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 一般错误 |
| 2 | 无效参数 |
| 3 | 技能未找到 |
| 4 | 安全错误 |
| 5 | 验证错误 |
| 6 | 网络错误 |

---

## 另见

- [快速开始](/zh/getting-started/) — 安装教程
- [OntoCore](/zh/ontocore/) — 编译器参考
- [商店](/zh/store/) — 包管理详情
- [故障排除](/zh/troubleshooting/) — 常见问题
