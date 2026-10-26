"""jira_writer 단위 테스트: 담당자 -> Jira 계정 찾기 순서."""
import pytest

from src.jira_writer import JiraClient, JiraError


def client_without_network(calls: list) -> JiraClient:
    client = JiraClient("https://example.atlassian.net", "me@example.com", "token")

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("params")))
        return [{"accountId": "by-email", "accountType": "atlassian", "emailAddress": "a@example.com"}]

    client._request = fake_request
    return client


def test_members에_이름이_있으면_Jira를_검색하지_않는다():
    calls = []
    client = client_without_network(calls)
    assert client.resolve_account("김지윤", None, {"김지윤": "acc-1"}) == "acc-1"
    assert calls == []


def test_members에_없고_이메일이_있으면_이메일로_찾는다():
    calls = []
    client = client_without_network(calls)
    assert client.resolve_account("조유진", "a@example.com", {}) == "by-email"
    assert calls[0][2] == {"query": "a@example.com"}


def test_이름도_이메일도_없으면_members에_추가하라고_알려준다():
    client = client_without_network([])
    with pytest.raises(JiraError, match="members"):
        client.resolve_account("새팀원", None, {})
