"""번역기 검사: 설계 모델(pysim) 대 방출한 RTL. 손으로 쓴 SV 모듈과도 대조하고, 틀린 RTL을 잡는지 본다."""
import json
import shutil

import pytest

pytest.importorskip("cocotb_tools.runner")
if not shutil.which("verilator"):
    pytest.skip("verilator 없음", allow_module_level=True)

from pipeline.emitter.sv import emit  # noqa: E402
from pipeline.ir.model import Module, load  # noqa: E402
from pipeline.verify.pyequiv import check  # noqa: E402
from test_pipeline import ROOT  # noqa: E402

PY = ROOT / "tests" / "fixtures" / "py"


def _emit(tmp_path, m, text=None, lib=None):
    f = tmp_path / f"{m.name}.sv"
    f.write_text(text if text is not None else emit(m, lib).text)
    return f


@pytest.mark.parametrize("name", ["pkt_parser", "py_ops"])
def test_translation_matches_model(tmp_path, name):
    m = load(PY / f"{name}.ir.json")
    res = check(name, {name: m}, [_emit(tmp_path, m)], tmp_path / "b", cycles=1500)
    assert res["ok"] and res["mismatch"] is None


def test_model_matches_hand_written_sv_module(tmp_path):
    """같은 동작을 SV 조각으로 쓴 모듈(기존 픽스처)의 RTL과 Python 조각 모듈의 설계 모델이 같다."""
    py = load(PY / "pkt_parser.ir.json")
    sv = Module(json.loads((ROOT / "tests" / "fixtures" / "pkt_parser.ir.json").read_text()))
    res = check("pkt_parser", {"pkt_parser": py}, [_emit(tmp_path, sv)], tmp_path / "b", cycles=1500)
    assert res["ok"]


def test_wrong_rtl_is_caught(tmp_path):
    m = load(PY / "py_ops.ir.json")
    text = emit(m).text
    assert "(acc - {b, a})" in text
    res = check("py_ops", {"py_ops": m}, [_emit(tmp_path, m, text.replace("(acc - {b, a})", "(acc + {b, a})"))],
                tmp_path / "b", cycles=500)
    assert not res["ok"] and res["mismatch"]["output"] == "acc"


def test_parameterized_module_with_overridden_params(tmp_path):
    """폭이 파라미터 식인 캐스트: 기본값이 아닌 파라미터로 인스턴스해도 설계 모델과 RTL이 같고, 손으로 쓴 SV 판과도 같다."""
    core = load(PY / "axis_adapter.ir.json")
    over = {"S_DATA_WIDTH": "64", "S_KEEP_WIDTH": "8", "M_DATA_WIDTH": "16", "M_KEEP_ENABLE": "1", "M_KEEP_WIDTH": "2",
            "ID_WIDTH": "4", "DEST_WIDTH": "5", "USER_WIDTH": "3"}

    def sub(t):
        for k, v in over.items():
            t = t.replace(k, v)
        return t
    ports = [{**{k: v for k, v in p.items() if k != "signals"},
              "signals": [{k: (sub(v) if k == "type" else v) for k, v in s.items() if k not in ("kind", "reset")}
                          for s in p["signals"]]} for p in core.source_raw["ports"]]
    wrap = Module({"module": "wrap", "role": "block_top", "params": [], "domains": core.raw["domains"], "ports": ports,
                   "instances": [{"name": "u", "module": "axis_adapter", "params": over, "domain_map": {"sys": "sys"}}],
                   "connections": [{"id": "c_s", "from": "self.s_axis", "to": "u.s_axis"},
                                   {"id": "c_m", "from": "u.m_axis", "to": "self.m_axis"}]})
    lib = {"wrap": wrap, "axis_adapter": core}
    files = [_emit(tmp_path, wrap, lib=lib), _emit(tmp_path, core)]
    assert "(~(S_KEEP_WIDTH)'(0))" in files[1].read_text()
    assert check("wrap", lib, files, tmp_path / "b", cycles=1500)["ok"]
    golden = Module(json.loads((ROOT / "tests" / "golden" / "axis_adapter" / "ir" / "axis_adapter.ir.json").read_text()))
    (tmp_path / "g").mkdir()
    files[1] = _emit(tmp_path / "g", golden)   # SV 조각으로 쓴 원본
    assert check("wrap", lib, files, tmp_path / "b2", cycles=1500)["ok"]
