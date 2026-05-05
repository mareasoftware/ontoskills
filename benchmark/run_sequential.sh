#!/usr/bin/env bash
# SkillsBench multi-mode sequential run.
# Runs all 3 modes in sequence: baseline → acp+hints → acp-mcp+hints.
# Resume-safe: only baseline gets --force-restart, the rest use --resume.
#
# Usage: ./benchmark/run_sequential.sh [--workers N] [--attempts N] [--max-tasks N]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$REPO_ROOT/benchmark_results.log"

# Source env vars if .env exists
if [ -f "$REPO_ROOT/.env" ]; then
    set -a; source "$REPO_ROOT/.env"; set +a
fi

WORKERS="${1:-2}"
ATTEMPTS="${2:-5}"
MAX_TASKS="${3:-10}"

COMMON_ARGS="--max-tasks $MAX_TASKS --model glm-5.1 --attempts $ATTEMPTS"
COMMON_ARGS="$COMMON_ARGS --workers $WORKERS"
COMMON_ARGS="$COMMON_ARGS --skillsbench-repo ~/.ontoskills/skillsbench"
COMMON_ARGS="$COMMON_ARGS --output-dir benchmark/results -v"

echo "=== RUN 1: baseline+nohints ===" >> "$LOG_FILE"
python3 benchmark/run.py --mode baseline $COMMON_ARGS --force-restart >> "$LOG_FILE" 2>&1

echo "=== RUN 2: acp+hints ===" >> "$LOG_FILE"
python3 benchmark/run.py --mode acp $COMMON_ARGS --resume >> "$LOG_FILE" 2>&1

echo "=== RUN 3: acp-mcp+hints ===" >> "$LOG_FILE"
python3 benchmark/run.py --mode acp-mcp $COMMON_ARGS --resume >> "$LOG_FILE" 2>&1

echo "=== DONE ===" >> "$LOG_FILE"
