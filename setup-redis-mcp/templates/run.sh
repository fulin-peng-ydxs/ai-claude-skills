#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$BASE_DIR/build/classes"
SRC="$BASE_DIR/src/main/java/com/gzzn/mcp/redis/RedisMcpServer.java"
CLASS="$BUILD_DIR/com/gzzn/mcp/redis/RedisMcpServer.class"

# 连接参数（REDIS_MCP_HOST/PORT/DATABASE/PASSWORD）由 MCP 注册环境（.mcp.json 的 env）提供。
# Redis MCP 为纯 Java 零依赖实现，无需任何外部 JAR。
if [ ! -f "$CLASS" ] || [ "$SRC" -nt "$CLASS" ]; then
  mkdir -p "$BUILD_DIR"
  javac -encoding UTF-8 -d "$BUILD_DIR" "$SRC"
fi

exec java -cp "$BUILD_DIR" com.gzzn.mcp.redis.RedisMcpServer
