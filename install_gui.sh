#!/usr/bin/env bash
# install_gui.sh
set -e

echo "=== whisper-ptt GUI installer for Arch Linux ==="

echo "[1/3] Installing system packages…"
sudo pacman -S --needed --noconfirm \
    python python-pip python-gobject gtk4 libadwaita \
    portaudio xdotool xclip ffmpeg

echo "[2/3] Setting up Python virtualenv…"
VENV_DIR="$HOME/.venv/whisper-ptt"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$VENV_DIR" ]; then
    # --system-site-packages so PyGObject (GTK bindings) from pacman are visible
    python -m venv --system-site-packages "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet
pip install openai-whisper sounddevice numpy scipy pyperclip pynput

echo "[3/3] Writing .desktop launcher…"
mkdir -p "$HOME/.local/share/applications"

# Use bash -c with full paths — app launchers don't inherit PATH or venv
cat > "$HOME/.local/share/applications/whisper-ptt.desktop" << EOF
[Desktop Entry]
Name=Whisper PTT
Comment=Push-to-talk speech to text (offline)
Exec=bash -c 'source $VENV_DIR/bin/activate && python $SCRIPT_DIR/whisper_ptt_gui.py'
Icon=audio-input-microphone
Terminal=false
Type=Application
Categories=Utility;Accessibility;
Keywords=speech;voice;transcribe;whisper;stt;
StartupNotify=true
EOF

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo ""
echo "✅ Done! Find 'Whisper PTT' in your app launcher."
echo "   Crash log (if anything goes wrong): ~/.local/share/whisper-ptt/crash.log"
