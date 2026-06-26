from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _ROOT / "config.yaml"

load_dotenv(_ROOT / ".env")


def _load_yaml() -> dict[str, Any]:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class Config:
    def __init__(self) -> None:
        raw = _load_yaml()

        self.my_profile: str = raw["my_profile"]
        self.search: dict[str, Any] = raw["search"]
        self.locations: list[dict[str, Any]] = raw.get("locations", [])
        self.ats_title_keywords: list[str] = [
            kw.lower() for kw in raw.get("ats_title_keywords", [])
        ]
        self.companies: list[dict[str, str]] = raw.get("companies", [])
        self.digest: dict[str, Any] = raw["digest"]
        self.llm: dict[str, Any] = raw["llm"]

        # Env overrides
        if os.getenv("JOBHUNT_TOP_N"):
            self.digest["top_n"] = int(os.environ["JOBHUNT_TOP_N"])
        if os.getenv("JOBHUNT_HOURS_OLD"):
            self.search["hours_old"] = int(os.environ["JOBHUNT_HOURS_OLD"])

        self.anthropic_api_key: str = os.environ["ANTHROPIC_API_KEY"]

        # SMTP (all optional)
        self.adzuna_app_id: str = os.getenv("ADZUNA_APP_ID", "")
        self.adzuna_app_key: str = os.getenv("ADZUNA_APP_KEY", "")

        self.resend_api_key: str = os.getenv("RESEND_API_KEY", "")
        self.email_to: str = os.getenv("EMAIL_TO", "")

        self.output_dir: Path = _ROOT / self.digest.get("output_dir", "output")
        self.data_dir: Path = _ROOT / "data"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def adzuna_configured(self) -> bool:
        return bool(self.adzuna_app_id and self.adzuna_app_key)


# Singleton — import and reuse
cfg = Config()
