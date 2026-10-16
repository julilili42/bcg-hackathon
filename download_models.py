"""Download the two TTS models (~150 MB each) into models/sw and models/en.  Run: uv run download_models.py"""
from huggingface_hub import snapshot_download
from tts import MODELS, HERE
import os

for lang, repo in MODELS.items():
    dest = os.path.join(HERE, "models", lang)
    print(f"{repo} -> models/{lang}")
    snapshot_download(repo, local_dir=dest, allow_patterns=["*.json", "*.bin", "*.safetensors"])
print("done")
