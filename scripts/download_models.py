"""Download the two TTS models (~150 MB each) into models/sw and models/en.  Run: uv run scripts/download_models.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from huggingface_hub import snapshot_download
from gateway.tts import MODELS, ROOT

for lang, repo in MODELS.items():
    print(f"{repo} -> models/{lang}")
    snapshot_download(repo, local_dir=os.path.join(ROOT, "models", lang), allow_patterns=["*.json", "*.bin", "*.safetensors"])
print("done")
