"""validator.validate() 단위 테스트: 노션 줄이 컨벤션에 맞는지 검사하는 규칙."""
from src.models import Task
from src.validator import epic_code, validate

RULES = {"allowed_sp": [1, 2, 3, 5], "weekly_sp_min": 25, "weekly_sp_max": 30}
EPICS = {"F-02": "PROJ-3", "공통": "PROJ-11"}


def make_task(**overrides) -> Task:
    """모든 칸이 올바르게 채워진 할 일. 테스트마다 필요한 칸만 바꿔 쓴다."""
    values = dict(
        page_id="page-1",
        url="https://notion.so/page-1",
        title="굽힘 쪽 관절 각도 계산 함수 초안",
        assignees=[("조유진", "yujin@example.com")],
        date="2026-10-20",
        part="ENGINE",
        epic="F-02 보행 수치 계산",
        sp="2",
        priority="High",
    )
    values.update(overrides)
    return Task(**values)


def run(*tasks: Task, week_tasks=None):
    return validate(list(tasks), list(week_tasks or tasks), RULES, "Medium", EPICS)


# ---------- 정상 ----------

def test_올바른_줄은_등록_대상이다():
    result = run(make_task())
    assert len(result.ready) == 1
    assert result.problems == []


# ---------- 빈 칸 ----------

def test_빈_칸은_모두_한번에_알려준다():
    task = make_task(title="", assignees=[], date=None, part=None, epic=None, sp=None)
    result = run(task)

    assert result.ready == []
    errors = result.problems[0][1]
    for word in ("할 일", "담당자", "날짜", "파트", "에픽", "SP"):
        assert any(word in e for e in errors), f"'{word}' 오류가 없어요: {errors}"


# ---------- SP ----------

def test_SP는_1_2_3_5만_허용한다():
    result = run(make_task(sp="4"))
    assert result.ready == []
    assert "1, 2, 3, 5" in result.problems[0][1][0]


# ---------- 담당자 ----------

def test_담당자가_두_명이면_제외한다():
    result = run(make_task(assignees=[("A", "a@example.com"), ("B", "b@example.com")]))
    assert result.ready == []
    assert "한 명" in result.problems[0][1][0]


def test_담당자_이메일을_못_읽으면_제외한다():
    result = run(make_task(assignees=[("조유진", None)]))
    assert result.ready == []
    assert "이메일" in result.problems[0][1][0]


# ---------- 에픽 ----------

def test_설정에_없는_에픽은_제외한다():
    result = run(make_task(epic="F-99 없는 기능"))
    assert result.ready == []
    assert "jira.epics" in result.problems[0][1][0]


def test_에픽_코드는_첫_단어다():
    assert epic_code("F-02 보행 수치 계산") == "F-02"
    assert epic_code("공통") == "공통"
    assert epic_code(None) == ""


# ---------- 자동 보정 ----------

def test_할_일에_직접_쓴_태그는_지우고_경고한다():
    result = run(make_task(title="[ENGINE] 각도 계산"))
    assert result.ready[0].title == "각도 계산"
    assert any("태그" in w for w in result.warnings)


def test_우선순위가_비면_기본값으로_채운다():
    result = run(make_task(priority=None))
    assert result.ready[0].priority == "Medium"
    assert any("우선순위" in w for w in result.warnings)


def test_오류가_있는_줄에는_우선순위_경고를_하지_않는다():
    result = run(make_task(title="", priority=None))
    assert not any("우선순위" in w for w in result.warnings)


# ---------- 주간 SP 합계 ----------

def test_주간_합계는_이미_등록된_줄도_포함한다():
    new = make_task(sp="5")
    registered = make_task(page_id="page-2", sp="3", jira_key="PROJ-20")
    result = run(new, week_tasks=[new, registered])
    assert result.sp_by_person == {"조유진": 8}


def test_주간_합계가_기준보다_적으면_경고한다():
    result = run(make_task(sp="5"))
    assert any("적어요" in w for w in result.warnings)


def test_주간_합계가_기준_안이면_경고하지_않는다():
    week = [make_task(page_id=f"p{i}", sp="5") for i in range(5)]  # 25 SP
    result = run(week[0], week_tasks=week)
    assert not any("SP (기준" in w for w in result.warnings)


def test_주간_합계가_기준보다_많으면_경고한다():
    week = [make_task(page_id=f"p{i}", sp="5") for i in range(7)]  # 35 SP
    result = run(week[0], week_tasks=week)
    assert any("많아요" in w for w in result.warnings)
