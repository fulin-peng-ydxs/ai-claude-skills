#!/usr/bin/env bash
set -euo pipefail

repo="${1:-/Users/pengshuaifeng/ai-trend-analysis}"

cd "$repo"
node scripts/validate-knowledge-base.js
