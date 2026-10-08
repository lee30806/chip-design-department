"""테스트용 가짜 coding agent. 작업 디렉터리(cwd)에서 FAKE_MODE에 따라 행동한다."""
import json
import os
import subprocess
import sys
from pathlib import Path

FIX = Path(__file__).resolve().parent / "fixtures" / "pkt_parser.ir.json"
mode = os.environ["FAKE_MODE"]
cwd = Path.cwd()
assert (cwd / "TASK.md").exists()
out = cwd / "out" / "pkt_parser.ir.json"


def validate():
    subprocess.run([sys.executable, "tools/validate_ir.py", str(out.relative_to(cwd))], capture_output=True)


if mode == "good":
    out.write_text(FIX.read_text())
    validate()
elif mode == "bad_then_good":
    # 첫 실행은 틀린 파일, 재시도(TASK.md에 검사 결과 포함)에서 고침
    if "이전 시도의 검사 결과" in (cwd / "TASK.md").read_text():
        out.write_text(FIX.read_text())
    else:
        out.write_text('{"module": "pkt_parser"}')
elif mode == "touch_l1":
    out.write_text(FIX.read_text())
    (cwd / "l1.json").write_text("{}")
elif mode == "crash":
    sys.exit(3)
elif mode == "wave":
    (cwd / "out" / "wave.json").write_text(os.environ["FAKE_WAVE"])
