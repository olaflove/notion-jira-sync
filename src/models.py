"""노션 한 줄(할 일)을 담는 데이터 구조."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Task:
    page_id: str
    url: str
    title: str
    assignees: list[tuple[str, str | None]] = field(default_factory=list)  # (이름, 이메일)
    date: str | None = None  # YYYY-MM-DD
    part: str | None = None
    epic: str | None = None
    sp: str | None = None
    priority: str | None = None
    jira_key: str | None = None

    @property
    def assignee_name(self) -> str:
        return self.assignees[0][0] if len(self.assignees) == 1 else "(담당자 오류)"

    @property
    def assignee_email(self) -> str | None:
        return self.assignees[0][1] if len(self.assignees) == 1 else None
