"""Server-side Azure Neural TTS; resource credentials never reach the browser."""
import os
import re
from html import escape
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
DEFAULT_ENDPOINT = "https://germanywestcentral.api.cognitive.microsoft.com/"


def spoken_text(text):
    """Keep technical references and formatting out of either voice adapter."""
    text = re.sub(r"\b(?:community report|report|source)\s+[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b",
                  "a community report", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"[ \t]+", " ", re.sub(r"[*`#]", "", text)).strip()


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4096)
    voice: Literal["en-US-AvaMultilingualNeural", "en-US-AndrewMultilingualNeural", "en-GB-SoniaNeural"] = "en-US-AvaMultilingualNeural"


def synthesis_endpoint():
    """Accept the Azure portal's regional base URL or the regional TTS URL."""
    endpoint = urlsplit(os.getenv("AZURE_SPEECH_ENDPOINT", "").strip() or DEFAULT_ENDPOINT)
    match = re.fullmatch(r"([a-z][a-z0-9]+)\.(?:api\.cognitive\.microsoft\.com|tts\.speech\.microsoft\.com)", endpoint.hostname or "")
    if (not match or endpoint.scheme != "https" or endpoint.username or endpoint.password
            or endpoint.netloc.lower() != endpoint.hostname or endpoint.query or endpoint.fragment
            or endpoint.path.rstrip("/") not in {"", "/cognitiveservices/v1"}):
        raise HTTPException(503, "AZURE_SPEECH_ENDPOINT must be an Azure regional Speech or Cognitive Services HTTPS endpoint.")
    return f"https://{match[1]}.tts.speech.microsoft.com/cognitiveservices/v1"


@router.post("/speech")
async def create_speech(request: SpeechRequest):
    key = os.getenv("AZURE_SPEECH_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Spoken replies are not configured yet. Add AZURE_SPEECH_KEY to .env and restart the API.")
    if not request.text.strip():
        raise HTTPException(422, "Speech text cannot be blank.")
    endpoint = synthesis_endpoint()
    # Escape the answer as text, so source content cannot inject SSML instructions.
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{request.voice[:5]}">'
            f'<voice name="{request.voice}"><prosody rate="-2%">{escape(spoken_text(request.text))}</prosody></voice></speak>')
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(endpoint,
                headers={"Ocp-Apim-Subscription-Key": key,
                         "Content-Type": "application/ssml+xml",
                         "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                         "User-Agent": "WaterLine-Demo"},
                content=ssml.encode("utf-8"))
        response.raise_for_status()
        if not response.content or not response.headers.get("content-type", "").startswith("audio/"):
            raise ValueError("Invalid speech response")
    except httpx.HTTPStatusError as error:
        # Do not pass through Azure error bodies, which may contain private request details.
        if error.response.status_code in {401, 403}:
            raise HTTPException(503, "Azure speech authentication failed. Check that AZURE_SPEECH_KEY belongs to a Speech-enabled resource in the endpoint's region. Your text answer is still available.") from None
        if error.response.status_code == 429:
            raise HTTPException(503, "Azure speech quota or rate limit reached. Check your resource quota, then use Hear last reply. Your text answer is still available.") from None
        if error.response.status_code == 400:
            raise HTTPException(502, "Azure could not synthesize this reply. Check voice availability for your region or select another voice. Your text answer is still available.") from None
        raise HTTPException(502, "Speech generation is temporarily unavailable. Your text answer is still available.") from None
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Speech generation is temporarily unavailable. Your text answer is still available.") from None
    return Response(response.content, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
