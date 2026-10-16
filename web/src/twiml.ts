/** Parse the TwiML the voice/SMS handlers return, so the virtual phone can act like Twilio. */

export type Utterance = { kind: "say"; text: string } | { kind: "play"; url: string };

export interface GatherSpec {
  action: string;
  input: string;
  language: string;
  hints: string[];
  prompt: Utterance[];
}

export interface TwimlResult {
  utterances: Utterance[];
  gather: GatherSpec | null;
  hangup: boolean;
  messages: string[];
  redirect: string | null;
}

function utterancesOf(parent: Element): Utterance[] {
  const out: Utterance[] = [];
  for (const child of Array.from(parent.children)) {
    if (child.tagName === "Say") out.push({ kind: "say", text: child.textContent ?? "" });
    else if (child.tagName === "Play") out.push({ kind: "play", url: child.textContent ?? "" });
  }
  return out;
}

export function parseTwiml(xml: string): TwimlResult {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const result: TwimlResult = { utterances: [], gather: null, hangup: false, messages: [], redirect: null };
  const root = doc.documentElement;
  if (!root || root.tagName !== "Response") return result;
  for (const el of Array.from(root.children)) {
    switch (el.tagName) {
      case "Say":
        result.utterances.push({ kind: "say", text: el.textContent ?? "" });
        break;
      case "Play":
        result.utterances.push({ kind: "play", url: el.textContent ?? "" });
        break;
      case "Gather": {
        const prompt = utterancesOf(el);
        result.utterances.push(...prompt);
        result.gather = {
          action: el.getAttribute("action") ?? "",
          input: el.getAttribute("input") ?? "speech dtmf",
          language: el.getAttribute("language") ?? "en-US",
          hints: (el.getAttribute("hints") ?? "").split(",").map((h) => h.trim()).filter(Boolean),
          prompt,
        };
        break;
      }
      case "Message":
        result.messages.push(el.textContent ?? "");
        break;
      case "Hangup":
        result.hangup = true;
        break;
      case "Redirect":
        result.redirect = el.textContent ?? null;
        break;
      default:
        break;
    }
  }
  return result;
}
