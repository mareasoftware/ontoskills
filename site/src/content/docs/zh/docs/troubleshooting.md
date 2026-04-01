---
title: 故障排除
description: 安装、商店访问、编译器设置和 OntoMCP 的常见问题
sidebar:
  order: 16
---

## 安装问题

### `ontoskills install mcp` 失败

检查：

- Node.js 18+ 可用
- 当前版本的发布产物存在
- 你的机器可以下载 GitHub 发布资产
- 没有代理或防火墙阻止 `github.com` 和 `api.github.com`

**错误："Failed to fetch release metadata"**

网络连接问题。检查互联网连接并重试。如果在企业代理后面：

```bash
export HTTPS_PROXY=http://proxy.example.com:8080
ontoskills install mcp
```

**错误："Release does not contain asset"**

该平台可能不受支持。检查可用平台：

```bash
# 支持：darwin-arm64, darwin-x64, linux-arm64, linux-x64
uname -m && uname -s
```

### `ontoskills install core` 失败

编译器需要 Python 3.10+：

```bash
python3 --version
```

如果已安装 Python 但找不到：

```bash
export PYTHON=/path/to/python3
ontoskills install core
```

---

## 商店和包问题

### "找不到包"

- 检查包 ID 拼写
- 运行 `ontoskills search <query>` 发现可用包
- 如果使用第三方商店，验证已配置：

```bash
ontoskills store list
```

### 商店技能未出现在 OntoMCP 中

技能安装后默认启用。如果技能不可见：

1. 检查是否被禁用：

```bash
ontoskills list-installed
```

2. 如需要，重新启用：

```bash
ontoskills enable mareasw/greeting/hello
```

3. 重建索引：

```bash
ontoskills rebuild-index
```

4. 重启 MCP 进程

### "启用后技能仍不可见"

MCP 服务器会缓存本体索引。确保：

1. 索引已重建：`ontoskills rebuild-index`
2. MCP 服务器已重启（关闭并重新打开你的 AI 客户端）
3. 检查 `~/.ontoskills/ontologies/system/index.enabled.ttl` 存在

---

## 编译器问题

### 编译器命令失败

先安装编译器：

```bash
ontoskills install core
```

然后初始化本体基础：

```bash
ontoskills init-core
```

### "ANTHROPIC_API_KEY 未设置"

编译器需要 Anthropic API key 进行基于 LLM 的知识提取：

```bash
export ANTHROPIC_API_KEY="你的-key"
ontoskills compile my-skill
```

添加到你的 shell 配置文件（`~/.bashrc`、`~/.zshrc`）以持久化。

### "SHACL 验证失败"

你的技能缺少必需字段。检查：

- 至少一个 `resolvesIntent`（在"何时使用"部分）
- 顶部有清晰的一句话性质声明
- 正确的 YAML 前置元数据，包含 `name` 和 `description`

使用详细输出查看详情：

```bash
ontoskills compile my-skill -v
```

### "Nature not extracted"

在 SKILL.md 开头添加清晰的一句话摘要：

```markdown
# 技能标题

简短描述这个技能做什么。

## 功能
...
```

### "Missing resolvesIntent"

确保你的技能有"何时使用"或类似部分：

```markdown
## 何时使用

当用户想从 PDF 文件提取文本时使用此技能。
```

---

## 导入问题

### 导入的源仓库已编译，但技能仍然不可见

导入的技能默认启用。如果不可见：

1. 重建索引：

```bash
ontoskills rebuild-index
```

2. 重启 MCP 进程

3. 如果仍然不可见且技能之前被禁用过，重新启用它：

```bash
ontoskills enable <qualified-id>
ontoskills rebuild-index
```

### "源导入失败"

确保：

1. Git 已安装且可访问
2. 仓库 URL 正确且可访问
3. OntoCore 已安装：`ontoskills install core`

### "未找到 SKILL.md 文件"

导入过程会在仓库中查找 `SKILL.md` 文件。确保：

- 文件名完全是 `SKILL.md`（区分大小写）
- 文件在仓库根目录或子目录中
- 文件有有效的 YAML 前置元数据

---

## MCP 连接问题

### "MCP 服务器未启动"

检查二进制文件存在且可执行：

```bash
ls -la ~/.ontoskills/bin/ontomcp
```

如果缺失，重新安装：

```bash
ontoskills install mcp
```

### "Connection refused" 或 "Timeout"

MCP 服务器可能启动缓慢。检查：

1. 服务器正在运行：`ps aux | grep ontomcp`
2. 没有端口冲突
3. 系统资源充足

### "Claude Code 找不到 ontomcp"

确保 `~/.ontoskills/bin` 在你的 PATH 中，或在 MCP 配置中使用完整路径：

```json
{
  "command": "/home/user/.ontoskills/bin/ontomcp"
}
```

---

## 索引和状态问题

### "索引损坏"

从头重建：

```bash
ontoskills rebuild-index
```

如果失败，检查锁定文件：

```bash
cat ~/.ontoskills/state/registry.lock.json
```

### "状态文件缺失"

状态目录应包含：

- `registry.sources.json` — 配置的商店
- `registry.lock.json` — 已安装的包

如果缺失，它们会在下次操作时重新创建。

### "Permission denied" 错误

检查 `~/.ontoskills/` 的所有权：

```bash
ls -la ~/.ontoskills/
```

如需要，修复权限：

```bash
chmod -R u+rw ~/.ontoskills/
```

---

## 诊断工具

### `ontoskills doctor`

运行全面的健康检查：

```bash
ontoskills doctor
```

这会检查：

- MCP 二进制文件存在且可执行
- 核心本体有效
- 环境变量已设置
- 索引一致
- 可用更新

### 详细输出

大多数命令支持 `-v` 获取详细日志：

```bash
ontoskills compile my-skill -v
ontoskills install mcp -v
```

---

## 重置和恢复

### 重置所有内容

删除整个托管主目录：

```bash
ontoskills uninstall --all
```

**警告：** 这会删除 `~/.ontoskills/` 下的所有内容。

### 从头重新安装

```bash
ontoskills uninstall --all
ontoskills install mcp
ontoskills install core  # 如需要
ontoskills init-core     # 如需要
# 重新安装技能
ontoskills install mareasw/greeting/hello
```

---

## 获取帮助

如果你的问题未在此处涵盖：

1. 运行 `ontoskills doctor` 并检查输出
2. 在 GitHub 上搜索现有问题
3. 提交新问题，包含：
   - `ontoskills doctor` 输出
   - 失败的命令
   - 错误消息
   - 你的操作系统和版本
