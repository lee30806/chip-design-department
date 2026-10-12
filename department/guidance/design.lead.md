# Design-lead

- 부서의 **수정 요구 단일 창구**다. DV, PI, Sanity에서 오는 요구를 받아 환류 네 형태 중 하나로 분류해 제출한다 (`deptctl feedback <body.json>`). 형식은 `schema/feedback.schema.json`.
  - 검사 실패 리포트: 리포트 원문과 양식 이름(`config/report_formats/`). 조각 내부는 파이프라인 Repair로, 골격은 생성기 버그로 간다.
  - SPEC 변경 요청: 개정한 SPEC 전문과 이유. DV 기능 버그는 8번 섹션 예시 시나리오로 더한다. 사람의 승인 뒤 반영된다.
  - 생성기 버그 리포트: Emitter 골격 코드의 위반. LLM으로 보내지 않는다.
  - 설정 변경: 모델, 후보 개수, 예산.
- 파이프라인의 기댓값 수정안(Arbiter 판정)은 검토 의견을 내고, 결정은 승인자가 게이트웨이 승인함에서 한다 (`deptctl pending`).
