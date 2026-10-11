# IR 작성 안내 (에이전트용)

모듈 하나는 JSON 파일 하나다. 구조는 JSON이고, 동작은 SystemVerilog 조각(body, cond)이다. 형식은 `tools/schema/ir.schema.json`, 예시는 `examples/`에 있다.

## 계층

| 계층 | 필드 | 누가 정함 |
| --- | --- | --- |
| L0 | `instances`, `connections` | Architect |
| L1 | `module`, `role`, `params`, `domains`, `ports` | Architect가 동결. 바꾸면 안 됨 |
| L2 | `types`, `signals`, 출력 포트의 `kind`/`reset`, `local` 파라미터 | Author |
| L3 | `blocks` | Author |

동결된 L1에서 바꿀 수 있는 것은 세 가지뿐이다.
- 출력 포트에 `kind`(`reg` 또는 `wire`)를 붙이는 것
- `reg` 출력에 `reset`(리셋값)을 붙이는 것
- `"local": true` 파라미터를 더하는 것 (모듈 안의 localparam)

## 이름

- 클럭과 리셋 포트는 `domains`에서 나온다. `ports`에 쓰지 않고, 조각에서도 읽지 않는다.
- 번들 포트의 신호는 각자 이름으로 읽고 쓴다 (예: `s_axis_tvalid`).
- `fsm` 블록의 상태 레지스터는 `<state_name>_q`이다. 다른 블록이 읽을 수 있다.

## signals

- `{"name", "kind": "reg", "type", "domain", "reset"}`: `seq` 블록 하나가 쓰는 레지스터. 리셋이 없으면 `reset`을 뺀다.
- `{"name", "kind": "wire", "type"}`: `comb` 블록 하나, 또는 `cdc_sync`의 `dst`가 구동한다.

## blocks

| kind | 필드 | 규칙 |
| --- | --- | --- |
| `comb` | `reads`, `writes`, `body` | blocking(`=`)만. `writes`의 신호마다 body 첫머리에 조건 없는 기본 대입을 둔다 (래치 금지) |
| `seq` | `domain`, `reads`, `writes`, `body` | non-blocking(`<=`)만. 클럭, sensitivity, 리셋 분기는 쓰지 않는다. Emitter가 `always_ff`와 리셋 분기를 씌우고, 리셋값은 신호 선언의 `reset`에서 가져온다. 한 블록의 `writes`는 모두 리셋이 있거나 모두 없어야 한다 |
| `fsm` | `domain`, `state_type`(enum), `state_name`, `reset_state`, `reads`, `transitions` | 전이는 `{"id", "from", "to", "cond"}`. 같은 상태의 전이는 배열 순서가 우선순위이고, 맞는 전이가 없으면 현재 상태를 유지한다. 출력은 `comb`/`seq` 블록이 `<state_name>_q`를 읽어 만든다 |
| `cdc_sync` | `src`, `src_domain`, `dst`, `dst_domain`, `style` | 다른 도메인의 값을 읽는 유일한 방법이다. `style`은 1비트에 `2ff`, gray 코드로 만든 여러 비트 값에 `gray`를 쓴다. `dst`는 wire이고, 리셋 때 0이다 |
| `memory` | `name`, `word_type`, `depth`, `impl: "inferred"`, `ports` | 배열 `name[addr]`. 쓰기 포트 도메인의 `seq`만 쓰고, 읽기 포트 도메인의 `seq`만 읽는다 |

## 자주 틀리는 것

- `reads`에는 body가 읽는 신호를 모두 적는다. 같은 블록 안에서 먼저 쓰고 다시 읽는 신호도 포함한다. `writes`에는 실제로 쓰는 신호를 정확히 적는다.
- 신호 하나를 쓰는 블록은 하나뿐이다. 출력 포트도 마찬가지다.
- 폭을 맞춘다. 암묵적 확장과 절단은 오류다. `4'(X + 1)`, `8'd1`, `x[7:0]`처럼 명시한다. 파라미터(int, 32비트)와 비교하거나 더할 때도 캐스트한다.
- `seq` 블록 안에 임시 변수를 쓰지 않는다. `comb` 블록의 wire로 뺀다.
- 함수와 `generate`는 쓸 수 없다. `comb` 블록에서 `for` 루프로 풀어 쓴다.
- 비동기 입력(포트 `domain`이 null)은 `cdc_sync`의 `src`로만 읽는다.

## 검사

`python3 tools/pl.py validate <ir.json> --l1 l1.json`이 `"ok": true`가 될 때까지 고친다. 이 도구는 스키마, 참조, 표현식(pyslang), 조각의 읽기·쓰기, 구동, 래치와 루프, 리셋, 도메인, FSM, 동결 L1을 본다. 방출될 SystemVerilog는 `python3 tools/pl.py emit <ir.json>`으로 볼 수 있다.
