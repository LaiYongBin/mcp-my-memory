#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="${ROOT_DIR}/skills/personal-memory"
VENV_DIR="${SKILL_DIR}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${SKILL_DIR}/requirements.txt"

export PYTHONPATH="${SKILL_DIR}"
"${VENV_DIR}/bin/python" "${SKILL_DIR}/scripts/bootstrap.py" "$@"
