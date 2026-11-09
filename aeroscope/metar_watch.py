"""Pure logic for detecting changes to NOAA METARs, without GTK or IO."""
from __future__ import annotations
import json
import re


def metar_fingerprint(report) -> str:
    """Compare report content, not local refresh time or transient API metadata."""
    raw = re.sub(r'\s+', ' ', str(getattr(report, 'raw', '') or '')).strip().upper()
    if raw:
        return 'RAW:' + raw
    details = getattr(report, 'details', None) or {}
    if details:
        return 'FIELDS:' + json.dumps([getattr(report, 'category', ''), details],
                                      sort_keys=True, default=str, ensure_ascii=False)
    return 'OBS:' + str(getattr(report, 'observed', '') or '') + ':' + str(getattr(report, 'category', ''))


class MetarChangeTracker:
    """First valid report establishes a baseline. Missing and failed reports do not reset it."""
    def __init__(self):
        self._seen: dict[str, tuple[str, str]] = {}

    def retain(self, codes):
        valid = set(codes)
        for code in set(self._seen) - valid:
            self._seen.pop(code, None)

    def observe(self, code, report):
        if report is None:
            return False, None
        previous = self._seen.get(code)
        current = (metar_fingerprint(report), str(getattr(report, 'category', 'N/D') or 'N/D'))
        self._seen[code] = current
        if previous is None or previous[0] == current[0]:
            return False, None
        return True, previous[1]
