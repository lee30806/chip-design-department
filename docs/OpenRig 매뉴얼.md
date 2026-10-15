# OpenRig 매뉴얼

Oct 15, 2026 · @Seungjoon Lee

이 프로젝트에서 OpenRig를 설치하고 운영하는 방법입니다. 일반 사용법은 OpenRig 공식 문서([openrig.dev](https://openrig.dev), 저장소 [docs/reference](https://github.com/mvschwarz/openrig/tree/v0.6.10/docs/reference))를 정리했고, 이 프로젝트에 맞춘 운영 방법은 [department/README.md](../department/README.md)와 [P0 X5 기록](../experiments/p0/x5_offline_install/README.md)을 따랐습니다.

> **버전.** 이 매뉴얼은 OpenRig **0.6.10** 기준입니다. 명령과 옵션은 0.6.10의 `--help`로 확인했습니다. 문서와 `--help`가 다르면 `--help`를 따릅니다. 이 프로젝트의 운영 스크립트(`department/dept.py`)와 [department/README.md](../department/README.md)는 아직 0.6.6을 설치하도록 되어 있습니다. 부서 rig를 0.6.10으로 올리는 방법은 [0.6.10으로 올리기](#10-부서-rig를-0610으로-올리기)에 있습니다.

## 1. OpenRig란

OpenRig는 여러 coding agent(Claude Code, Codex, Pi 등)를 tmux 세션으로 나란히 띄우는 도구입니다. 로컬 데몬이 이 agent들의 토폴로지, 메시지, 작업 큐, 상태를 보관합니다. agent 세션이 오래 유지되므로, 맥락을 이미 아는 agent에게 다음 일을 보낼 수 있습니다. 사람은 lead agent(operator)와 대화하고, operator가 전문 agent에게 일을 나눠 주고 진행을 추적합니다.

| 용어 | 뜻 |
| --- | --- |
| 데몬 | 로컬 제어면. HTTP API(기본 포트 7433)로 rig, 세션, 큐, 스냅숏을 관리. tmux 위에서 동작 |
| rig | agent 팀 하나. RigSpec(`rig.yaml`)으로 정의 |
| pod | rig 안의 묶음. 연속성 정책과 startup 설정을 pod 단위로 둠 |
| member, seat | pod 안의 agent 자리 하나. 논리 ID는 `<pod>.<member>`, 세션 주소는 `<pod>-<member>@<rig>` (예: `dev-build@starter`) |
| runtime | seat를 돌리는 하니스. `claude-code`, `codex`, `pi`, `omp`, `terminal`(셸만 띄움) |
| edge | seat 사이의 관계. `delegates_to`, `escalates_to`, `collaborates_with`, `can_observe`, `spawned_by`. 조율을 위한 표시일 뿐이며 접근을 막지 않음 |
| kernel | 데몬이 시작될 때 함께 뜨는 OpenRig의 기본 rig. operator, advisor, queue worker가 있음 |
| operator | kernel의 대화 상대. 목표를 받아 팀을 추천하고, 동의를 받아 시작하고, 팀 lead에게 일을 넘김 |
| OpenRig 뷰 | operator, 대시보드(TUI), advisor를 한 터미널 창에 보여 주는 화면. `rig terminal open saved:kernel --window`로 염 |
| `rig send` | seat의 터미널에 메시지를 입력. 추적하지 않는 질문이나 알림에 씀 |
| `rig queue` | 주인이 있는 작업. 받는 seat가 claim하고, 진행과 handoff 이력이 남음 |
| `rig scope` | 디스크에 남는 작업 기록(mission, slice). 만들어도 일이 시작되지는 않음 |
| `rig workflow` | 다음 단계를 누가 할지 정하는 실행 중 인스턴스 |
| 스냅숏 | rig의 토폴로지와 세션 상태를 저장한 복구 지점 |

**메시지와 큐의 차이.** `rig send`는 대화를 시작할 뿐이고, 일의 소유와 결과는 큐와 저장소 산출물에 남습니다. 메시지가 전달되었다고 해서 일이 끝난 것은 아닙니다.

**시작과 준비는 다릅니다.** 데몬이 떠 있어도 kernel이나 각 seat가 준비되었다는 뜻은 아닙니다. kernel 상태는 `rig status`의 `Kernel:` 줄, seat 상태는 `rig ps --nodes --rig <rig>`로 따로 확인합니다.

## 2. 이 프로젝트에서 OpenRig가 하는 일

이 프로젝트의 부서 계층(Chip Design Department)은 OpenRig rig 하나(`chip-dept`)로 운영됩니다. 설계 근거는 [ARCHITECTURE.md](../ARCHITECTURE.md) 3절과 8절, [Chip Design Department 설계](Chip%20Design%20Department%20설계.md)에 있습니다.

| 항목 | 이 프로젝트의 방식 |
| --- | --- |
| rig 정의 | [department/rig.yaml](../department/rig.yaml). Pod 4개(총괄 `lead`, `design`, `dv`, `pi`)와 Seat 15개, infra Pod(파이프라인 API 서버, 게이트웨이) |
| Seat 런타임 | 모두 `runtime: terminal` 노드. 시작하면 `bin/seat <pod.member>`가 Seat별 sandbox 프로필로 감싼 agent(또는 시험용 셸)로 바뀜 |
| 권한 | OpenRig의 edge나 permission policy가 아니라 OS sandbox(`sandbox-exec`)와 게이트웨이로 강제. edge는 보고와 위임 관계만 나타냄 |
| kernel | 쓰지 않음. 데몬을 `--no-kernel`로 시작 |
| 사람과 Seat의 대화 | Web UI → 게이트웨이 → OpenRig 데몬 API → Seat. 게이트웨이가 보낸 사람과 메시지 ID를 붙여 `--raw`로 보내고, 응답은 transcript에서 메시지 ID로 찾음 |
| 파이프라인 에이전트 | OpenRig에 등록하지 않는 headless 실행. Seat와 메시지를 주고받지 않음 |
| 복구 | `rig down --snapshot`과 `rig up <rig>`. 안 되면 `rig.yaml`로 새로 띄움. Seat 상태는 세션이 아니라 worktree와 파이프라인 저장소에 있음 |

OpenRig의 조율은 메시지와 규범에 기반합니다. 그래서 접근 제어는 OpenRig에 맡기지 않고 sandbox, 작업 디렉터리 권한, 파이프라인 툴로 강제합니다.

## 3. 설치

### 요구사항

- macOS 또는 Linux. Windows는 WSL2만 지원하며 자동 시험은 하지 않음 (Linux 파일 시스템에 설치, Linux용 Node.js와 하니스 사용)
- Node.js 22 또는 24 (Apple silicon은 22). 20과 홀수 버전은 지원하지 않고, 26 이상은 시험하지 않음
- tmux. `tmux -V`가 `next-3.4`를 출력하는 배포판 tmux는 `capture-pane`에서 서버가 죽음 ([문제 해결](#9-문제-해결) 참고)
- 사용할 하니스(Claude Code, Codex 중 하나 이상)의 로그인. 두 계정이 다 필요하지는 않음

### 일반 설치

**스크립트 한 번으로.** Node.js와 npm이 있어야 합니다. `--dry-run`은 계획만 출력하고 아무것도 바꾸지 않습니다.

```bash
curl -fsSL https://raw.githubusercontent.com/mvschwarz/openrig/v0.6.8/scripts/install.sh | sh -s -- --dry-run
curl -fsSL https://raw.githubusercontent.com/mvschwarz/openrig/v0.6.8/scripts/install.sh | sh
```

스크립트는 최신 `@openrig/cli`를 `npm install -g`로 설치하고, Node.js와 SQLite 확인, `rig setup --dry-run`, `rig setup`을 차례로 실행합니다. 실패한 단계는 `FAILED [n/4] <명령> (exit <코드>)`로 출력됩니다. 남은 실패가 하니스 로그인뿐이면 설치는 끝난 것이므로, 로그인한 뒤 데몬 시작으로 넘어갑니다.

**단계별로.**

```bash
npm install -g @openrig/cli@0.6.10
rig preflight                         # Node, tmux, 데몬 포트, 상태 폴더
rig doctor                            # 설치, 의존성, 쓰기 경로, 로그인
claude --version && claude auth status   # Claude Code를 쓸 때. 로그인: claude auth login
codex --version && codex login status    # Codex를 쓸 때. 로그인: codex login
rig setup --dry-run
rig setup --providers claude          # 쓸 하니스만: claude, codex, both
```

| `rig setup` 옵션 | 뜻 |
| --- | --- |
| `--providers <claude\|codex\|both>` | 고른 하니스만 확인하고, 없으면 설치. 고르지 않은 쪽은 실패가 아니라 건너뜀 |
| `--no-herdr` | Herdr(기본 설치) 생략. OpenRig 뷰는 plain tmux로 열림 |
| `--ghostty`, `--no-ghostty` | macOS에서 Ghostty 설치 여부. 생략하면 Terminal.app 사용 |
| `--full` | 더 넓은 작업 도구 설치 |
| `--policy <이름> --spec <rig.yaml>` | 기존 spec에 permission policy 기록 |

`rig setup`은 macOS에서 기존 Homebrew로 빠진 tmux를 설치하고, `~/.tmux.conf`에 관리 블록(마우스 켜기, 긴 기록)을 씁니다. npm 11 이상에서 `npm warn install-scripts`가 나오면 postinstall 확인만 건너뛴 것입니다. `node "$(npm root -g)/@openrig/cli/scripts/check-abi.mjs"`로 따로 실행합니다.

**agent에게 맡기기.** 0.6.7부터 데몬이 시작될 때 `rigs` skill을 `~/.claude/skills`와 `~/.agents/skills`에 설치합니다. 그 전이라면 `npx skills add mvschwarz/openrig --skill rigs`로 추가한 뒤 Claude Code에 "OpenRig 설치해줘"라고 요청하면, skill이 설치부터 operator에게 넘기는 단계까지 진행합니다.

### 데몬과 kernel 시작

```bash
rig daemon start          # 멈춰 있을 때만. kernel도 함께 뜸
rig status                # Kernel: 줄로 kernel 상태 확인
rig ps --nodes --rig kernel
```

- `rig setup`은 데몬을 시작하지 않습니다. 데몬 시작(`rig daemon start`, 또는 `rig up`이나 `rig context add` 중의 암묵적 시작)이 kernel을 띄웁니다.
- 처음 시작할 때는 로그인된 하니스에 맞춰 kernel 구성을 고릅니다 (Claude만, Codex만, 둘 다).
- `rig daemon start --wait-for-kernel`은 kernel 준비까지 기다립니다. `--no-kernel`은 자동화용이며 operator 없이 시작합니다.
- 하니스가 하나도 로그인되어 있지 않으면 kernel이 `auth_blocked`를 보고합니다.

### OpenRig 뷰 열기

```bash
rig terminal open saved:kernel --window
```

새 터미널 창이나 탭에 operator, 대시보드, advisor를 엽니다.

- 120열 미만이면 operator가 첫 페이지를 채우고, 120열 이상이면 대시보드와 operator가 반씩 나눕니다. advisor는 별도 탭이나 tmux 창에 있습니다.
- Herdr가 있으면 Herdr로, 없으면 plain tmux로 엽니다 (`--provider tmux --window`로 지정 가능). plain tmux에서는 **Ctrl-b, w**로 `view-*` 창을 고릅니다.
- macOS에서 Claude Desktop, iTerm, VS Code에서 실행하면 Ghostty(1.3 이상) 새 창이나 Terminal.app을 엽니다. 처음 한 번 macOS의 Automation 권한을 묻는데, 허용하면 됩니다.
- 창을 닫거나 **Ctrl-b, d**로 빠져나와도 agent 대화는 계속 돕니다. 같은 명령으로 다시 엽니다.
- SSH나 화면이 없는 환경에서는 창을 열 수 없습니다. 출력된 `run:` 명령을 자기 터미널에서 실행하거나, operator 세션에 직접 붙습니다.

```bash
rig ps --nodes --rig kernel --json --fields logicalId,canonicalSessionName,tmuxAttachCommand
env -u TMUX <operator.agent의 tmuxAttachCommand>
```

창을 열 수 없을 때만 `rig tui --shared`(대시보드만, operator 대화는 없음)를 씁니다.

### 시작 TUI

일반 터미널에서 `rig`만 입력하면 시작과 작업 TUI가 열립니다.

| 키 | 동작 |
| --- | --- |
| Enter | 데몬이 멈춰 있으면 시작. 이전에 쓰던 seat는 이전 대화로 복구 시도 |
| **S** | 작업 화면에서 시작 화면으로 |
| **f** | 그 seat를 새 대화로 시작하는 결정 (Esc로 취소) |
| **o** | seat의 실제 터미널 열기 (로그인, 신뢰 질문에 답할 때) |
| **c** | 멈췄던 startup 맥락 전달 마치기 (`rig seat continue <seat>`와 같음) |
| **r**, **d**, **?** | 다시 읽기, 자세히, 도움말 |
| **L** | 로컬 spec, 프로젝트, mission과 slice 파일 읽기 |

TUI에서 데몬을 시작하면 kernel을 자동으로 띄우지 않고, 띄울 rig와 seat를 고르게 합니다.

### OpenRig가 만드는 파일

| 위치 | 파일 |
| --- | --- |
| rig 작업 디렉터리 (`cwd`) | `AGENTS.md`(관리 블록). `claude-code` 런타임이면 `CLAUDE.md`도. 팀의 skill과 plugin |
| `HOME` | `~/.codex/config.toml`의 hooks 설정, `~/.claude/skills`와 `~/.agents/skills`의 `rigs` skill, `~/.tmux.conf`의 관리 블록(`rig setup`) |

전체 목록은 [OpenRig README](https://github.com/mvschwarz/openrig#what-openrig-changes-on-your-machine)에 있습니다.

### 이 프로젝트용 격리 설치

데몬은 `~/.codex/config.toml`, `~/.claude/skills`, `~/.claude/plugins/cache`를 직접 읽고 씁니다. 부서 rig는 사용자 설정을 건드리지 않도록 OpenRig를 전용 prefix에 설치하고, `dept.py`가 `HOME`, `OPENRIG_HOME`, tmux 소켓, 포트를 따로 지정해 실행합니다.

```bash
npm install --prefix ~/.cache/chip-design-department/openrig @openrig/cli@<버전>
node ~/.cache/chip-design-department/openrig/node_modules/@openrig/cli/scripts/check-abi.mjs
```

`<버전>`은 지금 운영 스크립트가 기대하는 0.6.6입니다. 0.6.10으로 바꾸는 절차는 [10절](#10-부서-rig를-0610으로-올리기)에 있습니다.

`dept.py`가 데몬에 넘기는 격리 환경은 다음과 같습니다.

| 변수 | 값 | 이유 |
| --- | --- | --- |
| `HOME` | `$CHIPDEPT_OPENRIG/home` | 데몬과 Seat가 사용자 홈의 설정 파일을 쓰지 않게 함 |
| `OPENRIG_HOME` | `$CHIPDEPT_OPENRIG/orhome` | 데몬 DB와 Seat 상태 |
| `TMUX_TMPDIR` | 짧은 경로 | 소켓 경로가 길면 Unix 소켓 길이 제한(macOS 104자, Linux 108자)에 걸려 데몬이 tmux를 못 씀 |
| `OPENRIG_PORT` | `7533` | 사용자의 기본 데몬(7433)과 겹치지 않게 |
| `DISABLE_AUTOUPDATER` | `1` | Claude Code Seat가 실행 중에 스스로 업데이트하는 것을 막음 |

`CHIPDEPT_OPENRIG`의 기본값은 `~/.cache/chip-design-department/openrig`입니다. 나머지 `CHIPDEPT_*` 경로는 [department/README.md](../department/README.md#경로)에 있습니다. 격리 환경에서는 `HOME`이 바뀌므로 사용자 홈에는 쓰지 않습니다. 저장소 안에 생기는 `AGENTS.md`는 `.gitignore`에 넣습니다.

## 4. 이 프로젝트의 운영 명령

부서 rig는 `department/dept.py`로 다룹니다. 이 스크립트가 격리 환경을 만든 뒤 `rig` CLI를 부릅니다.

```bash
python3 department/dept.py up [--mode agent|shell] [--api-args "..."]   # 데몬을 격리 환경으로 다시 시작(--no-kernel)하고 rig를 올림
python3 department/dept.py status                                      # rig ps --nodes --rig chip-dept
python3 department/dept.py reset design.rtl                            # Seat 세션만 새로 시작 (진행 중인 실행은 그대로)
python3 department/dept.py run design.rtl 'ls'                         # shell 모드 Seat에 명령을 보내고 출력을 읽음
python3 department/dept.py snapshot-down                               # 스냅숏을 남기고 내림
python3 department/dept.py recover                                     # 스냅숏에서 복구. 안 되면 rig.yaml로 새로 띄움
python3 department/dept.py down                                        # rig 기록 삭제(--delete --force)와 데몬 중지
python3 department/dept.py rig <rig 인자...>                           # 격리 환경에서 rig CLI를 그대로 실행
```

**`rig`를 직접 부르지 않습니다.** 맨 `rig` 명령은 사용자의 `HOME`과 기본 포트 7433의 데몬을 봅니다. 부서 rig를 보려면 항상 `dept.py rig ...`를 씁니다.

```bash
python3 department/dept.py rig ps --nodes --rig chip-dept
python3 department/dept.py rig capture design-rtl@chip-dept
python3 department/dept.py rig transcript design-rtl@chip-dept
```

Seat 세션 이름은 `<pod>-<member>@chip-dept`입니다 (`seatlib.session`).

**데몬부터 새로 띄우는 이유.** Seat는 데몬의 환경 변수를 물려받습니다. 그래서 `up`은 데몬을 멈추고, 이 환경으로 다시 시작한 다음 rig를 올립니다. 이미 떠 있는 데몬에 rig만 올리면 Seat에 `CHIPDEPT_*` 경로가 전달되지 않습니다.

**복구 절차.** `recover`는 먼저 `rig up chip-dept`로 최근 스냅숏에서 되살립니다. Seat를 새로 띄운 뒤에는 OpenRig가 스냅숏의 점유자가 옛것이라며 거부하는데, 그때는 `rig.yaml`로 새로 띄웁니다. Seat 상태는 worktree와 파이프라인 저장소에 있으므로 어느 쪽이든 결과가 같습니다.

**게이트웨이 연결.** 게이트웨이는 `OPENRIG_URL`(기본 `http://127.0.0.1:7533`)의 데몬 API를 씁니다. 격리 데몬의 포트를 바꾸면 이 값도 같이 바꿉니다.

**시험.**

```bash
.venv/bin/python -m pytest tests/test_department.py                       # 명단, sandbox 프로필, deptctl 권한
CHIPDEPT_RIG_TEST=1 .venv/bin/python -m pytest tests/test_department.py   # OpenRig로 올린 rig에서 완료 기준까지
```

OpenRig 없이 도는 시험은 `tests/fake_rig.py`(가짜 `rig` CLI: `send`, `transcript`, `ps`)를 씁니다.

## 5. 자주 쓰는 rig 명령

부서 rig에 쓸 때는 앞에 `python3 department/dept.py`를 붙입니다.

### 상태 보기

| 명령 | 용도 |
| --- | --- |
| `rig status` | 데몬과 kernel 상태 |
| `rig ps` | rig 목록. `--json`으로 기계 판독 |
| `rig ps --nodes --rig <rig>` | seat별 상태와 startup 주의 사항. `--full`, `--fields logicalId,canonicalSessionName,tmuxAttachCommand` |
| `rig capture <seat>` | seat 터미널 화면 읽기 |
| `rig transcript <session>` | seat의 transcript 출력 |
| `rig tui` | 상태 대시보드 (agent 대화가 아님). `--shared`는 kernel의 대시보드에 붙음 |
| `rig terminal open <rig\|saved:kernel> --window` | rig의 seat를 터미널 타일로 열기 |
| `rig doctor [--spec rig.yaml]` | 설치 진단. `--spec`은 선언과 실행 중 토폴로지 비교 |
| `rig daemon status`, `rig daemon logs` | 데몬 상태와 로그 |
| `rig seat status <seat>` | seat 상태와 선택된 권한 |
| `rig whoami --json` | 지금 세션이 어느 seat로 붙어 있는지 |

### 대화와 작업

| 명령 | 용도 |
| --- | --- |
| `rig send <seat> '<본문>'` | seat 터미널에 메시지 입력. OpenRig는 From/To 봉투를 붙임 |
| `rig send <seat> '<본문>' --raw` | 봉투 없이 그대로 입력. 이 프로젝트의 게이트웨이와 `dept.py run`이 씀 |
| `rig send ... --wait-for-idle <초>`, `--verify` | 대기 상태가 된 뒤 보내기, 전달 확인 |
| `rig send --pod <pod>`, `--rig <rig>`, `--to a,b` | 여러 seat에 보내기 |
| `rig queue create --source <나> --destination <seat> --body-file <파일> --summary '<요약>'` | 주인이 있는 작업 만들기. 만든 뒤 `rig send`로 알림 |
| `rig queue list --destination <seat> -a` | 그 seat의 작업 (`-a`는 끝난 것 포함) |
| `rig queue show <id> --full`, `rig queue transitions <id>` | 작업 내용과 상태 이력 |
| `rig queue handoff <id> --to <seat> --body-file <파일>` | 작업 넘기기. 다음 작업은 `handedOffFrom`으로 찾음 |
| `rig queue block <id> --on <blocker-id> --continuation '<이어서 할 일>'` | 다른 작업을 기다리는 상태로 두기 |
| `rig watchdog register --policy periodic-reminder --target-session <seat> --interval-seconds <초> --registered-by <나>` | 대기 중인 일을 주기적으로 깨우는 알림 |
| `rig scope --workspace <경로> mission create <이름> --intent '<의도>'` | mission(디스크 기록) 만들기. slice는 `rig scope slice create` |
| `rig workflow specs`, `rig workflow instantiate <이름> --root-objective '<목표>' --created-by <나>` | 반복되는 조율을 workflow로 실행 |
| `rig attach --self --rig <rig> --pod <pod> --member <이름> --runtime <claude-code\|codex> --print-env` | 지금 세션을 rig의 새 member로 붙이기 |

### 수명주기

| 명령 | 용도 |
| --- | --- |
| `rig daemon start [--no-kernel] [--wait-for-kernel]`, `rig daemon stop` | 데몬 시작, 중지. 중지는 agent tmux 세션을 남김 |
| `rig start --last` | 데몬을 시작하고 마지막에 돌던 rig를 모두 복구 |
| `rig specs ls --kind rig`, `rig specs preview <이름> --kind rig` | 내장 팀 목록과 구성 미리 보기 |
| `rig up <spec\|이름\|GitHub 링크> --cwd . --plan` | 실행 계획 미리 보기 (바꾸지 않음) |
| `rig up <spec> [--cwd <경로>] [--yes] [--non-interruptive]` | rig 시작 |
| `rig up <rig> --existing [--fresh <seats...>]` | 기존 rig를 스냅숏에서 복구. 지정한 seat만 새 대화로 시작 |
| `rig down <rig> [--snapshot] [--delete] [--force]` | rig 내리기. 스냅숏 남기기, 기록 삭제, 즉시 종료 |
| `rig seat launch <seat> --stop --fresh --reason '<이유>'` | seat 하나만 새 점유자로 다시 시작 (`dept.py reset`이 씀) |
| `rig seat stop <seat>`, `rig seat clean <seat>` | 살아 있는 seat 하나 멈추기, 죽은 seat를 다시 띄울 수 있게 정리 |
| `rig seat continue <seat>` | seat가 로그인, 신뢰, bypass 경고에서 멈췄다가 답한 뒤 startup 맥락을 같은 대화에 전달 |
| `rig seat set-model <seat> --model <id> --reason '<이유>'` | seat의 모델 변경 (다음 복구부터 적용) |
| `rig grow <rig> <이름...> --pod <pod> --runtime <runtime> --cwd <경로>` | 실행 중인 rig에 seat 추가 (YAML 수정 없이) |
| `rig snapshot <rig>`, `rig restore` | 스냅숏 관리와 복구 |

**전부 멈추기.** `rig ps --json`으로 rig를 확인하고 각각 `rig down`합니다. kernel은 마지막에 내립니다. kernel을 내리면 operator도 끝나므로, 마지막 `rig daemon stop`은 자기 셸에서 실행합니다. 데몬이 이미 멈춰 있으면 `rig daemon start --no-kernel`로 API만 살린 뒤 남은 rig를 내립니다.

## 6. RigSpec 요점

RigSpec 0.2(pod-aware) 형식입니다. 전체 필드는 [rig-spec.md](https://github.com/mvschwarz/openrig/blob/v0.6.10/docs/reference/rig-spec.md)에 있습니다.

```yaml
version: "0.2"
name: chip-dept
summary: ...
culture_file: CULTURE.md        # rig 공통 규범
docs:
  - path: README.md
# permission_policy: builtin:yolo   # rig 단위 권한 (claude-code, codex member에 적용)
# non_interruptive: true            # full bypass seat의 첫 실행 경고 넘기기
pods:
  - id: design
    label: Design
    continuity_policy:          # 내리기 전 세션 기록과 복구 요약 남기기
      enabled: true
      sync_triggers: [pre_shutdown]
      artifacts: { session_log: true, restore_brief: true }
      restore_protocol: { peer_driven: false, verify_via_quiz: false }
    members:
      - id: rtl
        label: "RTL Engineer"
        agent_ref: "builtin:terminal"
        profile: none
        runtime: terminal
        cwd: "."
        startup:
          actions:
            - type: send_text   # 셸이 준비되면 Seat 진입점으로 바꿈
              value: "exec ./bin/seat design.rtl"
              phase: after_ready
              idempotent: true
    edges: []
edges: []                       # pod 사이 edge
```

- **이름.** member는 `<pod>.<member>` 논리 ID와 `<pod>-<member>@<rig>` 세션 이름을 갖습니다. edge, startup 지시, workflow 대상에서 같은 이름을 씁니다.
- **런타임별 필드.** `claude-code`와 `codex` member에는 `model`, `permission_policy`, `codex_config_profile`, `restore_policy`(예: `resume_if_possible`)를 둘 수 있습니다. 이 프로젝트의 `terminal` member에는 해당하지 않습니다.
- **startup.** rig, pod, member 단위로 `files`(지침 파일 전달)와 `actions`(입력 보내기 등)를 둡니다.
- **services.** compose 서비스, 대기 대상, URL과 명령 표면, 체크포인트를 rig와 함께 관리합니다.
- **내장 spec 고치기.** 내장 팀(예: starter)을 고칠 때는 `rig specs show starter --kind rig`로 경로를 찾고, `specs` 디렉터리 전체를 저장소의 `./openrig-specs`로 복사해서 고칩니다. `rig.yaml`만 복사하면 상대 경로 참조가 깨집니다.

## 7. 권한

### 기본 동작 (claude-code, codex seat)

| 하니스 | 기본 실행 | 팀 기본값 (policy나 seat별 선택이 없는 seat) |
| --- | --- | --- |
| Claude Code | `--permission-mode acceptEdits`. 편집은 진행하고 나머지는 네이티브 규칙과 확인을 따름 | 일반 `rig` 명령, 프로젝트 읽기, 흔한 시험은 확인 없이 실행. `rig up`, `rig down` 같은 수명주기 명령은 확인. 설정 파일에는 쓰지 않음 |
| Codex | `-s workspace-write`. 승인 정책은 네이티브 설정을 따름 | OpenRig 작업 공간 루트와 pod 상태 디렉터리를 쓰기 허용. Codex 설정이 막지 않으면 sandbox 안 네트워크(로컬 데몬 접근) 허용. 끄려면 `[sandbox_workspace_write]`에 `network_access = false` |

kernel의 seat는 더 넓은 운영용 기본값을 받습니다.

### rig와 seat 단위 선택

| 명령 | 효과 |
| --- | --- |
| `rig policy permissions list`, `show`, `current --spec <rig.yaml>` | 정책 목록과 spec에 실제로 적용될 정책 보기. `rig policy list/show/current/apply`도 같은 동작 |
| `rig policy apply yolo --spec <rig.yaml>` | `permission_policy: builtin:yolo` 기록. Claude는 `--dangerously-skip-permissions`, Codex는 `-s danger-full-access -a never` |
| `rig policy apply auto --spec <rig.yaml>` | Claude는 `--permission-mode auto`, Codex와 Pi는 기본 실행 |
| `rig policy apply none --spec <rig.yaml>` | 팀 허용 없이 `acceptEdits`만 |
| `rig seat set-permissions <seat> --mode <floor\|full_bypass\|inherit> --reason '<이유>'` | seat 하나의 다음 실행 권한 선택. 다시 띄우지는 않음. `inherit`은 선택을 지우고 rig 정책을 따름 |

- 우선순위는 seat 선택 > member `permission_policy` > rig `permission_policy` > 팀 기본값입니다.
- Codex는 named profile(`~/.codex/<이름>.config.toml`)을 만들고 member에 `codex_config_profile: <이름>`을 두는 방법도 있습니다.
- `rig up <spec> --non-interruptive`는 full bypass seat의 첫 실행 경고(Claude의 bypass 경고, Codex의 full-access와 GPT-5.1 안내)를 실행 플래그로 넘깁니다. 설정 파일에는 쓰지 않고, 선택은 rig에 저장됩니다. 끄려면 `rig down` 뒤 `rig up <rig> --existing --no-non-interruptive`. 새 rig의 기본값은 `rig config set launch.non_interruptive true`로 정합니다.
- 실행 중인 seat에는 정책 변경이 바로 적용되지 않습니다. 그 대화의 네이티브 `/permissions`로 바꾸거나, 같은 seat를 멈췄다 복구합니다. 중복 seat를 새로 띄워 해결하지 않습니다.
- OpenRig는 정책을 기록할 뿐이고, 실제 허용과 거부는 하니스의 네이티브 권한과 관리 설정이 강제합니다. 정해진 OpenRig 명령만 네이티브 설정에 허용으로 기억시키는 절차는 `rig context get skills/applying-a-permission-policy/SKILL.md`에 있습니다.

### 이 프로젝트

Seat가 `terminal` 런타임이므로 위의 정책과 seat별 선택은 Seat에 적용되지 않습니다. 권한은 `bin/seat`가 거는 sandbox 프로필과 게이트웨이가 강제합니다. 규칙과 시험 항목은 [department/README.md](../department/README.md#seat와-권한)에 있습니다. rig.yaml에 `permission_policy`를 추가해도 Seat 권한은 넓어지지도 좁아지지도 않습니다.

## 8. 팀으로 이 저장소 개발하기

이 저장소의 개발 작업 자체를 OpenRig 팀에 맡길 때의 공식 흐름입니다. 부서 rig와는 별개이며, 사용자 기본 데몬(7433)에서 돕니다.

### 팀 고르기

OpenRig 뷰에서 operator에게 목표, 저장소 경로, 브랜치를 알리면, operator가 팀 셋 중 하나를 추천하고 동의를 받아 시작합니다. 직접 고를 때는 `rig specs ls --kind rig`와 `rig specs preview <이름> --kind rig`로 확인합니다.

| 팀 | 대화 상대 | 구성 |
| --- | --- | --- |
| `starter` | `dev-build@starter` | `dev-build`(Claude Code)와 `dev-review`(Codex). 한정된 변경 하나 |
| `workshop` | `orch-lead@workshop` | lead, builder, QA, reviewer. 한 저장소의 지속 작업. 내장이 아닌 rig bundle이며 operator가 설치 |
| `factory` | `orch-lead@factory` | lead, advisor, build, QA, design, 독립 리뷰어 둘. 지속적인 제품 작업. 동시 사용량이 가장 큼 |

그 밖의 내장 팀으로 `code-review`, `research`, `pm`이 있습니다. starter는 Claude Code와 Codex를 둘 다 씁니다. 하나만 있으면 operator가 그 하니스에 맞춘 사본을 같은 이름으로 만듭니다.

### 실행과 지시

```bash
cd <저장소>
rig specs preview starter --kind rig
rig up starter --cwd . --plan
rig up starter --cwd .
rig ps --nodes --rig starter
```

seat가 로그인이나 신뢰 질문에서 멈추면 `rig up`이 `Status: partial`과 `Startup attention (<seat>): <이유>`를 출력하고 종료 코드 1로 끝납니다. 그 seat 터미널에서 답한 뒤 `rig seat continue <seat>`를 실행합니다.

builder에게는 사용자가 관찰할 결과, 범위, 확인 방법을 함께 지시합니다.

```bash
rig send dev-build@starter '<무엇을 바꿀지>. 회귀 시험을 추가하고 .venv/bin/python -m pytest tests로 확인한 뒤 dev-review에 독립 검토를 요청하고 결과와 확인 방법을 남길 것. 로컬에서만 작업하고 push하지 말 것.'
```

builder가 작업을 큐에 만들고 claim한 뒤 구현하고, reviewer에게 검토를 넘깁니다. 사람이 터미널 사이에서 리뷰를 중계할 필요는 없습니다.

### 결과 따라가기

```bash
rig queue list --destination dev-build@starter --limit 1000
rig queue list --destination dev-review@starter --limit 1000
rig queue show <id> --full
rig queue transitions <id>
```

작업이 넘어갔으면 다음 작업은 `handedOffFrom`이 그 ID인 것입니다. 메시지 전달이나 큐 완료만 보지 말고 산출물(브랜치, 커밋, 리뷰)을 직접 읽고 실행해 봅니다. 다음 일은 같은 builder에게 이전 결과를 인용해 보냅니다.

### 팀 키우기

- `rig grow "$RIG_ID" design qa --pod dev --runtime codex --cwd "$PROJECT_ROOT"`로 실행 중인 rig에 seat를 추가합니다.
- 새 seat에는 기존 seat에게 이전 결과를 물어보게 해서 맥락을 넘깁니다.
- 반복되는 조율은 Software Factory 절차(`rig context show skills/core/openrig-software-factory --json`)를 따릅니다.

### 주의

- `rig up`은 작업 디렉터리에 `AGENTS.md`와 `CLAUDE.md`를 만듭니다. 이 저장소에는 아직 이 파일이 없으므로, 팀을 띄우기 전에 커밋할지 `.gitignore`에 넣을지 정합니다.
- 팀이 만든 브랜치는 내 변경입니다. 정리하기 전에 내용을 확인합니다.
- 팀을 내리기 전에 `rig ps --nodes --rig starter`로 누가 멈출지 확인하고 `rig down starter`를 실행합니다.

## 9. 문제 해결

| 증상 | 원인과 조치 |
| --- | --- |
| `FAILED [4/4]` | 남은 실패가 하니스 로그인뿐이면 설치는 끝남. 로그인 후 `rig daemon start` |
| "Startup attention" 또는 "Startup details" | seat가 로그인, 폴더 신뢰, bypass 경고에서 멈춤. 그 seat 터미널에서 답한 뒤 `rig seat continue <seat>`. 결과를 모르면 `rig seat status <seat>`부터 확인 |
| "Readiness timeout after 30s" | 하니스가 늦게 뜸. `rig config set runtime.readiness_timeout_seconds <1-600>` 후 그 seat만 다시 시작 |
| kernel seat가 첫 시작 1초 안에 모두 실패, "server exited unexpectedly" | 배포판 tmux(`next-3.4`)가 `capture-pane`에서 죽음. 아래 확인 명령이 실패하면 정상 tmux를 `PATH` 앞에 두고 `rig daemon stop`, `rig start --last`, `rig up kernel --existing --fresh <실패한 seat> --yes` |
| OpenRig 뷰 창이 열리지 않음 | macOS Automation 거부면 시스템 설정 → 개인정보 보호 및 보안 → 자동화에서 허용. SSH와 화면 없는 환경은 출력된 `run:` 명령이나 `tmuxAttachCommand`로 붙음 |
| 뷰 창을 닫음 | `rig terminal open saved:kernel --window`로 다시 엶. 팀을 다시 띄우지 않음 |
| Codex가 rate limit 근처에서 더 싼 모델로 바꿀지 물음 | Codex 자체 메뉴. 사람이 seat 터미널에서 고름 |
| Codex seat가 로컬 데몬에 닿지 못함 | `workspace-write` sandbox의 네트워크가 꺼져 있음. Codex 설정의 `network_access`나 관리 정책 확인 |
| 데몬만 재시작했는데 tmux는 살아 있음 | 새 프로젝트가 아님. `rig status`와 기존 큐를 다시 읽음 |
| 재부팅으로 tmux 세션이 사라짐 | 부서 rig: `dept.py recover`. 일반: `rig`(시작 TUI)에서 데몬 시작 후 기존 rig와 seat 선택. 기본은 이전 대화 복구 |
| 데몬이 tmux를 쓰지 못함 (격리 환경) | `TMUX_TMPDIR` 경로가 소켓 길이 제한(macOS 104자, Linux 108자)을 넘음. 짧은 경로로 바꿈 |
| Claude Code seat가 실행 중 업데이트됨 | 데몬 환경에 `DISABLE_AUTOUPDATER=1`. 그 밖의 비필수 통신은 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` |
| 로컬 모델 환경에서 kernel seat가 404 | kernel seat에 모델이 지정되지 않음. 부서 rig는 `--no-kernel`로 끔 |
| 복구 시 스냅숏 점유자가 옛것이라며 거부 | Seat를 새로 띄운 뒤의 정상 동작. `dept.py recover`가 `rig.yaml`로 새로 띄움 |
| 데몬 시작 때 `github.com` 접속 | 플러그인 자동 갱신. 실패해도 동작함. 폐쇄망 확인 항목은 [X5 기록](../experiments/p0/x5_offline_install/README.md#폐쇄망에서-확인할-것) |
| `npm warn install-scripts` (npm 11) | postinstall이 건너뛰어졌을 뿐임. `check-abi.mjs`를 따로 실행 |

tmux 확인 (기존 세션을 건드리지 않는 임시 소켓):

```bash
tmux -L "openrig-check-$$" -f /dev/null new-session -d -s check
tmux -L "openrig-check-$$" capture-pane -p -t check >/dev/null && echo "capture-pane works"
tmux -L "openrig-check-$$" kill-server
```

알려진 문제: Claude seat가 복구 뒤 주의 상태로 보임([#86](https://github.com/mvschwarz/openrig/issues/86), [#273](https://github.com/mvschwarz/openrig/issues/273)), Claude 사용량 한도 감지 누락([#99](https://github.com/mvschwarz/openrig/issues/99)), Codex 프롬프트 변형을 대기 상태로 인식 못 함([#79](https://github.com/mvschwarz/openrig/issues/79)), Codex 네트워크([#275](https://github.com/mvschwarz/openrig/issues/275)), 배포판 tmux([#980](https://github.com/mvschwarz/openrig/issues/980)).

**도움 요청.** 설치된 버전의 도움말은 `rig context get help`(데몬 필요)로 읽습니다. 데몬이 없으면 `$(npm root -g)/@openrig/cli/daemon/docs/reference/help.md`를 엽니다. 진단은 `rig --version`, `rig doctor --json`, `rig daemon logs`로 모읍니다. 업그레이드 뒤에는 `rig context get reference/whats-new.md`를 먼저 읽습니다. 지원 메일은 hello@openrig.dev, 공개 질문은 [GitHub Q&A](https://github.com/mvschwarz/openrig/discussions/categories/q-a), 버그는 [issues](https://github.com/mvschwarz/openrig/issues)입니다.

## 10. 부서 rig를 0.6.10으로 올리기

지금 운영 스크립트는 0.6.6을 기대합니다. 부서 rig가 쓰는 명령(`daemon start --no-kernel`, `up <spec> --yes`, `up <rig>`, `down --snapshot/--delete/--force`, `ps --nodes`, `send --raw`, `capture`, `transcript`, `seat launch --stop --fresh --reason`)은 0.6.10에도 같은 형태로 있습니다. 0.6.10으로 올린 부서 rig는 아직 시험하지 않았습니다. 올릴 때는 다음 순서를 따릅니다.

1. 부서 rig를 내립니다: `python3 department/dept.py snapshot-down`
2. 격리 prefix에 0.6.10을 설치합니다: `npm install --prefix ~/.cache/chip-design-department/openrig @openrig/cli@0.6.10`
3. `department/dept.py`의 설치 안내 문구와 [department/README.md](../department/README.md)의 설치 명령을 0.6.10으로 바꿉니다.
4. `CHIPDEPT_RIG_TEST=1 .venv/bin/python -m pytest tests/test_department.py`로 완료 기준을 다시 확인합니다.
5. 폐쇄망 반입 목록([X5 기록](../experiments/p0/x5_offline_install/README.md))의 패키지 버전을 다시 뽑습니다.

0.6.6 이후 바뀐 주요 사항은 다음과 같습니다.

| 기능 | 0.6.6 | 0.6.10 |
| --- | --- | --- |
| OpenRig 뷰 창 | `rig terminal open --provider herdr\|cmux`만 | `--window`로 새 터미널 창을 직접 엶 (기본) |
| `rig setup` | `--dry-run`, `--json`, `--full`, `--policy`, `--spec` | `--providers`, `--no-herdr`, `--ghostty`, `--no-ghostty` 추가 |
| `rigs` skill | 따로 추가 | 0.6.7부터 데몬 시작 때 자동 설치 |
| `rig seat` 하위 명령 | `status`, typing guard, held message 관련 | `set-permissions`, `set-model`, `stop`, `clean`, `continue`, `launch`, `handover` 등이 도움말에 나옴 |
| permission 명령 | `rig policy list/show/current/apply` | `rig policy permissions ...` 추가 (기존 명령은 별칭) |

## 참고

- [openrig.dev](https://openrig.dev), [Getting started](https://openrig.dev/docs/getting-started), [Growing your team](https://openrig.dev/guides/growing-your-team), [에이전트용 도움말](https://www.openrig.dev/help/agents)
- 저장소 문서 (v0.6.10): [getting-started.md](https://github.com/mvschwarz/openrig/blob/v0.6.10/docs/reference/getting-started.md), [rig-spec.md](https://github.com/mvschwarz/openrig/blob/v0.6.10/docs/reference/rig-spec.md), [non-interruptive-mode.md](https://github.com/mvschwarz/openrig/blob/v0.6.10/docs/reference/non-interruptive-mode.md), [help.md](https://github.com/mvschwarz/openrig/blob/v0.6.10/docs/reference/help.md), [rigs skill](https://github.com/mvschwarz/openrig/blob/v0.6.10/skills/rigs/SKILL.md)
- 이 프로젝트: [department/README.md](../department/README.md), [department/rig.yaml](../department/rig.yaml), [P0 X5 설치 리허설](../experiments/p0/x5_offline_install/README.md), [Chip Design Department 설계](Chip%20Design%20Department%20설계.md)
