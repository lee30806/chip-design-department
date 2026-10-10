# X5 설치 리허설 기록

Oct 8, 2026 · @Seungjoon Lee

폐쇄망 설치 전에 인터넷이 되는 macOS(arm64)에서 OpenRig 0.6.6을 격리 환경에 설치하고 띄워 본 기록입니다. 폐쇄망 실측을 대신하지 않습니다. 폐쇄망에서 확인할 항목은 [P0 안내서](../README.md)의 X5 절차를 따릅니다.

## 격리 방법

데몬과 Seat가 사용자의 실제 설정을 건드리지 않게 다음을 모두 임시 디렉터리로 돌렸습니다.

| 변수 | 이유 |
| --- | --- |
| `HOME` | 데몬이 `~/.codex/config.toml`(`codex_hooks = true`), `~/.claude/skills`, `~/.claude/plugins/cache`를 직접 읽고 씀 |
| `OPENRIG_HOME` | 데몬 DB, Seat 상태, Pi Seat의 `models.json` 위치 |
| `TMUX_TMPDIR` | tmux 서버 분리. **경로가 길면 Unix 소켓 길이 제한(macOS 104자)에 걸려 데몬이 tmux를 쓰지 못함.** 짧은 경로를 써야 함 |
| `OPENRIG_PORT` | 기본 7433과 겹치지 않게 7533 사용 |

공용 서버에 설치할 때도 같은 이유로 OpenRig 전용 계정이나 전용 `HOME`을 권장합니다.

## 결과

| 항목 | 결과 |
| --- | --- |
| 설치 | `npm install @openrig/cli@0.6.6`. 패키지 114개, 2초. 버전 목록은 [openrig-0.6.6-versions.txt](openrig-0.6.6-versions.txt) (사내 npm 미러 반입 목록) |
| 네이티브 모듈 | `better-sqlite3@13.0.3` 하나. npm 패키지 안에 미리 빌드된 바이너리가 들어 있어 설치 중 내려받기가 없음. 들어 있는 플랫폼: darwin-arm64/x64, linux-arm64/x64, linuxmusl-arm64/x64, win32-arm64/x64 |
| 설치 스크립트 | npm 11은 `@openrig/cli`의 postinstall(`check-abi.mjs`)과 `better-sqlite3`의 install(`node-gyp rebuild`)을 실행하지 않고 경고만 냄. 미리 빌드된 바이너리로 로드는 정상. ABI 확인은 `node <prefix>/node_modules/@openrig/cli/scripts/check-abi.mjs`로 따로 실행 |
| 데몬 시작 시 외부 접속 | `github.com`(20.200.245.247:443) 1건. 소스에서 확인한 플러그인 자동 갱신(`openrig-plugins` 저장소)과 일치. 실패해도 동작하도록 되어 있음 |
| Pi Seat 실행 중 외부 접속 | 관측 시점(대기 상태)에는 없음. Seat 시작 순간은 기록하지 못함 |
| 저장소에 생기는 파일 | `rig up`이 rig 디렉터리(`cwd: .`)에 `AGENTS.md`를 만듦. `.gitignore`에 추가함 |

## 폐쇄망에서 확인할 것

- [ ] 사내 npm 미러에 버전 목록의 패키지가 모두 있는지
- [ ] 외부 접속이 막힌 상태에서 데몬 시작이 플러그인 갱신 타임아웃(5초) 뒤 정상으로 끝나는지
- [ ] Pi Seat 시작 순간의 외부 접속. Pi는 `--offline`(또는 `PI_OFFLINE=1`)으로 시작 시 네트워크 동작을 끌 수 있음. 하지만 OpenRig가 Pi에 넘기는 환경 변수는 허용 목록으로 제한되므로, `PI_OFFLINE`이 전달되는지 확인해야 함
- [ ] Linux 서버의 tmux 소켓 경로 길이 (Linux 제한 108자)
