"""X2 리허설용 합성 샘플 생성기.

정답 WaveJSON에서 타이밍 다이어그램 PNG를 그려 samples/에 <이름>.png, <이름>.json으로 둔다.
실제 SPEC 그림이 오기 전에 실행기와 비교기를 실제 비전 모델로 시험하는 용도이며,
X2의 판정에는 SPEC에서 잘라 낸 그림을 써야 한다. PyMuPDF(fitz)로 그린다.

  python3 experiments/p0/x2_wavejson/make_synthetic.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fitz  # PyMuPDF

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from x2_wavejson.wavejson import expand, flatten  # noqa: E402

SAMPLES = {
    "syn_handshake": {"signal": [
        {"name": "clk", "wave": "p......."},
        {"name": "valid", "wave": "01...0.."},
        {"name": "ready", "wave": "0.1.0.1."},
        {"name": "data", "wave": "x=.=.x..", "data": ["A", "B"]},
    ]},
    "syn_reset_fsm": {"signal": [
        {"name": "clk", "wave": "p......."},
        {"name": "rst_n", "wave": "0.1....."},
        {"name": "state", "wave": "=..=.=..", "data": ["IDLE", "RUN", "DONE"]},
        {"name": "busy", "wave": "0..1.0.."},
    ]},
    "syn_read_burst": {"signal": [
        {"name": "clk", "wave": "p........"},
        {"name": "req", "wave": "010......"},
        {"name": "addr", "wave": "x=x......", "data": ["0x40"]},
        {"name": "rvalid", "wave": "0..1...0."},
        {"name": "rdata", "wave": "x..====x.", "data": ["D0", "D1", "D2", "D3"]},
    ]},
    "syn_fifo": {"signal": [
        {"name": "clk", "wave": "p........"},
        {"name": "wr_en", "wave": "0110....."},
        {"name": "rd_en", "wave": "0...110.."},
        {"name": "full", "wave": "0..1.0..."},
        {"name": "empty", "wave": "1.0...1.."},
        {"name": "count", "wave": "=.==.==..", "data": ["0", "1", "2", "1", "0"]},
    ]},
}

CW, RH, X0, Y0, AMP = 48, 36, 90, 20, 18  # 사이클 폭, 행 높이, 파형 시작 x, 첫 행 y, 진폭


def draw(wj: dict, path: Path) -> None:
    sigs = list(flatten(wj).values())
    ncyc = max(len(expand(s)) for s in sigs)
    doc = fitz.open()
    page = doc.new_page(width=X0 + CW * ncyc + 20, height=Y0 + RH * len(sigs) + 10)
    black, grey = (0, 0, 0), (0.75, 0.75, 0.75)
    for c in range(ncyc + 1):  # 사이클 경계 보조선
        page.draw_line((X0 + c * CW, Y0 - 8), (X0 + c * CW, Y0 + RH * len(sigs)), color=grey, width=0.5, dashes="[2] 0")
    for r, sig in enumerate(sigs):
        top = Y0 + r * RH + 6
        hi, lo, mid = top, top + AMP, top + AMP / 2
        page.insert_text((8, mid + 4), sig["name"], fontsize=11, color=black)
        prev = None
        for i, (st, label) in enumerate(expand(sig)):
            x1, x2 = X0 + i * CW, X0 + (i + 1) * CW
            line = lambda a, b: page.draw_line(a, b, color=black, width=1.2)  # noqa: E731
            if st in ("p", "n"):
                first, second = (hi, lo) if st == "p" else (lo, hi)
                line((x1, lo), (x1, hi)) if st == "p" else line((x1, hi), (x1, lo))
                line((x1, first), ((x1 + x2) / 2, first))
                line(((x1 + x2) / 2, first), ((x1 + x2) / 2, second))
                line(((x1 + x2) / 2, second), (x2, second))
            elif st in ("0", "1"):
                y = lo if st == "0" else hi
                if prev and prev[0] in ("0", "1") and prev[0] != st:
                    line((x1, hi), (x1, lo))
                line((x1, y), (x2, y))
            elif st in ("=", "x"):
                new_seg = prev != (st, label)
                start = x1 + 6 if new_seg else x1
                if new_seg:
                    line((x1, mid), (start, hi))
                    line((x1, mid), (start, lo))
                line((start, hi), (x2, hi))
                line((start, lo), (x2, lo))
                if st == "x":
                    for k in range(int(start), int(x2), 8):
                        page.draw_line((k, lo), (min(k + 8, x2), hi), color=grey, width=0.8)
                elif new_seg and label:
                    page.insert_text((start + 4, mid + 4), label, fontsize=10, color=black)
            elif st == "z":
                line((x1, mid), (x2, mid))
            prev = (st, label)
    page.get_pixmap(dpi=144).save(str(path))
    doc.close()


def main() -> int:
    out = HERE / "samples"
    out.mkdir(exist_ok=True)
    for name, wj in SAMPLES.items():
        draw(wj, out / f"{name}.png")
        (out / f"{name}.json").write_text(json.dumps(wj, indent=1), encoding="utf-8")
        print(out / f"{name}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
