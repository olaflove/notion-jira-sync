"""설정 읽기: .env(비밀 값) + config.yaml(프로젝트 설정)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_ENV = ("NOTION_TOKEN", "JIRA_EMAIL", "JIRA_API_TOKEN")


class ConfigError(Exception):
    """설정 파일이나 환경 변수가 잘못됐을 때."""


def load_config(path: str | None = None) -> dict:
    load_dotenv(ROOT / ".env")
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        raise ConfigError(f".env에 값이 없어요: {', '.join(missing)} (.env.example 참고)")

    cfg_path = Path(path) if path else ROOT / "config.yaml"
    if not cfg_path.exists():
        raise ConfigError(f"{cfg_path.name} 파일이 없어요. config.example.yaml을 복사해서 만드세요.")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    for section in ("notion", "jira", "rules"):
        if section not in cfg:
            raise ConfigError(f"{cfg_path.name}에 '{section}' 항목이 없어요.")

    cfg["secrets"] = {k: os.environ[k] for k in REQUIRED_ENV}
    return cfg
