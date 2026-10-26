"""등록 전에 노션 줄이 컨벤션에 맞는지 검사한다."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .models import Task

TAG_PREFIX = re.compile(r"^\[[^\]]+\]\s*")


def epic_code(epic: str | None) -> str:
    """'F-02 보행 수치 계산' -> 'F-02', '공통' -> '공통'"""
    return epic.split()[0] if epic else ""


@dataclass
class ValidationResult:
    ready: list[Task] = field(default_factory=list)
    problems: list[tuple[Task, list[str]]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sp_by_person: dict[str, int] = field(default_factory=dict)


def validate(
    new_tasks: list[Task],
    week_tasks: list[Task],
    rules: dict,
    default_priority: str,
    epics: dict,
    members: dict | None = None,
) -> ValidationResult:
    """new_tasks: 아직 Jira 키가 없는 줄, week_tasks: 그 주의 모든 줄(합계 계산용).
    members: config.yaml의 '이름 또는 이메일 -> Jira accountId' 표."""
    members = members or {}
    allowed = sorted({int(x) for x in rules.get("allowed_sp", [1, 2, 3, 5])})
    allowed_str = {str(x) for x in allowed}
    result = ValidationResult()

    for t in new_tasks:
        errs: list[str] = []
        if not t.title:
            errs.append("할 일이 비어 있어요")
        elif TAG_PREFIX.match(t.title):
            t.title = TAG_PREFIX.sub("", t.title)
            result.warnings.append(f"'{t.title}': 할 일에 직접 쓴 [태그]는 빼고 등록해요 (파트 칸에서 자동으로 붙어요)")

        if not t.assignees:
            errs.append("담당자가 비어 있어요")
        elif len(t.assignees) > 1:
            errs.append("담당자는 한 명만 지정해야 해요")
        elif t.assignee_name not in members and not t.assignee_email:
            errs.append(
                f"담당자 '{t.assignee_name}'의 Jira 계정을 알 수 없어요 "
                "(config.yaml의 members에 '이름: accountId'를 추가하거나, 사람 속성이면 이메일 권한 확인)"
            )

        if not t.date:
            errs.append("날짜가 비어 있어요")
        if not t.part:
            errs.append("파트가 비어 있어요")
        if not t.epic:
            errs.append("에픽이 비어 있어요")
        elif epic_code(t.epic) not in epics:
            errs.append(f"에픽 '{t.epic}'이 config.yaml의 jira.epics에 없어요")
        if not t.sp:
            errs.append("SP가 비어 있어요")
        elif t.sp not in allowed_str:
            errs.append(f"SP는 {', '.join(map(str, allowed))} 중 하나여야 해요")

        if errs:
            result.problems.append((t, errs))
            continue
        if not t.priority:
            t.priority = default_priority
            result.warnings.append(f"'{t.title}': 우선순위가 비어 있어 {default_priority}로 등록해요")
        result.ready.append(t)

    # 사람별 주간 SP 합계 (이미 등록된 줄 포함)
    totals: dict[str, int] = defaultdict(int)
    for t in week_tasks:
        if len(t.assignees) == 1 and t.sp and t.sp.isdigit():
            totals[t.assignee_name] += int(t.sp)
    result.sp_by_person = dict(totals)

    lo, hi = rules.get("weekly_sp_min"), rules.get("weekly_sp_max")
    for name, total in sorted(totals.items()):
        if lo is not None and total < lo:
            result.warnings.append(f"{name}: 이번 주 합계 {total} SP (기준 {lo}~{hi}보다 적어요)")
        elif hi is not None and total > hi:
            result.warnings.append(f"{name}: 이번 주 합계 {total} SP (기준 {lo}~{hi}보다 많아요)")
    return result
