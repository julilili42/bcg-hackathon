"""Local recording -> Whisper transcript -> existing HTTP POST /interact."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx


def transcribe(path: Path, model_name: str) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install local audio support: pip install -r requirements-audio.txt") from exc
    model = WhisperModel(model_name, device="cpu", compute_type="int8",
                         download_root=str(Path(__file__).parent / ".cache" / "whisper"))
    segments, _ = model.transcribe(str(path), language="en", vad_filter=True,
        initial_prompt="Water point names: Alero, Lumwa, Palaro. Clinic pump, school borehole, market tap.")
    return " ".join(segment.text.strip() for segment in segments).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="A recorded audio file, e.g. WAV, MP3 or M4A")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="WaterLine server origin")
    parser.add_argument("--user-id", default="demo-audio-user")
    parser.add_argument("--turn-id", default=str(uuid4()), help="Reuse this ID when retrying the same recording")
    parser.add_argument("--model", default="base.en", help="Local Whisper model; downloaded on first use")
    parser.add_argument("--transcribe-only", action="store_true", help="Print transcript without sending it")
    parser.add_argument("--speak", action="store_true", help="Read the answer using macOS's system voice")
    args = parser.parse_args()
    if not args.audio.is_file():
        parser.error(f"Audio file not found: {args.audio}")
    if args.speak and not shutil.which("say"):
        parser.error("--speak requires the macOS say command; omit it to get a text answer.")
    try:
        print("Transcribing locally (the first run downloads the Whisper model)...", flush=True)
        transcript = transcribe(args.audio, args.model)
        if not transcript:
            parser.exit(1, "No speech detected. Nothing was sent or saved.\n")
        print(f"Transcript: {transcript}", flush=True)
        if args.transcribe_only:
            return
        if len(transcript) > 5000:
            parser.error("Transcript exceeds the API's 5000-character limit; use a shorter recording.")
        print(f"Sending to /interact with turn_id={args.turn_id}", flush=True)
        response = httpx.post(args.url.rstrip("/") + "/interact", json={
            "message": transcript, "user_id": args.user_id, "turn_id": args.turn_id,
        }, timeout=180)
        if response.is_error:
            parser.exit(1, f"HTTP {response.status_code}: {response.text}\nRetry with --turn-id {args.turn_id}\n")
        result = response.json()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.speak:
            subprocess.run(["say"], input=result["answer"], text=True, check=True)
    except httpx.RequestError:
        parser.exit(1, f"Could not reach {args.url}. Start Uvicorn and retry with --turn-id {args.turn_id}.\n")
    except (RuntimeError, ValueError, OSError) as exc:
        parser.exit(1, f"Audio test failed: {exc}\n")


if __name__ == "__main__":
    main()
