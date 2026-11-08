#!/usr/bin/env python3
"""Keeps data/status.json on the website up to date so progress and errors are visible from a phone.

Usage:
  status.py plan <phase> <cycle> id=label [id=label ...]   start a new list of steps
  status.py step <id> <running|done|error|skipped> [note]
  status.py phase <phase> [message]
  status.py history <json-object>                          append a finished cycle summary
"""
import json, os, sys, tempfile, time
from datetime import datetime, timezone

WEB = os.environ.get("WEB", "/var/www/swrf")
PATH = os.path.join(WEB, "data", "status.json")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load():
    try:
        with open(PATH) as f:
            return json.load(f)
    except Exception:
        return {"phase": "idle", "steps": [], "history": []}


def save(d):
    d["updated"] = now()
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(PATH))
    with os.fdopen(fd, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, PATH)


def main(argv):
    d = load()
    cmd = argv[1]
    if cmd == "plan":
        d["phase"], d["cycle"] = argv[2], argv[3]
        d["message"] = ""
        d["started"] = now()
        d["steps"] = []
        for item in argv[4:]:
            sid, _, label = item.partition("=")
            d["steps"].append({"id": sid, "label": label.replace("_", " "), "state": "pending"})
    elif cmd == "step":
        sid, state = argv[2], argv[3]
        note = argv[4] if len(argv) > 4 else None
        for s in d.get("steps", []):
            if s["id"] == sid:
                s["state_prev"] = s.get("state")
                s["state"] = state
                if state == "running":
                    if s.get("state_prev") != "running":
                        s["started"] = now()
                    s.pop("ended", None)
                else:
                    s["ended"] = now()
                if note is not None:
                    s["note"] = note
    elif cmd == "phase":
        d["phase"] = argv[2]
        d["message"] = argv[3] if len(argv) > 3 else ""
        if argv[2] in ("idle", "error"):
            d["finished"] = now()
    elif cmd == "history":
        h = d.setdefault("history", [])
        h.insert(0, json.loads(argv[2]))
        del h[20:]
    save(d)


if __name__ == "__main__":
    main(sys.argv)
