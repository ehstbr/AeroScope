"""Local airport bookmarks, separate from monitored aircraft registrations."""
from __future__ import annotations

import json
import re
from pathlib import Path
from .settings import CONFIG_DIR

AIRPORT_FAVORITES_FILE = CONFIG_DIR / 'favorite_airports.json'


def normalize_airport(code: str) -> str:
    code = str(code or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{3}', code):
        raise ValueError('Invalid airport IATA code')
    return code


def load_airport_favorites(path: Path = AIRPORT_FAVORITES_FILE) -> set[str]:
    try:
        rows = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return set()
    if not isinstance(rows, list):
        return set()
    result: set[str] = set()
    for row in rows:
        try:
            result.add(normalize_airport(row))
        except ValueError:
            continue
    return result


def save_airport_favorites(codes: set[str], path: Path = AIRPORT_FAVORITES_FILE) -> None:
    clean = sorted({normalize_airport(code) for code in codes})
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)
