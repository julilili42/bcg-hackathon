"""Tiny TwiML builder with proper escaping. No Twilio SDK needed."""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr


def response(*children: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(children) + "</Response>"


def say(text: str, language: str | None = None) -> str:
    attr = f" language={quoteattr(language)}" if language else ""
    return f"<Say{attr}>{escape(text)}</Say>"


def play(url: str) -> str:
    return f"<Play>{escape(url)}</Play>"


def gather(
    inner: str,
    action: str,
    *,
    input_: str = "speech dtmf",
    language: str = "sw-TZ",
    num_digits: int = 1,
    speech_timeout: str = "auto",
    hints: str | None = None,
    timeout: int = 6,
) -> str:
    attrs = (
        f' input={quoteattr(input_)} action={quoteattr(action)} method="POST"'
        f' language={quoteattr(language)} numDigits="{num_digits}" speechTimeout={quoteattr(speech_timeout)}'
        f' timeout="{timeout}"'
    )
    if hints:
        attrs += f" hints={quoteattr(hints[:500])}"
    return f"<Gather{attrs}>{inner}</Gather>"


def message(text: str) -> str:
    return f"<Message>{escape(text)}</Message>"


def hangup() -> str:
    return "<Hangup/>"


def redirect(url: str) -> str:
    return f'<Redirect method="POST">{escape(url)}</Redirect>'
