#!/usr/bin/env python3
"""Fetch the two MMS-TTS models (~300 MB) into models/{sw,en}. Needs: uv sync --extra tts."""

from __future__ import annotations

import sys
from pathlib import Path

MODELS = {"sw": "facebook/mms-tts-swh", "en": "facebook/mms-tts-eng"}


def main() -> int:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub missing: run `uv sync --extra tts` first", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parents[1] / "models"
    for lang, repo in MODELS.items():
        target = root / lang
        if target.is_dir():
            print(f"{lang}: present")
            continue
        print(f"{lang}: downloading {repo}")
        snapshot_download(repo, local_dir=str(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
