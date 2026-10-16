# ADR 0004 — Reporter identity stored as salted hash only

**Status:** accepted, 2026-10-16

## Context
Twilio delivers the caller's number. Phone numbers are personal data. The hackathon demo uses team
phones, but the code must be safe to run with real users, and the repo is public.

## Decision
Compute `reporter_hash = sha256(REPORTER_SALT + E.164 number)` at the channel boundary and discard the
raw number. Store and log the hash only. `REPORTER_SALT` is a setting, never committed. Raw message text
is kept 30 days for debugging and then purged by a scheduled function. Fixtures and tests use numbers in
a documented fake range.

## Consequences
- Rate limiting and conflict detection still work per reporter.
- No call-back feature without an explicit, separate consent flow (out of scope).
- The team confirms review of the BCG Guidelines for the Use of AI for Personal Data Processing before
  the first real-phone test (open item O9).
