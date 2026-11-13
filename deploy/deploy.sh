#!/usr/bin/env bash
# Upload the website to the server (only what the browser needs).
#
#   deploy/deploy.sh ubuntu@hsoul.ink
#   SSH_KEY=~/.ssh/aws.pem deploy/deploy.sh ubuntu@hsoul.ink
#
# Safe to run again for every update: unchanged files aren't re-sent, and files
# you deleted locally are removed on the server (--delete).
set -euo pipefail

HOST="${1:?usage: deploy/deploy.sh user@host   (e.g. ubuntu@hsoul.ink)}"
REMOTE_DIR="${REMOTE_DIR:-/var/www/hsoul-ink/live-projects/letters/invitacion-boda-isaias-y-nicole}"
SSH=(ssh); [ -n "${SSH_KEY:-}" ] && SSH=(ssh -i "$SSH_KEY")

cd "$(dirname "$0")/.."                      # project root

# Fingerprint the CSS/JS links in index.html (main.js?v=3f9a1c2b): when a file changes,
# its URL changes, so no phone, browser or CDN can keep serving an old copy.
hash8() { if command -v md5sum >/dev/null; then md5sum "$1" | cut -c1-8; else md5 -q "$1" | cut -c1-8; fi; }
for f in css/fonts.css css/styles.css js/config.js js/main.js; do
  h=$(hash8 "$f")
  sed -E -i.bak "s#\"$f(\?v=[0-9a-f]+)?\"#\"$f?v=$h\"#" index.html && rm -f index.html.bak
done
echo "Fingerprinted: $(grep -oE '(css|js)/[a-z]+\.(css|js)\?v=[0-9a-f]+' index.html | tr '\n' ' ')"

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
