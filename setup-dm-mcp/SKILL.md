---
name: setup-dm-mcp
description: 为当前项目注册达梦数据库 MCP 服务器。检测项目是否存在 .codex-mcp/dm-db-mcp/run.sh，有则复用并写入 .mcp.json（MCP 名称以项目前缀开头，如 aiot-dm-database），没有则报错退出。同时更新 .claude/settings.json 完成免确认授权配置。
---

# setup-dm-mcp

为当前项目注册达梦数据库 MCP 服务器。

## 执行步骤

### 第一步：检查 codex DM MCP 是否存在

运行以下命令检查当前项目是否有 codex 的 DM MCP 实现：

```bash
ls "$(pwd)/.codex-mcp/dm-db-mcp/run.sh" 2>/dev/null && echo "FOUND" || echo "NOT_FOUND"
```

- 如果输出 `NOT_FOUND`，**立即停止并报错**：
  ```
  错误：当前项目没有 .codex-mcp/dm-db-mcp/run.sh，无法注册 DM MCP。
  请先在项目中创建 codex DM MCP 实现，或确认你在正确的项目目录下。
  ```
- 如果输出 `FOUND`，继续下一步。

### 第二步：推导 MCP 名称

运行以下命令获取项目目录名，并提取第一段作为前缀：

```bash
basename "$(pwd)"
```

规则：取目录名，按 `-` 分割，取第一段，拼接 `-dm-database`。
例如：`aiot-admin` → 前缀 `aiot` → MCP 名称 `aiot-dm-database`

### 第三步：确认 run.sh 绝对路径

```bash
echo "$(pwd)/.codex-mcp/dm-db-mcp/run.sh"
```

### 第四步：读取现有 .mcp.json（如果有）

```bash
cat "$(pwd)/.mcp.json" 2>/dev/null || echo "{}"
```

### 第五步：写入 .mcp.json

在项目根目录的 `.mcp.json` 中，添加或更新 `{前缀}-dm-database` 条目，**只包含 command 字段，不加任何 env**（连接信息从 `~/.codex/secrets/*.env` 自动加载）：

```json
{
  "mcpServers": {
    "{前缀}-dm-database": {
      "command": "{绝对路径}/.codex-mcp/dm-db-mcp/run.sh"
    }
  }
}
```

如果 `.mcp.json` 已有其他 mcpServers 条目，**保留它们**，只添加/更新 `{前缀}-dm-database`。

### 第六步：更新 .claude/settings.json 权限

读取 `$(pwd)/.claude/settings.json`，在 `permissions.allow` 数组中添加（如不存在）：

```json
"mcp__{前缀}-dm-database__*"
```

如果 `settings.json` 不存在，**不创建**，仅告知用户手动添加。

### 第七步：输出结果

报告：
- MCP 名称（如 `aiot-dm-database`）
- run.sh 路径
- 提示用户重启 Claude Code 使配置生效
- 提示用户确认 `~/.codex/secrets/` 下有对应的数据库连接配置（DM_MCP_HOST、DM_MCP_PASSWORD 等）