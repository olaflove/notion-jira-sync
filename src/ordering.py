"""Jira에 만드는 순서 정하기.

Jira 이슈 키(S15P31A404-158, 159, ...)와 보드 순서는 만든 순서를 따른다.
노션이 돌려주는 순서대로 만들면 같은 사람의 일이 키 번호상 흩어지고, (1/3)·(2/3)·(3/3)이 거꾸로 번호를 받을 수 있어서,
만들기 전에 담당자별로 묶은 뒤 마감일 오름차순 -> 같은 날이면 (n/m)의 n 오름차순으로 정렬한다.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from .models import Task

SEQUENCE = re.compile(r"^\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)")


def sequence_number(title: str) -> int:
    """'(2/3) 착지 검출' -> 2. 순번이 없으면 0 (같은 날의 순번 있는 일보다 앞)."""
    match = SEQUENCE.match(title or "")
    return int(match.group(1)) if match else 0


def sort_for_creation(tasks: list[Task], person_order: Sequence[str] = ()) -> list[Task]:
    """정렬 기준: 담당자 -> 마감일 -> (n/m)의 n -> 제목.

    person_order: 담당자 순서 (보통 config.yaml members에 적은 순서). 목록에 없는 사람은 그 뒤에 이름순.
    """
    rank = {name: i for i, name in enumerate(person_order)}

    def key(task: Task) -> tuple:
        name = task.assignee_name
        return (
            rank.get(name, len(rank)),
            name,
            task.date or "9999-12-31",
            sequence_number(task.title),
            task.title,
        )

    return sorted(tasks, key=key)
