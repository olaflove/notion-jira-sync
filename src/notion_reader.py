"""노션 API: 주간 할 일 표 읽기, Jira 키 적기."""
from __future__ import annotations

from datetime import date

import requests

from .models import Task

NOTION_API = "https://api.notion.com/v1"


class NotionError(Exception):
    """노션 API 호출 실패."""


class NotionClient:
    def __init__(self, token: str, version: str = "2025-09-03"):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": version,
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self.session.request(method, f"{NOTION_API}{path}", timeout=30, **kwargs)
        if resp.status_code >= 400:
            try:
                message = resp.json().get("message", resp.text)
            except ValueError:
                message = resp.text
            hint = ""
            if resp.status_code == 401:
                hint = " -> .env의 NOTION_TOKEN이 맞는지 확인하세요."
            elif resp.status_code == 404:
                hint = " -> 노션 Jira 페이지의 '연결'에 이 통합을 추가했는지 확인하세요."
            raise NotionError(f"{resp.status_code} {message}{hint}")
        return resp.json()

    def query_rows(self, data_source_id: str, date_prop: str, start: date, end: date) -> list[dict]:
        """날짜가 start~end(포함)인 줄을 모두 가져온다. 100줄 넘으면 이어서 가져온다."""
        payload: dict = {
            "filter": {
                "and": [
                    {"property": date_prop, "date": {"on_or_after": start.isoformat()}},
                    {"property": date_prop, "date": {"on_or_before": end.isoformat()}},
                ]
            },
            "page_size": 100,
        }
        results: list[dict] = []
        while True:
            data = self._request("POST", f"/data_sources/{data_source_id}/query", json=payload)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                return results
            payload["start_cursor"] = data["next_cursor"]

    def set_text(self, page_id: str, prop: str, value: str) -> None:
        body = {"properties": {prop: {"rich_text": [{"type": "text", "text": {"content": value}}]}}}
        self._request("PATCH", f"/pages/{page_id}", json=body)


def _plain(items: list | None) -> str:
    return "".join(i.get("plain_text", "") for i in items or []).strip()


def parse_task(page: dict, props: dict) -> Task:
    """노션 API 응답의 페이지 한 개를 Task로 바꾼다."""
    p = page.get("properties", {})

    def get(key: str) -> dict:
        name = props[key]
        if name not in p:
            raise NotionError(f"노션 표에 '{name}' 칸이 없어요. config.yaml의 notion.properties를 확인하세요.")
        return p[name]

    def select(key: str) -> str | None:
        value = get(key).get("select")
        return value["name"] if value else None

    people = [
        (u.get("name") or "(이름 없음)", (u.get("person") or {}).get("email"))
        for u in get("assignee").get("people", [])
    ]
    d = get("date").get("date")

    return Task(
        page_id=page["id"],
        url=page.get("url", ""),
        title=_plain(get("title").get("title")),
        assignees=people,
        date=d["start"][:10] if d and d.get("start") else None,
        part=select("part"),
        epic=select("epic"),
        sp=select("sp"),
        priority=select("priority"),
        jira_key=_plain(get("jira_key").get("rich_text")) or None,
    )
