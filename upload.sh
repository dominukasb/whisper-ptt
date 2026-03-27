#!/usr/bin/env bash
# upload_to_github.sh
# Run this from inside your whisper-ptt folder AFTER:
#   sudo pacman -S github-cli
#   gh auth login
set -e

REPO_NAME="whisper-ptt"
DESCRIPTION="Push-to-talk speech-to-text for Arch Linux using local Whisper"

echo "=== Creating private GitHub repo: $REPO_NAME ==="

# Initialise git if not already done
if [ ! -d ".git" ]; then
    git init
    echo "Initialised git repo."
fi

# Create .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
dist/
build/
.eggs/
# Whisper model cache (large, no need to commit)
~/.cache/whisper/
# Audio temp files
*.wav
*.mp3
EOF

git add .
git commit -m "Initial commit: whisper push-to-talk STT for Arch Linux"

# Create private repo on GitHub and push
gh repo create "$REPO_NAME" \
    --private \
    --description "$DESCRIPTION" \
    --source=. \
    --remote=origin \
    --push

echo ""
echo "✅ Done! Your private repo is live at:"
gh repo view --json url -q .url
