#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$BASE_DIR/build/classes"
TAOS_JDBC_JAR="${TAOS_JDBC_JAR:-}"
HTTPCLIENT_JAR="${HTTPCLIENT_JAR:-}"
HTTPCORE_JAR="${HTTPCORE_JAR:-}"
COMMONS_LOGGING_JAR="${COMMONS_LOGGING_JAR:-}"
COMMONS_CODEC_JAR="${COMMONS_CODEC_JAR:-}"
FASTJSON_JAR="${FASTJSON_JAR:-}"
GUAVA_JAR="${GUAVA_JAR:-}"
JAVA_WEBSOCKET_JAR="${JAVA_WEBSOCKET_JAR:-}"

SECRETS_DIR="$HOME/.codex/secrets"
if [ -d "$SECRETS_DIR" ]; then
  for env_file in "$SECRETS_DIR"/*.env; do
    [ -r "$env_file" ] && source "$env_file"
  done
fi

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
