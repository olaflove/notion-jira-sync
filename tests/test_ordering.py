"""ordering 단위 테스트: Jira 이슈를 만드는 순서 (담당자별로 묶고 -> 마감일 -> (n/m) 순번)."""
from src.models import Task
from src.ordering import sequence_number, sort_for_creation


def task(title: str, date: str | None, name: str = "조유진") -> Task:
    return Task(page_id=title, url="", title=title, assignees=[(name, None)], date=date)


def titles(tasks):
    return [t.title for t in tasks]


def test_순번을_읽는다():
    assert sequence_number("(2/3) 착지·이지 검출 정답 대조") == 2
    assert sequence_number(" ( 10 / 12 ) 띄어쓰기가 있어도") == 10
    assert sequence_number("유효 판별 규칙 함수 구현") == 0
    assert sequence_number("중간에 (1/3)이 있으면 순번이 아니다") == 0
    assert sequence_number("") == 0


# ---------- 한 사람 안에서 ----------

def test_마감일_오름차순으로_정렬한다():
    tasks = [task("C", "2026-10-30"), task("A", "2026-10-28"), task("B", "2026-10-29")]
    assert titles(sort_for_creation(tasks)) == ["A", "B", "C"]


def test_같은_날이면_순번_오름차순이다():
    # 노션이 거꾸로 돌려줘도 (1/3) -> (2/3) -> (3/3) 순서로 만든다
    tasks = [
        task("(3/3) 착지·이지 검출 단위 테스트", "2026-10-28"),
        task("(2/3) 착지·이지 검출 정답 대조", "2026-10-28"),
        task("(1/3) 착지·이지 시점 검출 함수", "2026-10-28"),
    ]
    assert titles(sort_for_creation(tasks)) == [
        "(1/3) 착지·이지 시점 검출 함수",
        "(2/3) 착지·이지 검출 정답 대조",
        "(3/3) 착지·이지 검출 단위 테스트",
    ]


def test_날짜가_순번보다_먼저다():
    tasks = [task("(1/2) 다음 날 시작", "2026-10-29"), task("(2/2) 오늘 마무리", "2026-10-28")]
    assert titles(sort_for_creation(tasks)) == ["(2/2) 오늘 마무리", "(1/2) 다음 날 시작"]


def test_순번_없는_일은_같은_날의_순번_있는_일보다_앞이다():
    tasks = [task("(1/2) 나눈 일", "2026-10-28"), task("한 번에 끝나는 일", "2026-10-28")]
    assert titles(sort_for_creation(tasks)) == ["한 번에 끝나는 일", "(1/2) 나눈 일"]


def test_날짜가_없으면_그_사람의_맨_뒤로_보낸다():
    tasks = [task("날짜 없음", None), task("날짜 있음", "2026-10-30")]
    assert titles(sort_for_creation(tasks)) == ["날짜 있음", "날짜 없음"]


# ---------- 여러 사람 ----------

def test_같은_사람의_일은_이어서_만든다():
    # 날짜가 섞여 있어도 한 사람의 일이 키 번호상 끊기지 않게 묶는다
    tasks = [
        task("지윤 10-28", "2026-10-28", "김지윤"),
        task("유진 10-27", "2026-10-27", "조유진"),
        task("지윤 10-26", "2026-10-26", "김지윤"),
        task("유진 10-29", "2026-10-29", "조유진"),
    ]
    assert titles(sort_for_creation(tasks, ["김지윤", "조유진"])) == [
        "지윤 10-26",
        "지윤 10-28",
        "유진 10-27",
        "유진 10-29",
    ]


def test_담당자_순서는_members_순서를_따른다():
    tasks = [task("A의 일", "2026-10-26", "김지윤"), task("B의 일", "2026-10-26", "허정원")]
    assert titles(sort_for_creation(tasks, ["허정원", "김지윤"])) == ["B의 일", "A의 일"]


def test_members에_없는_사람은_뒤에_이름순으로_둔다():
    tasks = [
        task("나중", "2026-10-26", "하하하"),
        task("먼저", "2026-10-26", "가나다"),
        task("등록된 사람", "2026-10-30", "조유진"),
    ]
    assert titles(sort_for_creation(tasks, ["조유진"])) == ["등록된 사람", "먼저", "나중"]


def test_원본_목록은_바꾸지_않는다():
    tasks = [task("B", "2026-10-29"), task("A", "2026-10-28")]
    sort_for_creation(tasks)
    assert titles(tasks) == ["B", "A"]
