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


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from x2_wavejson.wavejson import render as draw  # noqa: E402

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
    "syn_apb_write": {"signal": [
        {"name": "pclk", "wave": "p......"},
        {"name": "psel", "wave": "01..0.."},
        {"name": "penable", "wave": "0.1.0.."},
        {"name": "pwrite", "wave": "x1..x.."},
        {"name": "paddr", "wave": "x=..x..", "data": ["0x08"]},
        {"name": "pready", "wave": "0..10.."},
    ]},
    "syn_apb_read_wait": {"signal": [
        {"name": "pclk", "wave": "p......."},
        {"name": "psel", "wave": "01...0.."},
        {"name": "penable", "wave": "0.1..0.."},
        {"name": "pready", "wave": "0...10.."},
        {"name": "prdata", "wave": "x...=x..", "data": ["0x5A"]},
    ]},
    "syn_irq_pulse": {"signal": [
        {"name": "clk", "wave": "p........"},
        {"name": "event", "wave": "0.10..10."},
        {"name": "irq", "wave": "0..10..10"},
        {"name": "irq_en", "wave": "1........"},
    ]},
    "syn_cmd_queue": {"signal": [
        {"name": "clk", "wave": "p........."},
        {"name": "cmd_valid", "wave": "01.0.1.0.."},
        {"name": "cmd_ready", "wave": "1.01..0..."},
        {"name": "cmd_op", "wave": "x=.x.==x..", "data": ["WR", "RD", "WR"]},
        {"name": "busy", "wave": "0.1......0"},
    ]},
    "syn_counter_wrap": {"signal": [
        {"name": "clk", "wave": "p......."},
        {"name": "en", "wave": "01.....0"},
        {"name": "cnt", "wave": "=.=====.", "data": ["0", "1", "2", "3", "0", "1"]},
        {"name": "wrap", "wave": "0....10."},
    ]},
    "syn_scl_sda_start": {"signal": [
        {"name": "clk", "wave": "p........."},
        {"name": "scl", "wave": "1...0.1.0."},
        {"name": "sda", "wave": "1.0.....1."},
        {"name": "start_det", "wave": "0..10....."},
    ]},
    "syn_resp_fifo": {"signal": [
        {"name": "clk", "wave": "p........"},
        {"name": "resp_valid", "wave": "0.1..0.1."},
        {"name": "resp_ready", "wave": "0.1.01.1."},
        {"name": "resp_code", "wave": "x.=.=x.=.", "data": ["OK", "NACK", "OK"]},
    ]},
    "syn_soft_reset": {"signal": [
        {"name": "clk", "wave": "p......."},
        {"name": "soft_rst", "wave": "0.10...."},
        {"name": "enable", "wave": "1..0.1.."},
        {"name": "status", "wave": "=..=.=..", "data": ["RUN", "RESET", "IDLE"]},
    ]},
}

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
