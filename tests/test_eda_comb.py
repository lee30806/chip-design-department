"""PI의 eda comb: 입력→출력 조합 경로를 찾고, 플립플롭을 거치는 경로는 빼는지 본다 (P8 회고)."""
import shutil
import subprocess
import sys

import pytest
from test_pipeline import ROOT

if not shutil.which("yosys"):
    pytest.skip("yosys 없음", allow_module_level=True)

SV = """module t (input logic clk, input logic [3:0] a, input logic b, input logic rdy_in,
          output logic [3:0] y, output logic q, output logic rdy_out);
  always_ff @(posedge clk) q <= b;
  assign y = a + 4'd1;
  assign rdy_out = rdy_in & q;
endmodule
"""


def test_eda_comb_finds_input_to_output_paths(tmp_path):
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "t.sv").write_text(SV)
    p = subprocess.run([sys.executable, str(ROOT / "department" / "bin" / "eda"), "comb", str(tmp_path / "rtl"), "--top", "t",
                        "--out", str(tmp_path / "o")], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    warn = [ln for ln in p.stdout.splitlines() if " WARNING " in ln]
    assert any("a → 출력 y" in w for w in warn) and any("rdy_in → 출력 rdy_out" in w for w in warn)
    assert not any("b → " in w for w in warn)   # 플립플롭을 거치는 b → q는 조합 경로가 아님
    assert "조합 경로 2개" in p.stdout


LOOP = """module l (input logic a, output logic y);
  logic p, q;
  assign p = a ^ q;
  assign q = p & a;
  assign y = q;
endmodule
"""


def test_eda_comb_reports_combinational_loop(tmp_path):
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "l.sv").write_text(LOOP)
    p = subprocess.run([sys.executable, str(ROOT / "department" / "bin" / "eda"), "comb", str(tmp_path / "rtl"), "--top", "l",
                        "--out", str(tmp_path / "o")], capture_output=True, text=True)
    err = [ln for ln in p.stdout.splitlines() if " ERROR " in ln]
    assert p.returncode == 1 and len(err) == 1 and "조합 루프: p" in err[0], p.stdout   # 합성이 q를 p 식에 합쳐 자기 루프가 됨
