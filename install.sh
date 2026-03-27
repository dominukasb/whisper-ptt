#!/usr/bin/env bash
# install.sh — Install dependencies for whisper_ptt on Arch Linux
set -e

echo "=== whisper-ptt installer for Arch Linux ==="

# ── System packages ──────────────────────────────────────────────────────────
echo ""
echo "[1/3] Installing system packages via pacman…"
sudo pacman -S --needed --noconfirm \
    python \
    python-pip \
    portaudio \
    xdotool \
    xclip \
    ffmpeg

# ── Python packages ───────────────────────────────────────────────────────────
echo ""
echo "[2/3] Installing Python packages…"

# Use a virtual environment to avoid conflicts with system Python
VENV_DIR="$HOME/.venv/whisper-ptt"

if [ ! -d "$VENV_DIR" ]; then
    python -m venv "$VENV_DIR"
    echo "Created virtualenv at $VENV_DIR"
fi

# Activate venv for installation
source "$VENV_DIR/bin/activate"

pip install --upgrade pip --quiet
pip install \
    openai-whisper \
    sounddevice \
    numpy \
    scipy \
    pyperclip \
    pynput

echo ""
echo "[3/3] Creating launcher script at ~/bin/whisper-ptt…"
mkdir -p "$HOME/bin"

cat > "$HOME/bin/whisper-ptt" << EOF
#!/usr/bin/env bash
source "$VENV_DIR/bin/activate"
exec python "$(pwd)/whisper_ptt.py" "\$@"
EOF

chmod +x "$HOME/bin/whisper-ptt"

# Add ~/bin to PATH if not already there
if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
    echo ""
    echo "Adding ~/bin to PATH in ~/.bashrc …"
    echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.bashrc"
    echo "(Restart your terminal or run: source ~/.bashrc)"
fi

echo ""
echo "══════════════════════════════════════════════════"
echo "✅ Installation complete!"
echo ""
echo "Run it with:"
echo "  whisper-ptt"
echo ""
echo "Or directly:"
echo "  source $VENV_DIR/bin/activate"
echo "  python whisper_ptt.py"
echo "══════════════════════════════════════════════════"
