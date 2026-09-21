#!/usr/bin/env bash
# Build & verify script for Allin1.
#
# - Installs Python dependencies (if not already satisfied)
# - Lints with ruff
# - Runs the offline test-suite (uses a locally generated media file, no
#   live network / social platform dependency)
# - Packages a distributable artifact under dist/
#
# Safe to run both locally and inside CI.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Checking ffmpeg availability"
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg is not installed. Install it with 'apt-get install -y ffmpeg' (or brew on macOS)." >&2
  exit 1
fi
ffmpeg -version | head -n 1

echo "==> Installing Python dependencies"
PIP_INSTALL=(python3 -m pip install --quiet)
python3 -m pip install --quiet --upgrade pip || true
if ! "${PIP_INSTALL[@]}" -r requirements.txt -r requirements-dev.txt 2>/tmp/pip-install.log; then
  if grep -q "externally-managed-environment" /tmp/pip-install.log; then
    echo "==> System Python is externally managed; retrying with --break-system-packages"
    "${PIP_INSTALL[@]}" --break-system-packages -r requirements.txt -r requirements-dev.txt
  else
    cat /tmp/pip-install.log >&2
    exit 1
  fi
fi

echo "==> Linting with ruff"
ruff check backend

echo "==> Running test suite"
pytest -q

echo "==> Packaging build artifact"
rm -rf dist
mkdir -p dist
ARTIFACT="dist/allin1-app.tar.gz"
tar czf "$ARTIFACT" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  backend \
  frontend \
  requirements.txt \
  requirements-dev.txt \
  Dockerfile \
  README.md \
  scripts \
  pyproject.toml

echo "==> Build artifact created at $ARTIFACT"
ls -lh "$ARTIFACT"

if command -v docker >/dev/null 2>&1; then
  echo "==> Docker detected, building container image as an extra sanity check"
  docker build -t allin1:ci -f Dockerfile . && echo "==> Docker image built successfully"
else
  echo "==> Docker not available, skipping container build (not required for the artifact)"
fi

echo "==> Build script completed successfully"
