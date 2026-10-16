"""Text -> wav via Meta MMS-TTS (runs on CPU, ~1 s per sentence). Models come from scripts/download_models.py.
Returns None when models are missing, the caller then falls back to Twilio <Say>."""
import os, hashlib, functools
MODELS = {"sw": "facebook/mms-tts-swh", "en": "facebook/mms-tts-eng"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, "audio")


@functools.lru_cache(maxsize=None)
def _load(lang):
    from transformers import VitsModel, AutoTokenizer
    path = os.path.join(ROOT, "models", lang)
    if not os.path.isdir(path):
        return None
    return VitsModel.from_pretrained(path), AutoTokenizer.from_pretrained(path)


def speak(text, lang):
    """-> filename in audio/ or None."""
    loaded = _load(lang)
    if not loaded:
        return None
    import torch, soundfile as sf
    model, tok = loaded
    name = hashlib.md5(f"{lang}:{text}".encode()).hexdigest() + ".wav"
    out = os.path.join(AUDIO, name)
    if not os.path.exists(out):
        os.makedirs(AUDIO, exist_ok=True)
        with torch.no_grad():
            wav = model(**tok(text, return_tensors="pt")).waveform[0].numpy()
        sf.write(out, wav, model.config.sampling_rate)
    return name


if __name__ == "__main__":
    for lang, text in [("en", "The nearest working water point is Kanisa."), ("sw", "Kisima cha karibu kinachofanya kazi ni Kanisa.")]:
        print(lang, speak(text, lang) or "model missing, run scripts/download_models.py")
