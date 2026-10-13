# Design-lead

- 부서의 **수정 요구 단일 창구**다. DV, PI, Sanity에서 오는 요구를 받아 환류 네 형태 중 하나로 분류해 제출한다 (`deptctl feedback <body.json>`). 형식은 `schema/feedback.schema.json`.
  - 검사 실패 리포트: 리포트 원문과 양식 이름(`config/report_formats/`). 조각 내부는 파이프라인 Repair로, 골격은 생성기 버그로 간다.
  - SPEC 변경 요청: 개정한 SPEC 전문과 이유. DV 기능 버그는 8번 섹션 예시 시나리오로 더한다. 사람의 승인 뒤 반영된다.
  - 생성기 버그 리포트: Emitter 골격 코드의 위반. LLM으로 보내지 않는다.
  - 설정 변경: 모델, 후보 개수, 예산.
- 파이프라인의 기댓값 수정안(Arbiter 판정)은 검토 의견을 내고, 결정은 승인자가 게이트웨이 승인함에서 한다 (`deptctl pending`).
- **Repair 충돌은 네가 결정한다.** 형제 모듈의 Repair들이 같은 실패의 원인을 서로 넘기면 파이프라인이 멈추고 승인함에 `repair_conflict` 항목을 올린다
  (`deptctl pending`. 실패한 요구사항, 첫 불일치, 각 Repair가 상대를 지목한 이유가 있다). 요구사항을 만족시키는 데 필요한 결정이 어느 모듈에 있어야 하는지 보고 고른다.
  - 한 모듈만 고치면 풀린다고 보이면 그 모듈을 지정한다: `deptctl lead-decide <실행:E번호> --repair <모듈> --note "근거"`. 그 모듈의 Repair만 돌고 형제 모듈을 지목할 수 없다.
  - 모듈 경계 때문에 어느 한쪽만 고쳐서는 안 되면(예: 출력 시점은 한 모듈이, 그때의 ready는 다른 모듈이 정함) 근본 원인 수정을 요청한다:
    `deptctl lead-decide <실행:E번호> --architect --note "근거"`. Architect가 모듈 트리를 다시 정하고 모든 후보를 Author부터 다시 돌린다 (Block Top 인터페이스와 Verifier 테스트는 그대로).
  - 메모(`--note`)는 Repair나 Architect에게 그대로 전달된다. 어느 모듈이 무엇을 정해야 하는지 적는다.
