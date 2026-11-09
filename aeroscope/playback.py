"""Timestamp-accurate ADSB.aero flight playback (no GTK dependency).

Each MultiLineString segment has its own synchronized timestamps. Missing
coverage is NEVER interpolated across separate segments.
"""
from __future__ import annotations
from .i18n import _
from bisect import bisect_right
from dataclasses import dataclass, field
import math


@dataclass(frozen=True)
class TrackSample:
    time: float
    lat: float
    lon: float
    altitude_ft: float | None = None
    speed_kt: float | None = None


@dataclass(frozen=True)
class PlaybackPosition:
    time: float
    lat: float
    lon: float
    altitude_ft: float | None
    segment: int
    coverage_gap: bool = False
    speed_kt: float | None = None


@dataclass
class HistoricalReplay:
    segments: list[list[TrackSample]]
    start: float
    end: float
    speed_segments: list[list[tuple[float, float]]] = field(default_factory=list)

    @property
    def total_distance_km(self):
        return sum(_segment_distance(segment)[-1] for segment in self.segments if segment)

    def distance_at(self, timestamp):
        """Distance along observed geometry; gaps add no fictitious mileage."""
        target = min(self.end, max(self.start, float(timestamp)))
        total = 0.0
        for segment in self.segments:
            if not segment or segment[0].time > target:
                break
            distances = _segment_distance(segment)
            times = [p.time for p in segment]
            if target >= segment[-1].time:
                total += distances[-1]
                continue
            i = max(0, bisect_right(times, target) - 1)
            if i + 1 < len(segment):
                ratio = (target - times[i]) / max(.001, times[i+1]-times[i])
                return total + distances[i] + ratio * (distances[i+1]-distances[i])
            return total + distances[i]
        return total

    def time_at_distance(self, distance):
        """Inverse of observed cumulative distance for clickable distance axis."""
        target = max(0, min(self.total_distance_km, float(distance)))
        accum = 0.0
        for segment in self.segments:
            if not segment:
                continue
            distances = _segment_distance(segment)
            if target > accum + distances[-1]:
                accum += distances[-1]
                continue
            partial = target - accum
            index = max(0, bisect_right(distances, partial) - 1)
            if index + 1 >= len(segment):
                return segment[-1].time
            span = distances[index+1] - distances[index]
            ratio = (partial - distances[index]) / span if span > .00001 else 0.0
            return segment[index].time + ratio * (segment[index+1].time-segment[index].time)
        return self.end

    def series(self, metric):
        """Exact ADSB.aero time series; independently sampled GS and geometry."""
        if metric == 'altitude':
            return [[(p.time, p.altitude_ft) for p in seg if p.altitude_ft is not None]
                    for seg in self.segments]
        if metric != 'speed':
            raise ValueError(_('Unknown metric'))
        result = []
        for segment, speeds in zip(self.segments, self.speed_segments):
            if not speeds:
                result.append([])
                continue
            steps = []
            # Sparse ADSB.aero ground speed is STEPWISE, not sampled at every
            # geometry vertex. A single sample extends to the observed end.
            for t, speed in speeds:
                if steps and t > steps[-1][0]:
                    steps.append((t, steps[-1][1]))
                steps.append((t, speed))
            if steps and segment[-1].time > steps[-1][0]:
                steps.append((segment[-1].time, steps[-1][1]))
            result.append(steps)
        return result

    def speed_at(self, timestamp, segment_index):
        if segment_index < 0 or segment_index >= len(self.speed_segments):
            return None
        measurements = self.speed_segments[segment_index]
        if not measurements:
            return None
        times = [t for t, _ in measurements]
        j = bisect_right(times, float(timestamp)) - 1
        return measurements[j][1] if j >= 0 else None

    def bearing_at(self, timestamp, default=0.0):
        """Forward course from points of the SAME observed segment (degrees)."""
        when = min(self.end, max(self.start, float(timestamp)))
        for segment in self.segments:
            if len(segment) < 2:
                continue
            if when < segment[0].time:
                return default
            if when <= segment[-1].time:
                times = [p.time for p in segment]
                i = min(len(segment)-2, max(0, bisect_right(times, when)-1))
                return _bearing(segment[i], segment[i+1], default)
            default = _bearing(segment[-2], segment[-1], default)
        return default

    @property
    def duration(self):
        return max(0.0, self.end - self.start)

    def seek(self, timestamp: float) -> PlaybackPosition | None:
        """Interpolate *inside* an observed segment, freeze on gaps.

        The frozen marker is labeled as no coverage by the player. A new
        segment is never joined by a fictitious path or interpolated position.
        """
        if not self.segments:
            return None
        when = min(self.end, max(self.start, float(timestamp)))
        previous = None
        for index, segment in enumerate(self.segments):
            if not segment:
                continue
            if when < segment[0].time:
                if previous is None:
                    first = segment[0]
                    return PlaybackPosition(when, first.lat, first.lon, first.altitude_ft, index, True, self.speed_at(when, index))
                return PlaybackPosition(when, previous.lat, previous.lon,
                                        previous.altitude_ft, index - 1, True, self.speed_at(previous.time, index-1))
            if when > segment[-1].time:
                previous = segment[-1]
                continue
            times = [sample.time for sample in segment]
            i = max(0, bisect_right(times, when) - 1)
            a = segment[i]
            if i + 1 >= len(segment) or a.time >= when:
                return PlaybackPosition(when, a.lat, a.lon, a.altitude_ft, index, False, self.speed_at(when, index))
            b = segment[i + 1]
            ratio = (when - a.time) / max(0.001, b.time - a.time)
            # Wrap longitude across the international date line, not the globe.
            delta_lon = (b.lon - a.lon + 180) % 360 - 180
            lon = (a.lon + ratio * delta_lon + 180) % 360 - 180
            if a.altitude_ft is not None and b.altitude_ft is not None:
                alt = a.altitude_ft + ratio * (b.altitude_ft - a.altitude_ft)
            else:
                alt = a.altitude_ft
            return PlaybackPosition(when, a.lat + ratio * (b.lat - a.lat), lon, alt, index, False, self.speed_at(when, index))
        last = self.segments[-1][-1]
        return PlaybackPosition(when, last.lat, last.lon, last.altitude_ft,
                                len(self.segments) - 1, when > last.time, self.speed_at(last.time, len(self.segments)-1))

    def visible_segments(self, timestamp: float) -> list[list[tuple[float, float]]]:
        """Only positions observed by the playback time, segmented by coverage."""
        when = min(self.end, max(self.start, float(timestamp)))
        out = []
        for segment in self.segments:
            points = [(p.lat, p.lon) for p in segment if p.time <= when]
            if points:
                out.append(points)
            if segment and segment[-1].time > when:
                break
        return out

    def full_coordinates(self) -> list[list[tuple[float, float]]]:
        return [[(p.lat, p.lon) for p in segment] for segment in self.segments]



def _distance_km(a, b):
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians((b.lon - a.lon + 180) % 360 - 180)
    h = math.sin(dlat / 2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon / 2)**2
    return 6371.0088 * 2 * math.asin(min(1., math.sqrt(h)))


def _segment_distance(segment):
    distance = [0.0]
    for a, b in zip(segment, segment[1:]):
        distance.append(distance[-1] + _distance_km(a, b))
    return distance


def _bearing(a, b, default=0.0):
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlon = math.radians((b.lon - a.lon + 180) % 360 - 180)
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    if abs(x) + abs(y) < 1e-12:
        return default
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _speed_groups(raw, coordinate_chunks):
    """Sparse ADSB.aero path_gs series: [[timestamp, knots], ...] per segment.

    Never treat null/synthetic/derived speeds as an actual transmitted value.
    """
    if not isinstance(raw, list):
        return [[] for _ in coordinate_chunks]
    groups = raw if raw and all(isinstance(g, list) for g in raw) and (
        not raw[0] or (isinstance(raw[0][0], (list, tuple, dict)))) else [raw]
    result = []
    for i in range(len(coordinate_chunks)):
        data = groups[i] if i < len(groups) else []
        clean = []
        for item in data:
            if isinstance(item, dict):
                t = _number(item.get('t', item.get('time')))
                v = _number(item.get('v', item.get('value')))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                t, v = _number(item[0]), _number(item[1])
            else:
                continue
            if t is not None and v is not None and 0 <= v < 1800:
                clean.append((t, v))
        result.append(sorted(clean))
    return result

def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def parse_historical_replay(payload: dict) -> HistoricalReplay | None:
    """Parse ADSB.aero /flights/{id} native path + time series safely."""
    if not isinstance(payload, dict):
        return None
    path = payload.get('path')
    stamps = payload.get('timestamps')
    if not (isinstance(path, dict) and path.get('type') == 'MultiLineString'
            and isinstance(path.get('coordinates'), list) and isinstance(stamps, list)):
        return None
    chunks = []
    speed_groups = _speed_groups(payload.get('path_gs'), path['coordinates'][:100])
    for chunk_index, (coordinates, times) in enumerate(zip(path['coordinates'][:100], stamps[:100])):
        if not isinstance(coordinates, list) or not isinstance(times, list):
            continue
        if len(coordinates) != len(times):
            continue  # Time/coordinate misalignment is not safe for playback.
        clean = []
        sparse_speeds = speed_groups[chunk_index]
        speed_times = [t for t, value in sparse_speeds]
        for point, ts in zip(coordinates, times):
            if not isinstance(point, (tuple, list)) or len(point) < 2:
                continue
            t, lon, lat = _number(ts), _number(point[0]), _number(point[1])
            if t is None or lat is None or lon is None or not (-85 <= lat <= 85 and -180 <= lon <= 180):
                continue
            alt = _number(point[2]) if len(point) >= 3 else None
            if clean and t <= clean[-1].time:
                continue
            j = bisect_right(speed_times, t) - 1
            # Do not invent speed for timestamps before first measured value.
            speed = sparse_speeds[j][1] if j >= 0 else None
            clean.append(TrackSample(t, lat, lon, alt, speed))
        if len(clean) >= 2:
            # Retain timestamps in lockstep when downsampling long flight paths.
            if len(clean) > 3000:
                stride = math.ceil(len(clean) / 2999)
                clean = clean[::stride] + ([clean[-1]] if clean[-1] not in clean[::stride] else [])
            chunks.append((clean, sparse_speeds))
    chunks.sort(key=lambda group: group[0][0].time)
    # Reject overlapping/non-sequential segments instead of producing a false route.
    separated = []
    separate_speeds = []
    for segment, speeds in chunks:
        if separated and segment[0].time <= separated[-1][-1].time:
            continue
        separated.append(segment)
        separate_speeds.append([(t,v) for t,v in speeds if t <= segment[-1].time])
    if not separated:
        return None
    return HistoricalReplay(separated, separated[0][0].time, separated[-1][-1].time,
                            separate_speeds)
