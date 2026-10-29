"""노션 '주간 할 일' -> Jira 이슈 등록.

사용법 (저장소 폴더에서):
    python -m src.main                  # 미리보기(dry-run): 아무것도 만들지 않음
    python -m src.main --apply          # 실제로 Jira 이슈 생성 + 노션에 키 기록 + 스프린트 배정
    python -m src.main --week 2026-10-27   # 다른 주(그 주의 아무 날짜) 대상
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import requests

from .config import ConfigError, load_config
from .jira_writer import JiraClient, JiraError, build_fields
from .notion_reader import NotionClient, NotionError, parse_task
from .ordering import sort_for_creation
from .validator import validate


def week_range(day: date) -> tuple[date, date]:
    """월요일 ~ 일요일"""
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="노션 주간 할 일 -> Jira 이슈 등록")
    ap.add_argument("--apply", action="store_true", help="실제로 Jira 이슈를 만든다 (없으면 미리보기만)")
    ap.add_argument("--week", help="대상 주에 속한 아무 날짜 YYYY-MM-DD (기본: 오늘)")
    ap.add_argument("--no-sprint", action="store_true", help="스프린트 배정을 건너뛴다")
    ap.add_argument("--config", help="설정 파일 경로 (기본: config.yaml)")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"[설정 오류] {e}")
        return 2

    try:
        day = date.fromisoformat(args.week) if args.week else date.today()
    except ValueError:
        print("[입력 오류] --week 는 YYYY-MM-DD 형식이어야 해요.")
        return 2
    start, end = week_range(day)

    n_cfg, j_cfg, rules = cfg["notion"], cfg["jira"], cfg["rules"]
    props = n_cfg["properties"]
    notion = NotionClient(cfg["secrets"]["NOTION_TOKEN"], n_cfg.get("api_version", "2025-09-03"))
    jira = JiraClient(j_cfg["base_url"], cfg["secrets"]["JIRA_EMAIL"], cfg["secrets"]["JIRA_API_TOKEN"])

    mode = "실제 등록" if args.apply else "미리보기(dry-run)"
    print(f"== {start} ~ {end} 주간 할 일 -> Jira [{mode}] ==\n")

    # 1. 노션 읽기
    try:
        pages = notion.query_rows(n_cfg["data_source_id"], props["date"], start, end)
        week_tasks = [parse_task(p, props) for p in pages]
    except (NotionError, requests.RequestException) as e:  # 네트워크 오류 포함
        print(f"[노션 오류] {e}")
        return 1
    new_tasks = [t for t in week_tasks if not t.jira_key]
    print(f"노션에서 {len(week_tasks)}줄 읽음 (이미 등록 {len(week_tasks) - len(new_tasks)}줄, 새로 등록할 후보 {len(new_tasks)}줄)")

    # 2. 검사
    members = cfg.get("members") or {}
    result = validate(new_tasks, week_tasks, rules, j_cfg.get("default_priority", "Medium"), j_cfg["epics"], members)
    if result.sp_by_person:
        print("\n[사람별 이번 주 SP 합계]")
        for name, total in sorted(result.sp_by_person.items()):
            print(f"  {name}: {total}")
    if result.warnings:
        print("\n[확인 필요]")
        for w in result.warnings:
            print(f"  ! {w}")
    if result.problems:
        print("\n[등록 제외 - 노션에서 고쳐 주세요]")
        for t, errs in result.problems:
            print(f"  X {t.title or '(제목 없음)'} / {t.assignee_name}")
            for err in errs:
                print(f"      - {err}")
            print(f"      {t.url}")

    # 3. Jira 계정 찾기 + 필드 만들기 (만드는 순서 = 담당자(members 순) -> 마감일 -> (n/m) 순번)
    planned: list[tuple] = []
    for t in sort_for_creation(result.ready, list(members)):
        try:
            account_id = jira.resolve_account(t.assignee_name, t.assignee_email, members)
        except JiraError as e:
            print(f"  X {t.title} / {t.assignee_name}: {e}")
            continue
        planned.append((t, build_fields(t, j_cfg, account_id)))

    if not planned:
        print("\n등록할 이슈가 없어요.")
        return 1 if result.problems else 0

    print(f"\n[{'등록할' if args.apply else '등록 예정'} 이슈 {len(planned)}개]")
    for t, f in planned:
        print(f"  - {f['summary']}  | {t.assignee_name} | {t.date} | {t.sp} SP | {f['priority']['name']} | 에픽 {f['parent']['key']}")

    if not args.apply:
        print("\n미리보기만 했어요. 실제로 만들려면 --apply 를 붙여 다시 실행하세요.")
        return 0

    # 4. 이슈 생성 + 노션에 키 기록
    created: list[str] = []
    print()
    for t, f in planned:
        try:
            key = jira.create_issue(f)
        except JiraError as e:
            print(f"  X 생성 실패: {f['summary']} -> {e}")
            continue
        created.append(key)
        try:
            notion.set_text(t.page_id, props["jira_key"], key)
            print(f"  OK {key}  {f['summary']}")
        except NotionError as e:
            print(f"  ! {key} 는 만들었지만 노션에 키를 못 적었어요: {e}")
            print(f"    -> 노션 'Jira 키' 칸에 {key} 를 직접 적어 주세요. 안 적으면 다음 실행 때 중복으로 만들어져요.")

    # 5. 스프린트 배정
    sprint_cfg = j_cfg.get("sprint") or {}
    if created and sprint_cfg.get("enabled", True) and not args.no_sprint:
        try:
            board_id = sprint_cfg.get("board_id") or jira.find_board_id(j_cfg["project_key"])
            sprint = jira.find_sprint(board_id) if board_id else None
            if sprint:
                jira.add_to_sprint(sprint["id"], created)
                print(f"\n스프린트 '{sprint['name']}'에 {len(created)}개 넣었어요.")
            else:
                print("\n! 진행 중이거나 예정된 스프린트가 없어 백로그에 남겨 뒀어요.")
        except JiraError as e:
            print(f"\n! 스프린트 배정 실패 (이슈는 백로그에 있어요): {e}")

    print(f"\n완료: {len(created)}/{len(planned)}개 생성")
    return 0 if len(created) == len(planned) and not result.problems else 1


if __name__ == "__main__":
    sys.exit(main())
