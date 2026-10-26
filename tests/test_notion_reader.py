"""notion_reader 단위 테스트: 노션 API 응답 파싱, 페이지 이어 받기, 오류 안내.

실제 노션에 접속하지 않고, 노션 API가 돌려주는 JSON 모양을 그대로 흉내 낸 가짜 응답으로 확인한다.
"""
import copy
from datetime import date

import pytest

from src.notion_reader import NotionClient, NotionError, parse_task

PROPS = {
    "title": "할 일",
    "assignee": "담당자",
    "date": "날짜",
    "part": "파트",
    "epic": "에픽",
    "sp": "SP",
    "priority": "우선순위",
    "jira_key": "Jira 키",
}


def notion_page(**overrides) -> dict:
    """노션 data_sources/{id}/query 응답의 results 한 개와 같은 모양."""
    props = {
        "할 일": {"type": "title", "title": [{"plain_text": "굽힘 쪽 관절 각도 "}, {"plain_text": "계산 함수 초안"}]},
        "담당자": {"type": "people", "people": [{"object": "user", "name": "조유진", "person": {"email": "yujin@example.com"}}]},
        "날짜": {"type": "date", "date": {"start": "2026-10-20", "end": None}},
        "파트": {"type": "select", "select": {"name": "ENGINE"}},
        "에픽": {"type": "select", "select": {"name": "F-02 보행 수치 계산"}},
        "SP": {"type": "select", "select": {"name": "2"}},
        "우선순위": {"type": "select", "select": {"name": "High"}},
        "Jira 키": {"type": "rich_text", "rich_text": []},
    }
    props.update(overrides)
    return {"object": "page", "id": "page-1", "url": "https://www.notion.so/page-1", "properties": props}


# ---------- parse_task ----------

def test_모든_칸을_Task로_읽는다():
    t = parse_task(notion_page(), PROPS)
    assert t.title == "굽힘 쪽 관절 각도 계산 함수 초안"  # 조각난 텍스트를 이어 붙인다
    assert t.assignees == [("조유진", "yujin@example.com")]
    assert (t.date, t.part, t.epic, t.sp, t.priority) == ("2026-10-20", "ENGINE", "F-02 보행 수치 계산", "2", "High")
    assert t.jira_key is None


def test_시간이_들어간_날짜는_날짜만_쓴다():
    page = notion_page(**{"날짜": {"type": "date", "date": {"start": "2026-10-21T09:00:00.000+09:00"}}})
    assert parse_task(page, PROPS).date == "2026-10-21"


def test_빈_칸은_None으로_읽는다():
    page = notion_page(
        **{
            "날짜": {"type": "date", "date": None},
            "파트": {"type": "select", "select": None},
            "담당자": {"type": "people", "people": []},
        }
    )
    t = parse_task(page, PROPS)
    assert t.date is None and t.part is None and t.assignees == []


def test_이메일_권한이_없으면_이메일은_None():
    page = notion_page(**{"담당자": {"type": "people", "people": [{"object": "user", "name": "조유진", "person": {}}]}})
    assert parse_task(page, PROPS).assignees == [("조유진", None)]


def test_담당자가_선택_속성이면_이름만_읽는다():
    page = notion_page(**{"담당자": {"type": "select", "select": {"name": "김지윤"}}})
    assert parse_task(page, PROPS).assignees == [("김지윤", None)]


def test_선택_속성_담당자가_비어_있으면_빈_목록():
    page = notion_page(**{"담당자": {"type": "select", "select": None}})
    assert parse_task(page, PROPS).assignees == []


def test_이미_등록된_줄은_Jira_키를_읽는다():
    page = notion_page(**{"Jira 키": {"type": "rich_text", "rich_text": [{"plain_text": " PROJ-12 "}]}})
    assert parse_task(page, PROPS).jira_key == "PROJ-12"


def test_칸_이름이_바뀌면_어떤_칸인지_알려준다():
    page = notion_page()
    del page["properties"]["SP"]
    with pytest.raises(NotionError, match="'SP' 칸이 없어요"):
        parse_task(page, PROPS)


# ---------- NotionClient (가짜 네트워크) ----------

class FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def fake_client(responses: list[FakeResponse], calls: list) -> NotionClient:
    client = NotionClient("secret-token")

    def fake_request(method, url, timeout=None, **kwargs):
        # 요청 본문은 보낸 순간의 모습으로 기록 (클라이언트가 같은 dict를 재사용하므로 복사)
        calls.append((method, url, copy.deepcopy(kwargs.get("json"))))
        return responses.pop(0)

    client.session.request = fake_request
    return client


def test_100줄이_넘으면_다음_페이지를_이어서_가져온다():
    calls = []
    client = fake_client(
        [
            FakeResponse(200, {"results": [{"id": "a"}], "has_more": True, "next_cursor": "cursor-2"}),
            FakeResponse(200, {"results": [{"id": "b"}], "has_more": False, "next_cursor": None}),
        ],
        calls,
    )
    rows = client.query_rows("ds-1", "날짜", date(2026, 10, 19), date(2026, 10, 25))

    assert [r["id"] for r in rows] == ["a", "b"]
    assert len(calls) == 2
    assert "start_cursor" not in calls[0][2]
    assert calls[1][2]["start_cursor"] == "cursor-2"


def test_주_범위로_날짜_필터를_건다():
    calls = []
    client = fake_client([FakeResponse(200, {"results": [], "has_more": False})], calls)
    client.query_rows("ds-1", "날짜", date(2026, 10, 19), date(2026, 10, 25))

    method, url, body = calls[0]
    assert method == "POST" and url.endswith("/data_sources/ds-1/query")
    conditions = body["filter"]["and"]
    assert conditions[0]["date"] == {"on_or_after": "2026-10-19"}
    assert conditions[1]["date"] == {"on_or_before": "2026-10-25"}


def test_연결이_안_된_페이지면_해결_방법을_알려준다():
    client = fake_client([FakeResponse(404, {"message": "Could not find data_source"})], [])
    with pytest.raises(NotionError, match="연결"):
        client.query_rows("ds-1", "날짜", date(2026, 10, 19), date(2026, 10, 25))


def test_토큰이_틀리면_해결_방법을_알려준다():
    client = fake_client([FakeResponse(401, {"message": "API token is invalid."})], [])
    with pytest.raises(NotionError, match="NOTION_TOKEN"):
        client.query_rows("ds-1", "날짜", date(2026, 10, 19), date(2026, 10, 25))


def test_Jira_키_기록은_rich_text로_보낸다():
    calls = []
    client = fake_client([FakeResponse(200, {})], calls)
    client.set_text("page-1", "Jira 키", "PROJ-12")

    method, url, body = calls[0]
    assert method == "PATCH" and url.endswith("/pages/page-1")
    assert body["properties"]["Jira 키"]["rich_text"][0]["text"]["content"] == "PROJ-12"
