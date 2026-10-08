# P0 선행 확인

Oct 8, 2026 · @Seungjoon Lee

[IMPLEMENTATION.md](../../IMPLEMENTATION.md)의 P0를 실행하기 위한 안내서입니다. 실험 여섯 개(X1\~X6)의 절차, 통과 기준, 결과 기록 방법과 받아야 할 자료를 담았습니다.

모든 실험은 시스템의 두 가지 확정 원칙을 그대로 따릅니다.
- **LLM은 coding agent로만 씁니다.** 실험 스크립트는 모델 API를 직접 부르지 않습니다. 파이프라인 스케줄러처럼 작업 디렉터리에 과제 파일과 도구를 두고 coding agent를 headless로 실행한 뒤, 결과 파일을 회수해 검사합니다.
- **사람과 Seat의 대화는 OpenRig를 거칩니다.**

## 현황

| # | 실험 | 상태 | 준비물 |
| --- | --- | --- | --- |
| X1 | coding agent(로컬 모델)가 스키마에 맞는 IR 파일을 쓰고 검사 도구를 쓰는 비율 | 스크립트 준비 완료. 폐쇄망에서 실행 필요 | `x1_structured_output/run_x1.py` |
| X2 | 비전 모델을 쓰는 coding agent의 타이밍 다이어그램 → WaveJSON 정확도 | 스크립트 준비 완료. 샘플과 정답 필요 | `x2_wavejson/run_x2.py` |
| X3 | coding agent 런타임과 로컬 모델의 연결. OpenRig Seat와 headless 실행 둘 다 | 소스 확인으로 경로 찾음. 실측 필요 | 아래 절차 |
| X4 | rig.yaml edge 종류 | **완료 (소스 확인).** `handoff`, `can_message`는 없음 | 아래 결과 |
| X5 | 폐쇄망 설치 절차와 데몬의 외부 호출 | 외부 호출 1건 확인. 실측 필요 | 아래 절차 |
| X6 | 게이트웨이 → OpenRig → Seat 대화 왕복 | 데몬 API 확인. 실측 필요 | 아래 절차 |

X3\~X6은 [OpenRig](https://github.com/mvschwarz/openrig) v0.6.6(커밋 `114cdb1`, 2026-10-08)의 소스를 읽어 확인했습니다. 버전이 바뀌면 다시 확인해야 합니다.

**순서.** X3의 headless 실행이 되어야 X1과 X2를 돌릴 수 있습니다. X3 → X1, X2 → X6 순서로 진행합니다. X5는 설치 단계에서 함께 확인합니다.

## 공통 준비

1. 폐쇄망 장비에 Python 3.11 이상과 `jsonschema`를 사내 미러에서 설치합니다. 테스트까지 돌리려면 `pytest`도 설치합니다.
2. 후보 coding agent 런타임(Pi, Codex 등)을 설치하고 로컬 모델에 연결합니다(X3).
3. `agents.example.json`을 `agents.json`으로 복사하고, 런타임과 모델 조합마다 항목을 하나씩 채웁니다.
   - `command`는 headless 실행 명령의 템플릿입니다. 쓸 수 있는 자리표시자는 `{prompt}`, `{prompt_file}`, `{workdir}`, `{model}`입니다. 예시의 플래그는 설치된 버전의 `--help`로 확인합니다.
   - `family`는 모델 계열입니다. Author와 Verifier의 계열이 겹치는지 판단할 때 씁니다.
   - 이미지를 읽을 수 있는 구성은 `"vision": true`로 표시합니다. X2는 이 항목만 실행합니다.
   - `_`로 시작하는 키는 메모로 보고 무시합니다.
4. 실험 스크립트가 제대로 도는지 먼저 확인합니다. 아래 명령은 가짜 agent로 동작만 검사하며, 실제 모델은 쓰지 않습니다.

```bash
python3 -m pytest -q tests
```

결과는 `experiments/p0/results/<실험>-<시각>/`에 남습니다.
- `trials.jsonl`: 시도별 원본 기록
- `summary.md`: 요약 표
- `work/`: trial별 작업 디렉터리. agent가 실제로 무엇을 했는지 볼 수 있습니다.

---

## X1. IR 파일 작성과 검사 도구 사용

**과제.** Author 에이전트가 실제로 하는 일과 같은 형태입니다. trial마다 새 작업 디렉터리를 만들고, 아래 파일을 둔 뒤 coding agent를 실행합니다.

```
TASK.md                  # 과제와 규칙
l1.json                  # 동결된 L1 (설계 문서의 pkt_parser)
spec.md                  # SPEC 요구사항
schema/ir.schema.json    # IR 스키마 v0 초안
tools/validate_ir.py     # 검사 도구. 호출하면 .validate.log에 기록
out/                     # agent가 out/pkt_parser.ir.json을 써야 함
```

agent가 종료되면 결과 파일을 원본 스키마와 원본 L1로 검사합니다. 작업 디렉터리의 사본은 agent가 고칠 수 있으므로 채점에 쓰지 않습니다. 검사가 실패하면 오류를 붙인 새 TASK.md로 `--retry`회까지 다시 실행합니다. 이는 Classifier의 "스키마 위반 → 같은 에이전트 재시도"와 같은 동작입니다.

기능의 정확성은 보지 않습니다.

```bash
python3 experiments/p0/x1_structured_output/run_x1.py \
    --agents experiments/p0/agents.json --trials 10 --retry 1
```

**지표.** 정상 종료, 결과 파일 생성, 1회차 통과, 재시도 포함 통과, 동결 준수, 검사 도구 사용, 범위 밖 쓰기 없음, 평균 시간

**통과 기준 (제안. 확정 필요)**

| 지표 | 기준 |
| --- | --- |
| 재시도 1회 포함 통과 | 95% 이상 |
| 1회차 통과 | 80% 이상 |
| 검사 도구 사용 | 90% 이상 |
| 범위 밖 쓰기 없음 | 100% |
| 평균 시간 | 기록만 함. 예산과 반복 상한을 정할 때 씀 |

**기준에 못 미칠 때**
- 다른 런타임과 모델 조합으로 바꿉니다. 판정은 조합별로 하고, 역할별 배정에는 통과한 조합만 씁니다.
- 출력 단위를 블록 하나로 쪼갭니다.
- 범위 밖 쓰기가 나오면 런타임의 파일 쓰기 권한을 `out/`으로 제한하는 설정을 찾습니다. 실제 파이프라인은 종료 후 작업 디렉터리 비교로도 검출합니다.

## X2. 타이밍 다이어그램 → WaveJSON 정확도

**준비.** `x2_wavejson/samples/`에 그림과 정답 WaveJSON을 같은 이름으로 둡니다. 형식과 샘플 구성은 [samples/README.md](x2_wavejson/samples/README.md)를 따릅니다.

**과제.** trial마다 작업 디렉터리에 그림 하나와 TASK.md를 두고, agent가 `out/wave.json`을 쓰게 합니다. 런타임이 작업 디렉터리의 이미지 파일을 모델에 넘길 수 있어야 합니다. 이것도 X3에서 함께 확인합니다.

```bash
python3 experiments/p0/x2_wavejson/run_x2.py --agents experiments/p0/agents.json --repeat 3
```

**지표**
- **사이클 정확도.** 정답 신호의 모든 사이클 중에서 상태와 데이터 라벨이 모두 맞은 비율입니다. 빠진 신호는 전부 틀린 것으로 셉니다.
- **신호 재현율과 정밀도.** 신호 이름 기준입니다. 대소문자와 공백은 무시합니다.
- **완전 일치.** 그림 전체가 정답과 같은 시도의 수입니다.

**판정 (제안. 확정 필요)**

설계상 WaveJSON은 어느 경우든 사람이 전부 확인합니다. 이 실험은 비전 초안이 사람의 작업을 실제로 줄여 주는지를 봅니다.

| 결과 | 결정 |
| --- | --- |
| 평균 사이클 정확도 95% 이상, 신호 재현율 99% 이상 | 현재 설계 유지. coding agent가 변환하고 사람이 대조 |
| 80% 이상 95% 미만 | coding agent는 초안만 만들고, SPEC 작업대에 사이클 단위 편집기를 둠 |
| 80% 미만 | 사람이 WaveJSON을 작성. coding agent는 신호 이름 추출에만 사용 |

## X3. coding agent 런타임과 로컬 모델

coding agent는 두 가지 방식으로 씁니다. 둘 다 확인해야 합니다.

| 방식 | 쓰는 곳 | 확인할 것 |
| --- | --- | --- |
| OpenRig Seat (장기 세션) | 부서 계층의 15개 Seat | 대화형 세션, 도구 사용, 재시작 후 복구 |
| headless (단기 세션) | 파이프라인 에이전트, X1과 X2 | 명령 한 번으로 실행하고 종료, 종료 코드, 작업 디렉터리 안 파일 쓰기 |

**소스에서 확인한 사실**
- OpenRig가 지원하는 런타임은 `claude-code`, `codex`, `pi`, `omp`, `terminal`, `stub`입니다(`rigspec-preflight.ts`).
- **`pi` 런타임은 사용자 정의 provider를 지원합니다.** Seat마다 있는 `$OPENRIG_HOME/state/pi/<session>/agent/models.json`에 provider와 모델을 적으면 됩니다. OpenRig는 이 파일을 만들거나 쓰지 않습니다(`docs/reference/rig-spec.md`).
- Pi 프로세스로 넘어가는 환경 변수는 허용 목록으로 제한됩니다. 사용자 정의 provider의 키는 환경 변수가 아니라 `models.json`으로 넣어야 합니다.
- OpenRig는 Pi를 `pi --mode rpc`로 띄웁니다. headless 실행에 쓸 Pi의 비대화형 모드는 Pi 자체에서 확인해야 합니다.

**절차**
1. 테스트 rig에 `runtime: pi` Seat 하나를 정의합니다.
2. 그 Seat의 `models.json`에 사내 모델 엔드포인트를 provider로 등록합니다.
3. Seat를 띄우고 다음을 확인합니다.
   - [ ] 세션이 시작되고 메시지에 응답함
   - [ ] 작업 디렉터리 안에서 파일을 읽고 씀 (도구 사용)
   - [ ] 데몬을 재시작한 뒤 세션이 복구됨 (스냅숏)
   - [ ] 다른 Seat와 메시지와 큐를 주고받음
4. 같은 런타임과 모델을 headless로 실행합니다. `agents.json` 항목 하나를 만들고, X1을 `--trials 1`로 돌려 다음을 확인합니다.
   - [ ] 명령 한 번으로 실행되고 스스로 종료함 (입력 대기 없음)
   - [ ] 작업 디렉터리 안에 파일을 씀
   - [ ] 작업 디렉터리 안의 명령(`python3 tools/validate_ir.py`)을 실행함
   - [ ] (비전) 작업 디렉터리의 이미지 파일을 읽음
5. Codex 등 다른 후보 런타임으로 3\~4를 반복합니다. Author와 Verifier에 서로 다른 계열이 필요하므로, 동작하는 런타임과 모델 조합이 둘 이상 있어야 합니다.

**실패할 때.** `terminal` 런타임에 다른 coding agent를 올립니다. `claude-code` 런타임을 사내 프록시에 붙이는 방법도 있지만, 아직 확인하지 않은 경로입니다.

## X4. rig.yaml의 edge 종류 (완료)

RigSpec이 허용하는 edge 종류는 다섯 가지입니다(`packages/daemon/src/domain/rigspec-schema.ts`의 `VALID_EDGE_KINDS`). 처음 받은 구성안에 있던 `handoff`와 `can_message`는 없습니다. `handoff`는 edge가 아니라 큐 항목의 동작으로 존재합니다.

| edge 종류 | 이 설계에서의 쓰임 (제안) |
| --- | --- |
| `delegates_to` | Chip-lead → 각 lead, 각 lead → 자기 Pod의 Engineer |
| `escalates_to` | Engineer → 자기 Pod의 lead, 각 lead → Chip-lead |
| `collaborates_with` | Design-lead ↔ DV-lead, Design-lead ↔ PI-lead |
| `can_observe` | Chip-lead → 모든 Seat |
| `spawned_by` | 쓰지 않음 |

edge는 조율을 위한 표시일 뿐, 접근을 막지 않습니다. OpenRig 문서에 따르면 `rig send`는 edge와 관계없이 어느 세션에나 보낼 수 있습니다(`docs/reference/edge-types.md`). 설계대로 격리는 작업 디렉터리 권한, 저장소 권한, 파이프라인 툴로 강제합니다. 따라서 이 결과로 설계를 바꿀 것은 없습니다.

## X5. 폐쇄망 설치와 외부 호출

**소스에서 확인한 외부 호출**
- 데몬은 시작할 때 `github.com/mvschwarz/openrig-plugins`에서 플러그인 최신본을 가져오려고 합니다(`plugin-vendor-service.ts`).
- 이 호출은 실패해도 됩니다. 404, 네트워크 오류, 시간 초과를 모두 조용히 넘기고, 타임아웃은 5초입니다. 패키지에 들어 있는 플러그인 사본이 기준입니다.
- 따라서 폐쇄망에서는 시작이 최대 5초 늦어지는 것 말고는 영향이 없을 것으로 봅니다. 실측으로 확인해야 합니다.

**절차**
1. 사내 npm 미러에서 OpenRig 0.6.6을 설치합니다. 미러에 없는 의존성을 기록합니다.
2. 외부 통신을 기록하는 상태(방화벽 로그 또는 `lsof -i`)에서 데몬 시작, Seat 실행, 스냅숏 복구를 한 번씩 수행합니다.
3. 다음을 기록합니다.
   - [ ] 시도된 외부 호출 목록 (플러그인 저장소 외에 있는지)
   - [ ] 외부 호출 실패가 기능에 영향을 주는지
   - [ ] coding agent 런타임(Pi, Codex 등) 자체의 외부 호출 (업데이트 확인, 텔레메트리 등)
4. 재현할 수 있는 설치 절차를 문서로 남깁니다.

## X6. 게이트웨이 → OpenRig → Seat 대화 왕복

Web UI의 대화는 게이트웨이가 OpenRig를 통해 Seat에 전달합니다. 게이트웨이는 모델을 직접 부르지 않습니다.

**소스에서 확인한 사실**
- 데몬은 HTTP API를 제공합니다. 기본 포트는 7433이고 `OPENRIG_PORT`로 바꿀 수 있습니다.
- CLI의 `rig send`(에이전트 터미널로 메시지 전송)는 `POST /api/transport/send`를 씁니다. `rig capture`(터미널 출력 캡처)는 `POST /api/transport/capture`를 씁니다.
- transcript 읽기(`rig transcript`)에는 세션별 tail, full, grep 경로가 있습니다.
- 데몬의 사람 등록부(`rig gateway human`)는 사람 한 명만 지원합니다. 여러 사람의 구분은 우리 게이트웨이가 맡아야 합니다.

**절차**
1. X3에서 띄운 테스트 rig에 Seat 두 개(lead 하나, Engineer 하나)를 둡니다.
2. 게이트웨이 역할을 하는 작은 스크립트로 다음을 확인합니다.
   - [ ] 데몬 API(또는 `rig send`)로 특정 Seat에 메시지를 보냄
   - [ ] Seat의 응답을 transcript에서 읽어 메시지 단위로 잘라 낼 수 있음
   - [ ] 메시지에 보낸 사람(이름, 역할)을 붙였을 때 Seat가 이를 구분함
   - [ ] 두 사람이 같은 Seat에 거의 동시에 보낼 때 메시지가 섞이거나 사라지지 않음
   - [ ] Seat 상태(작업 중, 유휴, 멈춤)를 데몬 API에서 읽을 수 있음
   - [ ] 데몬 API의 인증 방식 (CLI가 쓰는 인증 헤더를 게이트웨이가 쓸 수 있는지)
3. 응답을 메시지 단위로 잘라 내기 어렵다면 대안을 정합니다. 예를 들어 Seat가 정해진 형식으로 응답 파일이나 큐 항목을 남기게 하는 규약입니다.

---

## 받아야 할 자료

| 자료 | 쓰이는 곳 | 요청 대상 |
| --- | --- | --- |
| 이식 시험 대상 블록 3개의 RTL과 테스트벤치 (FSM 중심, datapath 중심, 다중 클럭. 하나는 계층 모듈) | P1 | |
| 위 블록의 Word 또는 PDF SPEC, 엑셀 레지스터 맵 | P3 | |
| Word SPEC 양식 원본 | P3 템플릿 대응 | |
| 블록 다이어그램 원본 (Visio 또는 SVG) | P3 | |
| SPEC의 타이밍 다이어그램 10\~20장과 그 정답 WaveJSON | X2 | |
| VC SpyGlass 사내 템플릿의 호출 방식과 리포트 형식 | P1 판정, P2 E3 | |
| 프로젝트 표준 동기화 셀의 이름과 포트 | Emitter `cdc_sync` | |
| 메모리 매크로 래퍼 규약 | Emitter `memory` | |
| 표준 프로토콜 태그 목록 | 스키마, TB 라이브러리 | |
| 사내 코딩 가이드 (명명 규칙, 금지 구문) | Emitter, V4 | |
| 로컬 모델 목록 (언어, 비전)과 계열, 서빙 엔드포인트 | X1, X2, X3 | |
| 폐쇄망에 반입할 coding agent 런타임 패키지 (Pi, Codex 등) | X3, X5 | |

## P0 완료 기준

- X1\~X6의 결과가 이 문서의 현황 표와 `results/`에 남아 있습니다. 실패한 항목은 대안이 정해져 있습니다.
- X1과 X2의 통과 기준이 확정되어 있습니다.
- Author와 Verifier에 배정할 수 있는, 서로 다른 계열의 coding agent 런타임과 모델 조합이 둘 이상 있습니다.
- 이식 시험 블록 3개와 VC SpyGlass 사내 템플릿을 받았습니다.
