"""IR 모듈을 읽고 이름을 해석한다.

IR 파일 하나가 모듈 하나다. 구조(L0~L2)는 JSON이고 동작(L3)은 SV 조각이다.
이 모듈은 검사와 방출이 공통으로 쓰는 이름 해석만 맡는다.
- 번들 포트를 개별 포트로 펼친다.
- 클럭과 리셋 포트는 `domains`에서 유도한다. IR의 `ports`에는 적지 않는다.
- `fsm` 블록은 `<state_name>_q` 레지스터를 노출한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Port:
    name: str
    dir: str                 # input | output
    type: str
    domain: str | None       # None이면 비동기 입력
    kind: str | None = None  # 출력만: reg | wire
    reset: str | None = None
    bundle: str | None = None
    derived: bool = False    # domains에서 유도한 클럭/리셋 포트


@dataclass(frozen=True)
class Signal:
    name: str
    kind: str                # reg | wire
    type: str
    domain: str | None = None
    reset: str | None = None
    origin: str = "signal"   # signal | port | fsm


class Module:
    def __init__(self, raw: dict, path: Path | None = None):
        self.raw, self.path = raw, path
        # 형식이 틀린 IR도 V1이 보고할 수 있도록, 해석에 실패한 부분은 비워 둔다.
        self.name: str = raw.get("module", "") if isinstance(raw, dict) else ""
        self.role: str = raw.get("role", "") if isinstance(raw, dict) else ""
        try:
            self._init(raw)
        except (KeyError, TypeError, AttributeError):
            self.params, self.domains, self.types, self.blocks = [], {}, [], []
            self.instances, self.connections, self.bundles, self.ports, self.signals = [], [], {}, [], []

    def _init(self, raw: dict) -> None:
        self.params: list[dict] = raw.get("params", [])
        self.domains: dict[str, dict] = {d["name"]: d for d in raw.get("domains", [])}
        self.types: list[dict] = raw.get("types", [])
        self.blocks: list[dict] = raw.get("blocks", [])
        self.instances: list[dict] = raw.get("instances", [])
        self.connections: list[dict] = raw.get("connections", [])
        self.bundles: dict[str, dict] = {}
        self.ports: list[Port] = self._ports()
        self.signals: list[Signal] = [Signal(s["name"], s["kind"], s["type"], s.get("domain"), s.get("reset"))
                                      for s in raw.get("signals", [])]

    # -- 포트 --
    def _ports(self) -> list[Port]:
        out: list[Port] = []
        seen: set[str] = set()
        for d in self.raw.get("domains", []):
            for name in (d["clock"], d["reset"]["port"]):
                if name not in seen:
                    out.append(Port(name, "input", "logic", d["name"], derived=True))
                    seen.add(name)
        for p in self.raw.get("ports", []):
            if "bundle" in p:
                self.bundles[p["bundle"]] = p
                for s in p["signals"]:
                    out.append(Port(s["name"], s["dir"], s["type"], p["domain"], s.get("kind"), s.get("reset"), p["bundle"]))
            else:
                out.append(Port(p["name"], p["dir"], p["type"], p.get("domain"), p.get("kind"), p.get("reset")))
        return out

    def port(self, name: str) -> Port | None:
        return next((p for p in self.ports if p.name == name), None)

    # -- 이름 공간 --
    def state_regs(self) -> list[Signal]:
        return [Signal(f'{b["state_name"]}_q', "reg", b["state_type"], b["domain"], b["reset_state"], origin="fsm")
                for b in self.blocks if b["kind"] == "fsm"]

    def storage(self) -> dict[str, Signal]:
        """쓸 수 있는 모든 이름: 출력 포트, 내부 신호, FSM 상태 레지스터."""
        out = {p.name: Signal(p.name, p.kind or "wire", p.type, p.domain, p.reset, origin="port")
               for p in self.ports if p.dir == "output"}
        out.update({s.name: s for s in self.signals})
        out.update({s.name: s for s in self.state_regs()})
        return out

    def readable(self) -> set[str]:
        """조각에서 읽을 수 있는 신호 이름 (상수 제외)."""
        return {p.name for p in self.ports if not p.derived} | set(self.storage())

    def constants(self) -> set[str]:
        """파라미터와 enum 멤버. 조각의 reads 목록에 적지 않아도 된다."""
        out = {p["name"] for p in self.params}
        for t in self.types:
            if t["kind"] == "enum":
                out |= set(t["members"])
        return out

    def type_names(self) -> set[str]:
        return {t["name"] for t in self.types}


def load(path: str | Path) -> Module:
    path = Path(path)
    return Module(json.loads(path.read_text(encoding="utf-8")), path)


def load_library(paths) -> dict[str, Module]:
    mods = [load(p) for p in paths]
    return {m.name: m for m in mods}
