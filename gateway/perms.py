"""역할 5개와 권한. 사람과 Seat 모두 같은 표를 따른다.

| 역할 | 할 수 있는 것 |
| --- | --- |
| admin (관리자) | 사용자와 API 키 관리, 감사 기록 조회 |
| design (설계) | SPEC 작업 공간 만들기와 고치기, 검사 질문 답, SPEC 고정 요청, 실행 제출 |
| verification (검증) | 실행 판정 중 DV 검증 완료 판정 |
| implementation (구현) | 실행 판정 중 PI 구현 가능성 판정 |
| approver (승인자) | 승인과 반려: SPEC 고정, 최종 승인, RTL Freeze, 기댓값 변경, SPEC 변경 요청 |

모든 역할이 조회(실행, SPEC, 승인 기록, Seat 상태)를 할 수 있다.
역할과 별도로 `design_lead` 능력이 있어야 환류를 제출하고 Repair 충돌을 결정한다 (수정 요구의 단일 창구, Design-lead Seat도 가능).
승인은 사람만 한다 (Seat 계정은 승인자가 될 수 없음).
"""
from __future__ import annotations

ROLES = ("admin", "design", "verification", "implementation", "approver")
CAPS = ("design_lead",)

PERMS = {
    "view": set(ROLES),
    "manage_users": {"admin"},
    "view_audit": {"admin", "approver"},
    "spec_edit": {"design"},
    "submit_run": {"design"},
    "signoff_dv": {"verification"},
    "signoff_pi": {"implementation"},
    "approve": {"approver"},
}

APPROVAL_KINDS = ("spec_freeze", "final_approval", "rtl_freeze", "expectation_change", "spec_change")
LEAD_KINDS = ("repair_conflict",)   # Design-lead가 결정 (승인함에 함께 보이고 같은 기록에 남음)


class Forbidden(Exception):
    pass


def allowed(user: dict, perm: str) -> bool:
    if user.get("disabled"):
        return False
    if perm == "feedback":
        return "design" in user["roles"] and "design_lead" in user["caps"]
    if perm == "approve" and user.get("kind") != "human":
        return False
    return bool(set(user["roles"]) & PERMS[perm])


def require(user: dict, perm: str) -> None:
    if not allowed(user, perm):
        need = "design 역할과 design_lead 능력" if perm == "feedback" else f"{sorted(PERMS[perm])} 역할"
        raise Forbidden(f"{user['username']}: 이 작업({perm})에는 {need}이 필요함 (지금 {sorted(user['roles'])})")
