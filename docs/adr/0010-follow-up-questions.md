# ADR 0010 — Follow-up questions only when a slot is missing

**Status:** accepted, 2026-10-16

## Context
Callers and texters leave things out: "hakuna maji" without a place, "Marui borehole is dry" when
there are two Marui boreholes, or a name that speech recognition mangled. Until now SMS could only
say "please resend" and voice confirmed one case through state hidden in the action URL. Asking too
much is as bad as asking nothing: people hang up.

## Decision
The service keeps **one open question per sender and channel** (`conversations` table, key
`<channel>:<reporter_hash>`, 10-minute expiry) and asks only in three situations:

| Situation | Question | Answer accepted |
|---|---|---|
| Status given, no place found | "You said broken. Which water point?" | any text that matches a point |
| Two equally good places | "Did you mean A or B? Reply 1 or 2" (voice: press 1 or 2) | 1, 2, or one of the names |
| One uncertain place with a status (confidence below the channel threshold) | "Did you mean A? Reply YES or NO" (voice: press 1 or 2) | yes/no/ndiyo/hapana/1/2 |

Rules:
- A query (no status) is answered directly even when the match is uncertain; only ambiguity between
  two candidates asks, because the answer would otherwise be about the wrong place.
- The status is carried across the question: "hakuna maji" → "Which point?" → "Bwawa" records Bwawa
  as empty. "No" to a guess keeps the status and asks for the place.
- Any message that is itself a complete report replaces the open question.
- At most two follow-ups; then a short help text and the slate is cleared.
- Voice and SMS share the same logic; voice gathers the answer as key press or speech on
  `/api/voice/answer`.

## Consequences
- Fewer dead ends: a report with a missing slot becomes a two-message conversation instead of a
  "sorry".
- One new table, shared by channels; the web form never needs it.
- Templates per domain and language grew by seven keys (`confirm_sms`, `choose`, `choose_sms`,
  `need_entity`, `need_entity_sms`, `cancelled_sms`, `give_up`).
