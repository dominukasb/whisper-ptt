#!/usr/bin/env python3
"""
whisper_ptt.py — Push-to-talk speech-to-text for Arch Linux
Hold the hotkey → speak → release → text is typed at cursor + copied to clipboard

Requirements (see install.sh):
  pip install openai-whisper sounddevice numpy pyperclip pynput
  pacman -S xdotool portaudio
"""

import threading
import tempfile
import os
import sys
import time
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import pyperclip
import subprocess
import whisper
from pynput import keyboard

# ─── Configuration ────────────────────────────────────────────────────────────

# Hotkey to hold for recording. Options:
#   keyboard.Key.caps_lock   ← recommended (won't interfere with coding)
#   keyboard.Key.f9
#   keyboard.KeyCode.from_char('`')   ← backtick
PUSH_TO_TALK_KEY = keyboard.Key.caps_lock

# Whisper model size: "tiny", "base", "small", "medium", "large"
# Recommendation: "base" is fast and accurate enough for most use cases.
# "small" is noticeably better. "medium"/"large" are slower but very accurate.
WHISPER_MODEL = "base"

# Audio settings
SAMPLE_RATE = 16000   # Whisper expects 16kHz
CHANNELS = 1

# Language hint (speeds up transcription). None = auto-detect.
# Examples: "en", "lt", "de", "fr"
LANGUAGE = "en"

# Whether to type the text at the cursor position after transcription
TYPE_AT_CURSOR = True

# ─── State ────────────────────────────────────────────────────────────────────

recording = False
audio_frames = []
model = None
lock = threading.Lock()


# ─── Audio ────────────────────────────────────────────────────────────────────

def audio_callback(indata, frames, time_info, status):
    """Called by sounddevice for each audio chunk while recording."""
    if recording:
        audio_frames.append(indata.copy())


def start_recording():
    global recording, audio_frames
    with lock:
        audio_frames = []
        recording = True
    print("🎙  Recording… (release key to transcribe)", flush=True)


def stop_and_transcribe():
    global recording

    with lock:
        recording = False
        frames = list(audio_frames)

    if not frames:
        print("⚠  No audio captured.", flush=True)
        return

    audio_data = np.concatenate(frames, axis=0).flatten().astype(np.float32)

    # Normalise if needed
    max_val = np.abs(audio_data).max()
    if max_val > 0:
        audio_data = audio_data / max_val

    duration = len(audio_data) / SAMPLE_RATE
    if duration < 0.3:
        print("⚠  Recording too short, ignoring.", flush=True)
        return

    print(f"⏳ Transcribing {duration:.1f}s of audio…", flush=True)

    # Save to temp WAV file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        wav.write(tmp_path, SAMPLE_RATE, (audio_data * 32767).astype(np.int16))

        result = model.transcribe(
            tmp_path,
            language=LANGUAGE,
            fp16=False,
            condition_on_previous_text=False,
        )
        text = result["text"].strip()

        if not text:
            print("⚠  Nothing transcribed (silence?).", flush=True)
            return

        print(f"✅ \"{text}\"", flush=True)
        output_text(text)

    finally:
        os.unlink(tmp_path)


def output_text(text):
    """Copy to clipboard and optionally type at cursor."""
    # Copy to clipboard
    try:
        pyperclip.copy(text)
        print("📋 Copied to clipboard.", flush=True)
    except Exception as e:
        print(f"⚠  Clipboard error: {e}", flush=True)

    # Type at cursor using xdotool
    if TYPE_AT_CURSOR:
        try:
            # Small delay so key-release doesn't interfere with typing
            time.sleep(0.1)
            subprocess.run(
                ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
                check=True,
                timeout=10,
            )
            print("⌨  Typed at cursor.", flush=True)
        except FileNotFoundError:
            print("⚠  xdotool not found. Install with: sudo pacman -S xdotool", flush=True)
        except subprocess.CalledProcessError as e:
            print(f"⚠  xdotool error: {e}", flush=True)
        except subprocess.TimeoutExpired:
            print("⚠  xdotool timed out.", flush=True)


# ─── Hotkey listener ──────────────────────────────────────────────────────────

key_held = False


def on_press(key):
    global key_held
    if key == PUSH_TO_TALK_KEY and not key_held:
        key_held = True
        start_recording()


def on_release(key):
    global key_held
    if key == PUSH_TO_TALK_KEY and key_held:
        key_held = False
        threading.Thread(target=stop_and_transcribe, daemon=True).start()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global model

    print("🔄 Loading Whisper model (first run downloads it)…", flush=True)
    model = whisper.load_model(WHISPER_MODEL)
    print(f"✅ Whisper '{WHISPER_MODEL}' model ready.", flush=True)

    # Start audio stream (always open, only saves frames when recording=True)
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        callback=audio_callback,
        blocksize=1024,
    )

    key_name = str(PUSH_TO_TALK_KEY).replace("Key.", "")
    print(f"\n🎤 Push-to-talk ready! Hold [{key_name.upper()}] to record.")
    print("   Text will be typed at cursor + copied to clipboard.")
    print("   Press Ctrl+C to exit.\n")

    with stream:
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                print("\n👋 Exiting.")
                sys.exit(0)


if __name__ == "__main__":
    main()
