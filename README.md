# whisper-ptt

Push-to-talk speech-to-text for Arch Linux using OpenAI Whisper (local, offline).

Hold a hotkey → speak → release → text is **typed at your cursor** and **copied to clipboard**.
Works in VSCode, terminals, browsers — anywhere on your desktop.

---

## Quick Start

```bash
# 1. Clone or copy the files into a folder
mkdir ~/whisper-ptt && cd ~/whisper-ptt
# (copy whisper_ptt.py and install.sh here)

# 2. Run the installer
chmod +x install.sh
./install.sh

# 3. Start the app
whisper-ptt
```

The first run will **download the Whisper model** (~150 MB for "base"). This only happens once.

---

## Usage

| Action | Result |
|---|---|
| Hold `Caps Lock` | Starts recording |
| Release `Caps Lock` | Stops recording, transcribes, types text + copies to clipboard |
| `Ctrl+C` in terminal | Exits the app |

> **Tip for VSCode**: Click inside VSCode to focus it, then hold Caps Lock and speak. The text will appear wherever your cursor is.

---

## Configuration

Open `whisper_ptt.py` and edit the top section:

```python
# Change the hotkey (default: Caps Lock)
PUSH_TO_TALK_KEY = keyboard.Key.caps_lock
# Other options:
# PUSH_TO_TALK_KEY = keyboard.Key.f9
# PUSH_TO_TALK_KEY = keyboard.KeyCode.from_char('`')  # backtick

# Change the model (default: "base")
# tiny   → fastest, least accurate (~75 MB)
# base   → good balance (~150 MB)       ← default
# small  → better accuracy (~500 MB)
# medium → very accurate (~1.5 GB)
# large  → best accuracy (~3 GB)
WHISPER_MODEL = "base"

# Change language (default: English)
# Set to None for auto-detect (slower)
LANGUAGE = "en"
```

---

## Autostart (optional)

To have it start automatically when you log in, add this to your window manager's autostart config:

```bash
# For i3, add to ~/.config/i3/config:
exec --no-startup-id whisper-ptt

# For KDE/GNOME, add via the "Autostart" settings, pointing to:
/home/YOUR_USERNAME/bin/whisper-ptt
```

Or create a systemd user service:

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/whisper-ptt.service << EOF
[Unit]
Description=Whisper Push-to-Talk STT

[Service]
ExecStart=%h/bin/whisper-ptt
Restart=on-failure
Environment=DISPLAY=:0
Environment=XAUTHORITY=%h/.Xauthority

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now whisper-ptt
```

---

## Troubleshooting

**No audio captured / recording too short**
- Check your microphone is set as default: `pactl info | grep "Default Source"`
- List audio devices: `python -c "import sounddevice; print(sounddevice.query_devices())"`

**xdotool not typing in some apps**
- Some Wayland apps don't support xdotool. Use clipboard paste (`Ctrl+V`) instead.
- If on Wayland, consider switching `TYPE_AT_CURSOR = False` and just use clipboard.

**Wayland support**
- xdotool only works on X11. If you use Wayland (KDE Plasma Wayland, GNOME Wayland), set `TYPE_AT_CURSOR = False` and paste manually with `Ctrl+V`.
- Full Wayland typing support requires `ydotool` (needs a udev rule for `/dev/uinput`).

**Model download fails**
- Whisper downloads to `~/.cache/whisper/`. Make sure you have internet on first run.
- To download manually: `python -c "import whisper; whisper.load_model('base')"`

**"No module named X" errors**
- Make sure you activated the venv: `source ~/.venv/whisper-ptt/bin/activate`

---

## Dependencies

| Package | Purpose |
|---|---|
| `openai-whisper` | Speech recognition model |
| `sounddevice` | Microphone input |
| `scipy` / `numpy` | Audio processing |
| `pyperclip` | Clipboard output |
| `pynput` | Global hotkey listener |
| `xdotool` (system) | Type text at cursor (X11) |
| `portaudio` (system) | Audio backend for sounddevice |
| `ffmpeg` (system) | Audio decoding for Whisper |
