---
name: setup-taos-mcp
description: 为当前项目注册 TDengine（TaoS）时序数据库 MCP 服务器。如项目已有 .codex-mcp/taos-db-mcp/run.sh 则直接复用；否则从技能模板自动创建完整实现（Java 源码 + run.sh）。同时创建 ~/.codex/secrets/taos-db.env 连接配置、写入 .mcp.json、更新 .claude/settings.json 免确认授权。适用于用户要求"注册 TDengine MCP"、"setup taos mcp"、"创建 taos 数据库 mcp"等场景。
---

# setup-taos-mcp

为当前项目注册 TDengine（TaoS）时序数据库 MCP 服务器，支持全量创建和复用两种模式。

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
mkdir -p "$(pwd)/.codex-mcp/taos-db-mcp/build"
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

TDengine RESTful 驱动需要以下 JAR（从本地 Maven 仓库查找）：

```bash
find ~/.m2/repository/com/taosdata/jdbc/taos-jdbcdriver -name "taos-jdbcdriver-*.jar" | grep -v sources | grep -v javadoc | sort -V | tail -1
find ~/.m2/repository/org/apache/httpcomponents/httpclient -name "httpclient-*.jar" | grep -v sources | sort -V | tail -1
find ~/.m2/repository/org/apache/httpcomponents/httpcore -name "httpcore-*.jar" | grep -v sources | sort -V | tail -1
find ~/.m2/repository/commons-logging/commons-logging -name "commons-logging-*.jar" | grep -v sources | sort -V | tail -1
find ~/.m2/repository/commons-codec/commons-codec -name "commons-codec-*.jar" | grep -v sources | sort -V | tail -1
find ~/.m2/repository/com/alibaba/fastjson -name "fastjson-*.jar" | grep -v sources | sort -V | tail -1
find ~/.m2/repository/com/google/guava/guava -name "guava-*.jar" | grep -v sources | sort -V | tail -1
find ~/.m2/repository/org/java-websocket -name "Java-WebSocket-*.jar" | grep -v sources | sort -V | tail -1
```

如果某个 JAR 找不到，提示用户：
- 该项目是否依赖 `com.taosdata.jdbc:taos-jdbcdriver`（在 pom.xml 中检查）
- 或手动执行 `mvn dependency:resolve` 以下载缺失依赖

#### 2.4 试编译验证

```bash
TAOS_JAR=$(find ~/.m2/repository/com/taosdata/jdbc/taos-jdbcdriver -name "*.jar" | grep -v sources | sort -V | tail -1)
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

向用户询问以下连接参数（如果用户已在对话中提供则直接使用，不重复询问）：

| 参数 | 说明 | 示例 |
|------|------|------|
| `TAOS_MCP_HOST` | TDengine 服务器地址 | `8.138.127.55` |
| `TAOS_MCP_PORT` | RESTful 端口（通常 6041 或自定义） | `18809` |
| `TAOS_MCP_DATABASE` | 默认数据库名 | `mytest` |
| `TAOS_MCP_USER` | 用户名 | `root` |
| `TAOS_MCP_PASSWORD` | 密码 | `taosdata` |
| `TAOS_MCP_WRITABLE` | 是否允许写入（时序数据通常只读） | `false` |

### 第五步：创建/更新 secrets 文件

将连接配置写入 `~/.codex/secrets/taos-db.env`（如文件已存在则覆盖）：

```bash
mkdir -p ~/.codex/secrets
cat > ~/.codex/secrets/taos-db.env << 'SECRETS_EOF'
export TAOS_JDBC_JAR=<taos-jdbcdriver JAR 绝对路径>
export HTTPCLIENT_JAR=<httpclient JAR 绝对路径>
export HTTPCORE_JAR=<httpcore JAR 绝对路径>
export COMMONS_LOGGING_JAR=<commons-logging JAR 绝对路径>
export COMMONS_CODEC_JAR=<commons-codec JAR 绝对路径>
export FASTJSON_JAR=<fastjson JAR 绝对路径>
export GUAVA_JAR=<guava JAR 绝对路径>
export JAVA_WEBSOCKET_JAR=<Java-WebSocket JAR 绝对路径>
export TAOS_MCP_HOST=<host>
export TAOS_MCP_PORT=<port>
export TAOS_MCP_DATABASE=<database>
export TAOS_MCP_USER=<user>
export TAOS_MCP_PASSWORD_ENV=TAOS_MCP_PASSWORD
export TAOS_MCP_PASSWORD=<password>
export TAOS_MCP_WRITABLE=<true|false>
SECRETS_EOF
```

用第二步找到的实际 JAR 路径和第四步收集的连接参数填入。

### 第六步：写入/更新 .mcp.json

读取现有 `.mcp.json`（如有），在 `mcpServers` 中添加/更新 `{前缀}-taos-database` 条目，**保留已有条目**：

```json
{
  "mcpServers": {
    "{前缀}-taos-database": {
      "command": "{项目绝对路径}/.codex-mcp/taos-db-mcp/run.sh"
    }
  }
}
```

### 第七步：更新 .claude/settings.json 权限

读取 `$(pwd)/.claude/settings.json`，在 `permissions.allow` 数组中添加（如不存在）：

```json
"mcp__{前缀}-taos-database__*"
```

如果 `settings.json` 不存在，**不创建**，仅告知用户手动添加。

### 第八步：连接验证

```bash
source ~/.codex/secrets/taos-db.env
BUILD_DIR="$(pwd)/.codex-mcp/taos-db-mcp/build/classes"
CLASSPATH="$TAOS_JDBC_JAR:$HTTPCLIENT_JAR:$HTTPCORE_JAR:$COMMONS_LOGGING_JAR:$COMMONS_CODEC_JAR:$FASTJSON_JAR:$GUAVA_JAR:$JAVA_WEBSOCKET_JAR"

(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'; sleep 0.5; \
 echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health_check","arguments":{}}}'; sleep 4) | \
  java -cp "$BUILD_DIR:$CLASSPATH" com.gzzn.mcp.taosdb.TaosDbMcpServer 2>&1
```

成功输出示例：
```
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"ok: connected to ..."}]}}
```

### 第九步：输出结果

报告：
- MCP 服务器名称（如 `aiot-taos-database`）
- run.sh 路径
- secrets 文件路径
- 连接验证结果（成功/失败）
- **提示用户重启 Claude Code 使 MCP 配置生效**

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

**Q: 编译报 `NoClassDefFoundError`**  
A: 缺少依赖 JAR。检查 secrets 文件中的 JAR 路径是否正确，运行第二步的 `find` 命令重新定位。

**Q: health_check 超时无响应**  
A: TDengine RESTful 端口（通常 6041 或项目自定义端口）未开放，或服务未启动。确认 `TAOS_MCP_HOST:TAOS_MCP_PORT` 可访问。

**Q: TDengine RESTful 端口是多少？**  
A: 默认 6041；如服务器做了端口映射（如本项目用 18809），以实际映射端口为准。可从项目 `bootstrap-pro.yml` 中的 `jdbc:TAOS-RS://host:port/` 读取。

**Q: guava JAR 找不到**  
A: 有多个版本时取最高版本。若完全没有，说明项目未引入 TDengine 驱动依赖，先在 pom.xml 中添加并执行 `mvn dependency:resolve`。
