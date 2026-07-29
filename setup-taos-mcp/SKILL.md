---
name: setup-taos-mcp
description: 为当前项目注册 TDengine（TaoS）时序数据库 MCP 服务器。如项目已有 .codex-mcp/taos-db-mcp/run.sh 则直接复用；否则从技能模板自动创建完整实现（Java 源码 + run.sh）。连接参数直接写入 .mcp.json 的 env（不使用 ~/.codex/secrets），并更新 .claude/settings.json 免确认授权、执行 health_check 连接验证。适用于用户要求"注册 TDengine MCP"、"setup taos mcp"、"创建 taos 数据库 mcp"等场景。
---

# setup-taos-mcp

为当前项目注册 TDengine（TaoS）时序数据库 MCP 服务器，支持全量创建和复用两种模式。

**核心约定**：所有连接参数（host/port/database/user/password）直接写进项目 `.mcp.json` 的 `env` 字段，**不使用 `~/.codex/secrets/*.env`**。JDBC 依赖 JAR 由 run.sh 从本地 Maven 仓库按默认路径定位（可被同名环境变量覆盖）。

## 技能文件位置

本技能位于 `~/.claude/skills/setup-taos-mcp/`，其中：
- `templates/TaosDbMcpServer.java` — MCP 服务器 Java 实现（RESTful 驱动，无需本地 TDengine 客户端）
- `templates/run.sh` — 启动脚本模板

---

## 执行步骤

### 第一步：检查 MCP 实现是否已存在

```bash
ls "$(pwd)/.codex-mcp/taos-db-mcp/run.sh" 2>/dev/null && echo "FOUND" || echo "NOT_FOUND"
```

- **`FOUND`** → 跳到第三步（直接复用，只需注册）
- **`NOT_FOUND`** → 继续第二步（从模板创建）

### 第二步：从模板创建 MCP 实现（仅 NOT_FOUND 时执行）

#### 2.1 创建目录结构

```bash
mkdir -p "$(pwd)/.codex-mcp/taos-db-mcp/src/main/java/com/gzzn/mcp/taosdb"
mkdir -p "$(pwd)/.codex-mcp/taos-db-mcp/build/classes"
```

#### 2.2 复制 Java 源码和 run.sh

读取技能模板文件并写入项目：

- 读取 `~/.claude/skills/setup-taos-mcp/templates/TaosDbMcpServer.java`，写入 `$(pwd)/.codex-mcp/taos-db-mcp/src/main/java/com/gzzn/mcp/taosdb/TaosDbMcpServer.java`
- 读取 `~/.claude/skills/setup-taos-mcp/templates/run.sh`，写入 `$(pwd)/.codex-mcp/taos-db-mcp/run.sh`

设置执行权限：
```bash
chmod +x "$(pwd)/.codex-mcp/taos-db-mcp/run.sh"
```

#### 2.3 定位所需依赖 JAR

TDengine RESTful 驱动需要以下 JAR（从本地 Maven 仓库查找最高版本，排除 sources/javadoc）：

```bash
find ~/.m2/repository/com/taosdata/jdbc/taos-jdbcdriver -name "taos-jdbcdriver-*.jar" 2>/dev/null | grep -vi sources | grep -vi javadoc | sort -V | tail -1
find ~/.m2/repository/org/apache/httpcomponents/httpclient -name "httpclient-*.jar" 2>/dev/null | grep -vi sources | sort -V | tail -1
find ~/.m2/repository/org/apache/httpcomponents/httpcore -name "httpcore-*.jar" 2>/dev/null | grep -vi sources | sort -V | tail -1
find ~/.m2/repository/commons-logging/commons-logging -name "commons-logging-*.jar" 2>/dev/null | grep -vi sources | sort -V | tail -1
find ~/.m2/repository/commons-codec/commons-codec -name "commons-codec-*.jar" 2>/dev/null | grep -vi sources | sort -V | tail -1
find ~/.m2/repository/com/alibaba/fastjson -name "fastjson-*.jar" 2>/dev/null | grep -vi sources | grep -vi javadoc | sort -V | tail -1
find ~/.m2/repository/com/google/guava/guava -name "guava-*.jar" 2>/dev/null | grep -vi sources | sort -V | tail -1
find ~/.m2/repository/org/java-websocket -name "Java-WebSocket-*.jar" 2>/dev/null | grep -vi sources | sort -V | tail -1
```

模板 run.sh 已内置这些 JAR 的默认路径；若你的版本不同，可在 `.mcp.json` 的 `env` 用同名变量（`TAOS_JDBC_JAR`、`HTTPCLIENT_JAR` 等）覆盖。

如果某个 JAR 找不到，提示用户：
- 该项目是否依赖 `com.taosdata.jdbc:taos-jdbcdriver`（在 pom.xml 中检查）
- 或手动执行 `mvn dependency:resolve` 以下载缺失依赖

#### 2.4 试编译验证

```bash
TAOS_JAR=$(find ~/.m2/repository/com/taosdata/jdbc/taos-jdbcdriver -name "taos-jdbcdriver-*.jar" 2>/dev/null | grep -vi sources | grep -vi javadoc | sort -V | tail -1)
BUILD_DIR="$(pwd)/.codex-mcp/taos-db-mcp/build/classes"
mkdir -p "$BUILD_DIR"
javac -encoding UTF-8 -cp "$TAOS_JAR" -d "$BUILD_DIR" \
  "$(pwd)/.codex-mcp/taos-db-mcp/src/main/java/com/gzzn/mcp/taosdb/TaosDbMcpServer.java" 2>&1
```

编译成功则继续；失败则检查 Java 版本（需要 Java 8+）和 JAR 路径。

### 第三步：推导 MCP 名称

```bash
basename "$(pwd)"
```

规则：取目录名，按 `-` 分割取第一段，拼接 `-taos-database`。
例：`aiot-admin` → 前缀 `aiot` → MCP 名称 `aiot-taos-database`

### 第四步：收集 TDengine 连接信息

优先从项目配置自动读取；读不到再询问用户（若对话中已提供则直接用，不重复询问）。

**自动读取 Spring Boot 配置的参考命令：**

```bash
grep -iE "jdbc:TAOS-RS://|username|password" \
  "$(pwd)"/*/src/main/resources/bootstrap-pro.yml 2>/dev/null | head
```

从 `url: jdbc:TAOS-RS://<host>:<port>/<database>` 解析 host、port、database。

| 参数 | 说明 | 示例 |
|------|------|------|
| `TAOS_MCP_HOST` | TDengine 服务器地址 | `10.100.101.158` |
| `TAOS_MCP_PORT` | RESTful 端口（通常 6041 或自定义） | `6041` |
| `TAOS_MCP_DATABASE` | 默认数据库名 | `mytest` |
| `TAOS_MCP_USER` | 用户名 | `root` |
| `TAOS_MCP_PASSWORD` | 密码 | `taosdata` |
| `TAOS_MCP_WRITABLE` | 是否允许写入（时序数据通常只读） | `false` |

### 第五步：写入/更新 .mcp.json

读取现有 `.mcp.json`（如有），在 `mcpServers` 中添加/更新 `{前缀}-taos-database` 条目，**保留已有条目**。**连接参数全部写进 `env`**：

```json
{
  "mcpServers": {
    "{前缀}-taos-database": {
      "command": "{项目绝对路径}/.codex-mcp/taos-db-mcp/run.sh",
      "env": {
        "TAOS_MCP_HOST": "{host}",
        "TAOS_MCP_PORT": "{port}",
        "TAOS_MCP_DATABASE": "{database}",
        "TAOS_MCP_USER": "{user}",
        "TAOS_MCP_PASSWORD": "{password}",
        "TAOS_MCP_WRITABLE": "false"
      }
    }
  }
}
```

> 说明：`TaosDbMcpServer.java` 通过 `TAOS_MCP_PASSWORD_ENV`（默认 `TAOS_MCP_PASSWORD`）指定的变量读密码，`env` 直接放 `TAOS_MCP_PASSWORD` 即可。JAR 路径默认即可，无需写进 env；版本不同时再加 `TAOS_JDBC_JAR` 等覆盖。

### 第六步：更新 .claude/settings.json 权限

读取 `$(pwd)/.claude/settings.json`，在 `permissions.allow` 数组中添加（如不存在）：

```json
"mcp__{前缀}-taos-database__*"
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
} | TAOS_MCP_HOST="{host}" TAOS_MCP_PORT="{port}" TAOS_MCP_DATABASE="{database}" \
    TAOS_MCP_USER="{user}" TAOS_MCP_PASSWORD="{password}" \
    "$(pwd)/.codex-mcp/taos-db-mcp/run.sh" 2>&1 | tail -1
```

成功输出示例：
```
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"ok: connected to host:6041/mytest"}]}}
```

### 第八步：输出结果

报告：
- MCP 服务器名称（如 `aiot-taos-database`）
- run.sh 路径
- 连接验证结果（成功/失败）
- **提示用户重启 Claude Code（或 reconnect 该 MCP）使配置生效**
- 提示：密码以明文存于 `.mcp.json`，若该文件纳入版本控制需注意泄露风险

---

## MCP 工具说明

注册成功后，可使用以下工具（名称前缀为 MCP 名称）：

| 工具 | 说明 |
|------|------|
| `health_check` | 测试 TDengine 连接 |
| `list_tables` | 列出数据库下所有表（含子表） |
| `describe_table` | 查看表结构（字段、类型、TAG 标识） |
| `query_sql` | 执行只读 SELECT 查询，自动追加 LIMIT 限制行数 |
| `execute_sql` | 执行 INSERT（时序数据 append-only，默认 dry_run=true） |

---

## 常见问题

**Q: 编译/运行报 `NoClassDefFoundError`**
A: 缺少依赖 JAR。运行第二步的 `find` 命令重新定位；版本不同则在 `.mcp.json` 的 `env` 用 `TAOS_JDBC_JAR`/`HTTPCLIENT_JAR` 等覆盖。

**Q: health_check 超时无响应**
A: TDengine RESTful 端口（通常 6041 或项目自定义端口）未开放，或服务未启动。确认 `TAOS_MCP_HOST:TAOS_MCP_PORT` 可访问。

**Q: TDengine RESTful 端口是多少？**
A: 默认 6041；如服务器做了端口映射，以实际映射端口为准。可从项目 `bootstrap-pro.yml` 中的 `jdbc:TAOS-RS://host:port/` 读取。

**Q: guava/fastjson JAR 找不到**
A: 有多个版本时取最高版本（注意排除 javadoc）。若完全没有，说明项目未引入 TDengine 驱动依赖，先在 pom.xml 中添加并执行 `mvn dependency:resolve`。
