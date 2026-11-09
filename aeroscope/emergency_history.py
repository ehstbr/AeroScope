"""Volatile emergency observation log (not an aviation incident database).

UTC timestamps describe when AeroScope saw a transponder code in the global
ADSB.lol feed, and the first successful scan when it was no longer visible.
Partial failures never close alerts. No files are written to disk.
"""
from __future__ import annotations
from datetime import datetime, timezone


def observed_at(timestamp):
    return datetime.fromtimestamp(float(timestamp), timezone.utc).strftime('%d/%m %H:%M:%S UTC')


class SessionEmergencyHistory:
    def __init__(self, max_records=200):
        self.records = []
        self._current = {}
        self.max_records = max(10, int(max_records))

    def observe(self, rows, failed_codes, checked_at):
        """Store successful scans; return ended records only for scanned codes."""
        timestamp = float(checked_at)
        by_key = {}
        for row in rows:
            code = str(row.get('squawk') or '')
            ident = str(row.get('hex') or '').lower()
            if code in ('7500', '7600', '7700') and ident and code not in failed_codes:
                by_key[(ident, code)] = row
        for key, row in by_key.items():
            current = self._current.get(key)
            if current is None:
                current = {'hex': key[0], 'squawk': key[1], 'flight': row.get('flight') or '',
                           'registration': row.get('registration') or '',
                           'description': row.get('description') or '',
                           'first_seen': timestamp, 'last_seen': timestamp,
                           'no_longer_seen': None}
                self._current[key] = current
                self.records.append(current)
            else:
                current['last_seen'] = timestamp
                for field in ('flight', 'registration', 'description'):
                    if row.get(field):
                        current[field] = row[field]
        ended = []
        for key, current in tuple(self._current.items()):
            if key not in by_key and key[1] not in failed_codes:
                current['no_longer_seen'] = timestamp
                ended.append(current)
                del self._current[key]
        # Preserve all active records, and recent ended ones, with a bounded log.
        if len(self.records) > self.max_records:
            finished = [r for r in self.records if r['no_longer_seen'] is not None]
            for old in finished[:max(0, len(self.records)-self.max_records)]:
                self.records.remove(old)
        return ended

    def ended(self):
        return list(reversed([r for r in self.records if r['no_longer_seen'] is not None]))
