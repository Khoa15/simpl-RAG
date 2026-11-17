#!/usr/bin/env bash
# Regenerate be/requirements.txt with exact versions resolved from be/requirements.in.
set -euo pipefail
cd "$(dirname "$0")/../be"
docker run --rm -v "$PWD":/work -w /work python:3.11.11-slim-bookworm sh -c \
  'pip install -q --no-cache-dir -r requirements.in && pip freeze --exclude-editable' > requirements.txt.new
mv requirements.txt.new requirements.txt
echo "Wrote be/requirements.txt ($(wc -l < requirements.txt) pins)"
