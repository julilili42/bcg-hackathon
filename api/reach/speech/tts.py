"""TTS providers. ``NullTTS`` makes the channel fall back to Twilio's own voice."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Protocol

import httpx

from reach.core.schemas import Lang
from reach.settings import Settings

log = logging.getLogger(__name__)

AZURE_VOICES: dict[Lang, str] = {"sw": "sw-TZ-RehemaNeural", "en": "en-US-JennyNeural"}


def audio_filename(text: str, lang: str, provider: str) -> str:
    return hashlib.sha1(f"{provider}:{lang}:{text}".encode()).hexdigest() + ".wav"


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, lang: Lang) -> Path | None: ...


class NullTTS:
    name = "none"

    def synthesize(self, text: str, lang: Lang) -> Path | None:
        return None


class AzureSpeechTTS:
    """Azure AI Speech REST API. Swahili (Tanzania) neural voice; cached as wav per text."""

    name = "azure"

    def __init__(self, key: str, region: str, audio_dir: Path, client: httpx.Client | None = None) -> None:
        self.key = key
        self.region = region
        self.audio_dir = audio_dir
        self._client = client or httpx.Client(timeout=10.0)

    def synthesize(self, text: str, lang: Lang) -> Path | None:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        out = self.audio_dir / audio_filename(text, lang, self.name)
        if out.exists():
            return out
        voice = AZURE_VOICES[lang]
        xml_lang = "sw-TZ" if lang == "sw" else "en-US"
        ssml = (
            f"<speak version='1.0' xml:lang='{xml_lang}'><voice name='{voice}'>"
            f"{_xml_escape(text)}</voice></speak>"
        )
        try:
            resp = self._client.post(
                f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1",
                headers={
                    "Ocp-Apim-Subscription-Key": self.key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "riff-8khz-16bit-mono-pcm",
                    "User-Agent": "reach-hackathon",
                },
                content=ssml.encode("utf-8"),
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("azure tts failed: %s", exc)
            return None
        out.write_bytes(resp.content)
        return out


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_tts(settings: Settings) -> TTSProvider:
    choice = settings.tts_provider.lower()
    if choice in ("azure", "auto") and settings.azure_speech_key and settings.azure_speech_region:
        return AzureSpeechTTS(settings.azure_speech_key, settings.azure_speech_region, settings.audio_dir)
    if choice in ("mms", "auto"):
        try:
            from reach.speech.mms import MMSTTS

            provider = MMSTTS(settings.models_dir, settings.audio_dir)
            if provider.available():
                return provider
            if choice == "mms":
                log.warning("TTS_PROVIDER=mms but models are missing in %s", settings.models_dir)
        except ImportError:
            if choice == "mms":
                log.warning("TTS_PROVIDER=mms but torch/transformers are not installed (uv sync --extra tts)")
    return NullTTS()
