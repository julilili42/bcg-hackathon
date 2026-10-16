"""Fixed-clock CLI scenario. Live LLM + real Qdrant; no fabricated answers."""
import argparse
import asyncio
import json
from uuid import uuid4

from graph import ConfigurationError, check_configuration, handle_turn
from seed import seed

SCENARIO = [
    ("demo-user-a", "2026-10-16T08:30:00Z", "The clinic pump in Alero broke this morning. Is the school borehole still working?"),
    ("demo-user-b", "2026-10-16T09:00:00Z", "Is the Alero clinic pump working?"),
    ("demo-user-a", "2026-10-16T14:30:00Z", "I saw the Alero clinic pump repaired this afternoon. Is it usable now?"),
    ("demo-user-b", "2026-10-16T14:40:00Z", "Can I safely drink the water from the Alero market tap?"),
]


async def main(interactive=False):
    check_configuration()
    print("WaterLine | One report helps the next village.\nSYNTHETIC DEMO: fictional places and reports. Community contributions are stored and reused.\n")
    if interactive:
        from knowledge import utcnow
        while (message := input("Message (blank to exit): ").strip()):
            print(json.dumps(await handle_turn(message, "demo-user", str(uuid4()), utcnow()), indent=2))
    else:
        seed()
        for index, (user, timestamp, message) in enumerate(SCENARIO):
            print(f"\n{user} | {timestamp}\n> {message}")
            result = await handle_turn(message, user, f"demo-story-{index}", timestamp)
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.interactive))
    except ConfigurationError as exc:
        parser.exit(1, f"WaterLine setup required: {exc}\n")
