# 테스트벤치 작성 안내 (Verifier용)

하니스(클럭, 리셋, 번들 드라이버와 모니터, 프로토콜 체커, 스코어보드)는 툴이 L1에서 만든다. 너는 참조 모델, 속성, 시나리오를 쓴다. RTL과 내부 신호는 볼 수 없고, L1의 포트만 쓴다.

## 하니스

```python
import cocotb
from <module>_harness import make        # tools/pl.py harness로 만든 파일. 실행 때는 툴이 제공한다

class Model:
    streams = {"m_axis"}                  # 비교할 출력 (번들 이름이나 단독 출력 이름). 상태 출력처럼 예측하지 않는 것은 빼고 속성으로 본다
    def on_input(self, stream, txn):      # 입력 번들의 전송마다 불림. txn은 그 번들의 data 신호 값 dict (valid/ready 제외)
        return [("m_axis", {...}, "REQ-ID")]   # 기대 출력 목록. (stream, txn[, 요구사항 ID 또는 ID 목록])

@cocotb.test()
async def basic(dut):
    h = make(dut, Model(), name="basic")  # name은 테스트마다 달라야 한다
    h.add_property("이름", "<도메인>", lambda s, cycle: None if 조건 else "실패 사유", "REQ-ID")   # s: L1 포트 값 dict
    h.cover_protocol("m_axis", "REQ-ID")   # valid/ready 규칙 체커가 이 번들을 검사하면 그 요구사항을 실행한 것으로 셈
    h.set_ready("m_axis", [1, 0, 1])       # 출력 번들의 ready 패턴 (backpressure)
    await h.start()                       # 클럭 시작, 리셋, 표본 시작
    h.send("s_axis", {"s_axis_tdata": 1, "s_axis_tlast": 0}, idle=0)   # 입력 번들에 전송 하나 (data 신호 모두 지정)
    await h.drain()                       # 입력을 다 보내고 기대 출력이 다 올 때까지 기다림
    h.finish()                            # 불일치, 프로토콜 위반, 속성 위반이 있으면 AssertionError
```

- 기대 출력과 실제 출력은 순서대로 비교한다. 출력이 기대보다 먼저 와도 된다 (프레임 끝에서야 기대를 알 수 있는 모델).
- 1비트 단독 출력은 1인 사이클마다, 여러 비트 단독 출력은 값이 바뀔 때마다 트랜잭션 하나가 된다.
- 리셋이나 pause 같은 입력은 `dut.<포트>.value = 1`로 직접 바꿀 수 있다. 클럭 에지는 `from cocotb.triggers import ClockCycles`, `await ClockCycles(dut.<클럭>, n)`.
- 테스트는 SPEC의 요구사항 ID를 기대 출력, 속성, `cover_protocol`로 모두 하나 이상 실행해야 한다.

## 시나리오

- SPEC 8번 섹션의 예시 시나리오는 그대로 directed 테스트로 쓴다.
- 무작위 테스트는 `random.Random(고정 시드)`를 쓴다.
- backpressure(`set_ready`)와 입력 공백(`idle`)이 있는 테스트를 하나 이상 둔다.

## 검사

- `python3 tools/pl.py model <테스트 파일> l1.json`: 모델을 시뮬레이터 없이 무작위 입력으로 돌려 예외가 없는지 본다.
  SPEC이 허용하지 않는 입력(미정의)이 있으면 `Model.legal(self, stream, txn) -> bool`을 두어 그런 입력을 거른다.
- 문법 오류가 없어야 한다 (`python3 -m py_compile <파일>`).
