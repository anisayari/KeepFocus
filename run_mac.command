#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

REQ_STAMP=".venv/.requirements_installed"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -x ".venv/bin/python" ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

source ".venv/bin/activate"

if [[ ! -f "$REQ_STAMP" || requirements.txt -nt "$REQ_STAMP" ]]; then
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt
  touch "$REQ_STAMP"
fi

exec python main.py
