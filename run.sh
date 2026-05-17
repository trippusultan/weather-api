#!/usr/bin/env bash
# run.sh — bootstraps venv, loads .env, starts Flask dev server
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SP="${DIR}/venv/lib/python$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages"

export PYTHONPATH="${SP}"

if [[ -f "${DIR}/.env" ]]; then
  set -a; source "${DIR}/.env"; set +a
fi

if [[ ! -x "${DIR}/venv/bin/python" ]]; then
  echo "venv not found — run pip install -r requirements.txt first" >&2
  exit 1
fi

exec "${DIR}/venv/bin/python" "${DIR}/app.py"
