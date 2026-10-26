"""Jira API: 계정 찾기, 이슈 만들기, 스프린트에 넣기."""
from __future__ import annotations

import requests

from .models import Task
from .validator import epic_code


class JiraError(Exception):
    """Jira API 호출 실패."""


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        self._account_cache: dict[str, str] = {}

    def _request(self, method: str, path: str, **kwargs):
        resp = self.session.request(method, f"{self.base}{path}", timeout=30, **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                detail = "; ".join(body.get("errorMessages", [])) or str(body.get("errors") or body)
            except ValueError:
                detail = resp.text[:300]
            hint = " -> .env의 JIRA_EMAIL / JIRA_API_TOKEN을 확인하세요." if resp.status_code == 401 else ""
            raise JiraError(f"{resp.status_code} {detail}{hint}")
        return resp.json() if resp.content else {}

    # ---------- 계정 ----------
    def find_account_id(self, email: str, overrides: dict | None = None) -> str:
        if overrides and email in overrides:
            return overrides[email]
        if email in self._account_cache:
            return self._account_cache[email]
        users = self._request("GET", "/rest/api/3/user/search", params={"query": email})
        people = [u for u in users if u.get("accountType") == "atlassian" and u.get("active", True)]
        exact = [u for u in people if (u.get("emailAddress") or "").lower() == email.lower()]
        candidates = exact or people
        if len(candidates) != 1:
            raise JiraError(
                f"Jira에서 {email} 계정을 하나로 특정하지 못했어요 (찾은 수: {len(candidates)}). "
                "config.yaml의 members에 accountId를 직접 적어 주세요."
            )
        self._account_cache[email] = candidates[0]["accountId"]
        return self._account_cache[email]

    def resolve_account(self, name: str, email: str | None, members: dict | None = None) -> str:
        """담당자 -> Jira accountId. config.yaml members의 이름을 먼저 보고, 없으면 이메일로 찾는다.
        이름으로 Jira를 검색하지 않는 이유: 공용 사이트에는 같은 이름의 다른 계정이 있을 수 있다."""
        members = members or {}
        if name in members:
            return members[name]
        if email:
            return self.find_account_id(email, members)
        raise JiraError(f"'{name}'의 Jira 계정을 알 수 없어요. config.yaml의 members에 '{name}: accountId'를 추가하세요.")

    # ---------- 이슈 ----------
    def create_issue(self, fields: dict) -> str:
        return self._request("POST", "/rest/api/3/issue", json={"fields": fields})["key"]

    # ---------- 스프린트 ----------
    def find_board_id(self, project_key: str) -> int | None:
        boards = self._request("GET", "/rest/agile/1.0/board", params={"projectKeyOrId": project_key}).get("values", [])
        scrum = [b for b in boards if b.get("type") == "scrum"]
        chosen = (scrum or boards)[:1]
        return chosen[0]["id"] if chosen else None

    def find_sprint(self, board_id: int) -> dict | None:
        """진행 중인 스프린트를 우선, 없으면 가장 먼저 시작하는 예정 스프린트."""
        sprints = self._request(
            "GET", f"/rest/agile/1.0/board/{board_id}/sprint", params={"state": "active,future"}
        ).get("values", [])
        active = [s for s in sprints if s.get("state") == "active"]
        if active:
            return active[0]
        future = sorted((s for s in sprints if s.get("state") == "future"), key=lambda s: s.get("startDate") or "9999")
        return future[0] if future else None

    def add_to_sprint(self, sprint_id: int, keys: list[str]) -> None:
        for i in range(0, len(keys), 50):  # 한 번에 최대 50개
            self._request("POST", f"/rest/agile/1.0/sprint/{sprint_id}/issue", json={"issues": keys[i : i + 50]})


def _adf_description(task: Task) -> dict:
    """Jira 설명(ADF 형식): 컨벤션 템플릿 + 노션 원본 링크."""

    def heading(text: str) -> dict:
        return {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": text}]}

    empty = {"type": "paragraph", "content": []}
    source = {
        "type": "paragraph",
        "content": [
            {"type": "text", "text": "노션 주간 할 일에서 자동 등록: "},
            {"type": "text", "text": "원본 보기", "marks": [{"type": "link", "attrs": {"href": task.url}}]},
        ],
    }
    return {
        "type": "doc",
        "version": 1,
        "content": [heading("목적"), empty, heading("완료 조건"), empty, source],
    }


def build_fields(task: Task, jira_cfg: dict, account_id: str) -> dict:
    fields = {
        "project": {"key": jira_cfg["project_key"]},
        "issuetype": {"name": jira_cfg["issue_type"]},
        "summary": f"[{task.part}] {task.title}",
        "assignee": {"accountId": account_id},
        "parent": {"key": jira_cfg["epics"][epic_code(task.epic)]},
        "duedate": task.date,
        "labels": [task.part],
        "priority": {"name": task.priority},
        "description": _adf_description(task),
    }
    if jira_cfg.get("story_points_field"):
        fields[jira_cfg["story_points_field"]] = int(task.sp)
    return fields
