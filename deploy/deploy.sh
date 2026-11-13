#!/usr/bin/env bash
# Upload the website to the server (only what the browser needs).
#
#   deploy/deploy.sh ubuntu@my-brand.com
#   SSH_KEY=~/.ssh/aws.pem deploy/deploy.sh ubuntu@my-brand.com
#
# Safe to run again for every update: unchanged files aren't re-sent, and files
# you deleted locally are removed on the server (--delete).
set -euo pipefail

HOST="${1:?usage: deploy/deploy.sh user@host   (e.g. ubuntu@my-brand.com)}"
REMOTE_DIR="${REMOTE_DIR:-/var/www/my-brand/live-projects/letters/invitacion-boda-isaias-y-nicole}"
SSH=(ssh); [ -n "${SSH_KEY:-}" ] && SSH=(ssh -i "$SSH_KEY")

cd "$(dirname "$0")/.."                      # project root

# Create the folder once and make the login user its owner (nginx only needs to read).
"${SSH[@]}" "$HOST" "sudo mkdir -p '$REMOTE_DIR' && sudo chown -R \$(whoami): '$REMOTE_DIR'"

# Upload index.html, css/, js/ and assets/ — never tools/, design/ (36 MB of sources) or deploy/.
rsync -az --delete --info=stats1,progress2 \
  -e "${SSH[*]}" \
  --chmod=D755,F644 \
  --include='/index.html' --include='/css/***' --include='/js/***' --include='/assets/***' \
  --exclude='*' \
  ./ "$HOST:$REMOTE_DIR/"

echo "Uploaded to $HOST:$REMOTE_DIR"
