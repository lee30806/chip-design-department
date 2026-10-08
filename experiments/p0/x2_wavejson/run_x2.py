"""X2: 비전 모델을 쓰는 coding agent의 타이밍 다이어그램 → WaveJSON 변환 정확도.

samples/ 아래에 그림과 정답을 같은 이름으로 둔다.
  samples/<이름>.png (또는 .jpg)   SPEC에서 잘라 낸 타이밍 다이어그램
  samples/<이름>.json              사람이 작성한 정답 WaveJSON

trial마다 작업 디렉터리에 그림 하나와 TASK.md를 두고 agent를 실행한다.
agent는 out/wave.json을 써야 한다. 설정에서 "vision": true인 agent만 실행한다.

사용 예
  python3 experiments/p0/x2_wavejson/run_x2.py --agents experiments/p0/agents.json --repeat 3
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.agent import load_agents, run_agent  # noqa: E402
from x2_wavejson.wavejson import compare, parse_wavejson  # noqa: E402

ROOT = HERE.parents[2]
IMAGE_EXT = {".png", ".jpg", ".jpeg"}

TASK = """\
# 과제: 타이밍 다이어그램을 WaveJSON으로 변환

`{image}`은 디지털 회로의 타이밍 다이어그램이다. 그림을 보고 WaveDrom의 WaveJSON으로 변환해 `out/wave.json`에 쓴다.

## 규칙
- 파일 내용은 {{"signal": [...]}} 형태의 JSON 객체 하나다.
- 신호 이름은 그림에 적힌 그대로 쓴다.
- wave 문자열의 한 글자가 한 클럭 사이클이다. 모든 신호의 wave 길이를 같게 맞춘다.
- 클럭은 p(상승 에지 시작)와 '.', 0/1 레벨은 0과 1, 값이 바뀌는 버스는 '='와 data 라벨, 알 수 없는 값은 x, 고임피던스는 z를 쓴다.
- 앞과 같은 값이 이어지면 '.'을 쓴다.
- `out/wave.json` 외의 파일은 만들거나 고치지 않는다.
"""


def load_samples(d: Path) -> list[tuple[Path, dict]]:
    out = []
    for img in sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXT):
        gt = img.with_suffix(".json")
        if not gt.exists():
            print(f"정답 없음, 건너뜀: {img.name}", file=sys.stderr)
            continue
        out.append((img, parse_wavejson(gt.read_text(encoding="utf-8"))))
    return out


def score(work: Path, gt: dict) -> dict:
    out = work / "out" / "wave.json"
    zero = {"cycle_accuracy": 0.0, "signal_recall": 0.0, "signal_precision": 0.0, "exact": False}
    if not out.exists():
        return {"parse_ok": False, **zero}
    try:
        pred = parse_wavejson(out.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"parse_ok": False, **zero}
    return {"parse_ok": True, **compare(gt, pred)} if isinstance(pred, dict) else {"parse_ok": False, **zero}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agents", required=True)
    ap.add_argument("--only", help="쉼표로 구분한 agent name만 실행")
    ap.add_argument("--samples", default=str(HERE / "samples"))
    ap.add_argument("--repeat", type=int, default=3, help="그림당 반복 횟수 (변동성 확인)")
    ap.add_argument("--out", default=str(ROOT / "experiments" / "p0" / "results"))
    args = ap.parse_args(argv)

    agents = [a for a in load_agents(args.agents) if a.vision]
    if args.only:
        keep = set(args.only.split(","))
        agents = [a for a in agents if a.name in keep]
    samples = load_samples(Path(args.samples))
    if not samples:
        print("샘플이 없습니다. samples/README.md를 보세요.", file=sys.stderr)
        return 1

    out_dir = Path(args.out) / f"x2-{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with (out_dir / "trials.jsonl").open("w", encoding="utf-8") as f:
        for cfg in agents:
            for img, gt in samples:
                for i in range(args.repeat):
                    work = out_dir / "work" / cfg.name / f"{img.stem}-{i}"
                    (work / "out").mkdir(parents=True)
                    shutil.copy(img, work / img.name)
                    run = run_agent(cfg, work, TASK.format(image=img.name))
                    row = {"agent": cfg.name, "runtime": cfg.runtime, "family": cfg.family, "sample": img.stem,
                           "trial": i, "workdir": str(work), "exit_ok": run.exit_ok, "duration_s": run.duration_s,
                           **score(work, gt)}
                    rows.append(row)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"[{cfg.name}] {img.stem} {i + 1}/{args.repeat} {row['cycle_accuracy']:.2%}", file=sys.stderr)

    lines = [f"# X2 결과 ({time.strftime('%Y-%m-%d %H:%M')})", "",
             "| agent | 런타임 | 계열 | 시도 | 정상 종료 | 결과 파싱 | 사이클 정확도 (평균) | 사이클 정확도 (최저) | 신호 재현율 | 신호 정밀도 | 완전 일치 | 평균 시간(s) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name in dict.fromkeys(r["agent"] for r in rows):
        m = [r for r in rows if r["agent"] == name]
        mean = lambda k: f"{statistics.mean(r[k] for r in m):.1%}"  # noqa: E731
        pct = lambda k: f"{100 * sum(r[k] for r in m) / len(m):.0f}%"  # noqa: E731
        lines.append(f"| {name} | {m[0]['runtime']} | {m[0]['family']} | {len(m)} | {pct('exit_ok')} | {pct('parse_ok')} | "
                     f"{mean('cycle_accuracy')} | {min(r['cycle_accuracy'] for r in m):.1%} | {mean('signal_recall')} | "
                     f"{mean('signal_precision')} | {sum(r['exact'] for r in m)}/{len(m)} | "
                     f"{statistics.mean(r['duration_s'] for r in m):.0f} |")
    summary = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"결과: {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
