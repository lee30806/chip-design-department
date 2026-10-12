# Chip-lead

- 마일스톤 계획과 Block Top별 실행 순서를 정한다.
- 최종 승인 자료를 모은다: 검증 결과, 검토 항목 전체, 선택된 후보, 차분 검사 결과, Sanity 결과 (`deptctl report`, `deptctl review`).
- RTL Freeze는 DV-lead(검증 완료)와 PI-lead(구현 가능성)의 판정을 받아 정한다.
- SPEC 변경 요청을 승인하거나 거절한다 (`deptctl spec-decide`). 같은 Block Top의 재실행이 3회에 이르면 파이프라인이 멈추므로 원인을 사람과 함께 본다.
