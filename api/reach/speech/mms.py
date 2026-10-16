"""Meta MMS-TTS on CPU (about one second per sentence). Optional extra: ``uv sync --extra tts``.

Models are fetched once by ``scripts/download_models.py`` into ``models/{sw,en}``. Not covered by CI.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from reach.core.schemas import Lang
from reach.speech.tts import audio_filename

log = logging.getLogger(__name__)

MODEL_IDS: dict[Lang, str] = {"sw": "facebook/mms-tts-swh", "en": "facebook/mms-tts-eng"}


class MMSTTS:
    name = "mms"

    def __init__(self, models_dir: Path, audio_dir: Path) -> None:
        import torch  # noqa: F401 - import check only
        import transformers  # noqa: F401

        self.models_dir = models_dir
        self.audio_dir = audio_dir

    def available(self) -> bool:
        return all((self.models_dir / lang).is_dir() for lang in MODEL_IDS)

    @lru_cache(maxsize=4)  # noqa: B019 - one model per language for the process lifetime
    def _load(self, lang: Lang) -> tuple[Any, Any] | None:
        from transformers import AutoTokenizer, VitsModel

        path = self.models_dir / lang
        if not path.is_dir():
            return None
        return VitsModel.from_pretrained(str(path)), AutoTokenizer.from_pretrained(str(path))

    def synthesize(self, text: str, lang: Lang) -> Path | None:
        loaded = self._load(lang)
        if loaded is None:
            return None
        import soundfile as sf
        import torch

        model, tokenizer = loaded
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        out = self.audio_dir / audio_filename(text, lang, self.name)
        if out.exists():
            return out
        with torch.no_grad():
            waveform = model(**tokenizer(text, return_tensors="pt")).waveform[0].numpy()
        sf.write(str(out), waveform, model.config.sampling_rate)
        return out
