# whisper-ptt

Push-to-talk speech-to-text for Arch Linux using local OpenAI Whisper — fully offline, no API key needed.

Hold a hotkey → speak → release → text is **typed at your cursor** and **copied to clipboard**. Works anywhere on your desktop: VSCode, terminals, browsers.

Comes in two versions:
- **`whisper_ptt_gui.py`** — GTK4 desktop app with a proper UI (recommended)
- **`whisper_ptt.py`** — terminal-only version (legacy)

---

## Quick Start

```bash
chmod +x install_gui.sh
./install_gui.sh
```

Then find **Whisper PTT** in your app launcher, or run:

```bash
bash -c 'source ~/.venv/whisper-ptt/bin/activate && python whisper_ptt_gui.py'
```

The first launch downloads the Whisper model (~150 MB for `base`). After that it's fully offline.

---

## Dependencies

### System packages (pacman)

```bash
sudo pacman -S python python-pip python-gobject gtk4 libadwaita portaudio xdotool xclip ffmpeg
```

| Package | Purpose |
|---|---|
| `python-gobject` | GTK Python bindings — **must be installed via pacman, not pip** |
| `gtk4` | GTK4 toolkit |
| `libadwaita` | Adwaita widgets (modern GNOME/GTK style) |
| `portaudio` | Audio backend for sounddevice |
| `xdotool` | Types transcribed text at cursor (X11 only) |
| `xclip` | Clipboard support for pyperclip |
| `ffmpeg` | Audio decoding required by Whisper |

### Python packages (pip, inside venv)

```bash
pip install openai-whisper sounddevice numpy scipy pyperclip pynput
```

> **Important:** The virtualenv must be created with `--system-site-packages` so it can access `python-gobject` installed by pacman. The install script handles this automatically. If you create the venv manually, always use:
> ```bash
> python -m venv --system-site-packages ~/.venv/whisper-ptt
> ```

---

## Usage

| Action | Result |
|---|---|
| Hold `Caps Lock` | Starts recording |
| Release `Caps Lock` | Stops, transcribes, types at cursor + copies to clipboard |
| Click the mic button | Same as holding the hotkey |

---

## Configuration

Edit the top section of `whisper_ptt_gui.py`:

```python
# Hotkey (default: Caps Lock)
PUSH_TO_TALK_KEY = pynput_keyboard.Key.caps_lock
# Other options:
# PUSH_TO_TALK_KEY = pynput_keyboard.Key.f9
# PUSH_TO_TALK_KEY = pynput_keyboard.KeyCode.from_char('`')

# Whisper model size
# tiny   ~75 MB  — fastest, least accurate
# base   ~150 MB — good balance (default)
# small  ~500 MB — noticeably better
# medium ~1.5 GB — very accurate
# large  ~3 GB   — best accuracy
WHISPER_MODEL = "base"

# Language (speeds up transcription; None = auto-detect)
LANGUAGE = "en"

# Set False to only copy to clipboard, don't type at cursor
TYPE_AT_CURSOR = True
```

---

## Troubleshooting

**App closes immediately on launch**
Check the crash log:
```bash
cat ~/.local/share/whisper-ptt/crash.log
```

**`No module named 'gi'`**
The venv was created without `--system-site-packages`. Fix:
```bash
rm -rf ~/.venv/whisper-ptt
python -m venv --system-site-packages ~/.venv/whisper-ptt
source ~/.venv/whisper-ptt/bin/activate
pip install openai-whisper sounddevice numpy scipy pyperclip pynput
```

**Mic not detected**
Check your default audio source:
```bash
pactl info | grep "Default Source"
python -c "import sounddevice; print(sounddevice.query_devices())"
```

**xdotool not typing in some apps (Wayland)**
`xdotool` only works on X11. If you're on Wayland (KDE Plasma Wayland, GNOME Wayland), set `TYPE_AT_CURSOR = False` and paste manually with `Ctrl+V`. For full Wayland typing support, `ydotool` can be used but requires a udev rule for `/dev/uinput`.

**Model download fails**
Whisper caches models in `~/.cache/whisper/`. Download manually:
```bash
source ~/.venv/whisper-ptt/bin/activate
python -c "import whisper; whisper.load_model('base')"
```

---

## Autostart (optional)

The install script creates a `.desktop` entry so you can launch the app from your DE's app launcher. To make it start automatically on login:

**i3:**
```bash
echo "exec --no-startup-id bash -c 'source ~/.venv/whisper-ptt/bin/activate && python ~/whisper-ptt/whisper_ptt_gui.py'" >> ~/.config/i3/config
```

**systemd user service:**
```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/whisper-ptt.service << EOF
[Unit]
Description=Whisper Push-to-Talk STT

[Service]
ExecStart=bash -c 'source %h/.venv/whisper-ptt/bin/activate && python %h/whisper-ptt/whisper_ptt_gui.py'
Restart=on-failure
Environment=DISPLAY=:0
Environment=XAUTHORITY=%h/.Xauthority

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now whisper-ptt
```
