"""Volatile observation history for starred aircraft, independent of GTK.

An observed loss of signal is not a landing. Never transition to offline based
on a local 250 NM radar miss, provider error, or a single global lookup miss.
Timestamps refer to AeroScope observations, not official flight events.
"""
from __future__ import annotations
from .i18n import _
from .monitor_alerts import likely_airborne


STATES = {
    'airborne': _('Possibly in flight'),
    'ground': _('Detected on the ground'),
    'tracked': _('Tracked; status undetermined'),
    'no_position': _('Signal detected without position'),
    'offline': _('No recent signal'),
}


def classify_observation(state, aircraft):
    if state == 'offline':
        return 'offline'
    if state == 'active-no-position':
        return 'no_position'
    if state != 'active' or aircraft is None:
        return None
    if getattr(aircraft, 'on_ground', None) is True:
        return 'ground'
    if likely_airborne(aircraft):
        return 'airborne'
    return 'tracked'


class SessionFavoriteHistory:
    """One active event per starred identifier, with bounded prior events."""
    def __init__(self, max_records=200):
        self.records = []
        self.active = {}
        self._offline_streak = {}
        self._last_offline_check = {}
        self.max_records = max(10, int(max_records))

    def observe(self, checks, favorite_lookup):
        """Ingest actual completed checks; ignore errors/stale or duplicate timestamps."""
        changes = []
        for key, (status, aircraft, checked_at, *_rest) in checks.items():
            fav = favorite_lookup.get(key)
            if fav is None or checked_at is None:
                continue
            state = classify_observation(status, aircraft)
            if state is None:
                continue
            stamp = float(checked_at)
            previous = self.active.get(key)
            if previous is not None and stamp < previous['last_seen']:
                continue
            if state == 'offline':
                # Two different successful global checks must miss before a
                # transition becomes visible in the observation history.
                if self._last_offline_check.get(key) != stamp:
                    self._offline_streak[key] = self._offline_streak.get(key, 0) + 1
                    self._last_offline_check[key] = stamp
                if self._offline_streak[key] < 2:
                    continue
            else:
                self._offline_streak[key] = 0
                self._last_offline_check.pop(key, None)
            if previous and previous['state'] == state:
                previous['last_seen'] = max(previous['last_seen'], stamp)
                continue
            if previous:
                previous['ended_at'] = stamp
            name = str(getattr(fav, 'label', '') or getattr(fav, 'value', key))
            entry = {'key': key, 'name': name, 'state': state,
                     'description': STATES[state], 'first_seen': stamp,
                     'last_seen': stamp, 'ended_at': None}
            self.records.append(entry)
            self.active[key] = entry
            changes.append(entry)
        self._prune()
        return changes

    def remove(self, key, at):
        entry = self.active.pop(key, None)
        if entry is not None:
            entry['ended_at'] = float(at)
        self._offline_streak.pop(key, None)
        self._last_offline_check.pop(key, None)

    def ended(self):
        return list(reversed([e for e in self.records if e['ended_at'] is not None]))

    def _prune(self):
        excess = len(self.records) - self.max_records
        if excess > 0:
            for record in [r for r in self.records if r['ended_at'] is not None][:excess]:
                self.records.remove(record)
