"""P11 원본 RTL에서 IR과 SPEC 만들기: 결정론 부분 (R1 추출, R2 요청과 반영, R5 SPEC 표, 게이트). 시뮬레이션 없음."""
import json
from pathlib import Path

import pytest

from pipeline.agents import porter, spec_writer
from pipeline.importer import r2, spec_tables
from pipeline.importer.extract import Extractor
from pipeline.importer.sources import Design, Inputs, SourceError, read_filelist
from pipeline.ir.model import Module, frozen_l1
from pipeline.spec.l1 import block_top_l1
from pipeline.spec.parse import parse
from pipeline.validator.checks import errors, validate

ROOT = Path(__file__).resolve().parents[1]
G = ROOT / "tests" / "golden"
FX = ROOT / "tests" / "fixtures" / "port"


def _golden(blk: str):
    g = json.loads((G / blk / "golden.json").read_text())
    top = "uart" if blk == "uart" else g["runs"][0]["top"]
    params = {k: str(v) for k, v in g.get("upstream_params", {}).get(top, {}).items()}
    files = [G / blk / f for f in g["upstream_rtl"]]
    if blk == "uart":   # 하위 모듈 먼저
        files = sorted(files, key=lambda f: f.name != "uart_tx.v" and f.name != "uart_rx.v")
    return Extractor(Design(Inputs(files, top, params))).run()


@pytest.mark.parametrize("blk", ["uart", "axis_adapter", "axis_cobs_decode"])
def test_r1_l1_matches_hand_ported_golden(blk):
    """원본에서 뽑은 L1이 P1에서 손으로 옮긴 golden IR의 L1과 같다 (주파수와 도메인 관계는 R2에서 채움)."""
    res = _golden(blk)
    assert not res["rejects"]
    for name, m in res["modules"].items():
        gold = json.loads((G / blk / "ir" / f"{name}.ir.json").read_text())
        mine, want = frozen_l1(m.ir), frozen_l1(gold)
        for k in ("domains", "params", "ports"):
            assert mine[k] == want[k], (name, k)
    if blk == "uart":
        top = res["modules"]["uart"].ir
        assert top["role"] == "block_top" and {i["name"] for i in top["instances"]} == {"uart_tx_inst", "uart_rx_inst"}
        assert res["order"][-1] == "uart"


def test_r1_async_fifo_domains_and_reviews():
    res = _golden("axis_async_fifo")
    ir = res["modules"]["axis_async_fifo"].ir
    assert [(d["name"], d["clock"], d["reset"]["port"], d["reset"]["async"]) for d in ir["domains"]] == \
        [("s", "s_clk", "s_rst", False), ("m", "m_clk", "m_rst", False)]
    assert [p.get("bundle") for p in ir["ports"][:2]] == ["s_axis", "m_axis"]
    kinds = {r["kind"] for r in res["reviews"]}
    assert {"mixed_reset", "unused_param", "reset_at_end"} <= kinds
    assert "PAUSE_ENABLE" not in [p["name"] for p in ir["params"]]


def _mixed(defines=None):
    files, incs, defs = read_filelist(FX / "mixed" / "files.f")
    return Extractor(Design(Inputs(files, "mix_top", {}, incs, {**defs, **(defines or {})}))).run()


def test_r1_mixed_verilog_sv_sources():
    res = _mixed()
    assert not res["rejects"], res["rejects"]
    acc, top = res["modules"]["acc"], res["modules"]["mix_top"]
    # SV 예약어 포트 이름은 바꾸고, 부모 연결도 바꾼 이름을 쓴다
    assert acc.renames == {"logic": "logic_"}
    assert [p["name"] for p in acc.ir["ports"]] == ["logic_", "en", "sum"]
    assert acc.ir["ports"][0]["type"] == "logic [DW-1:0]"
    assert any(c["to"] == "u_acc_0.logic_" for c in top.ir["connections"])
    # 매크로와 package 상수는 localparam, 헤더의 parameter는 모듈 파라미터
    p = {x["name"]: x for x in acc.ir["params"]}
    assert p["DW"] == {"name": "DW", "type": "int", "default": "8", "local": True} and p["INIT"]["default"] == "0"
    assert {x["name"]: x["default"] for x in top.ir["params"]}["K"] == "3"
    # generate for는 인스턴스로 펼치고 genvar 바인딩은 값으로, defparam은 인스턴스 파라미터로
    inst = {i["name"]: i.get("params") for i in top.ir["instances"]}
    assert inst == {"u_acc_0": {"INIT": "0"}, "u_acc_1": {"INIT": "6"}, "u_extra": {"INIT": "5"}}
    # 배열 원소 연결은 Porter가 마무리
    assert {(x["instance"], x["expr"]) for x in top.pending} == {("u_acc_0", "s[i]"), ("u_acc_1", "s[i]")}
    kinds = [r["kind"] for r in res["reviews"]]
    assert "unused_param" in kinds and "rename" in kinds   # MODE는 generate 조건에서만 쓰여 지움
    assert "MODE" not in [x["name"] for x in top.ir["params"]]
    lib = {n: Module(m.ir) for n, m in res["modules"].items()}
    for n in lib:
        assert not errors(validate(lib[n], lib, upto=3)), n


def test_r1_ifdef_picks_branch_and_macro_order(tmp_path):
    a, b = _mixed(), _mixed({"USE_SUB": "1"})
    assert not a["rejects"] and not b["rejects"]
    files, incs, defs = read_filelist(FX / "mixed" / "files.f")
    wrong = [files[2], files[0], files[1], files[3]]   # acc.v가 매크로 파일보다 앞
    with pytest.raises(SourceError) as e:
        Design(Inputs(wrong, "mix_top", {}, incs, defs))
    assert any(i["kind"] == "macro_order" and "defs.v" in i["message"] for i in e.value.items)


def test_r1_inout_split_and_tristate():
    res = Extractor(Design(Inputs([FX / "inout" / "pp.v"], "pp_top"))).run()
    assert not res["rejects"]
    core, top = res["modules"]["pp_core"], res["modules"]["pp_top"]
    assert [p["name"] for p in core.ir["ports"]] == ["pad_o", "pad_oe", "pad_i", "q"]
    assert core.tri_split["pad"]["style"] == "push_pull"
    assert top.ir["role"] == "block_top"
    assert top.ir["ports"][0] == {"name": "pad", "dir": "inout", "type": "logic [3:0]", "domain": "sys"}
    assert top.ir["blocks"] == [{"id": "t_pad", "kind": "tristate", "pad": "pad", "oe": "pad_oe", "i": "pad_i",
                                 "domain": "sys", "style": "push_pull", "o": "pad_o"}]
    od = Extractor(Design(Inputs([FX / "inout" / "od.v"], "od_top"))).run()
    t = od["modules"]["od_top"].ir
    assert t["role"] == "block_top" and t["blocks"][0]["style"] == "open_drain" and "o" not in t["blocks"][0]
    assert t["blocks"][0]["oe"] == "sda_oe" and t["blocks"][0]["i"] == "sda_in"


def test_r1_rejects(tmp_path):
    f = tmp_path / "bad.v"
    f.write_text("module sub(input a, inout p); assign p = a ? 1'b1 : 1'bz; endmodule\n"
                 "module bad(input clk, input en, output reg q, inout p);\n"
                 "  always @(posedge clk) if (en) q <= ~q;\n"
                 "  wire w; sub u1(.a(en), .p(w)); sub u2(.a(q), .p(w)); assign p = w;\nendmodule\n")
    res = Extractor(Design(Inputs([f], "bad"))).run()
    kinds = {r["kind"] for r in res["rejects"]}
    assert "tristate_bus" in kinds
    assert {"no_reset", "comb_module"} <= {r["kind"] for r in res["reviews"]}   # 리셋 없는 도메인, 조합 모듈은 옮김
    g = tmp_path / "neg.v"
    g.write_text("module neg(input clk, input rst, output reg q); always @(negedge clk) if (rst) q <= 0; else q <= ~q; endmodule\n")
    res = Extractor(Design(Inputs([g], "neg"))).run()   # 하강 에지 클럭은 하강 에지 도메인으로 옮김
    assert not res["rejects"] and res["modules"]["neg"].ir["domains"][0]["edge"] == "neg"


def test_tristate_ir_validator_and_emitter():
    from pipeline.emitter.sv import emit
    lib = {n: Module(json.loads((FX / "inout" / "ported" / f"{n}.ir.json").read_text())) for n in ("pp_core", "pp_top", "od_ctrl", "od_top")}
    for n, m in lib.items():
        assert not errors(validate(m, lib)), (n, validate(m, lib))
    text = emit(lib["pp_top"], lib).text
    assert "inout  wire [3:0] pad" in text and "assign pad = pad_oe ? pad_o : 'z;" in text and "assign pad_i = pad;" in text
    assert "assign sda = sda_oe ? '0 : 'z;" in emit(lib["od_top"], lib).text
    # inout은 하위 모듈에 둘 수 없고, tristate는 하나만
    bad = json.loads((FX / "inout" / "ported" / "pp_core.ir.json").read_text())
    bad["ports"].append({"name": "x", "dir": "inout", "type": "logic", "domain": "sys"})
    assert any("inout 포트는 top과 block_top에만" in str(i) for i in validate(Module(bad), {}))


def test_r2_request_answers_and_propagation():
    res = _golden("uart")
    irs = {n: m.ir for n, m in res["modules"].items()}
    r1 = {"top": res["top"], "order": res["order"], "reviews": res["reviews"]}
    req = r2.make_request(r1, irs)
    ids = [i["id"] for i in req["items"]]
    assert ids[0] == "freq.sys" and "proto.uart.s_axis" in ids
    assert r2.set_answers(req, {"freq.sys": "abc"}) and r2.set_answers(req, {"nope": "1"})
    ans = {i["id"]: "valid_ready" for i in req["items"] if i["kind"] == "protocol"}
    ans["freq.sys"] = "125"
    ans["proto.uart_tx.s_axis"] = "none"
    assert r2.set_answers(req, ans) == []
    out, errs = r2.apply(req, r1, irs)
    assert errs == []
    assert out["uart"]["domains"][0]["freq_mhz"] == 125 and out["uart_tx"]["domains"][0]["freq_mhz"] == 125
    assert "bundle" not in json.dumps(out["uart_tx"]["ports"]) and any(c["from"] == "uart_rx_inst.m_axis" for c in out["uart"]["connections"])


def test_r2_relations_and_stop():
    res = _golden("axis_async_fifo")
    irs = {n: m.ir for n, m in res["modules"].items()}
    r1 = {"top": res["top"], "order": res["order"], "reviews": res["reviews"]}
    req = r2.make_request(r1, irs)
    assert r2.set_answers(req, {"rel.s.m": "x/2"})
    ans = {i["id"]: "ok" for i in req["items"] if i["kind"] == "review"}
    ans.update({i["id"]: "valid_ready" for i in req["items"] if i["kind"] == "protocol"})
    ans.update({"freq.s": "100", "rel.s.m": "s/2"})
    assert r2.set_answers(req, ans) == []
    out, errs = r2.apply(req, r1, irs)
    assert errs == [] and out["axis_async_fifo"]["domains"][1]["sync_to"] == {"domain": "s", "div": 2}
    assert out["axis_async_fifo"]["domains"][1]["freq_mhz"] == 50
    r2.set_answers(req, {"review.1": "stop"})
    _, errs = r2.apply(req, r1, irs)
    assert errs and errs[0].startswith("사용자가 멈춤")


@pytest.mark.parametrize("path", ["tests/golden/axis_async_fifo/ir/axis_async_fifo.ir.json", "tests/golden/uart/ir/uart.ir.json",
                                  "tests/fixtures/multiclock/mc_top.ir.json", "tests/fixtures/port/inout/ported/od_top.ir.json",
                                  "tests/fixtures/negedge/ported/ne_top.ir.json"])
def test_spec_tables_roundtrip(path):
    ir = json.loads((ROOT / path).read_text())
    l1, _ = block_top_l1(parse(f"# {ir['module']} SPEC\n\n" + spec_tables.tables_md(ir)))
    assert spec_tables.roundtrip_diff(ir, l1) == []


def test_spec_writer_gate(tmp_path):
    ir = json.loads((G / "axis_cobs_decode" / "ir" / "axis_cobs_decode.ir.json").read_text())
    base = (G / "axis_cobs_decode" / "block_spec.md").read_text()
    head, rest = base.split("\n## 2.", 1)
    good = head + "\n" + spec_tables.tables_md(ir) + rest[rest.index("\n## 5."):]
    (tmp_path / "good.md").write_text(good)
    assert spec_writer.gate(tmp_path / "good.md", ir) == []
    (tmp_path / "bad.md").write_text(good.replace("| sys | clk |", "| sys | clk2 |", 1))
    assert any(e.startswith("[2~4절]") for e in spec_writer.gate(tmp_path / "bad.md", ir))


def test_porter_gate_keeps_draft_structure(tmp_path):
    draft = json.loads((FX / "mixed" / "ported" / "default" / "mix_top.ir.json").read_text())
    acc = json.loads((FX / "mixed" / "ported" / "default" / "acc.ir.json").read_text())
    (tmp_path / "out").mkdir()
    out = tmp_path / "out" / "mix_top.ir.json"
    out.write_text(json.dumps(draft))
    check = porter.check(draft, {"acc": acc})
    assert check(tmp_path) == []
    moved = json.loads(json.dumps(draft))
    moved["instances"][0]["params"]["INIT"] = "9"
    moved["connections"] = moved["connections"][1:]
    out.write_text(json.dumps(moved))
    errs = check(tmp_path)
    assert any("instances" in e for e in errs) and any("연결이 빠지거나" in e for e in errs)


def test_r1_comb_module_and_no_reset_domain():
    res = Extractor(Design(Inputs([FX / "comb" / "cr.v"], "cr_top"))).run()
    assert not res["rejects"]
    dec, pipe, top = (res["modules"][n].ir for n in ("dec", "pipe", "cr_top"))
    assert dec["domains"] == [] and {p["domain"] for p in dec["ports"]} == {None}
    assert pipe["domains"] == [{"name": "sys", "clock": "clk", "edge": "pos"}]
    assert {i["name"]: i["domain_map"] for i in top["instances"]} == {"u_dec": {}, "u_pipe": {"sys": "sys"}}
    assert {p["name"]: p["domain"] for p in top["ports"]} == {"sel": "sys", "en": "sys", "q": "sys", "cnt": "sys"}
    lib = {n: Module(json.loads((FX / "comb" / "ported" / f"{n}.ir.json").read_text())) for n in ("dec", "pipe", "cr_top")}
    for n, m in lib.items():
        assert not errors(validate(m, lib)), (n, validate(m, lib))


def test_no_reset_domain_rules():
    pipe = json.loads((FX / "comb" / "ported" / "pipe.ir.json").read_text())
    bad = json.loads(json.dumps(pipe))
    bad["signals"][0]["reset"] = "'0"
    bad["blocks"][0]["writes"] = ["s"]
    bad["blocks"][0]["body"] = "s <= d;"
    bad["blocks"].append({"id": "k_q", "kind": "seq", "domain": "sys", "reads": ["s"], "writes": ["q"], "body": "q <= s;"})
    assert any("리셋 없는 도메인 sys의 레지스터에 리셋값" in str(i) for i in validate(Module(bad), {}))
    # 리셋 있는 자식 도메인을 리셋 없는 부모 도메인에 연결할 수 없음
    top = json.loads((FX / "comb" / "ported" / "cr_top.ir.json").read_text())
    top["domains"] = [{"name": "sys", "clock": "clk", "edge": "pos"}]
    top["ports"][3].pop("reset")
    top["blocks"] = []
    top["ports"] = top["ports"][:3]
    core = json.loads((FX / "rsync" / "ported" / "rs_core.ir.json").read_text())
    top["instances"][1] = {"name": "u_pipe", "module": "rs_core", "domain_map": {"sys": "sys"}}
    top["connections"] = [c for c in top["connections"] if "u_pipe" not in c["from"] + c["to"]]
    lib = {"rs_core": Module(core), "dec": Module(json.loads((FX / "comb" / "ported" / "dec.ir.json").read_text()))}
    assert any("리셋 없는 도메인 sys에 연결함" in str(i) for i in validate(Module(top), lib))
    # SPEC 2절: 리셋 포트 "없음" 왕복
    l1, _ = block_top_l1(parse("# pipe SPEC\n\n" + spec_tables.tables_md(pipe)))
    assert "reset" not in l1["domains"][0] and spec_tables.roundtrip_diff(pipe, l1) == []


def test_r1_reset_synchronizer_in_top():
    res = Extractor(Design(Inputs([FX / "rsync" / "rs.v"], "rs_top"))).run()
    assert not res["rejects"]
    top = res["modules"]["rs_top"].ir
    assert top["role"] == "block_top"
    assert top["domains"][0]["reset"] == {"port": "arst_n", "active": "low", "async": True, "synchronize": True}


def test_r1_reset_synchronizer_not_in_top(tmp_path):
    f = tmp_path / "x.v"
    f.write_text((FX / "rsync" / "rs.v").read_text().replace("module rs_top", "module rs_mid") +
                 "module x_top(input clk, input arst_n, input [7:0] d, output [7:0] q);\n"
                 "  rs_mid u_mid(.clk(clk), .arst_n(arst_n), .d(d), .q(q));\nendmodule\n")
    res = Extractor(Design(Inputs([f], "x_top"))).run()
    assert "reset_sync" in {r["kind"] for r in res["rejects"]}


def test_simcopy_moves_arrayed_defparam(tmp_path):
    from pipeline.importer import simcopy
    files, incs, defs = read_filelist(FX / "mixed" / "files.f")
    d = Design(Inputs(files, "mix_top", {}, incs, defs))
    out = simcopy.make(d, tmp_path)
    text = Path(out[str((FX / "mixed" / "mix_top.sv").resolve())]).read_text()
    assert "defparam g_acc[1]" not in text and "defparam u_extra.INIT = 5;" in text
    assert "acc #(.INIT(((i == 0) ? 0 : 6)))" in text


def test_spec_writer_revise_gets_failed_test_stimuli(tmp_path):
    """R6 고치기: 원본에서 실패한 Verifier 테스트의 자극을 `r6_stim/`으로 받고, refsim으로 다시 넣어 보라는 지시를 받는다."""
    prev = tmp_path / "spec_v0.md"
    prev.write_text("# m SPEC\n")
    st = tmp_path / "v0_t.json"
    st.write_text("{}")
    t = spec_writer.make_task("spec_writer/v1", "m", "", {}, {}, {}, prev_spec=prev, r6={}, stims={"v0_t.json": st})
    assert t.inputs["r6_stim/v0_t.json"] == st and "r6_stim/" in t.text
    t = spec_writer.make_task("spec_writer/v1", "m", "", {}, {}, {}, prev_spec=prev, r6={})
    assert not any(k.startswith("r6_stim/") for k in t.inputs) and "r6_stim/" not in t.text
