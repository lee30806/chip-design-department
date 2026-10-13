# 부서 계층 (OpenRig)

칩 설계 부서의 Seat 15개를 OpenRig로 띄우고, 권한은 Seat 프로세스를 감싼 OS sandbox로 강제합니다.
설계 근거는 [ARCHITECTURE.md](../ARCHITECTURE.md) 3절(부서 계층)과 8절(격리)입니다.

## 구성

| 파일 | 내용 |
| --- | --- |
| `rig.yaml` | RigSpec 0.2. Pod 4개(총괄, Design, DV, PI)와 Seat 15개, infra Pod의 파이프라인 API 서버, edge, 연속성 정책 |
| `seats.json` | Seat 명단. 파이프라인 API 역할(`api_role`), DV 여부(`verifier_blind`), 모델 |
| `CULTURE.md` | rig 공통 규범 (OpenRig `culture_file`) |
| `guidance/common.md`, `guidance/<pod.member>.md` | Seat 공통 규칙과 역할별 지침. Seat worktree의 `AGENTS.md`, `GEMINI.md`로 들어감 |
| `seatlib.py` | 경로와 Seat별 sandbox 프로필 |
| `bin/seat` | Seat 진입점: worktree 준비, 지침 배치, sandbox로 감싼 agy(또는 시험용 셸)로 바뀜 |
| `bin/deptctl` | Seat의 게이트웨이 클라이언트 (Seat별 API 키). 역할에 없는 쓰기 명령은 보이지 않고, 승인 명령은 없음 |
| `bin/pipeline-server` | 파이프라인 API 서버 (infra Pod). Seat sandbox 밖의 유일한 IR/RTL 쓰기 주체. 게이트웨이 토큰이 있는 쓰기만 받음 |
| `bin/gateway-server` | 게이트웨이 (infra Pod). 사람과 Seat의 인증, 권한, 승인 기록 ([gateway/README.md](../gateway/README.md)) |
| `dept.py` | 운영: 격리된 OpenRig 환경으로 올리기, 내리기, Seat 초기화, 스냅숏과 복구, Seat에 명령 보내기 |

## Seat와 권한

| Pod | Seat (`pod.member`) | 파이프라인 API 역할 |
| --- | --- | --- |
| 총괄 | `lead.chip` Chip-lead | 설계 역할: 실행 제출, 승인 자료 취합 |
| Design | `design.lead` Design-lead | 설계 역할 + design_lead: 환류 제출(단일 창구), Repair 충돌 결정(고칠 모듈 지정 또는 Architect 재구성) |
| | `design.arch` Architecture Engineer, `design.sanity` Sanity Engineer | 설계 역할 (SPEC 작업대) |
| | `design.rtl` RTL Engineer | 설계 역할: 고정된 SPEC으로 실행 제출과 감시 |
| DV | `dv.lead`, `dv.vplan`, `dv.tb`, `dv.checker` | 조회만. 파이프라인 Verifier 산출물 읽기 금지 |
| PI | `pi.lead`, `pi.synth`, `pi.lec`, `pi.power`, `pi.sta`, `pi.sdc` | 조회만 |

게이트웨이에서 Seat 계정의 역할은 Pod로 정합니다 (총괄, Design → 설계, DV → 검증, PI → 구현). 승인은 사람(승인자)만 하고 Seat 계정은 승인자가 될 수 없습니다.

Seat 프로세스(agy와 그것이 실행하는 모든 명령)는 `sandbox-exec` 프로필 안에서 돕니다.

| 규칙 | 강제 |
| --- | --- |
| 어떤 Seat도 IR, RTL, 실행 상태를 쓰지 못함 | 파이프라인 저장소(`CHIPDEPT_STORE`)와 에이전트 작업(`CHIPDEPT_RUNS`) 쓰기 거부 |
| Seat는 자기 worktree에서만 작업. 교환은 브랜치와 병합 | 저장소 원본과 다른 Seat의 worktree 쓰기 거부 (`.git` 메타데이터만 허용해 커밋은 가능) |
| DV는 파이프라인 Verifier의 참조 모델과 테스트를 볼 수 없음 | DV Seat는 RUNS와 STORE 읽기도 거부. 승인된 RTL과 SPEC은 API(`deptctl rtl`)로 받음 |
| 수정 요구는 Design-lead만 제출 | 게이트웨이가 Seat 계정의 역할을 검사함. 파이프라인 API는 게이트웨이 토큰이 있는 쓰기만 받으므로 Seat가 직접 보내면 401 |
| Seat가 남의 권한을 쓰지 못함 | 게이트웨이 저장소(토큰, 계정 DB)와 다른 Seat의 API 키 읽기 거부. 자기 키만 읽음 |
| Seat 세션과 실행 상태 분리 | 실행은 API 서버와 다른 세션의 프로세스(표준 입력 없음)이고, 상태는 저장소에 있음 |

## 경로

| 변수 | 기본값 | 내용 |
| --- | --- | --- |
| `CHIPDEPT_DEPT_HOME` | `~/.cache/chip-design-department/dept` | Seat worktree(`seats/`), sandbox 프로필(`profiles/`) |
| `CHIPDEPT_STORE` | `$CHIPDEPT_DEPT_HOME/store` | 파이프라인 API 저장소 |
| `CHIPDEPT_RUNS` | `~/.cache/chip-design-department/runs` | 에이전트 작업 디렉터리 |
| `CHIPDEPT_OPENRIG` | `~/.cache/chip-design-department/openrig` | OpenRig 설치와 격리된 HOME, OPENRIG_HOME |
| `CHIPDEPT_API_PORT` | `8740` | API 서버 포트 |
| `CHIPDEPT_SEAT_BRANCH_PREFIX` | `seat/` | Seat 브랜치 이름 앞부분 |
| `CHIPDEPT_GATEWAY_HOME` | `~/.cache/chip-design-department/gateway` | 게이트웨이 DB와 파이프라인 API 토큰 |
| `CHIPDEPT_GATEWAY_PORT` | `8750` | 게이트웨이 포트 |

## 설치와 운영

```bash
# OpenRig 0.6.6 (사용자 설정을 건드리지 않게 따로 설치)
npm install --prefix ~/.cache/chip-design-department/openrig @openrig/cli@0.6.6

python3 department/dept.py up                 # 데몬(--no-kernel)과 rig를 올림. Seat는 agy로 시작
python3 department/dept.py status
python3 department/dept.py reset design.rtl   # Seat 세션 초기화 (진행 중인 실행은 그대로)
python3 department/dept.py snapshot-down      # 스냅숏을 남기고 내림
python3 department/dept.py recover            # 스냅숏에서 복구. 쓸 수 없으면 rig.yaml로 새로 띄움
python3 department/dept.py down               # rig 삭제와 데몬 중지
```

**복구 절차.** `recover`는 먼저 최근 스냅숏으로 되살립니다(`rig up chip-dept`). Seat를 새로 띄운 뒤에는 OpenRig가 스냅숏의 점유자가 옛것이라며 거부하는데, 그때는 `rig.yaml`로 새로 띄웁니다. Seat의 상태는 세션이 아니라 worktree와 파이프라인 저장소에 있으므로 결과가 같습니다.

**agy 폴더 신뢰.** agy는 폴더마다 처음 한 번 신뢰 확인을 받습니다. 무인 운영을 위해 Seat 진입점이 agent 모드로 시작할 때 자기 worktree를 agy CLI 설정(`~/.gemini/antigravity-cli/settings.json`의 `trustedWorkspaces`)에 넣습니다 (사용자 승인 2026-10-12). 다른 설정은 바꾸지 않고, 이미 있으면 쓰지 않으며, 설정 파일이 깨져 있으면 건드리지 않습니다.

## 시험

```bash
.venv/bin/python -m pytest tests/test_department.py                       # 명단, sandbox 프로필, deptctl 권한
CHIPDEPT_RIG_TEST=1 .venv/bin/python -m pytest tests/test_department.py   # + OpenRig로 올린 rig에서 완료 기준
```

rig 시험은 Seat를 셸 모드로 띄우고, 파이프라인은 가짜 agent로 돌립니다. 확인하는 것:
- DV Seat가 Verifier 테스트를 읽으면 거부, Seat가 저장소 상태나 저장소 원본에 쓰면 거부, 자기 worktree에서 커밋은 가능, 환류 명령은 Design-lead 밖에서 거부
- Seat가 파이프라인 API에 직접 쓰기 요청을 보내면 401, 게이트웨이 토큰과 다른 Seat의 키는 못 읽음, Seat는 승인하지 못함
- 실행 중에 RTL Engineer, Chip-lead Seat와 API 서버, 게이트웨이 노드를 초기화해도 실행이 끝까지 감
- 스냅숏을 남기고 내린 뒤 복구하면 Seat에 sandbox가 다시 걸리고 실행 기록이 남아 있음

## 아직 없는 것

- 폐쇄망 설치 (사내 npm 미러, 외부 호출 차단): [P0 X5 기록](../experiments/p0/x5_offline_install/README.md)의 확인 목록을 따름
- Linux 서버의 격리: macOS `sandbox-exec` 대신 계정 분리나 bubblewrap
- Sanity 연동 (E3 결과, DCLint, EPC 래퍼): E3는 이번 구현에서 제외. 사내 툴 리포트는 양식 파일로 받음 (`config/report_formats/`)
