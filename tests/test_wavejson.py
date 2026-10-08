from x2_wavejson.wavejson import compare, expand, parse_wavejson


def test_expand_dots_data_and_period():
    assert expand({"name": "d", "wave": "x=.=", "data": ["A", "B"]}) == [
        ("x", None), ("=", "A"), ("=", "A"), ("=", "B")]
    assert expand({"name": "d", "wave": "x=.=", "data": "A B"})[3] == ("=", "B")
    assert expand({"name": "c", "wave": "P..", "period": 2}) == [("p", None)] * 6
    assert expand({"name": "v", "wave": "hl3"})[:2] == [("1", None), ("0", None)]


def test_parse_relaxed_wavedrom_syntax():
    wj = parse_wavejson("{signal: [{name: 'clk', wave: 'p...'},]}")
    assert wj["signal"][0]["wave"] == "p..."
    wj = parse_wavejson('{signal: [{name: "d", wave: "=", data: ["8\'hA5"]}]}')
    assert wj["signal"][0]["data"] == ["8'hA5"]


GT = {"signal": [
    {"name": "clk", "wave": "p..."},
    ["bus", {"name": "Data", "wave": "x=.x", "data": ["D0"]}],
    {},
    {"name": "valid", "wave": "01.0"},
]}


def test_exact_match_ignores_name_case_groups_and_color():
    pred = {"signal": [
        {"name": "CLK", "wave": "p..."},
        {"name": "data", "wave": "x4.x", "data": "D0"},
        {"name": "valid", "wave": "0h.l"},
    ]}
    r = compare(GT, pred)
    assert r["exact"] and r["cycle_accuracy"] == 1.0 and r["signal_recall"] == 1.0


def test_missing_and_wrong_cycles_are_counted():
    pred = {"signal": [
        {"name": "clk", "wave": "p..."},
        {"name": "valid", "wave": "011."},
        {"name": "ready", "wave": "1..."},
    ]}
    r = compare(GT, pred)
    # clk 4/4, data 0/4 (없음), valid 3/4
    assert r["cycle_accuracy"] == 7 / 12
    assert r["missing"] == ["data"] and r["extra"] == ["ready"]
    assert r["signal_recall"] == 2 / 3 and r["signal_precision"] == 2 / 3
    assert not r["exact"]


def test_length_mismatch_counts_as_error():
    r = compare({"signal": [{"name": "a", "wave": "0101"}]}, {"signal": [{"name": "a", "wave": "01"}]})
    assert r["cycle_accuracy"] == 0.5


def test_run_x2_end_to_end(tmp_path):
    import json
    import sys
    from pathlib import Path

    from x2_wavejson import run_x2

    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "w1.png").write_bytes(b"\x89PNG fake")
    (samples / "w1.json").write_text(json.dumps(GT))
    pred = {"signal": [{"name": "clk", "wave": "p..."}, {"name": "data", "wave": "x=.x", "data": ["D0"]},
                       {"name": "valid", "wave": "01.0"}]}
    fake = str(Path(__file__).resolve().parent / "fake_agent.py")
    cfg = {"name": "fake", "family": "F", "runtime": "fake", "vision": True,
           "command": [sys.executable, fake, "{prompt}"], "env": {"FAKE_MODE": "wave", "FAKE_WAVE": json.dumps(pred)}}
    blind = dict(cfg, name="blind", vision=False)
    (tmp_path / "agents.json").write_text(json.dumps({"agents": [cfg, blind]}))
    assert run_x2.main(["--agents", str(tmp_path / "agents.json"), "--samples", str(samples),
                        "--repeat", "2", "--out", str(tmp_path)]) == 0
    work = next(tmp_path.glob("x2-*/work/fake/w1-0"))
    assert (work / "w1.png").exists() and "w1.png" in (work / "TASK.md").read_text()
    summary = next(tmp_path.glob("x2-*/summary.md")).read_text(encoding="utf-8")
    assert "| fake | fake | F | 2 | 100% | 100% | 100.0% | 100.0% | 100.0% | 100.0% | 2/2 |" in summary
    assert "blind" not in summary
