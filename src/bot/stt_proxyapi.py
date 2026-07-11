from __future__ import annotations

import asyncio
from pathlib import Path

from openai import OpenAI

from .config import Settings


def transcribe_voice_file_sync(file_path: Path, settings: Settings) -> str:
    client = OpenAI(api_key=settings.proxy_api_key, base_url=settings.proxy_base_url)
    with file_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=settings.openai_model_voice,
            file=audio_file,
        )

    text = getattr(response, "text", "") or ""
    return text.strip()


async def transcribe_voice_file(file_path: Path, settings: Settings) -> str:
    return await asyncio.to_thread(transcribe_voice_file_sync, file_path, settings)
