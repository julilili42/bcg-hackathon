# ADR 0005 — Understanding via Claude Opus 5.5 with keyword fallback; Twilio STT; local TTS with Azure Speech option

**Status:** accepted, 2026-10-16

## Context
Callers speak loosely and speech recognition mangles place names. The prototype showed Claude handles
this well at ~2 s with low effort, and that Twilio Gather supports `sw-TZ` while Whisper-small is weak on
Swahili. Twilio has no Swahili voice, so the prototype used Meta MMS-TTS locally.

## Decision
- Understanding: `claude-opus-5-5` via the Python SDK, adaptive thinking (omit the parameter),
  `output_config` with `effort: low` and a JSON schema for structured output, server-side
  `fallbacks="default"`, 4 s timeout. On any failure or missing key: deterministic keyword matcher.
- Speech-to-text: Twilio Gather `sw-TZ` / `en-US`.
- Text-to-speech: MMS-TTS locally with pre-rendered template audio; Azure AI Speech
  (`sw-TZ-RehemaNeural`) behind the same interface for deployment.

## Consequences
- The demo must work on keywords alone; Claude improves recall, it is not a dependency.
- Prompt structure: stable domain text + candidate list first, user text last, to allow caching.
- Low-confidence matches trigger a confirmation turn in the voice flow.
- TTS cold start is mitigated by pre-rendering; live synthesis only for entity names.
