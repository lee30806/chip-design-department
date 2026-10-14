# PROGRESS

[IMPLEMENTATION.md](./IMPLEMENTATION.md)의 단계별 진행 현황입니다. 단계마다 한 일, 결과, 남은 일을 기록합니다. 최신 기록이 위에 옵니다.

## 단계 현황

| 단계 | 상태 | 비고 |
| --- | --- | --- |
| P0 선행 확인 | 완료 (2026-10-11) | 사내 자료는 공개 자료와 임시 표준으로 대체. X1, X2는 agy로 판정. 로컬 모델 판정은 사용자가 따로 진행 |
| P1 블록 이식 시험 | 완료 (2026-10-11) | 공개 블록 4개. 원본 테스트벤치 49개 통과 |
| P2 결정론적 툴 | **지금 할 수 있는 항목 완료 (2026-10-11)** | 남은 항목은 아래 대기 항목 (조건 충족 시 진행) |
| P3 SPEC 변환과 검사 | **지금 할 수 있는 항목 완료 (2026-10-11)** | 입력: I3C 예시 SPEC. 남은 항목은 대기 항목 (조건 충족 시 진행) |
| P4 에이전트와 스케줄러 | **완료** (E2E 3/3, 블록마다 기댓값 승인 1회 포함. 사용자 마감 2026-10-12) | 에이전트: agy (Author `gemini-3.8-flash-high`, Verifier 등 `gemini-3.1-pro-high`. 2026-10-13 오후부터 모든 역할 `claude-sonnet-5-5-low`, 17시경부터 Claude Code CLI Sonnet effort low) |
| P5 파이프라인 API와 환류 입력 | **완료 (가능한 범위)** | 사내 툴 리포트 양식은 샘플을 받으면 양식 파일만 추가 |
| P6 부서 계층 (OpenRig) | **완료 (가능한 범위)** | 완료 기준 2개 시험 통과. 폐쇄망 설치, Linux 격리, Sanity 연동은 대기 |
| P7 게이트웨이와 Web UI 1차 | **완료** | 완료 기준: 승인자만 승인, 모든 승인 기록. SSO와 대화 중계는 이후 |
| P8 첫 Block Top End-to-End | **완료 (2026-10-13)** | 신규 블록 `axis_crc_append` RTL Freeze (실행 674c). agy Seat, 오픈소스 대체 EDA. 커밋 `34b2205` |
| P8a Python 동작 조각 | **완료 (2026-10-14)** | 사용자 결정. 구조는 JSON, 동작은 SV 또는 Python 조각. 비교 4블록 모두 두 언어 후보 통과 (단 async_fifo는 방출기 버그로 무효, 재검증 필요). 범위: 후보 하나만 Python (후보 0 SV, 후보 1 Python) |
| P9 운영 안정화 | **보류 (사용자 결정 2026-10-13)** | P8 회고에서 넘긴 항목은 아래 대기 항목 |

## 제외 항목 (사용자 결정)

- VC SpyGlass(E3), 라이선스 대기열, Emitter 대표 출력의 SpyGlass 회귀

## 대기 항목 (조건이 갖춰지면 진행)

| 항목 | 단계 | 진행 조건 |
| --- | --- | --- |
| `memory`의 `impl: macro` 방출 | P2 | 사내 메모리 매크로 래퍼 규약 |
| 전력 도메인 출력(UPF 입력) | P2 | UPF 작성 형식 확정 |
| `valid_ready` 외 프로토콜 태그의 하니스와 체커 | P2 | 사내 표준 프로토콜 태그 목록 |
| 사내 블록으로 P1, P2 재판정 | P1, P2 | 사내 블록과 테스트벤치 |
| X2 재판정 | P0 | 실제 SPEC 타이밍 다이어그램과 정답 |
| 로컬 모델 판정 (X1, X2, X3) | P0 | 사용자가 진행 |
| Word SPEC 변환 (10개 섹션 대응) | P3 | 사내 Word 양식 원본 |
| 블록 다이어그램 파싱 (Visio, SVG)과 경계 신호 교차 검사 | P3 | 다이어그램 원본과 그림 작성 규칙 |
| IP-XACT와 레지스터 맵 대조 | P3 | IP-XACT 파일 |
| Linux 서버에서 에이전트와 Seat 격리 (계정 분리, bubblewrap 등) | P4, P6 | 폐쇄망 서버 환경 |
| 폐쇄망 설치 (사내 npm 미러, 외부 호출 차단, 설치 문서) | P6 | 사내 환경. P0 X5 확인 목록 |
| Sanity 연동 (E3 결과 수신, DCLint 입력, EPC 래퍼) | P6 | E3 제외, 사내 툴 |
| 사내 툴 리포트 양식 (Superlint, Xprop, DFT, DCLint, 합성, LEC) | P5 | 실제 리포트 샘플. `config/report_formats/`에 양식 파일만 추가 |
| 승인된 RTL을 읽기 전용 브랜치로 제공 | P5 | 사내 Git 서버와 브랜치 규칙 (지금은 통과한 실행의 RTL을 API로 읽기 전용 제공) |
| 사내 SSO | P7 | 사내 인증 방식. `gateway/auth.py`에 인증 제공자 하나를 더함 |
| 대화 중계 (게이트웨이 → OpenRig → Seat) | P7 | P9 (P0 X6에서 `--raw` 방식 확정) |
| 동결 해제 전파 (L1 변경 요청 → Architect 재실행, 진행 중 루프 취소) | P4 | L1 변경이 실제로 필요한 블록 (P8) |
| 두 단계 이상의 모듈 트리 | P4 | 하위 모듈이 다시 나뉘는 블록 (P8) |
| 에이전트 단독 평가 나머지 (Author, Verifier, Architect 각 3블록, Repair cobs) | P4 | agy 사용량 여유 |
| 대체 LEC 무한 증명 (사내 Formality/Conformal 또는 FSM 재인코딩 끄기) | P8 | 사내 LEC 또는 PI 결정 |
| `axis_crc_append` CRC-E03 정의, Q-01 결정, DV 공백(SVA, 16비트 롤오버) | P8 | 다음 SPEC 개정 |
| golden 블록 Verifier 체커의 리셋 표본 가정 재확인 | P8 | P9 재개 |
| 설계 모델 실행기 확장 (`memory`, `cdc_sync`, 다중 클럭, struct, signed) | P8a | 필요한 블록이 나올 때 |
| 하니스에서 설계 모델로 Verifier 테스트 실행 (RTL 전 빠른 실행) | P8a | 실제 비교에서 Repair 반복 비용이 크게 나올 때 |

## 진행 기록

### 2026-10-13 Repair 충돌을 Design-lead가 결정 (사용자 지시)

사용자 지시: Repair가 서로 다른 모듈을 지목해 충돌하면 lead가 Repair 위치를 지정하거나 Architect에 근본 원인 수정을 요청한다. 계기는 P8a 비교 실험의 `axis_crc_append`다. SV 후보와 Python 후보 모두 CRC-12("CRC 두 바이트를 내는 동안 s_axis_tready=0")에서 `crc_append_core` → `axis_out_stage` → `crc_append_core`로 원인을 넘기다 `CHILD_SUSPECT_LOOP`로 실패했다.

- **스케줄러** (`pipeline/scheduler/run.py`): 충돌하면 실패로 끝내지 않고 결정 항목 `repair_conflict`를 등록하고 후보 묶음을 멈춘다 (검토 항목 `REPAIR_CONFLICT`). 항목에는 실패한 요구사항, 첫 불일치, SPEC 구절, Repair들이 서로 넘긴 순서와 이유가 있다.
  - 고칠 모듈 지정(`repair`): 그 묶음을 다시 검증하고 Repair는 지정한 모듈에서만 한다. Repair 과제에 `lead.json`(메모, 경위)이 들어가고 형제 모듈 지목은 게이트가 거부한다.
  - Architect 재구성(`architect`): Architect가 지금 트리(`current/`)와 충돌 경위(`conflict.json`)를 받아 모듈 경계나 하위 인터페이스를 다시 정한다. Block Top L1은 그대로(게이트)라 Verifier 테스트를 그대로 쓴다. 이전 후보 상태는 `modules_a<판>/`, L1은 `ir_a<판>/`에 보관하고 모든 후보를 Author부터 다시 돌린다. 재구성 뒤 에이전트 작업 이름에는 `/a<판>`이 붙는다. 결정하지 않은 다른 충돌 항목은 대체됨으로 닫는다. 재구성이 실패하면 검토 항목을 남기고 그 후보는 실패로 끝낸다.
- **결정 경로:** `approve resolve <id> (--repair <모듈> | --architect)`, 파이프라인 API `POST /runs/{id}/decisions`(design-lead 역할만), 게이트웨이 승인함(design_lead 능력만, 승인자는 불가, Design-lead Seat 가능), Web UI 카드(모듈 선택, 두 버튼), `deptctl lead-decide`. 결정은 승인 기록에 같이 남는다.
- **문서:** ARCHITECTURE.md(실행 규칙, 흐름도, Design-lead 역할), 파이프라인 설계 문서(실패 분류 표, Repair 규칙), 부서 설계 문서, IMPLEMENTATION.md, gateway/README.md, department/README.md, Design-lead 지침.
- **시험:** 가짜 agent로 두 결정 모두 끝까지 통과(`test_repair_conflict_lead_pins_module`, `test_repair_conflict_lead_requests_architect_revision`). 게이트웨이에서 승인자와 다른 역할은 403, Design-lead 사람과 Seat는 결정 가능(`test_repair_conflict_decided_by_design_lead`). 전체 254 통과, 3 건너뜀.
- 파이프라인 API와 게이트웨이를 다시 띄웠다. 비교 실험의 두 번째 줄(`axis_cobs_decode` → `axis_async_fifo`)은 새 코드로 다시 시작했다. 첫 줄은 남은 `axis_adapter`가 하위 모듈 하나라 충돌이 생길 수 없어 그대로 둔다. `axis_crc_append`는 이전 흐름으로 이미 실패로 끝났다.

### 2026-10-13 P8a 작업 9 실제 비교 시작 (사용자 지시)

- 드라이버: `experiments/p8a/pilot.py`. 블록마다 스케줄러를 한 번 돌리고 Author 후보 c0는 SV 조각, c1은 Python 조각으로 씁니다. 두 후보는 같은 Verifier 테스트를 공유합니다.
- 대상: `axis_crc_append`(F0001 승인 개정판 SPEC, `experiments/p8a/axis_crc_append.spec.md`), golden `axis_adapter`, `axis_cobs_decode`, `axis_async_fifo`.
- 두 줄로 나눠 병렬 실행합니다 (crc_append → adapter, cobs_decode → async_fifo). 상태는 `build/pilot/pilot-<블록>/`, 결과는 같은 곳의 `pilot.json`입니다.
- 지표: 후보별 통과 여부, Repair 수, lint, 번역기 검사, 에이전트 실행 수, golden 블록은 후보별 IR의 원본 테스트벤치 결과.
- 첫 시작은 Architect에서 바로 실패했습니다. agy 제공 목록에서 `gemini-3.1-pro-high`가 빠졌습니다 (`agy models`에 없음, 바이너리 1.3.3은 그대로). 사용자 결정으로 Verifier, Architect, Arbiter를 `claude-opus-5-5-high`로 바꾸고(`experiments/p0/local/agents.agy.json`) 다시 시작했습니다. 같은 계열 경고(MODEL_FAMILY)는 더 나오지 않습니다. 이전 실행(P4, P8)과 모델 조건이 다릅니다.
- 다시 시작한 뒤 Architect 2회(`axis_crc_append`, `axis_cobs_decode`)는 통과했습니다. 그다음 Verifier 4개를 동시에 시작하자 agy의 Claude Opus 사용량 한도에 걸려 두 실행이 `paused_quota`로 멈췄습니다 (09:15경, "Resets in 4h54m"이라 14:10경 풀림). 같은 명령으로 이어서 실행할 수 있습니다.
- Sonnet도 같은 Claude 한도를 써서 바로 막혔고 GPT-OSS도 막혔습니다. 사용자 결정으로 Verifier, Architect, Arbiter를 `gemini-3.8-flash-high`로 바꿔 이어서 실행합니다. Author와 같은 모델이라 Verifier 독립성이 약하고 MODEL_FAMILY 경고가 나옵니다. SV와 Python 후보는 같은 Verifier 테스트를 쓰므로 두 후보 비교는 유효합니다. 이미 끝난 Architect 2회(Opus 결과)는 그대로 이어 씁니다.
- 10:54 Gemini 한도도 차서 두 실행이 다시 `paused_quota`로 멈췄습니다 (14:55경 풀림, 실행마다 에이전트 11회). 그때까지 결과: Verifier 4개 통과, Author 8개(SV 4, Python 4) 모두 첫 시도 통과, 에이전트가 쓴 Python 모듈 4개 번역기 검사 통과(2000사이클), Repair는 SV와 Python 후보에서 비슷한 횟수였습니다. 한도가 풀린 뒤 같은 명령으로 자동 재개하도록 걸어 두었습니다.
- `axis_adapter`(SV, Python 후보 모두 Repair 0회): Verifier 0의 ADP-T01 체커에서만 실패했고 Arbiter가 test_wrong으로 판정했다 (체커가 m_axis_tlast=0을 같은 비트의 남은 바이트로 오해석). 사용자가 E1, E2를 승인해 sjlee로 기록하고 이어서 실행한다.
- **16:37 Gemini 주간 한도로 다시 멈춤 ("Resets in 102h46m", 10월 17일 23시경).** 그때까지 결과:
  - `axis_adapter`: SV, Python 후보 모두 통과 (Repair 각 1회, lint 0, Python 번역기 검사 통과). 후보 간 차분 검사에서 Verifier 보강 단계에 멈춤.
  - `axis_cobs_decode`: 실패. SV, Python 후보 모두 Repair가 인터페이스 변경을 요청함 (COBS-E01 "rst=1인 동안 s_axis_tready=0"은 동기 리셋과 레지스터 출력으로는 같은 사이클에 만족할 수 없음. P8 CRC-E01과 같은 SPEC 문장 문제). 그런데 두 후보의 마지막 IR은 원본 테스트벤치를 모두 통과함 (16/16, 16/16).
  - `axis_crc_append`: 실패. SV, Python 후보 모두 Repair 충돌 (모듈 나누기 문제).
  - `axis_async_fifo`: Architect, Verifier 2개 통과 뒤 Author에서 멈춤.
  - 지금까지 SV와 Python 후보의 차이는 없음. 첫 시도 통과율, 실패 양상, Repair 수가 같고(cobs의 Python 후보만 Repair 2회 더) 번역기 검사는 모두 통과. 실패는 SPEC 문장과 모듈 나누기에서 나옴.
- 사용자 결정(16:55경): 모든 역할(Author 포함)을 `claude-sonnet-5-5-low`로 바꿔 남은 `axis_adapter`(마무리)와 `axis_async_fifo`를 이어서 실행한다. 앞 단계(Architect, Verifier, Author 결과)는 Gemini로 만든 것을 그대로 이어 쓰므로 블록 안에서 모델이 섞인다.
- 16:53 Claude 한도도 차서 두 실행이 다시 멈췄다 ("Resets in 146h", 10월 19일 19시경). Sonnet으로는 에이전트 3회(Verifier 보강 1, Author 1, 그리고 한도 오류)만 돌았다. `axis_adapter`는 보강 테스트 단계, `axis_async_fifo`는 Author 단계에서 멈춤. agy의 모든 모델 한도가 찼으므로 Gemini 한도가 풀리는 10월 17일 23시경 이후에 같은 명령으로 이어서 실행한다.
- 사용자 결정(17시경): coding agent를 agy에서 Claude Code CLI(2.1.295)로 바꾸고 모델은 Sonnet, effort low (`experiments/p0/local/agents.claude.json`, `config/roles.json`). 인증은 CLI 로그인을 쓰고, 사용자 설정·훅·플러그인·MCP·스킬은 읽지 않게 했다 (`--setting-sources ""`, `--strict-mcp-config`, `--disable-slash-commands`). 파이프라인 격리(sandbox-exec) 안에서 시험 실행 통과. 한도 문구에 Claude Code의 "usage limit", "hit your limit"을 더했다. 같은 명령으로 `axis_adapter`, `axis_async_fifo`를 이어서 실행한다.
- **19:14 Claude Code(Sonnet low)로 두 실행 마침.**
  - `axis_adapter`: 통과. SV, Python 후보 모두 통과(Repair 각 1회, lint 0, 번역기 검사 통과), 원본 테스트벤치 두 후보 모두 9/9. SV 후보(c0)를 고름.
  - `axis_async_fifo`: 실패. SV 후보는 Repair가 인터페이스 변경을 요청함 (AFIFO-E02 "s_rst가 걸린 사이클에 s_axis_tready=0"은 동기 리셋 도메인에서 조각이 리셋을 읽을 수 없어 같은 사이클에 만족할 수 없음. COBS-E01, CRC-E01과 같은 SPEC 문장 문제). 그래도 SV 후보 IR은 원본 테스트벤치 20/20 통과.
  - Python 후보는 `axis_async_fifo_mem`의 Author가 실패함: `mem[wr_addr] = wr_word`, `rd_word = mem[rd_addr]`를 Python 조각 번역기(pyfrag)가 받지 않음 ("비트 선택은 신호 이름에만"). memory 읽기·쓰기를 Python 조각에서 쓸 수 없는 번역기의 빈틈이다. 그래서 묶음 전체(c1)가 실패로 처리됨. pilot.json의 c1 원본 테스트벤치 20/20은 Python으로 쓴 m, s와 IR이 없는 mem 자리에 golden IR을 넣은 결과라 c1 통과로 볼 수 없다.
- **사용자 요청(19시 반경): 드러난 문제를 먼저 고침.**
  - **Repair의 L1 변경 요청은 Arbiter가 먼저 판정** (P8 회고 조정안 1): 지금까지 cobs, async_fifo, CRC(b60e)가 모두 테스트가 SPEC을 엄격하게 읽은 탓(리셋이 걸린 그 사이클)인데도 Arbiter 없이 실패로 끝났다. 이제 Repair가 `request_interface_change`를 내면 실패한 Verifier마다 Arbiter가 `repair_claim`(Repair의 주장)과 함께 판정한다. test_wrong이면 기댓값 수정 승인 대기, spec_ambiguous면 검토 항목, rtl_wrong일 때만 INTERFACE_CHANGE로 멈춘다. 한 후보가 여러 승인 항목을 기다릴 수 있어(`pending_ids`) 모두 결정돼야 다시 돈다. 시험 2개 추가.
  - **Python 조각의 메모리 읽기·쓰기:** `mem[addr]`로 한 워드씩 읽고 쓴다 (쓰기는 `seq`만, 워드 일부 선택이나 범위 선택은 오류). 설계 모델 실행기도 `memory`(inferred)를 실행한다 (워드는 쓴 적 없으면 0, 깊이 밖 쓰기는 무시). 깊이 식의 `**`를 상수로 계산. 실패했던 async_fifo Python 후보의 mem IR이 이제 검사와 방출을 통과한다. 안내서(`ir_guide.md`)에 규칙 추가, 픽스처 `py_ram`과 시험(번역, 실행, 오용 오류, 틀린 RTL 검출) 추가.
  - **비교 드라이버:** IR이 없는 모듈이 있는 후보는 원본 테스트벤치 판정을 건너뛰고 `skipped`로 남긴다 (golden IR로 채운 결과가 그 후보의 통과로 보이던 문제).
  - 커밋 711684c 뒤 사용자 지시로 cobs, async_fifo, CRC를 처음부터 다시 실행 (모든 역할 Claude Code Sonnet low). 이전 결과는 `build/pilot/pilot-<블록>.r1`과 작업 디렉터리 `runs/pilot-<블록>.r1`에 보관.
- **20:28 재실행 결과 (모든 역할 Claude Code Sonnet low).**
  - `axis_cobs_decode`: **통과** (에이전트 10회, 6분). SV 후보 Repair 1, Python 후보 Repair 2 (Arbiter rtl_wrong 1), lint 0, 번역기 검사 통과. 원본 테스트벤치 두 후보 모두 16/16. SV 후보를 고름. 이전 실행(Gemini)의 COBS-E01 L1 변경 요청은 이번에는 나오지 않음.
  - `axis_crc_append`: 승인 대기 (에이전트 10회, 4분). 두 후보 모두 Verifier 0의 `crc_no_accept` 속성에서 실패, Arbiter가 test_wrong으로 판정 (cycle 37 출력은 다음 프레임 데이터 바이트인데 속성이 출력 바이트를 잘못 셈). 이전 실행의 Repair 충돌은 이번 모듈 트리(axis_crc_core, crc16_step)에서는 나오지 않음. **사용자가 E1, E2를 승인했고 sjlee로 기록**, 이어서 실행.
  - `axis_async_fifo`: 실패. 모든 후보가 "TB 실행 오류"였으나 원인은 **방출기 버그**: 인스턴스끼리 잇는 wire의 타입에 자식 파라미터 이름(`WORD_WIDTH`)을 그대로 써서 Block Top이 컴파일되지 않음. E1이 골격 lint 에러로 잡았지만 스케줄러가 무시하고 E2 빌드 실패를 TB 오류로 분류함.
    - 고침: wire 타입의 자식 파라미터를 인스턴스가 준 값(없으면 자식 기본값)으로 바꿈 (`pipeline/emitter/sv.py` `_parent_type`). 번역기 검사로 두 인스턴스 계층을 확인하는 시험 추가.
    - 고침: 골격(조각 밖) lint 에러는 생성기 버그로 보고 후보를 멈추고 GENERATOR_BUG 검토 항목을 남김 (Repair나 TB 오류로 가지 않음). 시험 추가. 전체 265 통과.
    - 이전 결과를 `.r2`로 보관하고 처음부터 다시 실행.
- **21시경 crc 두 번째 승인 대기 (E3, E4).** Verifier 수정 뒤 reset_mid 테스트에서 하니스의 T2 검사(valid가 ready 전에 내려감)가 프레임 도중 리셋 뒤 valid 하강을 위반으로 봄. Arbiter는 RTL이 맞다(CRC-E01)고 판정했지만 원인은 Verifier 테스트가 아니라 **하니스(`pipeline/tb/lib.py`)의 T2 검사가 리셋을 모름** (P8 리셋 표본 결함과 같은 계열).
  - 사용자 결정: 하니스를 고치고 E3, E4는 거절 (sjlee 기록). T2는 리셋이 걸린 표본과 그 다음 표본에서 보지 않고 기다리던 전송을 버린다. 시험 추가 (고치기 전에는 리셋 사이클도 위반으로 잡음을 확인).
  - 이어서 실행.
- **21:20 결과.** `axis_crc_append` **통과** (하니스 T2 수정 뒤, 에이전트 누적 13회). SV, Python 후보 모두 통과, Python 번역기 검사 통과, SV 후보를 고름. `axis_async_fifo`는 실패 (에이전트 24회, 15분): 모듈 트리 afifo_wr/afifo_rd/afifo_mem에서 Repair를 여러 번 거친 뒤 Repair가 `out/patches.json`을 쓰지 않고 끝나 게이트에서 실패 (c0은 afifo_wr, c1은 afifo_mem). 원본 테스트벤치는 두 후보 모두 20/20.
  - **원인 (10월 14일 확인):** Repair 실패가 아니라 Claude Code 세션 한도("You've hit your session limit · resets 1:20am")로 에이전트가 끊긴 것. 한도 문구 목록에 이 문장이 없어 스케줄러가 멈추지 않고 Repair 실패로 처리함. `session limit`을 한도 문구에 더하고 시험 추가.
  - 복구: 끊긴 Repair 2건(afifo_wr c0 r2, afifo_mem c1 r0)의 작업 기록을 지우고 Repair 횟수를 하나씩 되돌린 뒤 후보 상태를 running으로 바꿔 이어서 실행 (손대기 전 상태는 `build/pilot/pilot-axis_async_fifo.bak-quota`).
- **10월 14일 06:52 async_fifo 재개 결과: 실패.** 두 후보 모두 `afifo_rd`의 Repair 상한 5회에 걸림 (에이전트 누적 32회). 두 Verifier가 함께 실패하므로 Arbiter를 거치지 않았다. 마지막 검증에서 실패한 테스트:
  - pause (AFIFO-07): v0 `m_pause_ack`가 1이 되지 않음, v1 `s_pause_ack`가 풀리지 않음. RTL 문제일 가능성이 높음.
  - AFIFO-08: v1이 `s_status_depth > DEPTH`를 위반으로 봄. SPEC은 깊이를 "비트 수"로 적어 단위가 모호함 (SPEC 문장 문제 후보).
  - AFIFO-E02: v1이 m 리셋 중 `s_axis_tready=0`을 그 사이클에 요구함 (동기화 지연을 고려하지 않은 해석 후보).
  - 그런데도 두 후보 모두 원본 테스트벤치 20/20 통과 (원본 TB는 pause와 상태 출력을 깊게 보지 않음).
  - 다음 후보 작업: P8 회고 반복 상한 1(같은 테스트가 Repair 두 번 연속 실패하면 상한 전에 Arbiter를 부름)을 구현하면 이런 경우가 Arbiter와 사람에게 간다. SV와 Python 후보는 같은 이유로 실패해 언어 차이는 아님.
- **사용자 지시(10월 14일 아침): 커밋/푸시 후 제안안 진행.** 같은 실패(실패한 Verifier와 테스트 이름이 같음)가 Repair 두 번 뒤에도 이어지면 상한 전에 실패한 Verifier마다 Arbiter가 `repeated_failure`와 함께 판정한다. test_wrong이면 기댓값 수정 승인 대기, 모호하면 검토 항목, rtl_wrong이면 Repair를 이어 가고 같은 실패는 다시 판정하지 않는다. 한 Verifier만 실패한 경우는 이미 매번 Arbiter를 거치므로 제외. 시험 2개 추가.
- 커밋 2c0e592 뒤 async_fifo를 처음부터 다시 실행 (이전 결과는 `.r3`에 보관).
- **07:23 async_fifo 결과: 승인 대기.** 후보 0(SV)은 Repair 충돌 E1 (afifo_mem → afifo_rd → afifo_wr → afifo_rd, 실패 테스트 sc02_s_reset_mid_frame: s 리셋이 프레임 도중에 걸리면 tlast가 일찍 나옴). 후보 1(Python)은 afifo_rd가 같은 IR로 돌아와 진동으로 실패. Repair 2회라 반복 실패 Arbiter 기준에는 닿지 않음.
  - 사용자(Design-lead) 결정: afifo_rd에서 Repair (sjlee 기록). mem, wr 두 Repair가 AFIFO-05 종료 로직은 rd에 있다고 지목. 이어서 실행.
  - 관찰: rd의 Repair가 "failure.json에 report가 없어 불일치 위치를 특정하지 못함"이라고 함. 실패한 테스트의 불일치 리포트(트레이스)가 Repair에 전달되지 않은 경우가 있음. 조사 거리.
- **07:27 반복 실패 Arbiter가 처음 동작.** lead가 정한 afifo_rd Repair 전에, 같은 테스트(sc02_s_reset_mid_frame)가 Repair 2번 뒤에도 실패해 Arbiter가 판정: Verifier 0 test_wrong (E2). 테스트가 리셋 해제 뒤에도 보내던 프레임의 나머지를 계속 보내면서 "마지막 전에는 tlast 없음"을 단언해 AFIFO-05에 없는 것을 요구. 다른 테스트의 `set_ready`에 list를 넘기는 TypeError도 함께 고치도록 함.
  - 사용자가 E2를 승인했고 sjlee로 기록. 이어서 실행.
- **07:35 async_fifo 결과: 실패.** E2 반영 뒤 후보 0의 afifo_rd Repair(lead 지정) 3번이 상한 5회에 걸림. 후보 1(Python)은 앞서 진동으로 실패.
  - 원인 분석: E2 직전(r6) 첫 불일치가 `tid` 5 → 2, `tlast` 0 → 1로 한 비트 어긋남. afifo_wr이 데이터 워드를 묶는 비트 순서와 afifo_rd가 푸는 순서가 다르다 (모듈 사이 워드 배치 계약 불일치). Architect가 L1에 워드 폭만 정하고 필드 배치는 정하지 않아 두 Author가 각자 정함.
  - lead 지정 afifo_rd Repair는 이걸 바로잡지 못하고 RTL을 더 망가뜨림 (r7부터 sc01_single_frame에서 데이터 누락). Repair 충돌 E1의 바른 결정은 Architect 재구성(워드 배치를 L1 계약으로 정함)이었을 가능성이 높다. 사람 결정 시 첫 불일치 리포트가 없어(`first_failure` null) 판단 근거가 부족했다.
  - 개선 후보: (1) 모듈 사이 묶음 워드는 Architect가 필드 배치(struct나 비트 범위)를 L1에 정한다. (2) Repair 충돌 항목에 첫 불일치 리포트를 꼭 붙인다 (이번에 null). (3) lead 지정 Repair 뒤 실패가 늘면 되돌린다.
- **사용자 지시(10월 14일 오전): 개선 후보 세 가지 진행.**
  1. **묶음 워드 금지 (Architect):** 하위 모듈 사이에서 여러 필드를 한 워드로 묶어 넘기지 않는다는 규칙을 Architect 과제에 넣고, 게이트에서 하위 모듈끼리 잇는 포트의 폭이 파라미터 둘 이상의 합이면 거부한다 (인스턴스 바인딩으로 숨긴 `WORD_WIDTH`도 잡음). 지난 실행 트리에 적용해 보니 async_fifo r2, r3, r4만 걸리고 r1(메모리 모듈 안에서 묶고 풂)과 다른 블록은 통과.
  2. **첫 실패 리포트:** 하니스 결과가 없는 실패(테스트 안의 assert)도 실패한 테스트와 메시지를 리포트에 넣는다. Repair, Arbiter, Repair 충돌 항목이 첫 실패를 모른 채 판단하던 문제. 게이트웨이 화면도 메시지를 보여 줌.
  3. **lead 지정 Repair 되돌리기:** lead가 지정한 모듈의 Repair 뒤 실패한 테스트 수가 늘면 그 Repair를 되돌리고(IR과 patch 기록), 지정을 풀고, Repair 충돌 항목을 다시 올린다 (LEAD_REPAIR_REGRESSED). lead는 다른 모듈이나 Architect 재구성을 고를 수 있다.
  - 시험 3개 추가 (묶음 워드 검사, assert 실패 리포트, 되돌리기).
  - 전체 시험 271 통과, 1 실패(`test_http_api`: 부하 중 실행이 stopped로 끝남, 따로 돌리면 통과). async_fifo를 처음부터 다시 실행 (이전 결과 `.r4`).
- **08:28 async_fifo 재실행 결과: TB 실행 오류로 실패.** 새 Architect 트리(afifo_wr, afifo_rd, afifo_mem)는 묶음 워드 검사를 통과함. 실패 원인은 하니스: Verifier가 `cover_protocol`에 요구사항 ID 목록을 넘겨 `finish()`가 `unhashable type: 'list'`로 죽음 (앞서 Arbiter가 말한 TypeError와 같은 것). 요구사항은 ID 하나나 목록을 받도록 고침 (`req_ids`), 시험 추가. 후보 상태를 running으로 되돌려 이어서 실행 (손대기 전 `.bak-tberr`).
- **08:32 async_fifo: 승인 대기 (E1, E2).** 하니스를 고친 뒤 두 후보 모두 Verifier 0 테스트는 통과하고 Verifier 1의 fill_full 하나만 실패 (m_axis_tready를 1500클럭 0으로 둔 동안 못 나온 비트를 missing으로 봄). Arbiter test_wrong: 막힌 동안의 출력 기한은 SPEC에 없음.
  - 사용자가 E1, E2를 승인했고 sjlee로 기록. 이어서 실행.
- **08:45 async_fifo: 승인 대기 (E3, E4).** fill_full 수정 뒤 Verifier 1의 sc02 리셋 테스트가 두 후보에서 실패, Arbiter test_wrong (송신 큐의 남은 비트가 리셋 뒤에도 들어오는데 "마지막 출력이 종료 비트"를 요구). 지난 실행 E2와 같은 종류.
  - 사용자가 E3, E4를 승인했고 sjlee로 기록. 이어서 실행.
  - 관찰: 리셋 시험에서 하니스 송신 큐가 리셋 뒤에도 계속 보내는 것이 같은 오판을 두 번 만듦. 하니스에 "도메인 리셋 때 그 도메인 송신 큐 비우기"를 두는 것이 개선 거리.
- **09:05 async_fifo 통과.** SV, Python 후보 모두 통과 (Repair SV 4, Python 6, lint SV 20, Python 21). 원본 테스트벤치 두 후보 모두 20/20. SV 후보를 고름. 에이전트 누적 30회, 사람 결정은 기댓값 수정 4건(E1~E4) 승인. (Python 후보는 `memory`와 `cdc_sync`를 쓰는 모듈이라 번역기 검사를 건너뜀.)
- **P8a 비교 실험 결과 (4블록, 모든 역할 Claude Code Sonnet low):** adapter, cobs_decode, crc_append, async_fifo 모두 SV와 Python 후보가 함께 통과. 원본 테스트벤치도 두 후보 모두 통과. 언어 때문에 생긴 실패는 Python 조각의 메모리 지원 빈틈 하나(고침)뿐이고, 나머지 실패는 모두 파이프라인 쪽(방출기, 하니스 리셋 처리와 req 목록, 한도 문구, 묶음 워드 계약)이나 Verifier 테스트 해석에서 나왔다. Repair 수는 Python 후보가 같거나 조금 많다 (cobs 1→2, crc 0→1, fifo 4→6).
- **사용자 결정(10월 14일): Python 조각은 후보 하나만.** `config/roles.json`의 `author.langs`를 `["sv", "py"]`로 바꿈 (후보 0 SV, 후보 1 Python). 근거: 통과율 차이 없음, Python은 Repair가 같거나 조금 많음, 번역기 검사는 memory/cdc_sync 모듈을 아직 못 봄. 두 언어 후보의 차분 검사로 다양성을 얻고 비용은 후보 하나로 제한. 실제 설정을 읽는 시험(API, 게이트웨이, 부서) 통과. **P8a 완료.**
- **사용자 지시(10월 14일): P8 회고 조정안(운영 정리 제외)과 하니스 송신 큐 비우기 진행.**
  - **하니스:** 테스트 도중 리셋을 걸면 그 도메인 입력 번들의 남은 전송을 버린다 (async_fifo sc02 오판 두 번). Verifier 안내서에도 적음. 시험 추가 (고치기 전에는 실패 확인).
  - **반복 상한과 예산:** `repair_per_candidate` 5 → 3, `budget_agent_runs` 200 → 60 (P8a async_fifo 최대 30회). 실행 상태에 같은 Block Top 계보의 에이전트 실행 합계(`lineage_agent_runs`)를 보임. 실행이 2시간을 넘으면 감시(watchdog)가 운영에게 한 번 알림(멈추지 않음).
  - **툴 결함으로 버린 실행:** `POST /runs/<id>/discard`(chip-lead, design-lead)로 사유와 함께 기록하면 환류 재실행 상한 계산에서 뺀다.
  - **검토 항목:** (1) 같은 Verifier의 같은 테스트가 같은 이유로 여러 후보에서 실패하면 기댓값 수정 항목 하나로 묶고 한 번 결정으로 모든 후보를 풂. (2) 결정이 반영되면 그 검토 항목에 결과(결정, 사람, 시각)를 적음. (3) 가정은 Architect가 `affects`(l1, timing, reset, spec_gap)를 표시하고, 비지 않은 것만 검토 항목 (모듈 안 배분은 Architect 기록에만). 회고는 L1, 타이밍, 리셋만이었으나 SPEC 미정의를 정한 가정도 사람이 봐야 해서 spec_gap을 더함. 표시가 없는 가정은 검토 항목. (4) MODEL_FAMILY는 처음 보는 역할 설정에서만 (본 설정은 저장소 밖 `roles_seen.json`). (5) SPEC 변경 요청에 SPEC 툴 검사(게이트, 오류, 새로 생긴 검토 항목)를 붙이고 게이트웨이에 보임.
  - **조합 경로 검사:** SPEC 9절의 출력 레지스터·조합 통과 금지를 읽어, 통과한 후보의 입력→출력 조합 경로를 COMB_PATH 검토 항목으로 냄 (IR 그래프). PI에는 `eda comb`(합성 넷리스트 기준)을 더함. P8 첫 실행(0a82) RTL에서 두 검사 모두 pi.lead가 찾은 경로 3개(m_axis_tready→s_axis_tready, s_axis_tdata→m_axis_tdata, s_axis_tvalid→m_axis_tvalid)를 찾고, 674c와 P8a crc에서는 0개.
- **사용자 지시(10월 14일): 조합 경로 검사에 조합 루프 금지 추가.**
  - `eda comb`이 합성 넷리스트의 조합 루프를 ERROR로 낸다 (강연결 요소). 실제 RTL 6개(P8 0a82, 674c, P8a 4블록)에서 루프 0개로 오탐 없음. IR 단계는 Validator V6가 이미 조합 루프를 오류로 막는다.
  - **V6 빈틈과 방출기 버그 발견:** 인스턴스 출력이 부모 포트와 다른 인스턴스로 함께 나가면 넷 이름이 갈렸다. 방출기는 한쪽을 구동 없는 wire나 구동 없는 출력 포트로 남겼고, V6는 인스턴스를 넘는 조합 루프를 놓쳤다. 넷 이름을 부모 포트 이름으로 통일하고 V6가 방출기와 같은 넷 표를 쓰게 고침. 시험 2개 (번역기 검사로 RTL 동작 확인, 인스턴스를 넘는 루프).
  - **영향:** 지난 async_fifo 트리 모두 `m_pause_ack`가 이 모양이었다. 통과로 기록한 P8a async_fifo RTL은 출력 `m_pause_ack`가 구동되지 않는다 (verilator UNDRIVEN). 앞선 실행의 "m_pause_ack가 1이 되지 않음" 실패도 이 버그였고 Repair로는 고칠 수 없었다. **P8a async_fifo 통과는 무효.** 다른 P8a 블록과 P8 RTL Freeze(674c)에는 없음.
  - 골격 lint의 UNDRIVEN, MULTIDRIVEN 경고도 생성기 버그(GENERATOR_BUG)로 멈춤 (전에는 에러만).
- `department/seats.json`의 Seat 모델도 `gemini-3.1-pro-high`라서 Seat를 다시 띄우면 같은 문제가 납니다. 이번 비교에는 Seat를 쓰지 않아 그대로 두었습니다.
- `axis_async_fifo`는 `memory`, `cdc_sync`를 써서 설계 모델 실행기가 지원하지 않으므로 Python 후보의 번역기 검사는 건너뜁니다 (번역과 RTL 검증은 그대로 함).

### 2026-10-13 P8a Python 동작 조각 (사용자 결정)

사용자 결정: IR 구조는 JSON 그대로 두고 동작을 Python(사이클 단위)으로도 쓴다. 논의에서 정한 것은 셋이다. (1) Python 조각은 IR 슬롯 안에 두어 소스맵을 SV 줄 → (IR 노드, Python 줄) 한 번으로 줄인다. (2) 설계 모델(Author)과 참조 모델(Verifier)은 따로 쓴다. 같은 모델을 RTL 원천과 기댓값에 쓰면 검증이 순환한다. (3) 설계 모델 대 RTL 비교는 번역기 검사로만 쓰고 판정은 RTL 시뮬레이션이다.

- **스키마:** 모듈 `lang`(`sv` 기본, `py`). 설정 변경 환류에 `author_langs`.
- **조각 번역기** `pipeline/ir/pyfrag.py`:
  - Python 부분집합(대입과 비트/범위 대입, `op=`, if/elif/else, `for range`, 산술·비트·비교·논리, 조건식, `cat/rep/u/any_bits/all_bits/parity`)을 SV로 옮긴다.
  - reads/writes는 AST에서 계산한다. 문장 하나는 SV 문장 하나로만 옮긴다.
  - 폭은 IEEE 1800 규칙에 정수 리터럴만 문맥 폭을 따르게 정했다. 모든 확장과 절단은 캐스트로 적고, 폭이 파라미터에 달리면 파라미터 선형식 캐스트(`(S_KEEP_WIDTH)'(0)`)로 적는다. 처음에는 기본 파라미터 값으로 폭을 박아 넣어, 다른 파라미터로 인스턴스하면 틀리는 문제가 있어 고쳤다.
  - Verilator가 암묵적 폭 변환을 오류로 막아(프로젝트 규칙과 같음) 명시적 캐스트 방식으로 정했다. 방출 RTL은 lint 경고 0.
- **연결:** `Module`이 `py` IR을 읽을 때 SV 조각으로 낮춘다 (`raw`는 낮춘 IR, `source_raw`는 원문). Validator, Emitter, 하니스는 그대로 쓴다. 번역 오류는 V4(조각 줄 번호 포함).
- **소스맵:** Emitter가 문장별 `py_line` 항목을 내고, Classifier 메시지에 "Python 조각 N번째 줄"을 붙인다.
- **설계 모델 실행기** `pipeline/ir/pysim.py`: 번역기와 같은 폭 함수로 사이클 실행. 인스턴스와 파라미터 대입, 동기/비동기 리셋, FSM 지원. 도메인 하나만, `memory`/`cdc_sync`/struct/signed는 아직 없다.
- **번역기 검사** `pipeline/verify/pyequiv.py`: 같은 무작위 자극(가끔 리셋)을 설계 모델과 RTL에 넣어 사이클마다 출력 비교. 스케줄러가 `py` 모듈마다 E1 뒤에 돌리고, 불일치면 Repair 없이 후보를 멈추고 `PY_EQUIV` 검토 항목을 남긴다.
- **에이전트:** Author 후보 c의 언어는 `roles.author.langs[c % 길이]` (기본 `["sv"]`라 지금 동작은 그대로). Author 종료 게이트가 `lang`을 확인한다. 안내서에 Python 조각 절, `pl.py pysim` 명령. Repair 과제에 Python 조각 안내.
- **픽스처** `tests/fixtures/py/`: `pkt_parser`, 폭 규칙용 `py_ops`, golden `axis_adapter`의 Python 판.
- **확인:**
  - 번역기 검사 통과: `pkt_parser`, `py_ops`, `axis_adapter`. `axis_adapter`는 기본값이 아닌 파라미터(S_KEEP_WIDTH=8 등)로 감싼 Block Top에서도 통과.
  - Python 설계 모델이 손으로 쓴 SV 판(기존 `pkt_parser` 픽스처, golden `axis_adapter`)의 RTL과 같은 출력을 낸다.
  - 일부러 틀린 RTL은 번역기 검사가 잡는다.
  - 가짜 에이전트 스케줄러 시험: 후보 0은 SV, 후보 1은 Python. 둘 다 통과하고 후보 간 차분도 없다.
  - 전체 테스트 251 통과, 3 건너뜀 (24개 추가). 파이프라인 API 서버를 다시 띄웠다.
- **문서:** ARCHITECTURE(원칙, 데이터 흐름, 구성요소, IR, 추적성), 파이프라인 설계 문서(개요, 결정, IR 공통 원칙, 조각 언어 절, V4, 실패 분류, 검증), 부서 설계 문서, IMPLEMENTATION(P8a 단계, 저장소 구조, 위험).
- **남은 일:** 실제 블록에서 SV 후보와 Python 후보 비교 (agy 실행, 사용자 지시 대기). 실행기 확장과 Verifier 테스트의 설계 모델 실행은 대기 항목으로 둔다.

### 2026-10-13 P8 마감과 P9 보류

- P8 변경분을 커밋해 `origin/main`에 올렸습니다 (`34b2205`, 사용자 요청). 확인용 import 명령 패치는 지시대로 넣지 않았습니다.
- 사용자 결정: P9(운영 안정화)는 보류합니다. P8 회고 조정안과 남은 일은 대기 항목에 올렸습니다.
- 운영 주의: 승인 기록 스크립트를 만드는 중 게이트웨이 초기 비밀번호(admin, op, sjlee)가 세션 로그에 출력됐습니다. 게이트웨이는 로컬에서만 열려 있지만 비밀번호 변경을 권했습니다 (사용자 조치 대기).

### 2026-10-12 P8 시작: 신규 블록, 대체 EDA, agy Seat 운영

사용자 결정: 새 SPEC을 직접 쓴다, PI와 Sanity는 오픈소스로 대체 설치한다, Seat 일은 agy Seat가 직접 한다.

- **신규 블록 `axis_crc_append`** (`blocks/axis_crc_append/block_spec.md`, 이식 블록이 아님):
  - AXI-Stream 바이트 프레임을 통과시키며 CRC-16/CCITT-FALSE 2바이트를 덧붙이고, 프레임 수(`stat_frames`)를 냅니다.
  - 동작 기준은 200 MHz입니다. 요구사항은 기능 12개, 타이밍 3개, 예외 3개이고, 예시 시나리오가 3개 있습니다.
  - SPEC 검사에서 오류와 경고는 0건이고, 처음 판의 REQ_MULTI 7건은 요구사항을 나눠 없앴습니다.
- **대체 EDA:**
  - Yosys 0.69를 Homebrew로 설치했습니다. OpenSTA와 eqy는 Homebrew에 없습니다.
  - `department/bin/eda`: lint(Verilator), synth(Yosys), lec(Yosys 형식 등가: RTL 대 넷리스트, 메모리는 플립플롭으로 풀어 비교), sta(`department/tools/generic.lib` 일반 셀로 매핑 뒤 ABC `stime` 최악 경로 + clk-to-q + setup 대 SDC 주기), sdc(SDC 대 RTL 포트).
  - 리포트 양식 `config/report_formats/eda.json`을 더했습니다.
  - 확인한 것:
    - adapter RTL에서 다섯 검사가 모두 동작합니다 (LEC 173개 등가 증명).
    - 넷리스트에 버그를 넣으면 LEC가 등가 아님 2개를 냅니다.
  - 제약: `axis_async_fifo`(메모리 1024단을 플립플롭 8만 5천 셀로 풀어냄)는 LEC가 15분 넘게 끝나지 않았습니다. 큰 메모리는 사내 LEC나 메모리 블랙박스 처리가 필요합니다.
- **파이프라인과 게이트웨이:**
  - 통합 때 Block Top SDC 골격과 표준 셀을 `rtl/`에 남깁니다.
  - 게이트웨이 RTL 조회에 SDC가 들어갑니다.
  - `deptctl`에 `export`(RTL과 SDC를 파일로), `spec --markdown`, `signoff`(DV/PI Seat)를 더했습니다.
- **운영 환경:**
  - 게이트웨이 계정: admin, op(운영, 설계 역할), sjlee(승인자, Seungjoon Lee). 초기 비밀번호는 `~/.cache/chip-design-department/gateway/initial_passwords.txt`(0600)에 있습니다.
  - 부서 rig를 agent 모드로 올렸습니다 (Seat 15개 agy, 파이프라인 API, 게이트웨이).
- **agy 명령 확인:**
  - agy가 명령마다 실행 확인을 물어 무인 Seat가 멈췄습니다.
  - 권한은 OS sandbox가 강제하므로 Seat의 agy를 `--dangerously-skip-permissions`로 띄우게 바꿨습니다 (`department/bin/seat`).
  - 일하던 Seat 6개는 새로 띄우고 지시를 다시 보냈습니다.
- **진행 순서:**
  1. SPEC 고정: 운영이 SPEC을 올리고 Q-01에 답한 뒤 고정을 요청했고, 사용자가 승인했습니다 (기록: sjlee, 판 `52985d0f0a75`).
  2. 실행 제출과 병렬 준비:
     - RTL Engineer Seat가 실행 `axis_crc_append-20261012-175530-0a82`를 제출했습니다 (`seat-design-rtl`).
     - DV Pod: DV-lead가 계획(`dv_plan.md`)을 썼습니다. vPlan은 요구사항 ID별 검증 표, TB는 cocotb와 Verilator 독립 TB(파이썬 CRC 참조 모델, 시나리오 3개, backpressure 무작위), Checker는 SVA 모듈(lint 통과)을 만들었습니다.
     - Power Intent Seat가 UPF(단일 도메인 PD_TOP)를 썼습니다.
  3. 파이프라인 진행 (17:55\~19:23): Architect가 `crc16_ccitt`(조합 CRC)와 `axis_crc_core`(FSM, 핸드셰이크)로 나눴습니다. c0은 Repair 3회 뒤, c1은 Repair 1회 뒤 같은 테스트(`test_reset_and_recovery`의 CRC-08 검사)에서 Arbiter가 `test_wrong`으로 판정해 기댓값 변경 E1, E2가 대기에 올랐습니다.
     - 원인 확인: 하니스는 속성 검사 sample에서 domains로 유도한 클럭/리셋 포트를 뺍니다 (`pipeline/tb/gen.py:80`). Verifier 테스트의 `s.get("rst")`가 늘 `None`이라 리셋 중 `stat_frames=0`(CRC-E01대로)을 오류로 봤습니다.
     - 사용자가 E1, E2를 승인했고 게이트웨이에 sjlee로 기록했습니다 (20:00:25, 승인 기록 2, 3). 실행이 재개됐습니다.
     - 재개 뒤 20:15에 E3, E4로 다시 멈췄습니다. 고친 검사기가 리셋 첫 사이클(cycle 11)에 바로 `stat_frames=0`을 요구했는데, SPEC 2절은 동기 리셋이라 RTL은 다음 에지(cycle 12)에 0이 됐습니다. 두 후보 모두 Arbiter `test_wrong`. 사용자가 승인했고 sjlee로 기록했습니다 (20:50:58, 승인 기록 4, 5).
     - 회고 후보: CRC-E01 "rst=1인 동안 ... stat_frames=0"은 동기 리셋이면 첫 사이클에 지킬 수 없는 표현입니다. "rst=1을 본 다음 클럭부터"로 SPEC 문구를 다듬을 거리입니다.
     - 20:59 실행 통과. 선택 c1(`axis_crc_core`, `crc16_ccitt` 모두). Agent 실행 20회, 후보 4개 모두 통과(c0 Repair 3회, c1 1회), 통합 E1 깨끗, E2 Verifier 2개 통과. 검토 항목 14개(가정 8, 기댓값 변경 4, 열린 질문 1, 모델 계열 1).
  4. Sanity: design.sanity가 `deptctl export`와 `eda lint`를 돌려 ERROR 0, WARNING 0을 Design-lead용 리포트로 남겼습니다. 같은 lint를 직접 돌려 확인했습니다.
     - Seat 9개(lead.chip, design.lead, design.arch, design.sanity, pi.*의 5개)가 아직 확인 모드로 떠 있어 Sanity가 첫 명령에서 멈췄습니다. 모두 `--dangerously-skip-permissions`로 새로 띄웠습니다 (이제 15개 모두).
  5. 최종 승인: 사용자가 승인했고 sjlee로 기록했습니다 (22:29:40, 승인 기록 6).
  6. DV/PI 판정 시작: dv.tb에 독립 TB 실행, pi.synth/lec/sta/sdc에 `eda` 검사를 지시했습니다.
     - DV: 처음 6개 중 5개 실패. 원인은 TB 결함이었습니다 (모니터와 드라이버가 상승 에지 뒤 ReadOnly에서 읽어, 조합 통과 RTL에서 다음 바이트를 봄. test_01은 `m_axis_tready`를 주지 않고 `s_axis_tready=1`을 기대). TB는 DV Pod 산출물이라 dv.tb가 고쳤고(에지 직전 FallingEdge+ReadOnly 샘플링) 6/6 통과. 운영이 따로 다시 돌려 6/6과 참조 모델의 SPEC 시나리오 값(29B1, E1F0, 043B)을 확인했습니다.
     - 합성: 셀 163, 경고 0. STA: slack 4.075ns (일반 셀 라이브러리, 레지스터 사이 경로만). SDC: ERROR 0, 입출력 지연 없음 WARNING 12 (골격이라 예상됨).
     - LEC: 33개 "등가 아님"으로 나왔으나 실제로는 "이름 대조로 증명 못함"이었습니다. 합성의 `fsm_recode`가 상태 인코딩을 바꿔 equiv_make의 이름 대조가 안 됩니다. 귀납(`sat -tempinduct`)은 도달 불가 상태 때문에 실패하고, RTL 쪽에 `fsm`을 맞춰 적용해도 18개가 남았습니다. 리셋부터 15사이클 miter BMC는 증명됨(약 95초), 40사이클은 15분 안에 끝나지 않았습니다.
     - `eda lec` 수정: 남은 점을 WARNING "이름 대조로 증명 못함"으로 내고, 리셋부터 `--bmc`(기본 15) 사이클 순차 등가 검사를 덧붙입니다 (`--reset` 포트, `lec_bmc.log`). pi.lec가 고친 도구로 다시 돌려 증명됨.
     - 회고 후보: 대체 LEC는 무한 증명을 못 합니다. 사내 Formality/Conformal로 바꾸거나, 합성에서 FSM 재인코딩을 끄는 선택지를 PI가 정해야 합니다.
     - RTL은 입력→출력 조합 통과 경로(`s_axis_tdata`→`m_axis_tdata` 등)가 있고 현재 STA는 이 경로를 보지 않습니다. PI-lead 판단에 넘겼습니다.
  7. DV/PI 판정: DV-lead pass (22:55:45, 공백: SVA 미실행, 16비트 카운터 롤오버 미검증). PI-lead fail: 조합 통과 경로 3개 때문에 SoC 통합 시 200MHz 타이밍과 ready/valid 조합 루프 위험. 환류는 `spec_change`(source `sta`): CRC-T01을 N+3클럭으로, 9절에 출력 레지스터/스키드 버퍼 의무와 조합 통과 금지 추가.
     - Seat는 다른 worktree를 못 읽으므로 운영이 PI-lead 요청서를 Design-lead의 `inbox/`로 옮겼습니다. Design-lead가 고정판을 바탕으로 개정해(CRC-E01도 "rst=1을 본 다음 클럭부터"로) `deptctl feedback`으로 F0001을 제출했습니다. SPEC 변경 승인 대기입니다.
     - **파서 버그 발견:** 요구사항 ID 정규식이 `CRC-T01`, `CRC-E01`처럼 숫자 앞에 문자가 붙은 ID를 못 읽었습니다. golden SPEC의 `ADP-T01`, `AFIFO-E01` 등도 P1부터 요구사항으로 다뤄지지 않았습니다. F0001의 `spec_diff`가 비어 있어 드러났습니다. `REQ_ID`를 `...-[A-Z]?\d+`로 고쳤습니다.
     - 전체 테스트 227 통과, 3 건너뜀. 파이프라인 API 서버를 같은 명령으로 다시 띄워 고친 코드를 반영했습니다.
     - 사용자가 F0001을 승인했고 sjlee로 기록했습니다 (23:53:21, 승인 기록 7). 결정 때 다시 계산한 영향: 바뀐 요구사항 CRC-E01, CRC-T01, `constraints_changed` → 처음부터 다시 실행 `axis_crc_append-20261012-235321-b60e` (`spec_change_full`, 부모는 첫 실행).
     - 개정 SPEC을 DV Seat들의 `inbox/`에 넣고 dv.tb에 TB 갱신을 지시했습니다.
     - **SPEC 변경 경로 보완:** 9절(구현 제약)이 바뀌면 `constraints_changed`로 처음부터 다시 실행합니다 (구조 제약은 테스트로 드러나지 않아 실패 모듈만 고치는 경로로는 반영 안 됨). 영향은 결정할 때 다시 계산합니다 (요청 뒤 해석이 바뀐 F0001에도 적용되도록).
     - 회고 후보: 검토 항목의 기댓값 변경 문구가 결정 뒤에도 "(사람 승인 대기)"로 남습니다. 결정 결과로 바꿔 보여야 합니다.
     - 회고 후보: `add_property` 문서는 "sample은 L1 포트 값"이라고만 해서 Verifier가 리셋 포트가 있다고 가정했습니다. sample에 리셋 포트를 넣거나 문서와 Verifier 지침에 명시하는 조정이 필요합니다.
  8. **F0001 재실행 실패와 하니스 수정** (2026-10-13 00:53~01:02)
     - `axis_crc_append-20261012-235321-b60e`가 `failed`로 끝났습니다 (에이전트 8회). 두 후보 모두 Repair가 `interface_change`로 멈췄습니다. 원인은 RTL이 아니라 같은 리셋 표본 결함의 세 번째 발생입니다. v0 체커는 `sample.get("rst", 0)`이라 테스트 중간 리셋을 모르고 리셋 뒤 `stat_frames`=1을 기대했습니다(test_reset_recovery). v1 체커는 `s["rst"]`라 모든 테스트가 KeyError로 실패했습니다. Repair는 테스트 결함을 L1 변경 요청으로 올려 Arbiter로 가지 않았습니다.
     - **하니스 수정 (회고 후보를 앞당겨 반영):** 속성 표본에 그 도메인의 리셋 포트를 넣습니다 (`pipeline/tb/lib.py`, 클럭은 제외). `add_property` 문서와 `tb_guide.md`에 표본 내용과 동기 리셋 시점(리셋 1인 표본의 출력은 아직 리셋 전 값, 다음 표본부터 리셋 값)을 적었습니다. 하니스 시험 TB에 `reset_in_sample` 속성을 더했습니다.
     - 확인: 실패한 실행의 v0, v1 TB를 고친 하니스로 c1_r1 RTL에 다시 돌려 둘 다 통과(5/5, 5/5). 전체 테스트 227 통과, 3 건너뜀. 하니스 시험 7 통과.
     - 같은 승인 SPEC(sha 4bc9a419d8799b28)으로 처음부터 다시 실행 `axis_crc_append-20261013-010208-674c` (`spec_change_full`, 부모는 첫 실행, 제출자 operator). F0001 승인 범위의 재실행이고 새 사람 결정은 없습니다. 같은 Block Top의 환류 재실행은 2회째입니다 (상한 3).
     - dv.tb의 F0001 TB 갱신 확인: CRC-T01(`elapsed_clocks <= N+3`), CRC-E01(다음 클럭부터) 반영, 기존 RTL에서 6/6 통과.
     - 회고 후보: Repair가 Verifier 체커 결함을 `interface_change`로 분류하면 Arbiter를 거치지 않고 실패로 끝납니다. Repair 사유가 테스트 쪽을 가리키면 Arbiter로 보내는 경로가 필요합니다.
  9. **F0001 재실행 통과와 Sanity** (2026-10-13 01:34~)
     - `axis_crc_append-20261013-010208-674c` 통과 (01:34, 에이전트 5회, 약 32분). `axis_crc_core` 두 후보 모두 Repair 없이 통과, 두 Verifier 통과, 후보 간 차분 시뮬레이션 차이 없음. 선택 c0. 기댓값 변경 요청 없음. 하니스 수정 뒤 첫 실행 비용이 첫 실행(20회, 약 3시간)보다 크게 줄었습니다.
     - RTL 확인: `s_axis_tready`, `m_axis_tdata/tvalid/tlast`가 모두 레지스터 출력입니다 (출력 레지스터 + skid). 조합 통과 구조가 없어졌습니다. 정식 확인은 PI에서 합니다.
     - 검토 항목(가정 제외): CRC-E03 미정의(리셋 시 프레임 도중 바이트 처리), Q-01 CRC 바이트 순서 파라미터화, REQ_MULTI(CRC-E01 문장 둘).
     - design.sanity: `deptctl export`로 받은 RTL이 실행 RTL과 같음을 확인했습니다. `eda lint` ERROR 0, WARNING 0 (`sanity/lint2/`), 리포트에 "F0001 재실행 (674c)" 절이 추가됐습니다.
     - 사용자가 최종 승인했고 sjlee로 기록했습니다 (01:36:16, 승인 기록 8). 검토 항목 셋은 회고와 다음 SPEC 개정으로 넘깁니다.
     - DV: dv.tb가 F0001 TB로 새 RTL에서 6/6 통과 (운영이 복사본으로 다시 돌려 6/6 확인). dv.lead가 DV pass (01:39:57).
     - PI (Seat마다 직접 export): synth 233셀 경고 없음 (첫 실행 163셀, skid 버퍼 추가분), LEC 이름 대조 못한 84점은 WARNING이고 리셋에서 15사이클 출력 등가 증명, STA slack 4.030ns, SDC 입출력 지연 경고 12건(사람이 쓰는 제약).
     - 조합 통과 경로 확인: STA 대체는 레지스터 사이 경로만 보므로 운영이 yosys로 입력→출력 조합 경로를 찾았습니다(`select o:* %ci*:-<FF> i:* %i`). 첫 실행 RTL에서는 `m_axis_tready`, `s_axis_tvalid`, `s_axis_tdata`가 나와 검사가 유효함을 확인했고, 새 RTL에서는 없습니다. pi.lead에 증거로 넘겼고 pi.lead가 PI pass (01:41:43).
     - 회고 후보: 조합 통과 경로 검사를 `eda sta`(또는 별도 `eda` 검사)에 넣어 PI Seat가 직접 보게 합니다. 이번 첫 실행의 fail은 pi.lead가 RTL을 읽고 찾은 것입니다.
     - RTL Freeze 승인 대기: 새 실행은 `ready: true`. 첫 실행(0a82)의 RTL Freeze 항목은 PI fail로 `ready: false`인 채 남아 있습니다.
  10. **RTL Freeze** (2026-10-13 01:42): 사용자가 674c의 RTL Freeze를 승인했고 sjlee로 기록했습니다 (승인 기록 9). 첫 실행 0a82의 RTL Freeze 항목은 "F0001로 대체됨"으로 반려했습니다 (승인 기록 10, 사용자 결정).

#### P8 완료 기준 점검

- **RTL Freeze 도달:** `axis_crc_append-20261013-010208-674c` (SPEC sha 4bc9a419d8799b28).
- **환류 4형태 분류와 기록:** 부서 환류는 F0001 하나이고 `spec_change`(source `sta`, seat-design-lead)로 기록됐습니다. 결정 기록은 F0001-D(sjlee)입니다. `check_report`, `generator_bug`, `config_change`로 들어온 것은 없습니다. 운영이 직접 고친 툴 결함 다섯(하니스 리셋 표본, `eda lec`, 요구사항 ID 정규식, `spec_diff` 9절, 9절 변경 경로)은 부서 환류가 아니라 이 기록에만 있습니다. 부서에서 들어왔다면 `generator_bug`로 분류할 것들입니다.
  - 기록 공백: F0001-D의 `new_run`은 하니스 결함으로 실패한 b60e를 가리킵니다. 다시 돌린 674c는 계보(root 0a82)로만 연결됩니다.
- **회고의 조정안:** 아래.

#### P8 회고: 조정안

실측: 에이전트 실행이 첫 실행 20회(약 3시간), b60e 8회(하니스 결함으로 버림), 674c 5회(약 32분)로 계보 합계 33회였습니다. 사람 결정은 SPEC 고정 1, 기댓값 변경 4, 최종 승인 2, SPEC 변경 1, RTL Freeze 2였습니다. 기댓값 변경 4건과 b60e 실패는 모두 같은 원인(속성 표본에 리셋 없음)이었고, 하니스를 고친 뒤 첫 실행은 Repair와 사람 결정 없이 통과했습니다.

- **검토 항목 조건**
  1. Repair가 `interface_change`를 내도 사유가 테스트나 체커를 가리키면 Arbiter로 보냅니다. 지금은 Arbiter 없이 실패로 끝납니다 (b60e). **완료 (2026-10-13):** 실패한 Verifier마다 Arbiter가 먼저 판정.
  2. 같은 테스트와 속성이 두 후보에서 같은 이유로 실패하면 한 항목으로 묶습니다 (E1/E2, E3/E4는 같은 결정을 두 번 받음).
  3. 기댓값 변경 항목은 결정 뒤 결정 결과(승인자, 시각)로 바꿔 보입니다. 지금은 "(사람 승인 대기)"로 남습니다.
  4. ASSUMPTION(실행마다 7~8개)은 L1, 타이밍, 리셋을 건드리는 것만 검토 항목으로 올리고 나머지는 Architect 기록으로 둡니다. MODEL_FAMILY는 역할 설정이 바뀔 때만 올립니다.
  5. SPEC 변경 요청에도 SPEC 툴 검사를 돌려 승인 항목에 붙입니다. F0001이 새로 만든 REQ_MULTI(CRC-E01 문장 둘)는 승인 뒤 실행에서야 드러났습니다.
  6. 9절에 레지스터 출력 같은 구조 제약이 있으면 입력→출력 조합 경로 검사를 E1 단계에 넣어 위반을 검토 항목으로 냅니다. PI의 `eda`에도 같은 검사를 더합니다 (이번 fail은 pi.lead가 RTL을 읽어 찾았음).
- **반복 상한**
  1. `repair_per_candidate` 5 → 3. 이번 Repair 4회(c0 3, c1 1)는 모두 테스트 쪽 결함 때문이었습니다. 같은 테스트가 Repair 두 번 연속 실패하면 상한 전에 Arbiter를 부릅니다. **일부 완료 (2026-10-14):** 같은 테스트가 Repair 두 번 뒤에도 같은 이유로 실패하면 실패한 Verifier마다 Arbiter가 판정 (`limits.arbiter_after_repeats` 2). 상한 5 → 3은 하지 않음.
  2. 환류 재실행 상한 `RERUN_LIMIT` 3은 그대로 둡니다 (2회 사용). 다만 툴 결함으로 버린 실행은 사유와 함께 따로 기록하고, 상한 계산에서 빼는 것을 사람이 정할 수 있게 합니다.
- **예산**
  1. `budget_agent_runs` 200은 실측의 10배입니다 (한 실행 최대 20회). 실행당 60(실측 최대의 3배)으로 낮추고, 같은 Block Top 계보 합계를 따로 보여 줍니다.
  2. 시간: 하니스 수정 뒤 실행이 약 32분이었습니다. 실행 하나가 2시간을 넘으면 운영에게 알립니다.
- **P9로 넘길 것:** 대체 LEC의 무한 증명 불가(사내 Formality/Conformal 또는 FSM 재인코딩 끄기), CRC-E03 미정의와 Q-01(다음 SPEC 개정), DV 공백(SVA 미실행, 16비트 카운터 롤오버), 하니스 수정 이전 golden 블록들의 Verifier 체커 재확인.

### 2026-10-12 P7 게이트웨이와 Web UI 1차

- **게이트웨이 (`gateway/`, 표준 라이브러리와 SQLite):**
  - 자체 계정 인증(PBKDF2-SHA256, 세션 쿠키 12시간, Seat와 서비스 계정용 API 키).
  - 인증 제공자 인터페이스를 분리해 SSO로 바꿀 수 있습니다.
  - 역할 5개(관리자, 설계, 검증, 구현, 승인자)와 `design_lead` 능력(환류 제출)이 있습니다. Seat 계정은 승인자가 될 수 없습니다.
  - 쿠키로 인증한 쓰기 요청은 `X-CDD` 헤더가 있어야 합니다 (요청 위조 방지).
- **승인 다섯 가지:** SPEC 고정, 최종 승인, RTL Freeze, 기댓값 변경, SPEC 변경 요청.
  - 승인자 역할의 사람만 결정하고, 결정마다 누가, 언제, 역할, SPEC 버전, 실행 ID, 요구사항 ID, 메모를 기록합니다. 감사 기록에도 남습니다.
  - RTL Freeze는 DV 검증 완료 판정(검증 역할)과 PI 구현 가능성 판정(구현 역할)이 모두 pass여야 승인할 수 있습니다.
  - 실행 제출은 고정된 SPEC 판으로만 합니다.
- **파이프라인 API:** 게이트웨이 토큰(`X-Gateway-Token`)이 있는 쓰기 요청만 받습니다 (`--token-file`, `CHIPDEPT_API_TOKEN`). 조회는 토큰 없이 됩니다.
- **OpenRig 데몬 API:** `/healthz`, `/api/ps`, `/api/rigs/:id/nodes`로 Seat 상태를 조회합니다. 대화 중계는 P9에서 합니다.
- **Web UI 1차 (`gateway/ui/`, React, TypeScript, Vite. 외부 글꼴과 CDN 없음):**
  - 실행 목록.
  - 실행 상세 (읽기 전용): 개요와 승인/판정, 모듈 트리와 후보별 진행, 검토 항목, 실패 분류, RTL과 IR 노드 대응(소스맵), 에이전트 작업별 과제, 출력, transcript.
  - SPEC 작업대: 원본 PDF 쪽 또는 Markdown과 변환 결과 대조와 판 관리, 원본 그림과 WaveJSON 렌더링 대조, 검사 질문 답, 고정 요청, 실행 제출.
  - 승인함, 환류 양식(네 형태만), Seat 상태.
- **부서 계층 연결:**
  - infra Pod에 게이트웨이 노드를 추가했습니다.
  - `deptctl`은 Seat별 API 키로 게이트웨이를 부릅니다. 승인 명령은 없습니다.
  - Seat sandbox는 게이트웨이 저장소(토큰, 계정 DB)와 다른 Seat의 키 읽기를 거부합니다.
  - P6에서 남긴 "Seat가 직접 HTTP로 역할을 꾸밀 수 있음" 문제가 닫혔습니다. 직접 보낸 쓰기 요청은 401입니다.
- **확인:**
  - `tests/sim/test_gateway.py` 6개: 인증과 요청 위조 방지, 승인 다섯 가지에서 승인자가 아닌 역할(관리자, 설계, 검증, 구현) 모두 403, 기록 내용, SPEC 작업대(PDF, WaveJSON), 실행 상세, 환류 양식(자유 텍스트 거부, Design-lead만).
  - 파이프라인 API 토큰 시험 1개.
  - 부서 계층 rig 시험 3개를 게이트웨이 구성으로 다시 통과했습니다 (직접 쓰기 401, 토큰과 다른 Seat 키 읽기 거부 포함).
  - 전체 테스트 226개가 통과했습니다.
  - Web UI는 실제 E2E 결과 세 블록과 데모 계정으로 띄워 헤드리스 Chrome으로 화면을 확인했습니다.
  - 확인하면서 고친 것: RTL 화면에서 동결된 L1 줄(파라미터)을 "Repair 대상"으로 잘못 표시하던 것, 머리글의 이름과 역할이 겹쳐 나오던 것.
- **완료 기준:** 승인자 역할만 승인할 수 있고, 모든 승인이 기록에 남습니다. 시험으로 확인했습니다.

### 2026-10-12 P6 부서 계층 (OpenRig)

사용자 결정: OpenRig를 다시 설치해 완료 기준까지 시험합니다.

- **설치:**
  - OpenRig 0.6.6을 `~/.cache/chip-design-department/openrig`에 설치했습니다.
  - HOME, OPENRIG_HOME, tmux 소켓(`/tmp/cdrt`), 포트(7533)를 따로 둬서 사용자 설정을 건드리지 않습니다 (P0 X5와 같은 방식).
- **`department/`:**
  - `rig.yaml`: Pod 4개, Seat 15개, infra Pod의 파이프라인 API 서버, edge(위임, 보고), Pod 연속성 정책. `rig spec validate`를 통과합니다.
  - `seats.json`(명단, API 역할, DV 표시), `CULTURE.md`, `guidance/`(공통 규칙과 역할별 지침 15개).
  - `bin/seat`: Seat 진입점.
    - Seat별 Git worktree(저장소 밖)를 만들고, 지침을 `AGENTS.md`, `GEMINI.md`로 둡니다.
    - Seat별 `sandbox-exec` 프로필로 감싼 agy로 바뀝니다. 시험 때는 agy 대신 셸로 바뀝니다.
  - `bin/deptctl`: Seat의 API 클라이언트. 역할에 없는 쓰기 명령을 숨깁니다 (환류는 Design-lead만).
  - `bin/pipeline-server`: infra Pod의 API 서버.
  - `dept.py`: 올리기, 내리기, Seat 초기화, 스냅숏과 복구, Seat에 명령 보내기.
- **Seat 런타임:**
  - OpenRig는 agy를 직접 지원하지 않으므로 `terminal` 노드의 시작 동작(`send_text`)으로 Seat 진입점을 실행합니다 (P0 X3의 대안).
  - 권한은 OpenRig의 edge가 아니라 sandbox로 강제합니다.
- **sandbox 프로필:**
  - 모든 Seat: 파이프라인 저장소와 RUNS 쓰기 거부. 저장소 원본과 다른 Seat의 worktree 쓰기 거부(`.git`만 허용).
  - DV Seat: RUNS와 STORE 읽기 거부.
- **완료 기준 시험** (`CHIPDEPT_RIG_TEST=1`, Seat는 셸 모드, 파이프라인은 가짜 agent):
  - 권한 위반 시도가 실패합니다.
    - DV TB Seat가 실제 실행의 Verifier 테스트를 `cat`하면 `operation not permitted`가 납니다.
    - RTL Engineer, Design-lead, Chip-lead가 실행 상태 파일에 쓰려 하면 거부됩니다.
    - 저장소 원본 쓰기도 거부됩니다. 자기 worktree에서 커밋은 됩니다.
    - RTL Engineer의 `deptctl feedback`은 거부됩니다.
  - Seat 세션 초기화가 실행에 영향을 주지 않습니다. 실행 중에 RTL Engineer, Chip-lead Seat와 API 서버 노드를 새 세션으로 띄워도 실행이 `pass`로 끝납니다.
  - 복구: 스냅숏을 남기고 내린 뒤 복구하면, Seat에 sandbox가 다시 걸리고 실행 기록이 남아 있습니다.
- **시험에서 찾아 고친 것:**
  - 스케줄러 프로세스가 API 서버 터미널의 표준 입력을 물려받았습니다. 그래서 서버 노드를 초기화하면 그 뒤 시뮬레이터 빌드가 죽었습니다 (`Bad file descriptor`). 표준 입력을 `/dev/null`로 바꿨습니다.
  - cocotb는 빌드 환경의 PYTHONPATH를 이 프로세스의 `sys.path`(3.11)로 둡니다. PATH에서 `python3`가 다른 버전(시스템 3.9)이면 Verilator 빌드가 죽었습니다. `sim()`이 이 인터프리터의 `python3`를 PATH 맨 앞에 둡니다.
  - 데몬과 Seat에 호출한 프로세스의 파이썬 환경(PYTHONHOME 등)을 넘기지 않습니다.
- **스냅숏 복구의 제약:** Seat를 새로 띄운(`--fresh`) 뒤에는 OpenRig가 스냅숏의 점유자가 옛것이라며 복구를 거부합니다. 그래서 `recover`는 그때 `rig.yaml`로 새로 띄웁니다. Seat 상태는 worktree와 저장소에 있으므로 결과는 같습니다.
- **agy Seat 확인:**
  - agent 모드로 Seat 하나를 띄워 보니 sandbox 안에서 agy가 시작됐습니다.
  - agy가 Seat 폴더마다 처음 한 번 폴더 신뢰 확인을 받았습니다.
  - 사용자 결정에 따라 Seat 진입점이 agent 모드로 시작할 때 자기 worktree를 agy CLI 설정의 `trustedWorkspaces`에 넣게 했습니다. 다른 설정은 그대로 두고, 중복 없이 넣고, 깨진 설정은 건드리지 않습니다.
  - 다시 확인: 확인 없이 agy가 시작되어 `AGENTS.md`를 읽고 역할(TB)과 공통 규칙을 요약했습니다.
  - 시험용 항목은 지웠고, 사용자 agy 설정이 시험 전과 같음을 확인했습니다.
- **시험:** `tests/test_department.py` 7개 (기본 4개, rig 3개). rig 시험 3개는 기본 실행에서 건너뜁니다.

### 2026-10-12 P5 파이프라인 API와 환류 입력

사용자 결정: 외부 리포트는 나중에 양식 파일만 고쳐 반영할 수 있게 하고, 지금은 가능한 범위만 구현합니다.

- **리포트 양식 파일:** `config/report_formats/<이름>.json` + `pipeline/feedback/reports.py`.
  - 정규식의 이름 있는 그룹(severity, rule, file, line, message)으로 줄을 `Finding`으로 바꿉니다.
  - 기본값, 여러 줄 메시지(continuation), 무시할 줄(ignore), 심각도 대응(severity_map)을 지원합니다.
  - 양식 파일 검사가 있고, 사용법은 `config/report_formats/README.md`에 적었습니다.
  - 지금 있는 양식: `verilator`(파이프라인 E1 파서와 같은 결과), `iverilog`(실제 출력으로 시험).
- **환류 스키마:** `schema/feedback.schema.json`. 네 형태(검사 실패 리포트, SPEC 변경 요청, 생성기 버그 리포트, 설정 변경)만 받고 그 밖의 필드는 거부합니다.
- **저장소와 API:** `pipeline/api/store.py`, `server.py`(표준 라이브러리 HTTP), `__main__.py`(CLI).
  - 실행 제출: SPEC 원문과 설정 → 실행 ID. 스케줄러를 별도 프로세스로 돌립니다.
  - 조회: 상태, 모듈, 검토 항목, 보고서, 승인 대기, 최종 RTL(통과한 실행만, 읽기 전용), 이력.
  - 기댓값 수정 결정과 이어서 실행.
  - 역할은 `X-Role` 헤더로 밝힙니다: 제출은 rtl-engineer/chip-lead, 환류는 design-lead, SPEC 변경 승인은 chip-lead/rtl-engineer.
- **검사 실패 리포트 처리:**
  - 양식으로 파싱하고, 실행의 소스맵(`rtl/*.srcmap.json`, 통합 때 저장)으로 분류합니다.
  - 조각 내부(Repair 대상)는 재실행 `external_repair`로 넘깁니다. 이 재실행은 부모 실행의 선택 IR을 들여와 해당 모듈만 Repair한 뒤 전체 검증을 다시 합니다. 끝나면 `EXTERNAL_RECHECK` 검토 항목을 남깁니다.
  - 골격은 `generator_bugs.jsonl`에, 인터페이스 변경은 알림으로 보냅니다.
- **SPEC 변경 요청:**
  - 제출하면 `spec_diff`로 바뀐 요구사항, 시나리오, L1 변경 여부를 계산해 승인 대기로 둡니다.
  - 승인되면 두 갈래로 나뉩니다.
    - L1이 같으면 재실행 `spec_change`: Verifier가 테스트만 새 SPEC에 맞추고(고칠 것이 없으면 `no_change`), 선택된 RTL을 다시 검증해 실패한 모듈만 고칩니다.
    - L1이 바뀌면 처음부터 다시 실행합니다.
- **생성기 버그와 설정 변경:** 생성기 버그는 기록만 하고 LLM으로 보내지 않습니다. 설정 변경은 `config.json`에 남겨 다음 제출부터 반영합니다.
- **교착 방지:**
  - 같은 Block Top(같은 계보)의 환류 재실행이 3회에 이르면 거부하고 알립니다.
  - 24시간 동안 상태 파일 갱신이 없으면 멈추고(`halted`) 알립니다. 서버는 1시간마다 점검하고, `watchdog` 명령으로도 점검할 수 있습니다.
- **이력:** 모든 환류와 결정을 `feedback.jsonl`에 남깁니다. 실행 ID, 요구사항 ID, 제출자, 결과, 새 실행 ID가 들어갑니다.
- **완료 기준 확인 (가짜 agent 시험):** verilator 양식 리포트 한 건에서 조각 내부 줄은 `lint_fragment`로 Repair 재실행되고, 골격 줄은 `lint_skeleton`으로 생성기 버그가 됩니다.
- **시험:** `tests/test_feedback.py` 6개, `tests/sim/test_api.py` 4개(제출과 조회, 검사 리포트 재실행, SPEC 변경 재실행과 재실행 상한, 생성기 버그, 설정 변경, watchdog, HTTP). 전체 테스트 215개가 통과했습니다.

### 2026-10-12 P4 마감

- 사용자 결정: P4를 현재 결과(E2E 3/3, 블록마다 기댓값 수정 승인 1회 포함)로 마감합니다.
- Classifier 나머지 4종은 P4에서 구현했으므로 대기 항목에서 뺐습니다: 기댓값 오류 의심(Arbiter `test_wrong`), 자식 모듈 원인 의심(`suspect_module`), Verifier 간 불일치(`VERIFIER_DIFF`), 후보 간 불일치(`CANDIDATE_DIFF`, 차분 시뮬레이션).
- 남은 항목은 조건부 대기로 옮깁니다:
  - 동결 해제 전파
  - 두 단계 이상의 모듈 트리
  - 사용량 한도로 못 돌린 단독 평가
  - Linux 격리

### 2026-10-12 P4-9 E2E 3/3 통과 (09:49)

| 블록 | 스케줄러 | 원본 TB | 에이전트 실행(누적) | 선택 | golden과 같음 | 사람 결정 |
|---|---|---|---|---|---|---|
| `axis_adapter` | pass | 9/9 | 14 | c0 | 아님 | 기댓값 수정 승인 E1, E2 |
| `axis_cobs_decode` | pass | 16/16 | 10 | c0 | 아님 | 기댓값 수정 승인 E1, E2 |
| `axis_async_fifo` (하위 모듈 3개) | pass | 20/20 | 28 | c1 | 아님 | 기댓값 수정 승인 E1, E2 |

- `axis_async_fifo`의 마지막 흐름:
  - 차분 자극 축소 결과는 "트래픽 중 s_rst 4사이클 한 번"이었습니다.
  - Verifier 1의 보강 1차는 모두 실패해 다시 쓰게 했고, 2차가 c0만 통과시켜 채택됐습니다. 추가된 테스트는 `test_s_rst_mid_frame_backpressure`, `test_s_rst_flushes_queued_fifo`입니다.
  - Arbiter(c1)는 `rtl_wrong`(AFIFO-04, 05)으로 판정했습니다. 근거: 출력 backpressure 중 s_rst가 오면 ready를 기다리지 않고 m_axis_tvalid를 내림.
  - `_m`의 Repair 뒤 c1이 통과했습니다.
  - 이 결함은 원본 TB에서 c1이 멈춘 상황("sink pause 중 source 리셋")과 같은 종류입니다. 원본 TB를 보지 않고 SPEC과 후보 간 차분만으로 찾았습니다.
- 남은 검토 항목:
  - c0과 c1은 reset seed 3에서 여전히 출력이 다릅니다. 보강 상한(2회)에 이르러 `CANDIDATE_DIFF`로 남겼습니다.
  - 원본 TB는 둘 다 통과합니다 (c0은 앞서 20/20 확인).
- P4 완료 기준 대비:
  - "SPEC부터 끝까지, 결과 RTL이 기존 TB 통과": 3/3입니다.
    - 단, 블록마다 기댓값 수정 승인(사람 결정)이 한 번씩 있었습니다.
    - 설계상 승인은 사람 게이트이므로 "사람 개입 없이"를 엄격히 읽으면 조건부 충족입니다. 판단은 사용자에게 맡깁니다.
  - 재개: 사용량 한도 멈춤, 승인 대기, 상태 되돌림 뒤에 같은 명령으로 이어서 실행했습니다 (시험과 실제 실행 모두).
  - 격리: Verifier 입력에 L2, L3, RTL이 없습니다 (시험). Author 후보는 저장소 밖 작업 디렉터리에서 sandbox로 격리됩니다. 모든 결과가 golden과 다릅니다.

### 2026-10-12 P4 차분 자극 축소 (사용자 결정: 추천안)

- 자극 계획을 cocotb 밖에서 만들어 넘깁니다 (`make_plan`).
  - 계획을 사건 단위로 나눕니다(`episodes`): 리셋 펄스, 출력 ready=0 구간, 단독 입력=1 구간.
  - 사건 지우기(`without`)와 뒤 자르기(`truncate`)를 지원합니다.
- `minimize_diff`(시뮬레이션만, 에이전트 없음):
  - 차이 지점 뒤 50/200/800사이클에서 잘라 봅니다.
  - 사건 집합을 delta debugging으로 줄여, 차이를 유지하는 가장 작은 자극을 찾습니다 (최대 150회 실행).
  - 후보마다 빌드는 한 번만 하고, 자극만 바꿔 다시 돌립니다 (`sim(rebuild=False)`).
- Verifier 입력:
  - 무작위 사건 목록 대신 `scenario`를 줍니다: 배경 트래픽 설명과 시간순 사건 몇 줄.
  - 예: "s 도메인 사이클 317\~320 (4사이클): s_rst=1 (리셋)"
- 확인: 기존 `axis_async_fifo` c0, c1의 reset seed 3 차이를 8회 실행(6초)으로 **트래픽 중 s_rst 4사이클 한 번**까지 줄였습니다.
  - 프레임 도중(직전 출력 tlast=0)이었습니다.
  - c0은 리셋 뒤 정상 비트를 냈고, c1은 tlast=1, tuser=1 비트를 냈습니다 (AFIFO-05 관련).
  - 어느 쪽이 맞는지는 Verifier가 SPEC으로 판단합니다.
- 시험: 기존 차분 시험에 축소 결과 검사를 더했습니다. 데이터 오류는 사건 0개로 줄어듭니다. 전체 테스트 205개가 통과했습니다.
- `axis_async_fifo` E2E를 다시 이어서 실행 중입니다 (보강 라운드 1, Verifier 1).

### 2026-10-12 P4-9 `axis_async_fifo` 게이트 적용 후 재실행 결과 (09:0x)

- 보강 시도 0(되돌리기 전의 diff0 결과): 통과 묶음 0/2. 모두 실패했으므로 테스트 결함을 의심해 다시 쓰게 했습니다.
- 보강 시도 1: 통과 묶음 2/2. 상황을 재현하지 못했으므로 채택하지 않았습니다 (`CANDIDATE_DIFF` 검토 항목).
- 선택 규칙에 따라 c1이 선택됐고, 원본 TB `run_test_init_sink_pause_source_reset_001`에서 900초 시간 초과로 실패했습니다.
- 원인:
  - Verifier가 받는 차이 리포트는 수백 사이클의 무작위 사건 목록이라, 차이를 일으키는 최소 상황이 드러나지 않습니다.
  - 또 이번에 잡힌 차이(m_rst 직후)는 원본 TB가 c1을 멈추게 하는 상황(sink pause 중 s_rst)과 다릅니다.
- P4 E2E 현황: 2/3 (`axis_adapter`, `axis_cobs_decode` 통과). 다음 방향은 사용자 결정 대기입니다 (자극 축소, 보강 횟수 증가, 현 상태 기록).

### 2026-10-12 P4 차분 재실행과 보강 테스트 게이트 (08:18\~)

- 차분 시뮬레이션을 넣고 세 블록을 다시 이어서 실행했습니다.
  - `axis_adapter`, `axis_cobs_decode`: 두 묶음 사이에 차이가 없었고, 원본 TB도 그대로 통과했습니다 (9/9, 16/16).
  - `axis_async_fifo`: reset 모드 seed 3에서 차이를 찾았습니다(m_rst 직후 출력). Verifier 0이 `test_m_rst_mid_frame_drop_and_recover`를 더했습니다.
- 그런데 보강된 테스트 자체에 결함이 있었습니다.
  - 리셋 때 스코어보드 기댓값을 통째로 지워서, 이미 정상 출력된 비트의 기댓값까지 사라졌습니다.
  - 그래서 두 묶음 모두 실패했고, Arbiter는 둘 다 `test_wrong`(AFIFO-01, 06)으로 판정했습니다. 판정은 타당합니다.
- 고친 것: 보강 테스트 게이트
  - 보강된 테스트를 통과했던 묶음마다 돌려 보고, 일부만 통과해야(후보를 갈라야) 채택합니다.
  - 모두 실패하거나 모두 통과하면, 각 후보의 실패 내용을 `previous_attempt`로 Verifier에게 돌려 다시 쓰게 합니다 (`limits.augment_attempts`, 기본 2).
  - 끝까지 모두 실패하면 채택합니다. 후보가 모두 틀렸을 수 있으므로 Arbiter와 사람이 판단합니다.
  - 끝까지 모두 통과하면 채택하지 않고 `CANDIDATE_DIFF` 검토 항목으로 남깁니다.
- `axis_async_fifo` 실행 상태 되돌림:
  - 게이트 없이 채택된 보강(diff0)과 그 때문에 생긴 승인 대기 E3, E4는 사람이 결정할 대상이 아니므로 상태를 보강 직전으로 되돌렸습니다.
  - 이전 상태는 `build/e2e/axis_async_fifo.bak_before_rewind`에 보관했습니다.
  - 받은 보강 결과는 새 게이트의 첫 시도로 다시 씁니다.
- 시험: 보강이 후보를 가르지 못하는 경우를 추가했습니다. 전체 테스트 205개가 통과했습니다.

### 2026-10-12 P4 후보 간 차분 시뮬레이션 (사용자 결정)

Verifier 테스트가 놓친 경우 때문에 잘못된 후보가 선택되는 문제를 다룹니다.

- `pipeline/tb/diffsim.py`: 통과한 묶음마다 같은 무작위 자극을 넣고 출력 번들 트랜잭션 순서를 비교합니다.
  - 자극은 DUT 응답과 무관하게 시드로 미리 정합니다. 입력 트랜잭션 순서, 사이클별 valid 의도, 출력 ready(burst), 리셋, 단독 입력(pause 등)이 해당합니다. 그래서 지연이 달라도 SPEC을 지키는 후보끼리는 같은 출력 순서가 나옵니다.
  - 모드 `steady`(seed 1, 2): 처음 리셋 뒤에는 리셋을 넣지 않습니다.
  - 모드 `reset`(seed 3, 4): 중간에 무작위 리셋을 넣고, 마지막에 프로브 300사이클과 drain을 둡니다.
  - 리셋 때 흘러가던 데이터의 처리도 SPEC이 정할 수 있으므로(예: AFIFO-05) 출력 전체를 비교합니다.
  - 입력은 Verifier 모델의 `legal()`로 거릅니다 (SPEC 밖 입력에서 생기는 차이를 피함).
- 스케줄러 처리 (`diff_and_augment`):
  - 통과한 묶음이 둘 이상이면 차분 시뮬레이션을 돌립니다.
  - 차이가 나면 Verifier(돌아가며)가 차이 리포트를 받습니다. 리포트에는 모드, 첫 차이, 직전 자극 사건, A/B 출력이 들어 있고, 어느 쪽이 맞는지는 알려주지 않습니다.
  - Verifier는 SPEC으로 판단해 그 상황의 directed 테스트를 더합니다. SPEC이 정하지 않은 동작이면 `CANDIDATE_DIFF_UNDEFINED` 검토 항목으로 남깁니다.
  - 테스트를 보강하면 통과했던 묶음을 모두 다시 검증합니다. 보강은 `limits.candidate_diff_rounds`(기본 2)회까지입니다.
- 확인한 것:
  - `axis_async_fifo` c0, c1에서 steady는 같았고, reset 모드에서는 리셋 직후 출력이 달랐습니다.
  - 처음 비교 방식(프로브 뒤 꼬리만 비교)에서는 drain이 부족해 잘못된 경보가 났습니다. 그래서 프로브 구간을 유한하게 하고 출력 전체를 비교하도록 고쳤습니다.
- 시험: 약한 테스트를 둘 다 통과하는 두 후보(정상, adapter_shift 버그)를 넣었습니다.
  - 차분이 steady에서 데이터 차이를 찾고, Verifier가 보강하고, 버그 후보가 떨어지고, 정상 후보가 선택됩니다.
  - 전체 테스트 204개가 통과했습니다.

### 2026-10-12 P4-9 승인 후 재개 결과 (07:32)

세 블록의 E1, E2를 사용자가 승인했고(`--by "Seungjoon Lee"`), 같은 명령으로 이어서 실행했습니다.

| 블록 | 스케줄러 | 원본 TB | 승인 후 시간 | 선택 | golden과 같음 |
|---|---|---|---|---|---|
| `axis_adapter` | pass | 9/9 | 17.8분 | c0 | 아님 |
| `axis_cobs_decode` | pass | 16/16 | 2.6분 | c0 | 아님 |
| `axis_async_fifo` | pass | **멈춤** (`run_test_init_sink_pause_source_reset_001`, 900초 초과) | 15.8분 | c1 | 아님 |

- `axis_adapter`:
  - Verifier 0이 테스트를 고친 뒤 두 후보 모두 sim은 통과했습니다.
  - 남은 lint 조각 오류를 Repair가 한 번씩 더 고쳤습니다 (파라미터를 동작에 반영).
- `axis_cobs_decode`: Verifier 0이 테스트를 고친 뒤 바로 통과했습니다.
- `axis_async_fifo`:
  - Verifier 1이 테스트를 고친 뒤, c0에서 Arbiter가 `rtl_wrong`으로 판정해 `_s`의 Repair가 한 번 더 들어갔고, 두 묶음 모두 통과했습니다.
  - 묶음 선택에서 모듈 합계 Repair 수가 적은 c1이 골라졌습니다 (c0: 3, c1: 2).
  - c1은 원본 TB의 "sink pause 중 source 리셋"에서 멈춥니다. 선택되지 않은 c0을 따로 판정하면 20/20 통과합니다.
  - 즉 파이프라인은 맞는 후보를 만들었지만, Verifier 테스트 두 벌이 그 경우를 검사하지 않아 고를 근거가 없었습니다.
  - 후보 간 차분 검사(Verifier 테스트에서의 출력 비교)도 차이를 찾지 못했습니다.
- 결과: P4 완료 기준은 3블록 중 2블록만 충족했습니다.
- 고친 것: 재개 뒤 보고서에 이전 실행의 `MODULE_FAILED`가 남던 결함을 고쳤습니다 (묶음 선택 때 다시 판정).

### 2026-10-12 P5 일부: 기댓값 수정 승인 흐름 (P4 E2E를 끝내려고 앞당김)

사용자 결정: 승인 흐름을 먼저 만들어 P4 E2E를 원본 테스트벤치 통과까지 끝냅니다. HTTP API는 P5 본 작업에서 이 흐름을 감쌉니다.

- 승인 대기 항목:
  - Arbiter가 `test_wrong`이면 스케줄러가 항목(`E1`, `E2`, ...)을 `state.json`의 `pending`에 등록합니다.
  - 항목에는 Verifier 번호, 후보 묶음, 근거 요구사항, 판정 이유, 수정안, 첫 불일치를 담습니다.
- 결정 CLI: `python3 -m pipeline.scheduler.approve <run_dir> list | show <id> | approve <id>... --by <이름> [--note] | reject ...`
  - 결정은 `decisions.json`에 쌓입니다. 실행 ID, 요구사항 ID, SPEC 버전(sha256), 결정한 사람, 시각을 함께 남깁니다.
  - 결정한 사람이 없거나, 같은 항목을 두 번 결정하면 거부합니다.
- 반영: 같은 명령으로 스케줄러를 다시 실행하면 반영됩니다.
  - 승인: Verifier가 수정안대로 자기 테스트를 고칩니다(`make_revise_task`).
    - 게이트는 처음과 같고, 테스트가 실제로 바뀌어야 합니다.
    - 같은 Verifier를 기다리던 다른 항목은 `superseded`로 함께 풀고, 후보를 다시 검증합니다.
    - 수정 후 Verifier 간 차분 검사를 다시 합니다. 테스트 교체 이력은 `tb_history`에 남깁니다.
  - 거절: 테스트가 맞다고 보고, 그 후보에서 그 Verifier의 실패는 Arbiter 없이 Repair로 보냅니다.
- 시험(가짜 agent): 승인 → 테스트 수정 → 통과, 거절 → Repair. 전체 테스트 203개가 통과했습니다.
- 기존 E2E 세 블록의 상태에는 이전 Arbiter 판정으로 항목을 채웠습니다(블록마다 E1, E2). 사람의 결정을 기다립니다.

### 2026-10-12 P4-9 SPEC부터 끝까지 실행 (1차 결과)

세 블록 모두 사람 승인 대기(`waiting_approval`)에서 멈췄습니다. 이번 실행에서는 아무도 승인하지 않았고, 승인 흐름은 P5에서 만듭니다.
멈춘 후보들(현재 IR)이 맞는지 보려고, 에이전트 없이 원본 테스트벤치로 따로 판정했습니다.

| 블록 | 상태 | 에이전트 실행 | 원본 TB c0 | 원본 TB c1 | golden과 같음 |
|---|---|---|---|---|---|
| `axis_adapter` | 승인 대기 | 11 | 9/9 | 9/9 | 아님 |
| `axis_cobs_decode` | 승인 대기 | 9 | 16/16 | 16/16 | 아님 |
| `axis_async_fifo` (하위 모듈 3개) | 승인 대기 | 17 | 20/20 | 8번째 테스트에서 멈춤 | 아님 |

- `axis_async_fifo`의 흐름 (01:56에 이어서 실행, 36.6분):
  - 묶음 c0, c1 모두 원인 후보로 출력 구동 모듈 `_m`의 Repair가 먼저 불렸습니다.
  - 두 Repair 모두 트레이스를 근거로 형제 모듈 `_s`를 지목했습니다(`suspect_module`).
    - c0의 근거: `u_s.wptr_gray`가 1이 된 직후 0으로 초기화되어, 데이터가 메모리에 기록되지 않음
  - `_s`의 Repair가 그 부분을 고친 뒤, 두 묶음 모두 Verifier 0을 통과하고 Verifier 1에서만 실패했습니다.
  - Arbiter는 두 묶음 모두 `test_wrong`(AFIFO-03)으로 판정했습니다. 근거: Verifier 1의 속성이 리셋 예외를 "처음 10사이클"로 고정해, 테스트 도중 `s_rst`가 걸린 동안의 `s_axis_tready=0`을 위반으로 봄.
  - 이 판정은 대체로 타당합니다. 다만 SPEC 문장이 "그 밖에는 1"이어서 리셋 중의 동작을 SPEC에 적는 편이 낫습니다 (SPEC 보완 후보).
- c1이 원본 TB `run_test_init_sink_pause_source_reset_001`(sink pause 중 source 리셋)에서 멈춘 것은 Verifier 테스트 두 벌이 모두 놓친 경우입니다.
  - 그대로 승인했다면 Verifier 1의 기댓값을 고친 뒤 c1도 선택 후보가 될 수 있었습니다. 묶음 선택은 Repair 수가 적고 lint가 적은 것을 고르므로, c0이 선택된다는 보장이 없습니다.
  - P5 승인 흐름이나 Verifier 보강에서 다룰 항목입니다.
- 격리 확인: 모든 후보의 블록이 golden IR과 다릅니다 (golden을 베끼지 않음).
- 고친 것: sim 시간 초과
  - E2에 시간 초과가 없어서, RTL이 멈추면 스케줄러도 멈출 수 있었습니다.
  - 시드 한 번 실행이 `timeout_s`(기본 900초, `CHIPDEPT_SIM_TIMEOUT`)를 넘으면 시뮬레이터를 끝내고 `SIM_TIMEOUT`을 냅니다. 마지막으로 돌던 테스트 이름도 함께 냅니다.
  - 스케줄러는 이를 `sim_hang`으로 분류해 Repair에 넘깁니다.
  - 시험을 추가했고, 전체 테스트 201개가 통과했습니다.
- P4 완료 기준(사람 개입 없이 SPEC부터 원본 TB 통과)은 아직 충족하지 못했습니다. 세 블록 모두 기댓값 수정 승인이 필요해서입니다.

### 2026-10-11 P4-9 SPEC부터 끝까지 실행 (1차, 23:09)

블록을 하나씩 차례로 실행합니다 (사용량 한도 때문).

| 블록 | 결과 | 에이전트 실행 | 시간 |
|---|---|---|---|
| `axis_adapter` | 승인 대기 | 11 | 47.6분 |
| `axis_cobs_decode` | 승인 대기 | 9 | 47.2분 |
| `axis_async_fifo` | 사용량 한도로 멈춤 (`paused_quota`) | 9 | 37.9분 |

- 두 블록의 양상이 같습니다.
  - Architect, Verifier, Author 후보 2개는 모두 게이트를 통과했습니다.
  - 두 후보 모두 Verifier 1은 통과하고 Verifier 0에서 실패했습니다. Repair를 한 번 해도 결과는 같았습니다.
  - Arbiter는 두 블록의 후보 4개 모두 `test_wrong`으로 판정했습니다. 기댓값을 바꾸려면 사람의 승인이 필요해서 승인 대기로 멈췄습니다.
- `axis_adapter`:
  - Verifier 0의 처리량 속성이 tlast=0을 "입력 비트를 아직 내보내는 중"으로 잘못 해석했습니다.
  - Arbiter가 근거로 든 요구사항은 ADP-01, 02, 06입니다.
- `axis_cobs_decode`:
  - 세그먼트 중간에 tlast가 오는 오류 경우(`04 CC(tlast=1)`)에서 문제가 났습니다. SPEC은 그 바이트(CC)를 tlast=1, tuser=1로 내보내라고 정합니다. 그런데 Verifier 0의 모델은 직전 버퍼 값인 0을 냈습니다.
  - 테스트 파일의 주석은 CC를 기대 출력으로 적고 있어, 모델이 자기 주석과도 어긋납니다.
  - Arbiter가 근거로 든 요구사항은 COBS-07입니다.
- 두 판정 모두 SPEC 문장을 인용했고, 검토해 보니 타당합니다.
- Verifier 간 차분 검사 수정:
  - 결함: 1비트 신호에 0\~255 값(예: `s_axis_tlast=187`)을 넣었습니다.
  - 수정: `pl model`과 같은 신호 폭 기준 무작위 입력을 쓰도록 바꿨습니다 (`pipeline/tb/gen.py`의 `signal_widths`로 공통화).
  - 이번 두 블록의 Verifier 테스트로 다시 돌린 결과:
    - `axis_adapter`: 차이가 없어졌습니다. 앞의 보고는 잘못된 경보였습니다.
    - `axis_cobs_decode`: 차이가 남았습니다. 입력 `tdata=18, tlast=1, tuser=1`에서 v0은 0을, v1은 18을 냅니다. Arbiter가 찾은 Verifier 0의 결함과 같은 것입니다.
  - 에이전트와 스케줄러 테스트 14개가 통과했습니다.
- `axis_async_fifo`:
  - Architect는 하위 모듈 3개로 나눴습니다: `_s`, `_m`, `_mem`.
  - Author 후보 6개(모듈 3개 × 2)는 모두 게이트를 통과했습니다.
  - 그런데 검증에서 모두 실패했고, Repair 6개를 돌리던 중 사용량 한도에 걸렸습니다.
- 스케줄러 결함 (하위 모듈이 둘 이상일 때):
  - 후보 하나를 검증할 때 형제 모듈은 동작이 없는 L1만 둔 채 Block Top 테스트를 돌립니다.
  - 그래서 출력이 드라이브되지 않고(예: `tdata=160, tid=209`), 후보가 맞아도 반드시 실패합니다.
  - 이 실패를 받은 Repair는 고칠 수 없는 문제를 고치려 하게 됩니다.
  - 앞의 두 블록은 하위 모듈이 하나라 이 문제가 드러나지 않았습니다.
  - 수정 (사용자 결정: 같은 번호 후보끼리 묶어 검증):
    - 모든 모듈의 Author 후보를 먼저 만든 뒤, c0끼리, c1끼리 묶어 Block Top에서 검증합니다.
    - 실패하면 불일치 출력을 구동하는 인스턴스의 모듈을 원인 후보로 보고, 그 모듈의 Repair에 넘깁니다. 출력 불일치가 없으면 lint 조각 오류가 난 모듈로 정합니다.
    - 하위 모듈이 여럿이면 Repair는 Block Top의 연결과 형제 모듈의 L1(`block.json`)을 받습니다.
    - 원인이 형제 모듈에 있다고 보면 `suspect_module`을 써서 그 모듈의 Repair로 넘깁니다. 이것이 Classifier의 "자식 모듈 원인 의심"입니다.
    - Repair들이 원인을 서로 넘기면 `CHILD_SUSPECT_LOOP` 검토 항목으로 멈춥니다.
    - 묶음 선택: 모든 모듈이 통과한 묶음 가운데 Repair 수가 적고 lint가 적은 것을 고릅니다.
    - 시험: 하위 모듈 둘(통과)과, Repair가 출력 구동 모듈에서 지목된 형제 모듈로 넘어가는 경우를 추가했습니다. 전체 테스트 200개가 통과했습니다.
- 기댓값 수정 승인 흐름은 P5에서 정합니다 (사용자 결정).
- 23:21 `axis_async_fifo`를 이어서 실행했습니다.
  - 묶음 검증은 동작했습니다. 이번에는 진짜 불일치가 났고, 원인 후보로 출력 구동 모듈 `_m`을 골랐습니다.
  - Repair 단계에서 다시 사용량 한도에 걸렸습니다 (`Resets in 2h32m`, 약 01:53).
- 그 실행에서 찾아 고친 결함 2개:
  - 결과 파일 이름 불일치:
    - 결과 파일은 하니스의 `name`(`sc01_single_frame`)을 따르는데, 스케줄러는 cocotb 함수 이름(`test_sc01_single_frame`)으로 찾았습니다.
    - 그래서 불일치 리포트가 빠진 채 Repair에 넘어갔습니다.
    - 함수 이름, `test_`를 뗀 이름, 실패가 기록된 첫 결과 파일 순으로 찾게 했습니다.
    - 앞의 두 블록은 이름이 같아 리포트가 정상으로 들어갔습니다.
  - 원인 모듈을 좁힐 신호가 없음:
    - Block Top 트레이스에 인스턴스 포트(`u_m.mem_rdata` 등)를 넣었습니다.
    - 팬인은 인스턴스 입력을 거쳐 형제 인스턴스로 이어지게 했습니다.
    - 저장된 c0 묶음을 다시 검증한 결과: 팬인은 `u_m → u_mem → u_s` 순서입니다. `mem_raddr`가 2→5로 바뀌는 동안 `u_mem`의 출력 데이터가 213으로 고정된 것이 리포트에 보입니다.
  - 시험을 보강했고, 전체 테스트 200개가 통과했습니다.

### 2026-10-11 P4-8 스케줄러, 단독 평가 일부, 사용량 한도

**P4-8 스케줄러** (`pipeline/scheduler/run.py`)
- 흐름:
  - SPEC 검사 → Block Top L1 → Architect(모듈 트리, 동결 해시)
  - Verifier 후보와 참조 모델 차분 검사
  - 모듈마다 Author 후보 → 검증(Validator, V11, 방출, E1, 모든 Verifier 테스트로 E2)
  - 실패 처리: 일부 Verifier만 실패하면 Arbiter(rtl_wrong → Repair, test_wrong/모호 → 승인 대기), 그 밖에는 Repair 루프(상한, IR 해시 진동 감지, L1 변경 요청은 검토 항목)
  - 후보 선택(Repair 적음, lint 적음)과 Author 후보 간 출력 차분 검사 → 통합과 보고서
- 상태 저장과 재개: 단계는 `state.json`에, 병렬 후보와 에이전트 작업은 각자 파일에 저장. 다시 실행하면 끝난 단계와 작업은 건너뜀
- 예산 상한, 사용량 한도(429 RESOURCE_EXHAUSTED)는 `paused_quota`로 멈추고 이어서 실행
- 가짜 agent로 시험: SPEC부터 통합까지 통과, 중단 뒤 재개(끝난 Architect·Verifier 다시 안 부름), 한도 멈춤, 동결 L1 변경 거부, 두 차분 검사 (`tests/sim/test_scheduler.py`, `tests/test_agents.py`)
- 고친 결함: `frozen_l1`이 없는 키를 null로 넣음, Verifier 게이트의 도구 기록 파일이 쓰기 범위 위반으로 잡힘, 차분 검사가 하니스를 못 불러옴

**단독 평가 (격리 적용 후, agy)**
- Arbiter 2/2 정답: 일부러 틀린 기댓값은 `test_wrong`(ADP-01 근거, 수정안 정확), RTL 버그는 `rtl_wrong`(COBS-01\~03 근거)
- Repair 2/2 성공(한도 전에 끝난 것): `adapter_shift`, `fifo_slice` 모두 원인 노드 하나만 고쳐 원본 테스트벤치 통과(9/9, 20/20), 범위 위반 0
- 나머지(Author 3, Verifier 3, Architect 3, Repair 1)는 agy 사용량 한도(429, 개인 할당량)에 걸려 실행되지 않음. 14개를 동시에 돌린 탓. 한도가 풀리면(20:53쯤) 블록별로 순서대로 다시 돌림

**다음**
- P4-9: `tests/golden/e2e.py`로 golden 블록 3개를 SPEC부터 끝까지 실행하고 원본 테스트벤치로 판정

### 2026-10-11 P4-3\~7 에이전트 다섯 종 작성과 격리 위반 발견

**한 일**
- 에이전트 모듈 (`pipeline/agents/`): `author.py`, `repair.py`, `verifier.py`, `architect.py`, `arbiter.py`. 역할마다 볼 수 있는 입력, 쓸 수 있는 출력, 종료 게이트를 정함
- 에이전트용 안내서: `prompts/ir_guide.md`(IR 작성), `prompts/tb_guide.md`(하니스 API, 참조 모델 규약)
- golden 블록 3개의 10개 섹션 SPEC (`tests/golden/<블록>/block_spec.md`). SPEC 검사 게이트가 처음 쓴 `axis_async_fifo` SPEC에서 동작을 정하지 않은 출력 5개를 잡아 고침. SPEC에서 만든 L1은 golden과 같은 인터페이스
- 결정: 출력 포트의 kind(reg/wire)와 리셋값, local 파라미터는 동결 L1에서 뺌. SPEC 표에 없고 Author가 정하는 값 (`pipeline/ir/model.py`의 `frozen_l1`)
- 평가 스크립트 `tests/golden/eval_agents.py` (author, repair, verifier, architect, arbiter)

**발견: 격리 위반**
- 첫 평가에서 Author가 낸 `axis_async_fifo` IR이 golden IR과 똑같았음. 작업 디렉터리가 저장소 안(`build/agents/`)이었고, agy가 작업 디렉터리 밖의 golden 정답을 읽어 그대로 씀
- 대응: 격리를 파일 시스템으로 강제
  - 모든 에이전트 실행을 macOS `sandbox-exec`으로 감쌈. 저장소와 실행 디렉터리 전체의 읽기·쓰기를 막고 자기 작업 디렉터리만 허용
  - 작업 디렉터리는 저장소 밖(`~/.cache/chip-design-department/runs`). 저장소 안이면 실행 거부
  - 격리 수단이 없는 OS에서는 실행 거부
  - 저장소 읽기, 이웃 후보 디렉터리 읽기·쓰기가 막히는지 시험함 (`tests/test_agents.py`)
- 첫 평가 결과는 모두 버리고 격리한 상태로 다시 돌림. Author 평가는 결과가 golden과 같은지도 기록함
- 대기 항목 추가: Linux(폐쇄망 서버)용 격리 수단 (bubblewrap 등)

### 2026-10-11 P4-1, P4-2 작업 실행기와 에이전트 도구

**한 일**
- `pipeline/agents/task.py`: 모든 에이전트를 같은 작업 인터페이스로 다룸
  - 입력 산출물, 도구, 기대 출력, 쓰기 범위를 받음
  - 실행 전후 스냅숏으로 범위 밖 변경을 거부
  - 검사 오류를 TASK.md에 붙여 재시도
  - `.task.json`에 실행 기록
- `pipeline/agents/roles.py`, `config/roles.json`: 역할별 agent, 후보 수, 상한(Repair 5, 재시도 1, 예산 200회). Author와 Verifier가 같은 계열이면 경고
- `pipeline/agents/pl.py`: 작업 디렉터리에 설치되는 도구 CLI. validate(동결 L1 대조 포함), patch(사전 실행), emit, fanin, trace, spec(구절 조회), harness, model(참조 모델 단독 실행). 호출 기록을 남김

**결과**
- 가짜 agent로 출력 회수, 범위 위반 거부, 재시도, 출력 누락, 도구 9개 명령을 확인 (`tests/test_agents.py`)
- 현재 설정(agy, Gemini 두 모델)에서 계열 중복 경고가 나옴 (결정대로 허용)

### 2026-10-11 P4 시작

- 완료 기준: 이식 시험 블록 3개를 SPEC부터 끝까지 사람 개입 없이 실행하고 결과 RTL이 원본 테스트벤치 통과, 강제 중단 뒤 재개, 격리(Verifier에 L2/L3/RTL 없음, Author 후보끼리 서로 못 봄)
- 순서: P4-1 작업 실행기 → P4-2 에이전트 도구 CLI → P4-3\~7 에이전트 하나씩(Author, Repair, Verifier, Architect, Arbiter)과 golden 블록 단독 평가 → P4-8 스케줄러 → P4-9 통합 단계와 SPEC부터 끝까지 실행

### 2026-10-11 P3-5, P3-6 타이밍 다이어그램과 LLM 검사, P3 정리

**P3-5 타이밍 다이어그램** (`pipeline/spec/waveform.py`)
- coding agent 실행기를 `pipeline/agents/runner.py`로, WaveJSON 처리와 그리기를 `pipeline/spec/wavejson.py`로 옮김. 실험 키트에는 같은 이름을 내보내는 얇은 모듈을 남김
- 흐름:
  - PDF에서 캡션 위의 그림 영역을 잘라 냄
  - agy로 WaveJSON 변환
  - 원본 해시(+모델)로 캐시. 실패한 결과는 캐시하지 않음
  - 원본과 다시 그린 그림을 나란히 둔 검토 페이지
  - 그림별 주석 파일(`examples/i3c_basic_controller/figures.json`)의 태그 검사: 규범은 6번 섹션 요구사항, 예시는 8번 섹션 시나리오와 연결
- I3C PDF의 Figure 14, 16을 agy(Verifier 모델)로 변환: 형식 문제 없음(732초, 569초), 주석 검사 0건
- **품질 한계:** MIPI 그림은 사이클 단위가 아니라 아날로그 타이밍 그림이라 WaveJSON에 담긴 정보가 적음. Figure 16은 SDA, SCL 전이 순서만 담았고 기간 막대(Bus Free/Available/Idle)는 빠짐. Figure 14는 4사이클로 요약됨. X2를 실제 SPEC 그림으로 다시 판정해야 하는 이유를 확인함
- 잘라 내기 버그를 고침: PyMuPDF 사각형 합집합이 넓이가 0인 선을 무시해서 선으로 그린 그림이 범례만 남음. 좌표로 직접 합침

**P3-6 LLM 검사** (`pipeline/spec/llm_check.py`)
- coding agent가 `spec.md`만 보고 모호함, 모순, 빠진 코너 케이스를 `out/questions.json`으로 냄. 툴이 형식, 인용 ID, 쓰기 범위를 확인하고 검토 항목(질문)으로 바꿈. `check.py --llm`으로 툴 검사 결과에 합침
- I3C를 agy(Verifier 모델)로 검사(384초): 질문 15개(모순 6, 빠진 코너 케이스 6, 모호함 3). 형식 문제와 범위 위반 없음
- 쓸모 있는 질문이 많음 (재시도할 때 이미 꺼낸 TX FIFO 데이터 처리, IBI FIFO가 찬 상태의 Hot-Join, ENTDAA 주소 NACK 무한 반복 등)
- **틀린 지적 1건:** "FR-CCC-01의 패리티와 SC-03의 `07 T=0`이 모순"이라 했으나, FR-BUS-09 규칙으로 0x07의 패리티는 0이라 맞음. 사람 검토가 필요한 사례

**P3 상태**
- 지금 할 수 있는 항목 완료. I3C SPEC 게이트 통과, 검토 항목 52개(미정의 3, 열린 질문 7, 경고 27, LLM 질문 15)
- 남은 항목은 대기: Word 변환(사내 양식), 블록 다이어그램(원본과 그림 규칙), IP-XACT 대조, 실제 SPEC 그림으로 X2 재판정

### 2026-10-11 P3-4 PDF 변환

**한 일**
- `pipeline/spec/pdf.py`: PDF를 Markdown으로 변환. 제목은 글자 크기, 굵기, 절 번호로 추정하고, 표는 선으로 그린 표를 찾아 Markdown 표로 옮김. 쪽마다 반복되는 머리말·꼬리말과 여백의 줄 번호는 뺌
- 검토 리포트(`*.review.md`):
  - PDF 목차와 추정 제목의 일치율 (목차는 검증에만 씀)
  - 모양이 고르지 않은 표
  - 텍스트가 거의 없는 쪽 (빈 쪽이거나 스캔본)
  - 10개 섹션 템플릿 대응
  - 그림 캡션 목록 (P3-5의 타이밍 다이어그램 후보)

**결과**
- I3C 원본 PDF 37\~120쪽(3.6초): 제목 84개, 표 29개, 그림 20개
  - PDF 목차의 번호 붙은 항목 83개 중 82개를 제목으로 찾음 (98.8%). 놓친 1개는 두 줄로 줄바꿈된 긴 제목
  - 모양이 고르지 않은 표 10개를 검토 대상으로 표시
  - 템플릿 대응 0/10: MIPI 규격은 사내 10개 섹션 템플릿을 따르지 않는 문서라서, 대응표를 사람이 써야 함 (예상한 결과)
- 템플릿 형식의 합성 PDF(한글 제목, 선으로 그린 표, 반복 머리말)는 템플릿 대응 10/10, 목차 일치 100%

**발견**
- PDF는 절 번호와 제목을 같은 높이의 다른 줄 객체로 둠. 그대로 읽으면 제목을 9.6%만 찾았고, 같은 높이의 줄을 합친 뒤 98.8%가 됨

### 2026-10-11 P3-3 SPEC 툴 검사와 검토 항목

**한 일**
- `pipeline/spec/check.py`: SPEC 검사 게이트의 툴 검사
  - 필수 섹션 10개, 제목, 순서
  - 표 파싱과 L1의 V1\~V3
  - 요구사항 ID 중복, 의무 수준 표시, 인용한 ID가 있는지, 한 문장 한 동작(경고)
  - 출력 포트마다 그 포트를 다루는 요구사항이 있는지(오류), 입력 포트 참조(경고)
  - 프로토콜 태그가 표준 목록에 있는지(경고)
  - 예시 시나리오(정상 하나, 코너 하나 이상, 입력과 기대 출력 표)
  - 레지스터 맵 검사와 대조
- 미정의 동작, 열린 질문, 경고를 검토 항목으로 모아 `review.json`과 `review.md`로 냄. 오류가 없으면 게이트 통과

**결과 (I3C)**
- 게이트 통과. 오류 0건, 경고 27건, 검토 항목 37개
  - 경고: 한 요구사항에 문장 둘 이상 25건, `apb` 태그가 임시 표준 목록에 없음 1건, "APB 레지스터" 오탐 1건
  - 검토 항목: 미정의 3, 열린 질문 7, 경고 27
- SPEC을 일부러 망가뜨린 11가지 경우를 각 검사가 잡음 (`tests/test_spec.py`)

### 2026-10-11 P3-2 레지스터 맵

**한 일**
- `pipeline/spec/regmap.py`: 엑셀(.xlsx, 정본)과 CSV를 직접 파싱. 같은 (레지스터, 오프셋)을 워드 하나로 보고, 배열 레지스터(`DAT[i]`, 오프셋 식 `0x100+0x10*i`)는 파라미터의 배열 크기로 펼침
- 검사: 필수 열, bits 형식과 범위, access 종류, 리셋값 폭, 필드 겹침과 중복, 4바이트 정렬, 배열을 펼친 뒤의 워드 겹침, APB 주소 폭(SPEC의 `paddr` 폭)
- SPEC 대조: 본문의 `레지스터.필드` 인용이 맵에 있는지, 문서 안 레지스터 표가 맵과 다른지(경고, 맵을 따름)
- `pipeline/spec/issues.py`: SPEC 단계 검사 결과의 공통 형식(코드, 심각도, 위치, 메시지, 출처)

**결과**
- I3C 레지스터 맵: 레지스터 17개, 필드 41개, 형식 오류 0건. `DAT`, `DCT`를 8개로 펼쳐도 겹침 없음
- SPEC이 인용한 `레지스터.필드` 19개가 모두 맵에 있음. 경고 1건: "APB 레지스터로 다룹니다"를 레지스터 이름 `APB`로 읽음 ("<이름> 레지스터" 패턴은 추정이라 경고로만 냄)

**발견**
- 한글 조사가 식별자에 바로 붙으면(`CTRL.enable이`, `FR-CCC-05를`) 정규식 `\b` 경계가 성립하지 않아 인용을 놓쳤음. 처음 대조 결과가 비어 있던 것은 이 때문. ASCII 식별자 경계로 고쳐 레지스터 인용 19개, 요구사항 ID 인용 18개(이전 11개)를 찾음

### 2026-10-11 P3-1 SPEC 파서와 Block Top L1 생성

**한 일**
- `pipeline/spec/parse.py`: 10개 섹션 Markdown을 구조로 읽음. 섹션, 표, 요구사항(ID, 의무 수준, 인용한 다른 ID), 시나리오(정상/코너와 표), 열린 질문. 모든 항목이 원본 줄 번호를 가짐
- `pipeline/spec/l1.py`: 2\~4번 섹션 표에서 Block Top L1 생성. domains(주파수, 리셋 극성과 동기 여부, 도메인 간 비동기 관계, 전력 도메인과 isolation/retention), ports(굵은 글씨 행으로 번들 구분, 비동기 포트는 domain null, 클럭·리셋 포트는 domains에서 유도하므로 뺌), params(허용 범위 포함). IR 노드마다 SPEC 줄 번호를 provenance로 냄
- 의존성: `.venv`에 `openpyxl`(엑셀 레지스터 맵), `pymupdf`(PDF 변환) 추가

**결과**
- I3C SPEC: 섹션 10개, 요구사항 97개(필수 94, 미정의 3), 시나리오 7개(정상 3, 코너 4), 열린 질문 7개
- 생성한 `i3c_ctrl_top` L1이 Validator V1\~V3 통과 (도메인 1, 번들 6, 단독 포트 10, 파라미터 6)
- 두 도메인 SPEC(비동기 관계, 전력 도메인)도 V1\~V3 통과 (`tests/test_spec.py`)

### 2026-10-11 P3 시작

- 입력: I3C Basic controller 예시 SPEC(10개 섹션 Markdown), `registers.csv`, MIPI I3C Basic v1.2 PDF(저장소 밖, `experiments/specs/`)
- 순서: P3-1 SPEC 파서와 Block Top L1 생성 → P3-2 레지스터 맵 → P3-3 SPEC 툴 검사와 검토 항목 → P3-4 PDF 변환 → P3-5 타이밍 다이어그램 변환(agy) → P3-6 LLM 검사(agy)
- 대기: Word 변환, 블록 다이어그램, IP-XACT (위 대기 항목)

### 2026-10-11 P2-3, P2-4 불일치 리포트와 golden IR 검사

**P2-3 불일치 리포트.** golden 블록 세 개에 버그를 하나씩 넣고, 생성 하니스가 잡은 첫 실패로 리포트를 만들었습니다 (`tests/sim/test_golden_harness.py`).

| 블록 | 넣은 버그 | 잡은 검사 | 원인 노드 포함 |
| --- | --- | --- | --- |
| `axis_cobs_decode` | FSM 전이 `t_seg_next`의 세그먼트 길이 조건 | T3 (tlast·tuser가 일찍 나옴) | `blocks/k_fsm/transitions/t_seg_next` 포함 |
| `axis_adapter` | `k_data`의 바이트 시프트 폭 | T3 | `blocks/k_data` 포함 |
| `axis_async_fifo` | `k_m_comb`의 tid 필드 위치 | T3 | `blocks/k_m_comb` 포함 |

리포트에는 첫 실패(기댓값과 실제값), 실패 전후의 FSM 상태 트레이스, 팬인 노드와 그 신호 값, 요구사항 구절(`spec.md`)이 함께 들어갑니다.
- **한계:** 작은 블록에서는 팬인이 거의 모든 블록을 덮습니다. `axis_cobs_decode`에서는 블록 8개 중 8개였습니다. 원인 후보를 좁히는 힘은 약합니다. 신호 값의 차이로 좁히는 방법은 P4 Repair 평가에서 필요성을 보고 정합니다.

**P2-4 golden IR 검사.** 공개 블록 4개(모듈 7개)가 V1\~V10에서 오류와 경고 0건입니다. 같은 IR에 V11을 돌리면 변경 없음으로 나옵니다.

**P2 상태.** 지금 할 수 있는 항목을 모두 마쳤습니다. 남은 항목은 위 "대기 항목"에 있고, 조건이 갖춰지면 진행합니다.

### 2026-10-11 P2-1, P2-2 하니스 보강과 golden 블록 T1\~T5

**한 일**
- 하니스 라이브러리 보강 (`pipeline/tb/lib.py`, `pipeline/verify/run.py`, `pipeline/tb/report.py`)
  - 스코어보드: 기댓값과 실제값 중 먼저 온 쪽을 기다렸다가 비교. 프레임이 끝나야 기댓값을 아는 모델(COBS 등)을 위해
  - 모델이 `streams`로 비교할 출력을 정함. 상태 출력처럼 예측하지 않는 출력은 속성(T4)으로 봄
  - T5: Verilator line/toggle/branch 커버리지(`coverage=True`), 요구사항 ID 커버리지(`req_coverage`), 프로토콜 체커와 요구사항 연결(`cover_protocol`)
  - T1: data 출력은 valid가 1일 때만 비교. 클럭 도메인이 둘 이상이면 사이클 비교 대신 시드별 실패 목록만 비교
  - 클럭 주기를 ps 단위 짝수로 맞춤 (cocotb Clock 제약)
- golden 블록 3개에 L1에서 생성한 하니스와 손으로 쓴 참조 모델(Verifier 역할, `tests/golden/<블록>/harness/`)과 요구사항 발췌(`spec.md`)를 붙임. `run_golden.py --harness`

**결과** (시드 3개)

| 블록 | T1 | T2 위반 | T3 일치 | T4 위반 | 요구사항 | line | toggle | FSM 전이 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `axis_cobs_decode` | 통과 | 0 | 4524 | 0 | 4/4 | 79.3% | 100% | 9/9 |
| `axis_adapter` | 통과 | 0 | 1571 | 0 | 5/5 | 100% | 99.7% | – |
| `axis_async_fifo` | 통과 | 0 | 765 | 0 | 5/5 | 100% | 97.7% | – |

**발견**
- **`axis_async_fifo` 이식 IR의 기능 버그를 생성 하니스가 찾음.** 임시 표준 동기화 셀은 리셋 때 0을 내는데, 원본의 리셋 동기화 플롭은 리셋 없이 초기값이 1이다. 한쪽 도메인이 먼저 리셋에서 풀리면 잠깐 입력을 받았다가 그 데이터를 잃었다. 원본 테스트벤치는 두 리셋을 동시에 풀어 드러나지 않았다. "상대 도메인 준비됨" 플래그(리셋 시 0)를 동기화하도록 IR을 고쳤고, 원본 테스트벤치 20개도 여전히 통과한다. P1 우회 표현 8번이 실제 결함으로 이어진 사례로 `tests/golden/README.md`에 반영
- Verilator `--coverage` 빌드에서만 `UNOPTFLAT`(조합 루프 의심)이 나옴. 계측이 always 블록을 쪼개서 생기는 경고라 커버리지 빌드에서만 끔. 계측 없는 빌드와 E1에서는 그대로 봄
- `axis_cobs_decode`의 line 79%는 정상 프레임만 넣어 오류 처리 경로(프레임 중간의 0 바이트, tuser)가 안 돈 것. 설계상 Verifier에게 돌려 자극을 보강할 항목

**남은 일**
- P2-3 불일치 리포트 (golden 블록에 버그 주입)
- P2-4 golden IR의 V6\~V11 오탐 기록

### 2026-10-11 P2 남은 항목 시작

- PROGRESS.md를 만들었습니다.
- 지금 할 수 있는 P2 항목:
  1. 하니스 라이브러리 보강: 스코어보드 비교 순서, Verilator line/toggle 커버리지, 요구사항 ID 커버리지 (T5)
  2. golden 블록에 생성된 하니스와 손으로 쓴 참조 모델을 붙여 T1\~T5 실행
  3. golden 블록에 버그를 넣었을 때 불일치 리포트가 원인 노드를 포함하는지 확인
  4. golden IR이 V6\~V11에서 오탐 없이 통과하는지 기록
