import os
import yaml
from typing import Any, Dict


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Поддержка env-плейсхолдеров типа "env:VAR"
    def resolve_env(val):
        if isinstance(val, str) and val.startswith("env:"):
            return os.getenv(val.split(":", 1)[1], "")
        return val
    def walk(obj):
        if isinstance(obj, dict):
            return {k: walk(resolve_env(v)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [walk(resolve_env(x)) for x in obj]
        return resolve_env(obj)
    return walk(cfg)