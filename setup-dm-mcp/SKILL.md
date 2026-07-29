---
name: setup-dm-mcp
description: 为当前项目注册达梦（DM）数据库 MCP 服务器。如项目已有 .codex-mcp/dm-db-mcp/run.sh 则直接复用；否则从技能模板自动创建完整实现（Java 源码 + run.sh）。连接参数直接写入 .mcp.json 的 env（不使用 ~/.codex/secrets），并更新 .claude/settings.json 免确认授权、执行 health_check 连接验证。适用于用户要求"注册 DM MCP"、"setup dm mcp"、"创建达梦数据库 mcp"等场景。
---

# setup-dm-mcp

为当前项目注册达梦（DM）数据库 MCP 服务器，支持全量创建和复用两种模式。

**核心约定**：所有连接参数（host/port/schema/user/password）和 JDBC 驱动路径都直接写进项目 `.mcp.json` 的 `env` 字段，**不使用 `~/.codex/secrets/*.env`**。

## 技能文件位置

本技能位于 `~/.claude/skills/setup-dm-mcp/`，其中：
- `templates/DmDbMcpServer.java` — MCP 服务器 Java 实现（达梦 JDBC 驱动）
- `templates/run.sh` — 启动脚本模板（自动从本地 Maven 仓库定位 DM JDBC 驱动）

---

## 执行步骤

### 第一步：检查 MCP 实现是否已存在

```bash
ls "$(pwd)/.codex-mcp/dm-db-mcp/run.sh" 2>/dev/null && echo "FOUND" || echo "NOT_FOUND"
```

- **`FOUND`** → 跳到第三步（直接复用，只需注册）
- **`NOT_FOUND`** → 继续第二步（从模板创建）

### 第二步：从模板创建 MCP 实现（仅 NOT_FOUND 时执行）

#### 2.1 创建目录结构

```bash
mkdir -p "$(pwd)/.codex-mcp/dm-db-mcp/src/main/java/com/gzzn/mcp/dmdb"
mkdir -p "$(pwd)/.codex-mcp/dm-db-mcp/build/classes"
```

#### 2.2 复制 Java 源码和 run.sh

读取技能模板文件并写入项目：

- 读取 `~/.claude/skills/setup-dm-mcp/templates/DmDbMcpServer.java`，写入 `$(pwd)/.codex-mcp/dm-db-mcp/src/main/java/com/gzzn/mcp/dmdb/DmDbMcpServer.java`
- 读取 `~/.claude/skills/setup-dm-mcp/templates/run.sh`，写入 `$(pwd)/.codex-mcp/dm-db-mcp/run.sh`

设置执行权限：
```bash
chmod +x "$(pwd)/.codex-mcp/dm-db-mcp/run.sh"
```

#### 2.3 定位达梦 JDBC 驱动 JAR

从本地 Maven 仓库查找（取最高版本，排除 sources/javadoc）：

```bash
find ~/.m2/repository -iname 'dm8-jdbc-*.jar' -o -iname 'DmJdbcDriver*.jar' 2>/dev/null \
  | grep -vi sources | grep -vi javadoc | sort -V | tail -1
```

如果找不到，提示用户：
- 该项目是否依赖达梦驱动（在 pom.xml 中检查 `com.dm:dm8-jdbc` 或 `com.dameng:Dm8JdbcDriver`）
- 或手动执行 `mvn dependency:resolve` 下载驱动

记此路径为 `DM_JDBC_JAR`，第六步写入 `.mcp.json`。

#### 2.4 试编译验证

```bash
BUILD_DIR="$(pwd)/.codex-mcp/dm-db-mcp/build/classes"
javac -encoding UTF-8 -cp "$DM_JDBC_JAR" -d "$BUILD_DIR" \
  "$(pwd)/.codex-mcp/dm-db-mcp/src/main/java/com/gzzn/mcp/dmdb/DmDbMcpServer.java" 2>&1
```

编译成功则继续；失败则检查 Java 版本（需要 Java 8+）和 JAR 路径。

### 第三步：推导 MCP 名称

```bash
basename "$(pwd)"
```

规则：取目录名，按 `-` 分割取第一段，拼接 `-dm-database`。
例：`aiot-admin` → 前缀 `aiot` → MCP 名称 `aiot-dm-database`

### 第四步：收集 DM 连接信息

优先从项目配置自动读取；读不到再询问用户（若对话中已提供则直接用，不重复询问）。

**自动读取 Spring Boot 配置的参考命令：**

```bash
grep -iE "jdbc:dm://|driver-class-name|username|password" \
  "$(pwd)"/*/src/main/resources/bootstrap-pro.yml 2>/dev/null | head
```

从 `url: jdbc:dm://<host>:<port>/<schema>?...` 中解析出 host、port、schema；username/password 取对应字段。

| 参数 | 说明 | 示例 |
|------|------|------|
| `DM_MCP_HOST` | DM 服务器地址 | `10.100.101.158` |
| `DM_MCP_PORT` | DM 端口（默认 5236） | `5236` |
| `DM_MCP_SCHEMA` | 模式名（通常同用户名） | `AIOT` |
| `DM_MCP_USER` | 用户名 | `AIOT` |
| `DM_PASSWORD` | 密码 | `Gzzndba2024` |
| `DM_MCP_WRITABLE` | 是否允许写入（默认只读 false） | `false` |

### 第五步：写入/更新 .mcp.json

读取现有 `.mcp.json`（如有），在 `mcpServers` 中添加/更新 `{前缀}-dm-database` 条目，**保留已有条目**。**连接参数和驱动路径全部写进 `env`**：

```json
{
  "mcpServers": {
    "{前缀}-dm-database": {
      "command": "{项目绝对路径}/.codex-mcp/dm-db-mcp/run.sh",
      "env": {
        "DM_JDBC_JAR": "{2.3 找到的驱动绝对路径}",
        "DM_MCP_HOST": "{host}",
        "DM_MCP_PORT": "{port}",
        "DM_MCP_SCHEMA": "{schema}",
        "DM_MCP_USER": "{user}",
        "DM_PASSWORD": "{password}",
        "DM_MCP_WRITABLE": "false"
      }
    }
  }
}
```

> 说明：`DmDbMcpServer.java` 默认通过 `DM_MCP_PASSWORD_ENV`（默认值为 `DM_PASSWORD`）指定的环境变量读取密码，因此在 `env` 里直接放 `DM_PASSWORD` 即可。

### 第六步：更新 .claude/settings.json 权限

读取 `$(pwd)/.claude/settings.json`，在 `permissions.allow` 数组中添加（如不存在）：

```json
"mcp__{前缀}-dm-database__*"
```

如果 `settings.json` 不存在，**不创建**，仅告知用户手动添加。

### 第七步：连接验证

用与 `.mcp.json` 相同的环境变量，直接驱动 run.sh 做一次 `health_check`：

```bash
{
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'
  printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health_check","arguments":{}}}'
  sleep 5
} | DM_JDBC_JAR="{驱动路径}" DM_MCP_HOST="{host}" DM_MCP_PORT="{port}" \
    DM_MCP_SCHEMA="{schema}" DM_MCP_USER="{user}" DM_PASSWORD="{password}" \
    "$(pwd)/.codex-mcp/dm-db-mcp/run.sh" 2>&1 | tail -1
```

成功输出示例：
```
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"ok: connected to host:5236/SCHEMA"}]}}
```

### 第八步：输出结果

报告：
- MCP 服务器名称（如 `aiot-dm-database`）
- run.sh 路径、JDBC 驱动路径
- 连接验证结果（成功/失败）
- **提示用户重启 Claude Code（或 reconnect 该 MCP）使配置生效**
- 提示：密码以明文存于 `.mcp.json`，若该文件纳入版本控制需注意泄露风险

---

## MCP 工具说明

注册成功后，可使用以下工具（名称前缀为 MCP 名称，如 `mcp__aiot-dm-database__health_check`）：

| 工具 | 说明 |
|------|------|
| `health_check` | 测试 DM 连接 |
| `list_tables` | 列出 schema 下所有表/视图 |
| `describe_table` | 查看表结构（字段、类型、可空、备注） |
| `query_sql` | 执行只读 SELECT/WITH 查询，默认最多 1000 行 |
| `execute_sql` | 执行 INSERT/UPDATE/DELETE，dry_run 默认 true；禁用 DDL 关键字 |

**安全策略**：默认只读（`DM_MCP_WRITABLE=false`）；写操作要求 `requireWhere`（默认强制 WHERE）且禁用 CREATE/ALTER/DROP/TRUNCATE/GRANT 等关键字。

---

## 常见问题

**Q: run.sh 报 `DM_JDBC_JAR is not set ... no DM JDBC driver jar was found`**
A: 本地 Maven 仓库没有达梦驱动。在 pom.xml 加入驱动依赖并 `mvn dependency:resolve`，或在 `.mcp.json` 的 `env.DM_JDBC_JAR` 显式指定驱动路径。

**Q: health_check 连接超时**
A: DM 端口（默认 5236）未开放或服务未启动。确认 `DM_MCP_HOST:DM_MCP_PORT` 可访问：`nc -zv <host> <port>`。

**Q: 连接报认证失败**
A: 检查 `.mcp.json` 中 `DM_MCP_USER` / `DM_PASSWORD` 是否正确，以及 `DM_MCP_SCHEMA` 是否有访问权限。

**Q: 多个 dm8-jdbc 版本取哪个？**
A: `sort -V | tail -1` 取最高版本。若需固定版本，在 `.mcp.json` 的 `env.DM_JDBC_JAR` 写死路径即可（run.sh 优先使用该变量）。
