---
name: setup-redis-mcp
description: 为当前项目注册 Redis MCP 服务器。如项目已有 .codex-mcp/redis-mcp/run.sh 则直接复用；否则从技能模板自动创建完整实现（纯 Java 实现，零依赖，内置 RESP 协议）。同时创建 ~/.codex/secrets/redis.env 连接配置、写入 .mcp.json、更新 .claude/settings.json 免确认授权。适用于用户要求"注册 Redis MCP"、"setup redis mcp"、"创建 redis mcp"、"生成 redis mcp"等场景。
---

# setup-redis-mcp

为当前项目注册 Redis MCP 服务器，支持全量创建和复用两种模式。  
实现为纯 Java，**零第三方依赖**，内置 RESP 协议，只需 JDK 即可运行。

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

向用户询问以下连接参数（如果用户已在对话中提供则直接使用，不重复询问）。  
也可尝试从项目配置自动读取（如 `bootstrap-pro.yml` 中的 `spring.redis.*`）：

| 参数 | 说明 | 示例 |
|------|------|------|
| `REDIS_MCP_HOST` | Redis 服务器地址 | `8.138.127.55` |
| `REDIS_MCP_PORT` | Redis 端口 | `18803` |
| `REDIS_MCP_DATABASE` | 数据库编号（通常 0） | `0` |
| `REDIS_MCP_PASSWORD` | 密码（无密码时留空） | `Gzzn@2024` |
| `REDIS_MCP_WRITABLE` | 是否允许写入（缓存场景通常只读） | `false` |

**自动读取 Spring Boot 配置的参考路径：**

```bash
grep -A 10 "redis:" "$(pwd)/*/src/main/resources/bootstrap-pro.yml" 2>/dev/null | head -20
```

### 第五步：创建/更新 secrets 文件

将连接配置写入 `~/.codex/secrets/redis.env`（如文件已存在则覆盖）：

```bash
mkdir -p ~/.codex/secrets
cat > ~/.codex/secrets/redis.env << 'SECRETS_EOF'
export REDIS_MCP_HOST=<host>
export REDIS_MCP_PORT=<port>
export REDIS_MCP_DATABASE=<database>
export REDIS_MCP_PASSWORD_ENV=REDIS_MCP_PASSWORD
export REDIS_MCP_PASSWORD=<password>
export REDIS_MCP_WRITABLE=<true|false>
SECRETS_EOF
```

用第四步收集的实际参数填入。

### 第六步：写入/更新 .mcp.json

读取现有 `.mcp.json`（如有），在 `mcpServers` 中添加/更新 `{前缀}-redis` 条目，**保留已有条目**：

```json
{
  "mcpServers": {
    "{前缀}-redis": {
      "command": "{项目绝对路径}/.codex-mcp/redis-mcp/run.sh"
    }
  }
}
```

### 第七步：更新 .claude/settings.json 权限

读取 `$(pwd)/.claude/settings.json`，在 `permissions.allow` 数组中添加（如不存在）：

```json
"mcp__{前缀}-redis__*"
```

如果 `settings.json` 不存在，**不创建**，仅告知用户手动添加。

### 第八步：连接验证

```bash
source ~/.codex/secrets/redis.env
BUILD_DIR="$(pwd)/.codex-mcp/redis-mcp/build/classes"

echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health_check","arguments":{}}}' | \
  java -cp "$BUILD_DIR" com.gzzn.mcp.redis.RedisMcpServer 2>&1
```

成功输出示例：
```
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"ok: PONG — connected to host:port db=0"}]}}
```

### 第九步：输出结果

报告：
- MCP 服务器名称（如 `aiot-redis`）
- run.sh 路径
- secrets 文件路径
- 连接验证结果（成功/失败）
- **提示用户重启 Claude Code 使 MCP 配置生效**

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

**Q: health_check 返回 `Redis error: NOAUTH Authentication required`**  
A: `REDIS_MCP_PASSWORD` 未设置或密码错误，检查 `~/.codex/secrets/redis.env`。

**Q: health_check 连接超时**  
A: Redis 端口未开放，或防火墙拦截。确认 `REDIS_MCP_HOST:REDIS_MCP_PORT` 可访问：`nc -zv <host> <port>`。

**Q: 如何从 Spring Boot 项目自动获取 Redis 配置？**  
A: 查看项目的 `bootstrap-pro.yml` 或 `application.yml` 中 `spring.redis.host/port/password/database` 字段。

**Q: keys 工具返回太多结果怎么办？**  
A: 使用 pattern 缩小范围（如 `user:*`）并设置 `limit` 参数，避免扫描全库。生产环境慎用 `*` pattern。