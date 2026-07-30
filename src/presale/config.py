"""Config + secret loader.

Non-secret tunables live in config/settings.yaml; secrets come from the
environment only, loaded from a gitignored .env via python-dotenv.

SECURITY: .env is never read, printed, or logged. This module loads it into the
process environment with python-dotenv and exposes only typed accessors — it
never returns raw key strings to callers that would print them. See the
"Secrets & .env safety" section in CLAUDE.md.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_YAML = PROJECT_ROOT / "config" / "settings.yaml"
ENV_PATH = PROJECT_ROOT / ".env"

# Load .env into os.environ once, at import. `override=False` means real
# environment variables (e.g. CI secrets) win over the file.
load_dotenv(dotenv_path=ENV_PATH, override=False)


class Secrets(BaseSettings):
    """API keys and endpoints — read from the process environment only.

    Values are populated by python-dotenv's load_dotenv above; pydantic just
    validates and types them. Never log or print an instance of this class.
    """

    molit_api_key: str = ""
    ecos_api_key: str = ""
    vworld_api_key: str = ""
    kakao_rest_api_key: str = ""
    applyhome_api_key: str = ""
    neis_api_key: str = ""
    schoolinfo_api_key: str = ""
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    mlflow_artifact_root: str = "./mlartifacts"

    model_config = SettingsConfigDict(extra="ignore")

    def missing_keys(self) -> list[str]:
        """Names of required API keys that are still empty (for a startup check).

        Returns key *names* only — never the values — so it is safe to print.
        """
        required = (
            "molit_api_key",
            "ecos_api_key",
            "applyhome_api_key",
        )
        return [name for name in required if not getattr(self, name)]


def load_yaml(path: Path = SETTINGS_YAML) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class Settings:
    """Merged view: YAML tunables + environment secrets."""

    def __init__(self) -> None:
        self.yaml: dict[str, Any] = load_yaml()
        self.secrets = Secrets()

    @property
    def region(self) -> dict[str, Any]:
        return self.yaml["region"]

    @property
    def paths(self) -> dict[str, Any]:
        return self.yaml["paths"]

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.yaml
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def resolve_lawd_codes(self) -> list[str]:
        """MOLIT 시군구 codes to ingest.

        An explicit `region.lawd_codes` wins; otherwise codes are read from the
        bundled reference table and filtered by `region.sido_prefixes` (so
        expanding nationwide is a config change, not a code change).
        """
        explicit = self.get("region", "lawd_codes", default=[]) or []
        if explicit:
            return [str(c) for c in explicit]
        prefixes = tuple(str(p) for p in self.get("region", "sido_prefixes", default=[]))
        exclude = {str(c) for c in (self.get("region", "exclude_codes", default=[]) or [])}
        include = [str(c) for c in (self.get("region", "include_codes", default=[]) or [])]
        ref = self.get("region", "reference_file", default="data/reference/lawd_codes.csv")
        path = PROJECT_ROOT / ref
        codes: list[str] = []
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                code = row["lawd_cd"].strip()
                if (not prefixes or code.startswith(prefixes)) and code not in exclude:
                    codes.append(code)
        # extra codes not derivable from the (stale) reference table — e.g. the
        # 구-level codes MOLIT keys 부천/화성 data under (see settings.yaml).
        for code in include:
            if code not in exclude and code not in codes:
                codes.append(code)
        return codes


@lru_cache
def get_settings() -> Settings:
    return Settings()
