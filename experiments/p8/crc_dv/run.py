"""P8 axis_crc_append 동결 RTL(실행 674c)의 DV 공백 메우기: stat_frames 16비트 롤오버(CRC-08)와 SVA(--assert).

    .venv/bin/python experiments/p8/crc_dv/run.py <동결 RTL 디렉터리> [-o build/crc_dv]

동결 RTL 디렉터리는 부서 저장소의 `runs/axis_crc_append-20261013-010208-674c/rtl`. SVA 실패는 `[SVA] FAIL` 줄로 나온다.
"""
import argparse
import glob
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from pipeline.verify.run import sim  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rtl", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=HERE.parents[2] / "build" / "crc_dv")
    a = ap.parse_args()
    r = sim([a.rtl / "axis_crc_core.sv", a.rtl / "axis_crc_append.sv", HERE / "crc_sva.sv"], "axis_crc_append",
            "test_crc_dv", HERE, a.out, build_args=["--assert", "-Wno-fatal"], timeout_s=900)
    log = "".join(Path(p).read_text(errors="replace") for p in glob.glob(str(a.out / "*.log")))
    fails = re.findall(r"\[SVA\] FAIL[^\n]*", log)
    print(f"tests ok={r.ok}, SVA FAIL {len(fails)}", [(f.test, f.message[:200]) for f in r.findings], fails[:3])
    return 0 if r.ok and not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
