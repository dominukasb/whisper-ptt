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

# ── Python packages (pip) ───────────────────────────────────────────────────
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

APP_ID           = "com.dominukasb.whisperptt"
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
window { background-color: #0f0f11; }
headerbar { background: transparent; border: none; min-height: 48px; }

.app-title { font-size: 11px; font-weight: 700; letter-spacing: 0.15em; color: #666675; text-transform: uppercase; }

.status-pill { border-radius: 999px; padding: 4px 16px; font-size: 12px; font-weight: 600; transition: all 200ms ease; }
.status-idle       { background-color: #1a1a1f; color: #666675; border: 1px solid #252530; }
.status-loading    { background-color: #1a1625; color: #9a8ff0; border: 1px solid #352a55; }
.status-recording  { background-color: #2a1215; color: #ff6b7a; border: 1px solid #5a1a25; box-shadow: 0 0 15px rgba(224, 92, 106, 0.1); }
.status-processing { background-color: #121a25; color: #6bb9ff; border: 1px solid #1a3555; }
.status-done       { background-color: #12251a; color: #6bff9d; border: 1px solid #1a5525; }
.status-error      { background-color: #251a12; color: #ff9d6b; border: 1px solid #55351a; }

.mic-button        { border-radius: 999px; min-width: 100px; min-height: 100px; background-color: #1a1a1f; border: 1px solid #2a2a35; transition: all 250ms cubic-bezier(0.4, 0, 0.2, 1); margin-bottom: 8px; }
.mic-button:hover  { background-color: #252530; border-color: #404055; transform: scale(1.02); }
.mic-button.recording { background-color: #301518; border-color: #e05c6a; transform: scale(0.96); }
.mic-icon          { font-size: 36px; color: #444455; transition: color 200ms; }
.mic-icon.recording { color: #e05c6a; }

.transcript-box        { background-color: #16161c; border-radius: 16px; border: 1px solid #22222e; padding: 18px; }
.transcript-label      { font-size: 14px; line-height: 1.5; color: #777785; transition: color 300ms; }
.transcript-label.has-text { color: #e0e0ed; }

.section-header { font-size: 11px; font-weight: 700; letter-spacing: 0.1em; color: #444455; margin-bottom: 4px; }

.history-list { background: transparent; }
.history-row { background-color: #141418; border: 1px solid #1e1e26; border-radius: 10px; padding: 10px 14px; margin-bottom: 6px; transition: background 200ms; }
.history-row:hover { background-color: #1a1a22; }
.history-text { font-size: 12px; color: #77778a; }

.hotkey-badge { background-color: #22222d; border: 1px solid #333345; border-radius: 6px; padding: 3px 8px; font-size: 10px; font-weight: 700; color: #8888a0; }

.copy-btn       { border-radius: 8px; padding: 4px 12px; font-size: 12px; font-weight: 600; }

.log-hint { font-size: 10px; color: #333345; opacity: 0.7; }
.log-hint:hover { opacity: 1; }
"""

# ─── Window ────────────────────────────────────────────────────────────────────

class WhisperPTTWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Whisper PTT")
        self.set_icon_name(APP_ID)
        self.set_default_size(380, 620)
        self.set_resizable(False)
        self._last_text = ""
        
        self.toast_overlay = Adw.ToastOverlay()
        self._build_ui()

    def _build_ui(self):
        # Toolbar View provides the structure for HeaderBar + Content
        toolbar_view = Adw.ToolbarView()
        self.toast_overlay.set_child(toolbar_view)
        self.set_content(self.toast_overlay)

        # Header
        header = Adw.HeaderBar()
        title_lbl = Gtk.Label(label="Whisper PTT")
        title_lbl.add_css_class("app-title")
        header.set_title_widget(title_lbl)
        
        key_name = str(PUSH_TO_TALK_KEY).replace("Key.", "").upper()
        hotkey_lbl = Gtk.Label(label=key_name)
        hotkey_lbl.add_css_class("hotkey-badge")
        header.pack_end(hotkey_lbl)
        toolbar_view.add_top_bar(header)

        # Content container
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        toolbar_view.set_content(root)

        # Mic + status
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        center_box.set_margin_top(24); center_box.set_margin_bottom(24)
        center_box.set_halign(Gtk.Align.CENTER)
        
        self.mic_btn = Gtk.Button()
        self.mic_btn.add_css_class("mic-button")
        self.mic_icon = Gtk.Label(label="🎤")
        self.mic_icon.add_css_class("mic-icon")
        self.mic_btn.set_child(self.mic_icon)
        self.mic_btn.connect("clicked", self._on_mic_clicked)
        
        self.status_pill = Gtk.Label(label="Initialising...")
        self.status_pill.add_css_class("status-pill")
        self.status_pill.add_css_class("status-loading")
        
        center_box.append(self.mic_btn); center_box.append(self.status_pill)
        root.append(center_box)

        # Transcript
        transcript_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        transcript_section.set_margin_start(24); transcript_section.set_margin_end(24)
        
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        t_header_lbl = Gtk.Label(label="TRANSCRIPTION")
        t_header_lbl.add_css_class("section-header")
        t_header_lbl.set_halign(Gtk.Align.START); t_header_lbl.set_hexpand(True)
        
        self.copy_btn = Gtk.Button(label="copy")
        self.copy_btn.add_css_class("copy-btn"); self.copy_btn.add_css_class("flat")
        self.copy_btn.connect("clicked", self._on_copy)
        self.copy_btn.set_sensitive(False)
        
        header_row.append(t_header_lbl); header_row.append(self.copy_btn)
        transcript_section.append(header_row)

        self.transcript_box = Gtk.Box()
        self.transcript_box.add_css_class("transcript-box")
        self.transcript_lbl = Gtk.Label(label="Waiting for audio...")
        self.transcript_lbl.add_css_class("transcript-label")
        self.transcript_lbl.set_wrap(True)
        self.transcript_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.transcript_lbl.set_xalign(0)
        self.transcript_lbl.set_selectable(True)
        self.transcript_box.append(self.transcript_lbl)
        transcript_section.append(self.transcript_box)
        root.append(transcript_section)

        # Divider
        div = Gtk.Separator()
        div.set_margin_top(24); div.set_margin_bottom(20)
        div.set_margin_start(24); div.set_margin_end(24)
        root.append(div)

        # History
        history_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        history_section.set_margin_start(24); history_section.set_margin_end(24)
        hist_lbl = Gtk.Label(label="HISTORY")
        hist_lbl.add_css_class("section-header"); hist_lbl.set_halign(Gtk.Align.START)
        history_section.append(hist_lbl)
        
        self.history_list = Gtk.ListBox()
        self.history_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.history_list.add_css_class("history-list")
        history_section.append(self.history_list)
        
        self.empty_hist_lbl = Gtk.Label(label="No recordings yet.")
        self.empty_hist_lbl.add_css_class("history-text")
        self.empty_hist_lbl.set_margin_top(10)
        self.history_list.append(self.empty_hist_lbl)
        root.append(history_section)

        # Footer spacer pushes the log hint to the bottom without relying on
        # label expansion/alignment behavior that can vary across GTK/PyGObject
        # runtimes.
        footer_spacer = Gtk.Box()
        footer_spacer.set_vexpand(True)
        root.append(footer_spacer)

        lbl_log_path = Gtk.Label(label=f"Logs: {LOG_FILE}")
        lbl_log_path.add_css_class("log-hint")
        lbl_log_path.set_halign(Gtk.Align.START)
        lbl_log_path.set_margin_start(24)
        lbl_log_path.set_margin_end(24)
        lbl_log_path.set_margin_bottom(16)
        root.append(lbl_log_path)

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
        self.toast_overlay.add_toast(Adw.Toast(title="Transcribed and Copied"))

    def _add_history(self, text):
        if self.empty_hist_lbl.get_parent() is not None:
            self.history_list.remove(self.empty_hist_lbl)
        
        short = text if len(text) <= 50 else text[:47] + "..."
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.add_css_class("history-row")
        lbl = Gtk.Label(label=short)
        lbl.add_css_class("history-text")
        row.append(lbl)
        self.history_list.prepend(row)
        
        # Keep only last 5 items
        items = []
        curr = self.history_list.get_first_child()
        while curr:
            items.append(curr)
            curr = curr.get_next_sibling()
        
        for item in items[5:]:
            self.history_list.remove(item)

    def _on_copy(self, _btn):
        if self._last_text:
            pyperclip.copy(self._last_text)
            self.toast_overlay.add_toast(Adw.Toast(title="Copied to clipboard"))

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
        super().__init__(application_id=APP_ID)
        self._listener = None
        self.connect("activate", self.on_activate)
        self.connect("shutdown", self.on_shutdown)

    def _cleanup_runtime_state(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

        if state.audio_stream is not None:
            try:
                state.audio_stream.stop()
            except Exception:
                pass
            try:
                state.audio_stream.close()
            except Exception:
                pass
            state.audio_stream = None

    def on_shutdown(self, _app):
        self._cleanup_runtime_state()

    def _on_window_close_request(self, _win):
        self._cleanup_runtime_state()
        self.quit()
        return False

    def on_activate(self, app):
        global _window_ref

        windows = self.get_windows()
        if windows:
            windows[0].present()
            return

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        win = WhisperPTTWindow(application=app)
        win.connect("close-request", self._on_window_close_request)
        _window_ref = win
        win.present()

        # Audio — must come AFTER window is shown
        if not start_audio_stream():
            GLib.idle_add(win.on_audio_error)
            return

        # Whisper model in background
        threading.Thread(target=self._load_model, args=(win,), daemon=True).start()

        # Global hotkey
        self._listener = pynput_keyboard.Listener(
            on_press=on_key_press,
            on_release=on_key_release,
        )
        self._listener.daemon = True
        self._listener.start()

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
