#!/bin/bash
set -e
PORT="${PORT:-8000}"
echo "========================================================"
echo "  可持续发展报告指标平台 启动中..."
echo "  本地访问地址: http://127.0.0.1:${PORT}"
echo "========================================================"
if [ -x "./.venv/bin/python3" ]; then
  exec ./.venv/bin/python3 app.py
else
  exec python3 app.py
fi
