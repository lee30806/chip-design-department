"""Block Top과 Top의 SDC 골격. L1에서 유도할 수 있는 제약만 방출한다.

| 방출 항목         | 출처                                               |
| 클럭 정의         | `domains`의 클럭 포트와 `freq_mhz`                 |
| 비동기 클럭 그룹  | `domains`의 `async_to` (SPEC 2번 섹션)             |
| CDC 경로 제약     | 계층 전체의 `cdc_sync` 노드                        |

입출력 지연과 예외 경로는 방출하지 않는다. 사람이 쓴 제약과 SDC Lint에서 대조한다.
CDC 경로:
- 출발과 도착 도메인이 `async_to`로 비동기 그룹에 묶여 있으면 클럭 그룹이 경로를 이미 덮으므로 주석만 남긴다
  (클럭 그룹이 set_max_delay보다 우선한다).
- 그렇지 않으면 동기화 셀 데이터 핀까지 목적지 클럭 한 주기로 `set_max_delay`를 둔다.
- 비동기 입력 포트에서 오는 경로는 false path로 둔다. 하위 모듈의 포트는 시작점이 될 수 없으므로 `-through`로 쓴다.
"""
from __future__ import annotations

from pipeline.emitter.sv import SYNC_CELL, EmitError
from pipeline.ir.model import Module


def _period(dom: dict) -> float | None:
    f = dom.get("freq_mhz")
    return round(1000.0 / f, 3) if f else None


def _walk(m: Module, library: dict[str, Module], path: str, dmap: dict[str, str]):
    """(인스턴스 경로, 모듈, 이 모듈의 도메인 → 최상위 도메인)을 깊이 우선으로 돌려준다."""
    yield path, m, dmap
    for inst in m.instances:
        child = library.get(inst["module"])
        if child is None:
            raise EmitError(f'instances/{inst["name"]}: 라이브러리에 없는 모듈 {inst["module"]}')
        cmap = {cd: dmap[pd] for cd, pd in inst.get("domain_map", {}).items() if pd in dmap}
        yield from _walk(child, library, f'{path}{inst["name"]}/', cmap)


def emit_sdc(m: Module, library: dict[str, Module] | None = None) -> str:
    if m.role not in ("top", "block_top"):
        raise EmitError(f"SDC 골격은 top과 block_top에만 방출함 ({m.name}은 {m.role})")
    library = {**(library or {}), m.name: m}
    out = [f"# SDC skeleton for '{m.name}', generated from IR L1. Do not edit; IO delays and exceptions go in the",
           "# hand-written constraints.", ""]

    out.append("# @ir domains")
    for d in m.domains.values():
        per = _period(d)
        if per is None:
            out.append(f'# domains/{d["name"]}: freq_mhz 없음. 클럭 정의를 방출하지 않음')
            continue
        out.append(f'create_clock -name {d["name"]} -period {per} [get_ports {d["clock"]}]')

    pairs = sorted({tuple(sorted((d["name"], o))) for d in m.domains.values() for o in d.get("async_to", [])
                    if o in m.domains})
    if pairs:
        out += ["", "# @ir domains/async_to"]
        for a, b in pairs:
            out.append(f"set_clock_groups -asynchronous -group [get_clocks {a}] -group [get_clocks {b}]")

    cdc = []
    for path, mod, dmap in _walk(m, library, "", {d: d for d in m.domains}):
        for b in mod.blocks:
            if b["kind"] == "cdc_sync":
                cdc.append((path, mod, dmap, b))
    if cdc:
        out += ["", "# CDC paths into standard sync cells"]
    for path, mod, dmap, b in cdc:
        pin = f'{path}u_{b["id"]}/{SYNC_CELL["d"]}'
        dst = dmap.get(b["dst_domain"])
        out.append(f'# @ir {mod.name}/blocks/{b["id"]}')
        if b["src_domain"] is None:
            if not path:
                out.append(f"set_false_path -from [get_ports {b['src']}] -to [get_pins {pin}]")
            else:
                out.append(f"set_false_path -through [get_pins {path}{b['src']}] -to [get_pins {pin}]")
            continue
        src = dmap.get(b["src_domain"], b["src_domain"])
        if tuple(sorted((src, dst))) in pairs:
            out.append(f"# {src} -> {dst}: 비동기 클럭 그룹이 덮음 ({pin})")
            continue
        per = _period(m.domains[dst]) if dst in m.domains else None
        if per is None:
            out.append(f"# 목적지 도메인의 주기를 알 수 없음: {pin}")
            continue
        out.append(f"set_max_delay {per} -from [get_clocks {src}] -to [get_pins {pin}]")
    return "\n".join(out) + "\n"
