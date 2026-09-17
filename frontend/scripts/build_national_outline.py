#!/usr/bin/env python3
"""Build the POK-inclusive national outline (public/geo/india.json format) from
the DataMeet india-composite.geojson (Survey-of-India-aligned, ~37.1°N). Keeps
the existing asset shape: {"rings": [[[lon,lat],...], ...]}. Pure Python.

Source: DataMeet — Country/india-composite.geojson (https://github.com/datameet/maps).
"""
import json
import math

SRC = "/tmp/india_composite.geojson"
OUT = "/home/agasthya/HELIOS/frontend/public/geo/india.json"
TOL = 0.02          # simplification (deg)
MIN_RING_PTS = 20   # drop trivial slivers
MIN_AREA = 0.02     # deg^2, drop tiny islands but keep Andaman etc.


def rdp(points, eps):
    if len(points) < 3:
        return points
    dmax, idx = 0.0, 0
    a, b = points[0], points[-1]
    for i in range(1, len(points) - 1):
        d = _perp(points[i], a, b)
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(points[: idx + 1], eps)[:-1] + rdp(points[idx:], eps)
    return [a, b]


def _perp(p, a, b):
    if a == b:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    num = abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1]))
    den = math.hypot(b[0] - a[0], b[1] - a[1])
    return num / den


def area(ring):
    a = 0.0
    for i in range(len(ring) - 1):
        a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(a) / 2.0


def rings_of(geom):
    t = geom["type"]
    if t == "Polygon":
        for r in geom["coordinates"]:
            yield r
    elif t == "MultiPolygon":
        for poly in geom["coordinates"]:
            for r in poly:
                yield r


def main():
    d = json.load(open(SRC))
    rings = []
    for f in d["features"]:
        for r in rings_of(f["geometry"]):
            ring = [[round(x, 3), round(y, 3)] for x, y in r]
            simp = rdp(ring, TOL)
            if len(simp) < MIN_RING_PTS or area(simp) < MIN_AREA:
                continue
            if simp[0] != simp[-1]:
                simp.append(simp[0])
            rings.append(simp)
    # sort by area desc; keep mainland + significant islands
    rings.sort(key=area, reverse=True)
    out = {
        "name": "India (national outline, POK-inclusive)",
        "source": "DataMeet Country/india-composite.geojson (Survey of India aligned)",
        "note": "Full national claim incl. northern disputed territory (~37.1N). "
                "Simplified for the SVG map. No boundaries invented.",
        "rings": rings,
    }
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    import os
    ys = [p[1] for r in rings for p in r]
    xs = [p[0] for r in rings for p in r]
    print("rings:", len(rings), "bytes:", os.path.getsize(OUT))
    print("lat", round(min(ys), 2), "..", round(max(ys), 2), " lon", round(min(xs), 2), "..", round(max(xs), 2))
    print("northernmost lat:", round(max(ys), 2), "(>=36.5 => POK-inclusive)")


if __name__ == "__main__":
    main()
