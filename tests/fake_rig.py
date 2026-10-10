"""테스트용 가짜 OpenRig CLI. 상태는 FAKE_RIG_DIR의 파일에 둔다.

send를 받으면 Seat가 곧바로 답했다고 보고 transcript 파일에 보낸 본문과 답을 덧붙인다.
FAKE_RIG_MODE=silent 이면 답하지 않고, wrong_sender 이면 다른 이름으로 답한다.
"""
import json
import os
import re
import sys
from pathlib import Path

d = Path(os.environ["FAKE_RIG_DIR"])
mode = os.environ.get("FAKE_RIG_MODE", "ok")
cmd, args = sys.argv[1], sys.argv[2:]

if cmd == "send":
    session, text = args[0], args[1]
    log = d / f"{session}.log"
    with log.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
        m = re.search(r"보낸 사람: (\S+) .*메시지 ID: (\w+)", text)
        if m and mode != "silent":
            name = "someone" if mode == "wrong_sender" else m.group(1)
            f.write(f"ACK {m.group(2)} {name}\n")
    print(json.dumps({"outcome": "delivered"}))
elif cmd == "transcript":
    log = d / f"{args[0]}.log"
    print(log.read_text(encoding="utf-8") if log.exists() else "")
elif cmd == "ps":
    seats = os.environ.get("FAKE_RIG_SEATS", "").split(",")
    print(json.dumps([{"canonicalSessionName": s, "agentActivity": {"state": "idle"}} for s in seats if s]))
else:
    sys.exit(2)
