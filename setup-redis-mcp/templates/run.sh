#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$BASE_DIR/build/classes"
SRC="$BASE_DIR/src/main/java/com/gzzn/mcp/redis/RedisMcpServer.java"
CLASS="$BUILD_DIR/com/gzzn/mcp/redis/RedisMcpServer.class"

SECRETS_DIR="$HOME/.codex/secrets"
if [ -d "$SECRETS_DIR" ]; then
  for env_file in "$SECRETS_DIR"/*.env; do
    [ -r "$env_file" ] && source "$env_file"
  done
fi

if [ ! -f "$CLASS" ] || [ "$SRC" -nt "$CLASS" ]; then
  mkdir -p "$BUILD_DIR"
  javac -encoding UTF-8 -d "$BUILD_DIR" "$SRC"
fi

exec java -cp "$BUILD_DIR" com.gzzn.mcp.redis.RedisMcpServer