"""WaveJSON을 사이클 단위로 펼치고 정답과 비교한다.

비교 규칙
- 신호는 이름으로 짝짓는다 (대소문자, 공백 무시).
- 각 사이클의 상태와 데이터 라벨이 모두 같아야 일치로 본다.
- '.', '|'는 직전 사이클 유지. h/H→1, l/L→0, P→p, N→n, '2'~'9'→'=' (색 차이는 무시).
- period가 정수 k이면 문자 하나가 k 사이클. phase는 무시한다.
- 정답에 있는데 예측에 없는 신호는 모든 사이클을 불일치로 센다.
"""
from __future__ import annotations

import json
import re

_NORMALIZE = {"h": "1", "H": "1", "l": "0", "L": "0", "P": "p", "N": "n"}
_DATA_STATES = set("=23456789")


def parse_wavejson(text: str) -> dict:
    """JSON 또는 따옴표 없는 키를 쓴 WaveDrom 관용 표기를 읽는다."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', text)
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        # 작은따옴표 문자열. 8'hA5 같은 라벨이 있으면 여기서도 실패할 수 있다.
        return json.loads(fixed.replace("'", '"'))


def flatten(wj: dict) -> dict[str, dict]:
    """그룹(배열)과 빈 spacer({})를 걷어내고 이름 → 신호 사전을 만든다."""
    out: dict[str, dict] = {}

    def walk(items):
        for it in items:
            if isinstance(it, list):
                walk(it[1:] if it and isinstance(it[0], str) else it)
            elif isinstance(it, dict) and "wave" in it and "name" in it:
                out[norm_name(it["name"])] = it

    walk(wj.get("signal", []))
    return out


def norm_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name)).lower()


def expand(sig: dict) -> list[tuple[str, str | None]]:
    """신호 하나를 [(상태, 데이터 라벨)] 사이클 목록으로 펼친다."""
    data = sig.get("data", [])
    labels = data.split() if isinstance(data, str) else [str(d) for d in data]
    period = sig.get("period", 1)
    period = int(period) if isinstance(period, (int, float)) and period >= 1 else 1

    cycles: list[tuple[str, str | None]] = []
    li = 0
    prev: tuple[str, str | None] = ("x", None)
    for ch in sig.get("wave", ""):
        if ch in ".|":
            cur = prev
        elif ch in _DATA_STATES:
            cur = ("=", labels[li].strip() if li < len(labels) else None)
            li += 1
        else:
            cur = (_NORMALIZE.get(ch, ch), None)
        cycles.extend([cur] * period)
        prev = cur
    return cycles


def compare(gt: dict, pred: dict) -> dict:
    g, p = flatten(gt), flatten(pred)
    per_signal = {}
    total = hits = 0
    for name, gsig in g.items():
        gc = expand(gsig)
        pc = expand(p[name]) if name in p else []
        length = max(len(gc), len(pc))
        h = sum(1 for a, b in zip(gc, pc) if a == b)
        per_signal[name] = {"cycles": length, "match": h, "present": name in p}
        total += length
        hits += h
    missing = [n for n in g if n not in p]
    extra = [n for n in p if n not in g]
    return {
        "cycle_accuracy": hits / total if total else 1.0,
        "signal_recall": (len(g) - len(missing)) / len(g) if g else 1.0,
        "signal_precision": (len(p) - len(extra)) / len(p) if p else (1.0 if not g else 0.0),
        "missing": missing,
        "extra": extra,
        "exact": hits == total and not extra,
        "per_signal": per_signal,
    }
