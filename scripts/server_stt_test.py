#!/usr/bin/env python3
from __future__ import annotations

import struct
import sys
import wave
from pathlib import Path

ROOT = Path("/opt/kitchens-bot")
sys.path.insert(0, str(ROOT))

from src.bot.config import load_settings
from src.bot.stt_proxyapi import transcribe_voice_file_sync

p = Path("/tmp/test_voice.wav")
with wave.open(str(p), "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(b"".join(struct.pack("<h", 0) for _ in range(16000)))

settings = load_settings()
try:
    text = transcribe_voice_file_sync(p, settings)
    print("STT_OK", repr(text[:120]))
except Exception as exc:
    print("STT_ERR", type(exc).__name__, str(exc)[:300])
    sys.exit(1)
