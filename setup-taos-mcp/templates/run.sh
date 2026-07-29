#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$BASE_DIR/build/classes"

# 连接参数（TAOS_MCP_HOST/PORT/DATABASE/USER/PASSWORD）由 MCP 注册环境（.mcp.json 的 env）提供。
# 本脚本只负责定位 JDBC 依赖 JAR：默认取本地 Maven 仓库路径，可用同名环境变量覆盖。
TAOS_JDBC_JAR="${TAOS_JDBC_JAR:-$HOME/.m2/repository/com/taosdata/jdbc/taos-jdbcdriver/3.2.7/taos-jdbcdriver-3.2.7.jar}"
HTTPCLIENT_JAR="${HTTPCLIENT_JAR:-$HOME/.m2/repository/org/apache/httpcomponents/httpclient/4.5.14/httpclient-4.5.14.jar}"
HTTPCORE_JAR="${HTTPCORE_JAR:-$HOME/.m2/repository/org/apache/httpcomponents/httpcore/4.4.16/httpcore-4.4.16.jar}"
COMMONS_LOGGING_JAR="${COMMONS_LOGGING_JAR:-$HOME/.m2/repository/commons-logging/commons-logging/1.2/commons-logging-1.2.jar}"
COMMONS_CODEC_JAR="${COMMONS_CODEC_JAR:-$HOME/.m2/repository/commons-codec/commons-codec/1.15/commons-codec-1.15.jar}"
FASTJSON_JAR="${FASTJSON_JAR:-$HOME/.m2/repository/com/alibaba/fastjson/1.2.83/fastjson-1.2.83.jar}"
GUAVA_JAR="${GUAVA_JAR:-$HOME/.m2/repository/com/google/guava/guava/32.1.3-jre/guava-32.1.3-jre.jar}"
JAVA_WEBSOCKET_JAR="${JAVA_WEBSOCKET_JAR:-$HOME/.m2/repository/org/java-websocket/Java-WebSocket/1.5.4/Java-WebSocket-1.5.4.jar}"

check_jar() {
  local var_name="$1"
  local jar_path="${!var_name}"
  if [ ! -f "$jar_path" ]; then
    echo "$var_name is not set or the file does not exist: $jar_path" >&2
    exit 1
  fi
}

check_jar TAOS_JDBC_JAR
check_jar HTTPCLIENT_JAR
check_jar HTTPCORE_JAR
check_jar COMMONS_LOGGING_JAR
check_jar COMMONS_CODEC_JAR
check_jar FASTJSON_JAR
check_jar GUAVA_JAR
check_jar JAVA_WEBSOCKET_JAR

CLASSPATH="$TAOS_JDBC_JAR:$HTTPCLIENT_JAR:$HTTPCORE_JAR:$COMMONS_LOGGING_JAR:$COMMONS_CODEC_JAR:$FASTJSON_JAR:$GUAVA_JAR:$JAVA_WEBSOCKET_JAR"

if [ ! -f "$BUILD_DIR/com/gzzn/mcp/taosdb/TaosDbMcpServer.class" ] || [ "$BASE_DIR/src/main/java/com/gzzn/mcp/taosdb/TaosDbMcpServer.java" -nt "$BUILD_DIR/com/gzzn/mcp/taosdb/TaosDbMcpServer.class" ]; then
  mkdir -p "$BUILD_DIR"
  javac -encoding UTF-8 -cp "$CLASSPATH" -d "$BUILD_DIR" "$BASE_DIR/src/main/java/com/gzzn/mcp/taosdb/TaosDbMcpServer.java"
fi

exec java -cp "$BUILD_DIR:$CLASSPATH" com.gzzn.mcp.taosdb.TaosDbMcpServer
