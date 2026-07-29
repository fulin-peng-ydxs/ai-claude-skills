---
name: setup-redis-mcp
description: 为当前项目注册 Redis MCP 服务器。如项目已有 .codex-mcp/redis-mcp/run.sh 则直接复用；否则从技能模板自动创建完整实现（纯 Java 实现，零依赖，内置 RESP 协议）。连接参数直接写入 .mcp.json 的 env（不使用 ~/.codex/secrets），并更新 .claude/settings.json 免确认授权、执行 health_check 连接验证。适用于用户要求"注册 Redis MCP"、"setup redis mcp"、"创建 redis mcp"、"生成 redis mcp"等场景。
---

# setup-redis-mcp

为当前项目注册 Redis MCP 服务器，支持全量创建和复用两种模式。
实现为纯 Java，**零第三方依赖**，内置 RESP 协议，只需 JDK 即可运行。

**核心约定**：所有连接参数（host/port/database/password）直接写进项目 `.mcp.json` 的 `env` 字段，**不使用 `~/.codex/secrets/*.env`**。

## 技能文件位置

本技能位于 `~/.claude/skills/setup-redis-mcp/`，其中：
- `templates/RedisMcpServer.java` — MCP 服务器 Java 实现（纯 Java，内置 RESP 协议）
- `templates/run.sh` — 启动脚本模板

---

## 执行步骤

### 第一步：检查 MCP 实现是否已存在

```bash
ls "$(pwd)/.codex-mcp/redis-mcp/run.sh" 2>/dev/null && echo "FOUND" || echo "NOT_FOUND"
```

- **`FOUND`** → 跳到第三步（直接复用，只需注册）
- **`NOT_FOUND`** → 继续第二步（从模板创建）

### 第二步：从模板创建 MCP 实现（仅 NOT_FOUND 时执行）

#### 2.1 创建目录结构

```bash
mkdir -p "$(pwd)/.codex-mcp/redis-mcp/src/main/java/com/gzzn/mcp/redis"
mkdir -p "$(pwd)/.codex-mcp/redis-mcp/build/classes"
```

#### 2.2 复制 Java 源码和 run.sh

读取技能模板文件并写入项目：

- 读取 `~/.claude/skills/setup-redis-mcp/templates/RedisMcpServer.java`，写入 `$(pwd)/.codex-mcp/redis-mcp/src/main/java/com/gzzn/mcp/redis/RedisMcpServer.java`
- 读取 `~/.claude/skills/setup-redis-mcp/templates/run.sh`，写入 `$(pwd)/.codex-mcp/redis-mcp/run.sh`

设置执行权限：
```bash
chmod +x "$(pwd)/.codex-mcp/redis-mcp/run.sh"
```

#### 2.3 试编译验证（零依赖，直接编译）

```bash
BUILD_DIR="$(pwd)/.codex-mcp/redis-mcp/build/classes"
mkdir -p "$BUILD_DIR"
javac -encoding UTF-8 -d "$BUILD_DIR" \
  "$(pwd)/.codex-mcp/redis-mcp/src/main/java/com/gzzn/mcp/redis/RedisMcpServer.java" 2>&1
```

编译成功则继续；失败则检查 Java 版本（需要 Java 8+）。
无需任何外部 JAR——这是 Redis MCP 区别于 DM/TaoS MCP 的优势。

### 第三步：推导 MCP 名称

```bash
basename "$(pwd)"
```

规则：取目录名，按 `-` 分割取第一段，拼接 `-redis`。
例：`aiot-admin` → 前缀 `aiot` → MCP 名称 `aiot-redis`

### 第四步：收集 Redis 连接信息

优先从项目配置自动读取；读不到再询问用户（若对话中已提供则直接用，不重复询问）。

**自动读取 Spring Boot 配置的参考命令：**

```bash
grep -A 8 "redis:" "$(pwd)"/*/src/main/resources/bootstrap-pro.yml 2>/dev/null | head -12
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `REDIS_MCP_HOST` | Redis 服务器地址 | `10.100.101.158` |
| `REDIS_MCP_PORT` | Redis 端口 | `6379` |
| `REDIS_MCP_DATABASE` | 数据库编号（通常 0） | `0` |
| `REDIS_MCP_PASSWORD` | 密码（无密码时留空字符串 `""`） | `""` |
| `REDIS_MCP_WRITABLE` | 是否允许写入（缓存场景通常只读） | `false` |

> 注意：若项目配置里有 `spring.redis.password`，但 Redis 服务端未启用 requirepass，连接会报 `ERR AUTH <password> called without any password configured`。此时把 `REDIS_MCP_PASSWORD` 置为空字符串 `""`。

### 第五步：写入/更新 .mcp.json

读取现有 `.mcp.json`（如有），在 `mcpServers` 中添加/更新 `{前缀}-redis` 条目，**保留已有条目**。**连接参数全部写进 `env`**：

```json
{
  "mcpServers": {
    "{前缀}-redis": {
      "command": "{项目绝对路径}/.codex-mcp/redis-mcp/run.sh",
      "env": {
        "REDIS_MCP_HOST": "{host}",
        "REDIS_MCP_PORT": "{port}",
        "REDIS_MCP_DATABASE": "{database}",
        "REDIS_MCP_PASSWORD": "{password 或空字符串}",
        "REDIS_MCP_WRITABLE": "false"
      }
    }
  }
}
```

> 说明：`RedisMcpServer.java` 通过 `REDIS_MCP_PASSWORD_ENV`（默认 `REDIS_MCP_PASSWORD`）指定的变量读密码，`env` 直接放 `REDIS_MCP_PASSWORD` 即可；空字符串表示不认证。

### 第六步：更新 .claude/settings.json 权限

读取 `$(pwd)/.claude/settings.json`，在 `permissions.allow` 数组中添加（如不存在）：

```json
"mcp__{前缀}-redis__*"
```

如果 `settings.json` 不存在，**不创建**，仅告知用户手动添加。

### 第七步：连接验证

用与 `.mcp.json` 相同的环境变量，直接驱动 run.sh 做一次 `health_check`：

```bash
{
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'
  printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health_check","arguments":{}}}'
  sleep 4
} | REDIS_MCP_HOST="{host}" REDIS_MCP_PORT="{port}" REDIS_MCP_DATABASE="{database}" \
    REDIS_MCP_PASSWORD="{password}" \
    "$(pwd)/.codex-mcp/redis-mcp/run.sh" 2>&1 | tail -1
```

成功输出示例：
```
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"ok: PONG — connected to host:6379 db=0"}]}}
```

### 第八步：输出结果

报告：
- MCP 服务器名称（如 `aiot-redis`）
- run.sh 路径
- 连接验证结果（成功/失败）
- **提示用户重启 Claude Code（或 reconnect 该 MCP）使配置生效**
- 提示：密码以明文存于 `.mcp.json`，若该文件纳入版本控制需注意泄露风险

---

## MCP 工具说明

注册成功后，可使用以下工具（名称前缀为 MCP 名称，如 `mcp__aiot-redis__health_check`）：

| 工具 | 说明 |
|------|------|
| `health_check` | PING 测试连接，返回 PONG |
| `keys` | 按 pattern 列出 key，默认 `*`，可限制返回数量 |
| `get` | 获取 key 值 + TTL，自动识别 string / hash / list / set 类型 |
| `set` | SET key value，支持 TTL，dry_run 默认 true |
| `del` | 删除 key，dry_run 默认 true |
| `ttl` | 查看 key 过期时间（-1=永不过期，-2=不存在） |
| `execute_command` | 执行任意 Redis 命令；写命令 dry_run 默认 true |

**安全策略**：`REDIS_MCP_WRITABLE=false` 时，所有写命令（SET/DEL/FLUSHDB 等）直接拒绝。写命令包含明确的 dry_run 保护，防止误操作。

---

## 常见问题

**Q: 编译失败，提示 Java 版本问题**
A: 需要 Java 8 或以上版本。运行 `java -version` 检查，或指定 `JAVA_HOME` 路径。

**Q: health_check 返回 `ERR AUTH <password> called without any password configured`**
A: Redis 服务端未启用密码，但配置里给了密码。把 `.mcp.json` 的 `REDIS_MCP_PASSWORD` 置为空字符串 `""`。

**Q: health_check 返回 `NOAUTH Authentication required`**
A: 服务端要求密码但 `REDIS_MCP_PASSWORD` 为空或错误，补正确密码。

**Q: health_check 连接超时**
A: Redis 端口未开放，或防火墙拦截。确认 `REDIS_MCP_HOST:REDIS_MCP_PORT` 可访问：`nc -zv <host> <port>`。

**Q: keys 工具返回太多结果怎么办？**
A: 使用 pattern 缩小范围（如 `user:*`）并设置 `limit` 参数，避免扫描全库。生产环境慎用 `*` pattern。
