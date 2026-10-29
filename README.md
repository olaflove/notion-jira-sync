# notion-jira-sync

Notion 데이터베이스에 적은 주간 할 일을 Jira 이슈와 스프린트로 자동 등록하는 Python 스크립트입니다.

## 목적

팀원마다 Jira 이슈 제목·필드 형식이 달라 팀장이 매주 형식을 고쳐야 했습니다.
형식을 사람이 외우게 하는 대신, **노션 입력 칸(선택지)이 컨벤션을 강제**하고 스크립트가 Jira 형식으로 바꿔 등록합니다.

## 동작

1. 노션 표에서 이번 주(월~일) 날짜인 줄을 읽습니다.
2. 빈 칸, SP 값(1·2·3·5), 사람별 주간 SP 합계를 검사합니다.
3. 담당자의 Jira 계정을 찾습니다. config의 `members` 표(이름 → accountId)를 먼저 보고, 없으면 이메일로 찾습니다.
4. 만드는 순서를 **담당자별로 묶고(config `members` 순서) → 마감일 오름차순 → 같은 날이면 제목 앞 `(n/m)`의 n 오름차순**으로 정렬합니다. Jira 키와 보드 순서가 만든 순서를 따르기 때문에, 한 사람의 일이 키 번호상 끊기지 않고 `(1/3) → (2/3) → (3/3)`도 번호 순으로 이어집니다.
5. `[파트] 할 일` 제목, 담당자, 에픽, 기한, SP, 레이블, 우선순위를 채워 이슈를 만듭니다.
6. 만든 이슈 키를 노션 `Jira 키` 칸에 적습니다. 키가 있는 줄은 다시 실행해도 건너뜁니다(중복 방지).
7. 진행 중인 스프린트에 이슈를 넣습니다.

기본 실행은 **미리보기(dry-run)** 이고, `--apply`를 붙여야 실제로 만듭니다.

## 설정

```bash
python -m venv venv
venv\Scripts\activate        # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env       # 토큰 입력
copy config.example.yaml config.yaml   # 프로젝트 값 입력
```

- Notion: 개발자 도구 → 신규 연결(API 토큰). 기능은 **콘텐츠 읽기, 콘텐츠 업데이트, 이메일 포함 사용자 정보 읽기**만 켭니다. 대상 페이지의 `…` → 연결에서 추가합니다.
- Jira: Atlassian 계정 → 보안 → API 토큰.

## 실행

```bash
python -m src.main                     # 미리보기
python -m src.main --apply             # 실제 등록
python -m src.main --week 2026-10-27   # 다른 주
python -m src.main --apply --no-sprint # 스프린트 배정 생략
```

## 노션 표 구조

| 칸 | 종류 |
|---|---|
| 할 일 | 제목 |
| 담당자 | 선택 (팀원 이름) 또는 사람 |
| 날짜 | 날짜 |
| 파트 | 선택 |
| 에픽 | 선택 (첫 단어가 config의 `jira.epics` 키) |
| SP | 선택 (1, 2, 3, 5) |
| 우선순위 | 선택 |
| Jira 키 | 텍스트 (스크립트가 채움) |

### 담당자 칸: 선택(이름)과 사람 중 고르기

- **선택(이름)**: 팀원이 노션 워크스페이스에 없어도 쓸 수 있습니다. 대신 `config.yaml`의 `members`에 모든 팀원의 `이름: Jira accountId`를 적어야 합니다.
  Jira 이름 검색을 쓰지 않는 이유는, 여러 팀이 함께 쓰는 Jira 사이트에서는 같은 이름의 다른 계정이 나올 수 있기 때문입니다.
- **사람**: 팀원이 워크스페이스 멤버나 게스트여야 합니다. 이메일로 Jira 계정을 자동으로 찾습니다.
