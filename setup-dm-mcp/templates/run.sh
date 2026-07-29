#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$BASE_DIR/build/classes"
SRC="$BASE_DIR/src/main/java/com/gzzn/mcp/dmdb/DmDbMcpServer.java"
CLASS="$BUILD_DIR/com/gzzn/mcp/dmdb/DmDbMcpServer.class"

# 连接参数（DM_MCP_HOST/PORT/SCHEMA/USER、DM_PASSWORD）由 MCP 注册环境（.mcp.json 的 env）提供。
# 本脚本只负责定位达梦 JDBC 驱动 JAR：优先用环境变量 DM_JDBC_JAR，否则自动从本地 Maven 仓库取最高版本。
DM_JDBC_JAR="${DM_JDBC_JAR:-}"
if [ -z "$DM_JDBC_JAR" ]; then
  DM_JDBC_JAR="$(find "$HOME/.m2/repository" -iname 'dm8-jdbc-*.jar' -o -iname 'DmJdbcDriver*.jar' 2>/dev/null \
    | grep -vi sources | grep -vi javadoc | sort -V | tail -1)"
fi

if [ ! -f "$DM_JDBC_JAR" ]; then
  echo "DM_JDBC_JAR is not set and no DM JDBC driver jar was found under ~/.m2. Set DM_JDBC_JAR to the driver path." >&2
  exit 1
fi

if [ ! -f "$CLASS" ] || [ "$SRC" -nt "$CLASS" ]; then
  mkdir -p "$BUILD_DIR"
  javac -encoding UTF-8 -cp "$DM_JDBC_JAR" -d "$BUILD_DIR" "$SRC"
fi

exec java -cp "$BUILD_DIR:$DM_JDBC_JAR" com.gzzn.mcp.dmdb.DmDbMcpServer
