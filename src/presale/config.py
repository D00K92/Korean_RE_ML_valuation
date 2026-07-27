"""Config + secret loader.

Non-secret tunables live in config/settings.yaml; secrets come from the
environment (.env, gitignored) only. Nothing here is hardcoded — region codes,
comp radii, and windows are all read from the YAML.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_YAML = PROJECT_ROOT / "config" / "settings.yaml"


class Secrets(BaseSettings):
    """API keys and endpoints — environment only."""

    molit_api_key: str = ""
    ecos_api_key: str = ""
    vworld_api_key: str = ""
    kakao_rest_api_key: str = ""
    applyhome_api_key: str = ""
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    mlflow_artifact_root: str = "./mlartifacts"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
