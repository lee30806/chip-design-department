# 사내 자료 대체와 임시 표준 (2026-10-11)

P0에서 받기로 한 사내 자료를 아직 받지 못했습니다. 그래서 공개 자료와 현재 가정을 **임시 표준**으로 정해 P0와 P1을 진행했습니다. 사내 자료를 받으면 이 문서의 항목을 하나씩 바꾸고, 영향을 받는 시험을 다시 돌립니다.

## 자료별 대체

| 받아야 할 자료 | 대체 | 다시 판정할 것 |
| --- | --- | --- |
| 이식 시험 대상 블록 3개와 테스트벤치 | 공개 블록 4개: verilog-uart `uart`(계층), verilog-axis `axis_cobs_decode`(FSM), `axis_adapter`(datapath), `axis_async_fifo`(다중 클럭). 원저자의 cocotb 테스트벤치 사용. [tests/golden/](../../tests/golden/README.md) | P1 판정 전체 |
| 위 블록의 Word/PDF SPEC, 엑셀 레지스터 맵 | 공개 예시 SPEC: I3C Basic v1.2 controller ([examples/i3c_basic_controller/](../../examples/i3c_basic_controller/README.md)) | P3 |
| Word SPEC 양식 원본 | 10개 섹션 템플릿(설계 문서)과 위 예시 SPEC | P3 템플릿 대응 |
| 블록 다이어그램 원본 (Visio/SVG) | 없음 | P3 |
| 타이밍 다이어그램 10\~20장과 정답 WaveJSON | 정답에서 그린 합성 그림 12장 (`x2_wavejson/make_synthetic.py`) | X2. 실제 SPEC 그림은 합성 그림보다 어렵다고 봐야 함 |
| VC SpyGlass 사내 템플릿 | **이번 구현에서 제외** (사용자 결정). E1 Verilator lint로 대신함 | E3, P1 판정 6 |
| 표준 동기화 셀 | 아래 "동기화 셀" | Emitter `cdc_sync`, SDC 골격 |
| 메모리 매크로 래퍼 규약 | 추론형 배열만 (`impl: inferred`) | Emitter `memory` (`impl: macro`) |
| 표준 프로토콜 태그 목록 | `valid_ready` 하나 | 스키마, 하니스 생성기 |
| 사내 코딩 가이드 | [docs/RTL 코딩 규칙.md](../../docs/RTL%20코딩%20규칙.md) (Validator 규칙에서 정리) | Emitter, V4 |
| 로컬 모델 목록과 서빙 엔드포인트 | 이 Mac의 ollama 모델 (아래) | X1, X2, X3 |
| 폐쇄망 반입 coding agent 패키지 | 로컬 설치판으로 확인 | X3, X5 |

## 동기화 셀

```systemverilog
module sync_2ff #(parameter int WIDTH = 1) (
  input  logic             clk,      // 도착 도메인 클럭
  input  logic             rst_n,    // active-low 비동기 리셋, 0으로
  input  logic [WIDTH-1:0] d,
  output logic [WIDTH-1:0] q
);
```

- 2단 플립플롭입니다. 모델은 `pipeline/emitter/stubs/sync_2ff.sv`에 있습니다.
- `cdc_sync`의 `style: "2ff"`는 1비트에만 씁니다.
- `style: "gray"`는 gray 코드로 만든 여러 비트 값(FIFO 포인터 등)에 씁니다. 같은 셀에 `WIDTH`만 줍니다.
- 도착 도메인의 리셋이 active-high이면 Emitter가 반전해 `rst_n`에 연결합니다.
- 리셋이 없는 동기화 플롭을 쓰던 원본(`axis_async_fifo`)도 이 셀로 바뀝니다. 사내 셀의 리셋 규약을 받으면 다시 봅니다.

P10(다중 클럭과 리셋)에서 임시 셀 셋을 더했습니다. 모두 리셋은 active-low 비동기(0으로)이고, 모델은 `pipeline/emitter/stubs/`에 있습니다.

```systemverilog
module sync_pulse (input logic src_clk, src_rst_n, dst_clk, dst_rst_n, d, output logic q);   // cdc_sync style "pulse"
module cdc_fifo #(parameter int WIDTH = 1, parameter int DEPTH = 2) (                         // cdc_fifo 블록
  input  logic src_clk, src_rst_n, src_valid, output logic src_ready, input  logic [WIDTH-1:0] src_data,
  input  logic dst_clk, dst_rst_n, output logic dst_valid, input  logic dst_ready, output logic [WIDTH-1:0] dst_data);
module rst_sync (input logic clk, rst_n, output logic rst_n_sync);                             // reset.synchronize
```

- `sync_pulse`: 보내는 쪽 토글을 2단으로 동기화하고 한 단 더 늦춘 값과 비교해 받는 쪽 한 주기 펄스를 냅니다.
- `cdc_fifo`: 이진 포인터와 gray 포인터 레지스터, 상대 gray 포인터의 2단 동기화. 받는 쪽 데이터는 조합으로 읽습니다.
- `rst_sync`: 비동기 assert, 클럭 두 에지 뒤 동기 deassert.
- SDC 골격은 셀 안의 동기화 첫 단 핀(`s1/D`, `wq1/D`, `rq1/D`)과 `rst_sync`의 `rst_n`을 가리킵니다. 사내 셀을 받으면 핀 이름도 바꿉니다.

## 메모리

`memory` 블록의 `impl: "inferred"`만 방출합니다. Emitter는 `word_type name [depth];` 배열을 선언합니다.

- 쓰기는 쓰기 포트 도메인의 `seq` 블록이 `name[addr] <= ...`로 합니다.
- 읽기는 읽기 포트 도메인의 `seq` 블록이 `name[addr]`로 합니다.
- 쓰기 포트가 여러 도메인에 있으면 읽고 쓰는 도메인이 달라도 됩니다(비동기 FIFO). 도메인 규칙은 V5와 V8이 검사합니다.
- `impl: "macro"`는 래퍼 규약을 받기 전까지 방출을 거부합니다.

## 프로토콜 태그

| 태그 | role | 신호 이름 규칙 | 하니스 |
| --- | --- | --- | --- |
| `valid_ready` | `source`(모듈이 valid를 냄), `sink` | `..._valid`와 `..._ready`로 끝나는 신호가 하나씩. 나머지는 data. AXI-Stream(`tdata`, `tvalid`, `tready`, `tlast`, `tuser` 등)도 이 태그로 씀 | 드라이버, 모니터, 체커(ready 전까지 valid와 data 유지) |

## 코딩 규칙

[docs/RTL 코딩 규칙.md](../../docs/RTL%20코딩%20규칙.md)로 옮겼습니다 (2026-10-22). 사내 코딩 가이드를 받으면 그 문서와 대조합니다.

## 로컬 모델

ollama 0.35.1 (Mac mini, 메모리 24GB). Claude Code는 Anthropic Messages 호환 경로(`/v1/messages`)로, Pi는 OpenAI 호환 경로(`/v1`)로 붙습니다.

| 모델 | 계열 | 입력 | 쓰는 곳 |
| --- | --- | --- | --- |
| `qwen3.5:9b` | Qwen | 텍스트 | X1, X3, 기본 |
| `gemma4:12b` | Gemma | 텍스트 | X1 (다른 계열) |
| `qwen3-vl:8b` | Qwen | 텍스트, 이미지 | X2 |
| `gemma4:12b-mlx` | Gemma | 텍스트 | 쓰지 않음 |

컨텍스트 길이는 서버에서 정합니다(`OLLAMA_CONTEXT_LENGTH`).
- **Claude Code에는 65536이 필요합니다.** 32768에서는 Seat가 시작 프롬프트만으로 한도를 넘었고, headless도 X1 과제 중 자동 압축을 되풀이하다 실패했습니다.
- `CLAUDE_CODE_MAX_CONTEXT_TOKENS`를 서버 값과 같게 둡니다.
- 서버 컨텍스트를 너무 크게 잡아도 안 됩니다. 262144로 띄운 서버는 9B 모델에 14.5GB를 잡았고, 다른 서버와 함께 돌자 메모리가 모자라 요청이 실패했습니다.
