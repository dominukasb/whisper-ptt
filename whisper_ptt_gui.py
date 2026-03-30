#!/usr/bin/env python3
"""
whisper_ptt_gui.py — Push-to-talk speech-to-text, GTK4 desktop app.
Logs crashes to ~/.local/share/whisper-ptt/crash.log so issues are visible.
"""

# ── Crash logging — set up FIRST, before any other import can fail ─────────────
import sys, os, traceback, pathlib

LOG_DIR  = pathlib.Path.home() / ".local" / "share" / "whisper-ptt"
LOG_FILE = LOG_DIR / "crash.log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_orig_excepthook = sys.excepthook
def _excepthook(exc_type, exc_value, exc_tb):
    import datetime
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    with open(LOG_FILE, "a") as f:
        f.write(f"\n=== {datetime.datetime.now().isoformat()} ===\n{msg}\n")
    _orig_excepthook(exc_type, exc_value, exc_tb)
sys.excepthook = _excepthook

# ── Standard library ───────────────────────────────────────────────────────────
import threading
import tempfile
import time
import subprocess

# ── GTK ───────────────────────────────────────────────────────────────────────
try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, GLib, Gdk, Pango
except Exception as e:
    with open(LOG_FILE, "a") as f:
        f.write(f"FATAL: GTK import failed: {e}\n")
    raise

# ── Python packages (pip) ─────────────────────────────────────────────────────
try:
    import numpy as np
    import sounddevice as sd
    import scipy.io.wavfile as wav
    import pyperclip
    import whisper
    from pynput import keyboard as pynput_keyboard
except ImportError as e:
    with open(LOG_FILE, "a") as f:
        f.write(f"FATAL: Missing package: {e}\nRun: ./install_gui.sh\n")
    raise

# ─── Configuration ─────────────────────────────────────────────────────────────

PUSH_TO_TALK_KEY = pynput_keyboard.Key.caps_lock
WHISPER_MODEL    = "base"   # tiny / base / small / medium / large
SAMPLE_RATE      = 16000
CHANNELS         = 1
LANGUAGE         = "en"     # None = auto-detect
TYPE_AT_CURSOR   = True

# ─── State ─────────────────────────────────────────────────────────────────────

class AppState:
    recording    = False
    audio_frames = []
    key_held     = False
    model        = None
    model_ready  = False
    audio_stream = None
    lock         = threading.Lock()

state = AppState()
_window_ref = None   # set in on_activate

# ─── Audio (opened lazily in on_activate, NEVER at module level) ───────────────

def audio_callback(indata, frames, time_info, status):
    if state.recording:
        state.audio_frames.append(indata.copy())

def start_audio_stream():
    try:
        state.audio_stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=audio_callback,
            blocksize=1024,
        )
        state.audio_stream.start()
        return True
    except Exception as e:
        with open(LOG_FILE, "a") as f:
            f.write(f"Mic stream error: {e}\n{traceback.format_exc()}\n")
        return False

# ─── Transcription ─────────────────────────────────────────────────────────────

def transcribe_and_output(app_window):
    try:
        with state.lock:
            frames = list(state.audio_frames)

        if not frames:
            GLib.idle_add(app_window.set_status, "idle", "No audio captured.")
            return

        audio_data = np.concatenate(frames, axis=0).flatten().astype(np.float32)
        max_val = np.abs(audio_data).max()
        if max_val > 0:
            audio_data /= max_val

        duration = len(audio_data) / SAMPLE_RATE
        if duration < 0.3:
            GLib.idle_add(app_window.set_status, "idle", "Too short — try again.")
            return

        GLib.idle_add(app_window.set_status, "processing", f"Transcribing {duration:.1f}s…")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            wav.write(tmp_path, SAMPLE_RATE, (audio_data * 32767).astype(np.int16))
            result = state.model.transcribe(
                tmp_path, language=LANGUAGE, fp16=False,
                condition_on_previous_text=False,
            )
            text = result["text"].strip()
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        if not text:
            GLib.idle_add(app_window.set_status, "idle", "Nothing detected — try again.")
            return

        try:
            pyperclip.copy(text)
        except Exception:
            pass

        if TYPE_AT_CURSOR:
            try:
                time.sleep(0.12)
                subprocess.run(
                    ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
                    check=True, timeout=10,
                )
            except Exception:
                pass

        GLib.idle_add(app_window.on_transcription_done, text)

    except Exception as e:
        with open(LOG_FILE, "a") as f:
            f.write(f"Transcription error: {e}\n{traceback.format_exc()}\n")
        GLib.idle_add(app_window.set_status, "error", "Error — check crash.log")

# ─── Hotkey listener ───────────────────────────────────────────────────────────

def on_key_press(key):
    try:
        if not state.model_ready or state.key_held:
            return
        if key == PUSH_TO_TALK_KEY:
            state.key_held = True
            with state.lock:
                state.audio_frames = []
                state.recording = True
            GLib.idle_add(_window_ref.set_status, "recording", "Recording…")
    except Exception:
        pass

def on_key_release(key):
    try:
        if key == PUSH_TO_TALK_KEY and state.key_held:
            state.key_held = False
            state.recording = False
            threading.Thread(
                target=transcribe_and_output, args=(_window_ref,), daemon=True
            ).start()
    except Exception:
        pass

# ─── CSS ───────────────────────────────────────────────────────────────────────

CSS = b"""
window, .window-bg { background-color: #0f0f11; }

.app-title { font-size: 13px; font-weight: 500; letter-spacing: 0.12em; color: #555560; }

.status-pill { border-radius: 999px; padding: 6px 18px; font-size: 13px; font-weight: 500; }
.status-idle       { background-color: #1a1a1f; color: #555560; border: 1px solid #252530; }
.status-loading    { background-color: #1a1625; color: #7c6fcd; border: 1px solid #2d2550; }
.status-recording  { background-color: #1f1215; color: #e05c6a; border: 1px solid #4a1520; }
.status-processing { background-color: #12191f; color: #5b9fd6; border: 1px solid #153050; }
.status-done       { background-color: #111a14; color: #5dba7a; border: 1px solid #1a4025; }
.status-error      { background-color: #1f1510; color: #d4834a; border: 1px solid #4a2510; }

.mic-button        { border-radius: 999px; padding: 0; min-width: 90px; min-height: 90px; background-color: #1a1a1f; border: 1.5px solid #2a2a35; }
.mic-button:hover  { background-color: #222230; border-color: #3a3a50; }
.mic-button.recording { background-color: #2a1215; border-color: #8b2030; }
.mic-icon          { font-size: 32px; color: #444455; }
.mic-icon.recording { color: #e05c6a; }

.transcript-box        { background-color: #141418; border-radius: 12px; border: 1px solid #1e1e28; padding: 14px 16px; }
.transcript-label      { font-size: 13px; color: #8888a0; }
.transcript-label.has-text { color: #c8c8e0; }

.history-header { font-size: 10px; font-weight: 500; letter-spacing: 0.14em; color: #333345; }
.history-row    { font-size: 11px; color: #44445a; padding: 3px 0; }

.hotkey-badge { background-color: #1a1a22; border: 1px solid #252535; border-radius: 6px; padding: 2px 8px; font-size: 11px; color: #44445a; }

.copy-btn       { background: transparent; border: 1px solid #252535; border-radius: 6px; color: #44445a; font-size: 11px; padding: 2px 8px; }
.copy-btn:hover { border-color: #3a3a55; color: #8888a0; }

.log-hint { font-size: 10px; color: #2a2a38; }
"""

# ─── Window ────────────────────────────────────────────────────────────────────

class WhisperPTTWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Whisper PTT")
        self.set_default_size(360, 560)
        self.set_resizable(False)
        self._last_text = ""
        self._history_widgets = []
        self._build_ui()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.add_css_class("window-bg")
        self.set_content(root)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.set_margin_top(20); header.set_margin_start(24)
        header.set_margin_end(24); header.set_margin_bottom(0)
        title_lbl = Gtk.Label(label="WHISPER PTT")
        title_lbl.add_css_class("app-title")
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.set_hexpand(True)
        key_name = str(PUSH_TO_TALK_KEY).replace("Key.", "").upper()
        hotkey_lbl = Gtk.Label(label=key_name)
        hotkey_lbl.add_css_class("hotkey-badge")
        header.append(title_lbl); header.append(hotkey_lbl)
        root.append(header)

        # Mic + status
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        center_box.set_margin_top(36); center_box.set_margin_bottom(28)
        center_box.set_halign(Gtk.Align.CENTER)
        self.mic_btn = Gtk.Button()
        self.mic_btn.add_css_class("mic-button")
        self.mic_btn.set_halign(Gtk.Align.CENTER)
        self.mic_icon = Gtk.Label(label="⏺")
        self.mic_icon.add_css_class("mic-icon")
        self.mic_btn.set_child(self.mic_icon)
        self.mic_btn.connect("clicked", self._on_mic_clicked)
        self.status_pill = Gtk.Label(label="Starting…")
        self.status_pill.add_css_class("status-pill")
        self.status_pill.add_css_class("status-loading")
        center_box.append(self.mic_btn); center_box.append(self.status_pill)
        root.append(center_box)

        # Transcript
        transcript_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        transcript_outer.set_margin_start(20); transcript_outer.set_margin_end(20)
        t_header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        t_header_lbl = Gtk.Label(label="LAST TRANSCRIPT")
        t_header_lbl.add_css_class("history-header")
        t_header_lbl.set_halign(Gtk.Align.START); t_header_lbl.set_hexpand(True)
        self.copy_btn = Gtk.Button(label="copy")
        self.copy_btn.add_css_class("copy-btn")
        self.copy_btn.connect("clicked", self._on_copy)
        self.copy_btn.set_sensitive(False)
        t_header_row.append(t_header_lbl); t_header_row.append(self.copy_btn)
        self.transcript_box = Gtk.Box()
        self.transcript_box.add_css_class("transcript-box")
        self.transcript_lbl = Gtk.Label(label="Initialising…")
        self.transcript_lbl.add_css_class("transcript-label")
        self.transcript_lbl.set_wrap(True)
        self.transcript_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.transcript_lbl.set_xalign(0)
        self.transcript_lbl.set_max_width_chars(38)
        self.transcript_lbl.set_selectable(True)
        self.transcript_box.append(self.transcript_lbl)
        transcript_outer.append(t_header_row); transcript_outer.append(self.transcript_box)
        root.append(transcript_outer)

        # Divider
        div = Gtk.Separator()
        div.set_margin_top(20); div.set_margin_bottom(16)
        div.set_margin_start(20); div.set_margin_end(20)
        root.append(div)

        # History
        history_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        history_outer.set_margin_start(20); history_outer.set_margin_end(20)
        hist_lbl = Gtk.Label(label="HISTORY")
        hist_lbl.add_css_class("history-header"); hist_lbl.set_halign(Gtk.Align.START)
        history_outer.append(hist_lbl)
        self.history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        history_outer.append(self.history_box)
        self.empty_hist_lbl = Gtk.Label(label="No recordings yet.")
        self.empty_hist_lbl.add_css_class("history-row")
        self.empty_hist_lbl.set_halign(Gtk.Align.START)
        self.history_box.append(self.empty_hist_lbl)
        root.append(history_outer)

        # Log path hint
        log_lbl = Gtk.Label(label=f"log: {LOG_FILE}")
        log_lbl.add_css_class("log-hint")
        log_lbl.set_margin_top(14); log_lbl.set_margin_bottom(14)
        log_lbl.set_selectable(True)
        root.append(log_lbl)

    # ── Callbacks ────────────────────────────────────────────────────

    def set_status(self, kind, text):
        for cls in ["status-idle","status-loading","status-recording",
                    "status-processing","status-done","status-error"]:
            self.status_pill.remove_css_class(cls)
        self.status_pill.add_css_class(f"status-{kind}")
        self.status_pill.set_label(text)
        is_rec = kind == "recording"
        if is_rec:
            self.mic_btn.add_css_class("recording")
            self.mic_icon.add_css_class("recording")
        else:
            self.mic_btn.remove_css_class("recording")
            self.mic_icon.remove_css_class("recording")

    def on_audio_error(self):
        self.set_status("error", "Mic error — check log")
        self.transcript_lbl.set_label(f"Microphone could not be opened.\nSee: {LOG_FILE}")

    def on_model_ready(self):
        state.model_ready = True
        key_name = str(PUSH_TO_TALK_KEY).replace("Key.", "").upper()
        self.set_status("idle", f"Hold {key_name} to record")
        self.transcript_lbl.set_label(f"Hold {key_name} to start recording…")

    def on_transcription_done(self, text):
        self._last_text = text
        self.transcript_lbl.set_label(text)
        self.transcript_lbl.add_css_class("has-text")
        self.copy_btn.set_sensitive(True)
        self._add_history(text)
        self.set_status("done", "Done ✓")
        key_name = str(PUSH_TO_TALK_KEY).replace("Key.", "").upper()
        GLib.timeout_add(2000, lambda: self.set_status("idle", f"Hold {key_name} to record") or False)

    def _add_history(self, text):
        if self.empty_hist_lbl.get_parent() is not None:
            self.history_box.remove(self.empty_hist_lbl)
        short = text if len(text) <= 48 else text[:45] + "…"
        row = Gtk.Label(label=f"› {short}")
        row.add_css_class("history-row")
        row.set_halign(Gtk.Align.START)
        row.set_selectable(True)
        self.history_box.prepend(row)
        self._history_widgets.insert(0, row)
        for old in self._history_widgets[5:]:
            if old.get_parent() is not None:
                self.history_box.remove(old)
        self._history_widgets = self._history_widgets[:5]

    def _on_copy(self, _btn):
        if self._last_text:
            pyperclip.copy(self._last_text)
            self.copy_btn.set_label("copied!")
            GLib.timeout_add(1500, lambda: self.copy_btn.set_label("copy") or False)

    def _on_mic_clicked(self, _btn):
        if not state.model_ready:
            return
        if state.recording:
            state.recording = False
            state.key_held = False
            threading.Thread(target=transcribe_and_output, args=(self,), daemon=True).start()
        else:
            with state.lock:
                state.audio_frames = []
                state.recording = True
                state.key_held = True
            self.set_status("recording", "Recording…")

# ─── Application ───────────────────────────────────────────────────────────────

class WhisperPTTApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.dominukasb.whisperptt")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        global _window_ref

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        win = WhisperPTTWindow(application=app)
        _window_ref = win
        win.present()

        # Audio — must come AFTER window is shown
        if not start_audio_stream():
            GLib.idle_add(win.on_audio_error)
            return

        # Whisper model in background
        threading.Thread(target=self._load_model, args=(win,), daemon=True).start()

        # Global hotkey
        listener = pynput_keyboard.Listener(on_press=on_key_press, on_release=on_key_release)
        listener.daemon = True
        listener.start()

    def _load_model(self, win):
        try:
            GLib.idle_add(win.set_status, "loading", f"Loading '{WHISPER_MODEL}' model…")
            state.model = whisper.load_model(WHISPER_MODEL)
            GLib.idle_add(win.on_model_ready)
        except Exception as e:
            with open(LOG_FILE, "a") as f:
                f.write(f"Model load failed: {e}\n{traceback.format_exc()}\n")
            GLib.idle_add(win.set_status, "error", "Model failed — check log")


if __name__ == "__main__":
    app = WhisperPTTApp()
    sys.exit(app.run(sys.argv))
