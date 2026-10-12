# 게이트웨이와 Web UI

파이프라인 API와 OpenRig 데몬 앞에 두는 다중 사용자 게이트웨이입니다. 사람은 Web UI로, Seat는 `deptctl`(API 키)로 들어옵니다.
모델은 직접 부르지 않습니다. 설계 근거는 [ARCHITECTURE.md](../ARCHITECTURE.md) 6, 7, 9절입니다.

## 구성

| 파일 | 내용 |
| --- | --- |
| `auth.py` | 인증 제공자 인터페이스(`AuthProvider`)와 자체 계정(`LocalAuth`, PBKDF2-SHA256). 세션(12시간)과 API 키는 해시만 저장. SSO로 바꿀 때는 제공자 하나를 더함 |
| `perms.py` | 역할 5개와 권한, `design_lead` 능력 |
| `db.py` | SQLite: 사용자, 세션, API 키, 승인 기록, SPEC 작업 공간과 판, 질문 답, 실행 대응, 판정, 감사 기록 |
| `clients.py` | 파이프라인 API(게이트웨이 토큰과 역할을 붙임), OpenRig 데몬 API(Seat 상태 조회) |
| `specws.py` | SPEC 작업대 |
| `service.py` | 승인함과 승인 기록, 실행 제출과 상세, 판정, 환류 |
| `server.py`, `__main__.py` | HTTP 서버(`/api/*`와 Web UI 정적 파일), CLI |
| `ui/` | Web UI (React, TypeScript, Vite). 외부 글꼴이나 CDN을 쓰지 않음 (폐쇄망) |

## 역할과 권한

| 역할 | 할 수 있는 것 |
| --- | --- |
| 관리자 (admin) | 사용자와 API 키 관리, 감사 기록 |
| 설계 (design) | SPEC 작업 공간 만들기와 고치기, 검사 질문 답, SPEC 고정 요청, 실행 제출 |
| 검증 (verification) | DV 검증 완료 판정 (RTL Freeze 자료) |
| 구현 (implementation) | PI 구현 가능성 판정 (RTL Freeze 자료) |
| 승인자 (approver) | 승인과 반려 다섯 가지. 사람 계정만 (Seat 계정은 승인자가 될 수 없음) |

모든 역할이 조회할 수 있습니다. 환류 제출은 설계 역할에 `design_lead` 능력이 있어야 합니다 (수정 요구의 단일 창구).

## 승인

| 승인 | 조건 | 결과 |
| --- | --- | --- |
| SPEC 고정 | 설계가 고정을 요청함 (SPEC 검사 통과, 질문에 모두 답함) | 그 판(sha)이 고정됨. 실행은 고정된 판으로만 제출 |
| 최종 승인 | 실행이 통과함 | |
| RTL Freeze | 최종 승인 + DV 검증 완료 판정과 PI 구현 가능성 판정이 모두 pass | |
| 기댓값 변경 | 파이프라인이 Arbiter의 test_wrong을 승인 대기로 등록함 | 파이프라인에 결정을 넘기고 실행이 이어짐 |
| SPEC 변경 요청 | Design-lead가 환류로 냄 | 파이프라인에 결정을 넘김. 승인이면 영향 모듈만(또는 처음부터) 다시 실행 |

모든 결정은 `approvals`에 누가, 언제, 역할, SPEC 버전, 실행 ID, 요구사항 ID, 메모와 함께 남고, 감사 기록에도 남습니다.

## 화면 (1차)

| 화면 | 내용 |
| --- | --- |
| 실행 | 실행 목록과 승인 상태 |
| 실행 상세 (읽기 전용) | 개요(승인과 판정), 모듈 트리와 후보별 진행, 검토 항목, 실패 분류, RTL과 IR 노드 대응(줄을 누르면 소스맵으로 노드를 보여 줌), 에이전트 작업별 과제, 출력, transcript |
| SPEC 작업대 | 원본(PDF 쪽 그림 또는 Markdown)과 변환 결과 대조와 고치기(판 관리), 원본 그림과 WaveJSON 렌더링 대조, 검사 질문 답하기, 고정 요청, 고정된 SPEC으로 실행 제출 |
| 승인함 | 대기 항목(승인자만 승인과 반려 가능)과 승인 기록 |
| 환류 | 네 가지 양식(검사 실패 리포트, SPEC 변경 요청, 생성기 버그, 설정 변경)과 이력. 자유 텍스트로 수정을 요청하는 경로는 없음 |
| Seat | OpenRig 데몬에서 읽은 Seat 상태 |

transcript는 에이전트 실행기가 남긴 시도별 표준 출력 끝부분(1500자)입니다.

## 파이프라인 API와의 관계

파이프라인 API는 게이트웨이 토큰(`<게이트웨이 홈>/api_token`)이 있는 쓰기 요청만 받습니다. Seat가 게이트웨이를 건너 직접 쓰기 요청을 보내면 역할을 밝혀도 거부됩니다(401).
게이트웨이는 사용자 권한을 확인한 뒤 파이프라인 역할(rtl-engineer, design-lead, chip-lead)을 붙여 보냅니다.

## 설치와 실행

```bash
cd gateway/ui && npm ci && npm run build && cd ../..   # Web UI 빌드 (dist/)
python3 -m gateway init --admin admin                  # DB, 파이프라인 API 토큰, 관리자 (비밀번호는 표준 입력)
python3 -m gateway user add kim --roles design --caps design_lead
python3 -m gateway user add park --roles approver
python3 -m gateway seats                               # Seat 계정과 Seat별 API 키 (부서 계층)
python3 -m gateway serve --port 8750
```

| 환경 변수 | 기본값 |
| --- | --- |
| `CHIPDEPT_GATEWAY_HOME` | `~/.cache/chip-design-department/gateway` |
| `CHIPDEPT_API` | `http://127.0.0.1:8740` |
| `CHIPDEPT_STORE` | `~/.cache/chip-design-department/dept/store` (실행 상세를 읽음) |
| `OPENRIG_URL` | `http://127.0.0.1:7533` |

부서 계층(`department/dept.py up`)은 게이트웨이를 infra Pod의 노드로 띄우고, 올리기 전에 `seats`를 실행합니다.

## 시험

`tests/sim/test_gateway.py`: 실제 HTTP(쿠키, API 키)로 인증과 요청 위조 방지, 승인 다섯 가지(승인자만, 모두 기록), SPEC 작업대(PDF와 WaveJSON 포함), 실행 상세, 환류 양식을 봅니다. 파이프라인은 가짜 agent로 돕니다.

## 아직 없는 것

- 사내 SSO (인증 제공자로 더함)
- 대화 중계 (OpenRig 데몬 API로 Seat에 전달. 지금은 Seat 상태 조회만)
- 승인된 RTL의 읽기 전용 브랜치
- 2차 화면 (대시보드, 환류 관리, 리포트), 3차 화면 (조직과 Seat, 설정, 사용자 관리 화면)
