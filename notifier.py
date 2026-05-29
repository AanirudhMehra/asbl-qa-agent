import os
import json
import requests
from datetime import datetime

TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")

def notify(agent_name: str, status: str, details: dict):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Always log to console
    print(f"\n{'='*60}")
    print(f"[{timestamp}] {agent_name} — {status}")
    for key, value in details.items():
        print(f"  {key}: {value}")
    print(f"{'='*60}\n")

    # Always log to file
    log_entry = {
        "timestamp": timestamp,
        "agent": agent_name,
        "status": status,
        **details
    }
    log_path = os.path.join(os.path.dirname(__file__), "results", "qa_log.jsonl")
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Send to Teams only if webhook is configured
    if TEAMS_WEBHOOK_URL and TEAMS_WEBHOOK_URL != "add_later":
        try:
            payload = {
                "text": f"**{agent_name}** — {status}\n" +
                        "\n".join([f"• {k}: {v}" for k, v in details.items()])
            }
            requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=5)
        except Exception as e:
            print(f"[notifier] Teams webhook failed: {e}")
