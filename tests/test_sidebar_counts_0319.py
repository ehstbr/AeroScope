"""Regression tests for sidebar labels and trustworthy counts."""
import unittest
from dataclasses import dataclass
from aeroscope.sidebar_counts import tab_label, airborne_favorites_count
from aeroscope.monitor import normalize_favorite


@dataclass
class Plane:
    hex: str = 'aabbcc'
    altitude_ft: float = 32000
    speed_kts: float = 450
    on_ground: bool | None = False


class SidebarCountsTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(tab_label('Visíveis', 6), 'Visíveis (6)')
        self.assertEqual(tab_label('Favoritos', 1), 'Favoritos (1)')
        self.assertEqual(tab_label('Emergências', None), 'Emergências (—)')
        self.assertEqual(tab_label('Emergências', 0), 'Emergências (0)')

    def test_airborne_only(self):
        f = [normalize_favorite('registration', x) for x in ('PT-MUJ', 'PR-AAA', 'PR-BBB', 'PR-CCC')]
        statuses = {
            f[0].key: ('active', Plane(), 123.0, ''),
            f[1].key: ('active', Plane(hex='ddeeff', on_ground=True), 123.0, ''),
            f[2].key: ('active', Plane(hex='123456', altitude_ft=0, speed_kts=15), 123.0, ''),
            f[3].key: ('offline', None, 123.0, ''),
        }
        self.assertEqual(airborne_favorites_count(f, statuses), 1)

    def test_same_airframe_favorited_twice(self):
        f = [normalize_favorite('registration', 'PT-MUJ'), normalize_favorite('icao', 'AABBCC')]
        statuses = {favorite.key: ('active', Plane(), 123.0, '') for favorite in f}
        self.assertEqual(airborne_favorites_count(f, statuses), 1)

    def test_no_valid_position(self):
        f = [normalize_favorite('registration', 'PT-MUJ')]
        self.assertEqual(airborne_favorites_count(f, {f[0].key: ('active-no-position', None, 1, '')}), 0)
        self.assertEqual(airborne_favorites_count(f, {f[0].key: ('error', None, 1, '')}), 0)

if __name__ == '__main__':
    unittest.main()
