# IR 작성 안내 (에이전트용)

모듈 하나는 JSON 파일 하나다. 구조는 JSON이고, 동작은 슬롯(body, cond) 안의 조각이다. 조각 언어는 IR 최상위의 `lang`으로 정한다: `sv`(기본, SystemVerilog) 또는 `py`(Python, 아래 "Python 조각" 절). 과제가 정한 언어를 쓴다. 형식은 `tools/schema/ir.schema.json`, 예시는 `examples/`에 있다.

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

## Python 조각 (`"lang": "py"`)

body와 cond를 Python 문법으로 쓴다. 실행되는 Python이 아니라 사이클 단위 기술이고, 툴이 SV로 옮긴다. 구조(signals, blocks의 종류, 도메인, 리셋값)는 SV 조각과 같다.

- `comb` body의 대입은 blocking, `seq` body의 대입은 non-blocking으로 옮겨진다. `seq` 안에서 대입한 값은 다음 클럭부터 보인다.
- `reads`와 `writes`는 툴이 계산해 채운다. 쓰지 않아도 된다.
- 문장: `x = e`, `x[i] = e`, `x[hi:lo] = e`, `x += e`(+ - & | ^ << >>), `if/elif/else`, `for i in range(N)`, `pass`.
- 식: `+ - * & | ^ ~ << >>`, 비교 하나(`a == b`, 사슬 비교 금지), `and or not`, `a if c else b`, `x[i]`, `x[hi:lo]`(SV처럼 양 끝 포함).
- 메모리(`memory` 블록의 `name`): `mem[addr]`로 한 워드씩 읽고 쓴다. 쓰기는 `seq`에서만 (`if wr_en:` / `    mem[wr_addr] = wr_word`). 워드의 일부는 워드를 신호에 받은 뒤 고른다.
- 도움 함수: `cat(a, b)`(연결), `rep(n, x)`(반복), `u(w, v)`(폭 w 상수), `any_bits(x)`, `all_bits(x)`, `parity(x)`.
- 폭: 툴이 SV 규칙대로 계산하고 확장과 절단을 캐스트로 적는다. 대입 대상보다 넓은 결과는 잘린다. 정수 리터럴은 식의 다른 피연산자 폭을 따른다 (`cnt == 0`, `cnt + 1`). 연결 안의 상수는 `u(4, 9)`처럼 폭을 쓴다.
- 쓸 수 없는 것: 함수 정의, 리스트, 문자열, `while`, 나눗셈, 사슬 비교, 부호 있는 값, struct 타입.
- 예: `if state_q == HEADER and s_valid:` / `    byte_cnt = s_data` / `elif state_q == PAYLOAD and s_valid:` / `    byte_cnt = byte_cnt - 1`
- 설계 모델을 RTL 없이 돌려 볼 수 있다: `python3 tools/pl.py pysim <ir.json> --cycles 20` (또는 `--stim stim.json`).
- 검사 오류의 "Python 조각 N번째 줄"은 그 조각의 N번째 줄이다.

## 검사

`python3 tools/pl.py validate <ir.json> --l1 l1.json`이 `"ok": true`가 될 때까지 고친다. 이 도구는 스키마, 참조, 표현식(pyslang), 조각의 읽기·쓰기, 구동, 래치와 루프, 리셋, 도메인, FSM, 동결 L1을 본다. 방출될 SystemVerilog는 `python3 tools/pl.py emit <ir.json>`으로 볼 수 있다.
