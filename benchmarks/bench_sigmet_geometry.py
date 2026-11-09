#!/usr/bin/env python3
"""Synthetic *geometry-only* SIGMET benchmark (no GI, maps, or network).

Usage: PYTHONPATH=. python3 benchmarks/bench_sigmet_geometry.py
No FPS claims: real rendering performance must be measured on GNOME/KDE.
"""
import math
import time
from aeroscope.weather_data import Sigmet
from aeroscope.sigmet_geometry import (prepare_sigmets, project,
                                       viewport_bounds, scene_visible)


def generate(n=150, vertices=250):
    advisories = []
    for i in range(n):
        lat = -34 + (i * 11 % 34)
        lon = -74 + (i * 17 % 38)
        radius = .4 + (i % 4) * .3
        ring = tuple((lat + radius * math.sin(k*math.tau/vertices),
                      lon + radius * math.cos(k*math.tau/vertices))
                     for k in range(vertices))
        advisories.append(Sigmet('TS', (ring,), 'FRQ TS FCST'))
    return advisories


def main():
    advisories = generate()
    t = time.perf_counter()
    scene = prepare_sigmets(advisories)
    prep = (time.perf_counter() - t) * 1000
    original = sum(len(r) for a in advisories for r in a.rings)
    print(f'NOAA sintético: {len(scene)} avisos, {original:,} vértices originais')
    print(f'Preparação inicial: {prep:.2f} ms')
    for zoom in (4, 6, 8):
        center = project(-18, -52)
        bounds = viewport_bounds(*center, 1180, 750, 256 * 2**zoom)
        t = time.perf_counter()
        visible = scene_visible(scene, bounds)
        first = sum(len(r.at_zoom(zoom)) for sh, rings in visible for r, shift in rings)
        initial = (time.perf_counter() - t)*1000
        t = time.perf_counter()
        for _ in range(100):
            sample = scene_visible(scene, bounds)
            repeated = sum(len(r.at_zoom(zoom)) for sh, rings in sample for r, shift in rings)
        cached = (time.perf_counter() - t)*10  # per iteration, ms
        print(f'Zoom {zoom}: {len(visible)} áreas visíveis, {first:,} vértices desenhados '
              f'({100*first/original:.1f}% do total); primeira {initial:.2f} ms; '
              f'geom. em cache {cached:.3f} ms/consulta')


if __name__ == '__main__':
    main()
