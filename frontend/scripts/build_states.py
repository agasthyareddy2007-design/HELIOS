#!/usr/bin/env python3
"""
Build a compact, SVG-ready India state/UT boundary asset from an authoritative
India state GeoJSON. Simplifies geometry (Douglas-Peucker) and computes a robust
interior label point (polylabel / pole of inaccessibility) per state so names sit
inside irregular states. Output matches the frontend SVG convention: polygons as
arrays of [lon, lat].

SOURCE (current, Survey-of-India-aligned, POK-inclusive):
  DataMeet — States/Admin2.* shapefile (converted to GeoJSON by
  scripts/read_datameet_shp.py). https://github.com/datameet/maps
  Provenance: community-maintained Indian open geographic data following the
  Survey of India national representation — includes the full northern claim
  (Ladakh reaches ~37.1°N, i.e. POK / Aksai Chin territory) and the post-2019
  reorganisation (Jammu & Kashmir and Ladakh as separate UTs; Telangana and
  Andhra Pradesh separate; Odisha/Uttarakhand modern names). License: the
  DataMeet maps collection is published for open community use (attribution to
  DataMeet). Field carrying the state/UT name: ST_NM (mapped to NAME_1 here).
  Converted to /tmp/india_state.geojson before running this script.

  Disputed-territory note: disputed northern territory is presented per the
  Indian version via the authoritative source's own geometry (Ladakh UT). No
  administrative subdivision is invented; POK proper is not labelled as an
  ordinary state — it lies within the national outline / Ladakh extent as the
  source provides it.

Local build tool for the media/geo asset only. Touches nothing scientific.
"""
import json
import math

SRC = "/tmp/india_state.geojson"
OUT = "/home/agasthya/HELIOS/frontend/public/geo/india_states.json"
SIMPLIFY_TOL = 0.02  # degrees (~2 km); balances detail vs. size for a dark map

# short display names / abbreviations for tight states (DataMeet ST_NM values)
RENAME = {
    "Andaman & Nicobar": "A & N",
    "Dadra and Nagar Haveli and Daman and Diu": "DNH & DD",
    "Jammu & Kashmir": "Jammu & Kashmir",
    "Ladakh": "Ladakh",
    "Arunachal Pradesh": "Arunachal Pr.",
    "Himachal Pradesh": "Himachal Pr.",
    "Uttar Pradesh": "Uttar Pradesh",
    "Madhya Pradesh": "Madhya Pradesh",
    "Andhra Pradesh": "Andhra Pradesh",
    "Delhi": "Delhi",
    "Puducherry": "Puducherry",
    "Chandigarh": "Chandigarh",
    "Lakshadweep": "Lakshadweep",
}


def rdp(points, eps):
    """Ramer–Douglas–Peucker simplification for a ring of [lon,lat]."""
    if len(points) < 3:
        return points
    dmax, idx = 0.0, 0
    a, b = points[0], points[-1]
    for i in range(1, len(points) - 1):
        d = _perp(points[i], a, b)
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        left = rdp(points[: idx + 1], eps)
        right = rdp(points[idx:], eps)
        return left[:-1] + right
    return [a, b]


def _perp(p, a, b):
    if a == b:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    num = abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1]))
    den = math.hypot(b[0] - a[0], b[1] - a[1])
    return num / den


def ring_area(ring):
    a = 0.0
    for i in range(len(ring) - 1):
        a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(a) / 2.0


def polygons_of(geom):
    """Yield outer rings from Polygon / MultiPolygon."""
    if geom["type"] == "Polygon":
        yield geom["coordinates"][0]
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            yield poly[0]


# ---- polylabel (pole of inaccessibility) -----------------------------------
def _point_to_poly_dist(x, y, polygon):
    inside = False
    min_sq = math.inf
    for ring in polygon:
        n = len(ring)
        for i in range(n):
            j = (i - 1) % n
            ax, ay = ring[i]
            bx, by = ring[j]
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay + 1e-15) + ax:
                inside = not inside
            min_sq = min(min_sq, _seg_dist_sq(x, y, ax, ay, bx, by))
    d = math.sqrt(min_sq)
    return d if inside else -d


def _seg_dist_sq(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx or dy:
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        if t > 1:
            x1, y1 = x2, y2
        elif t > 0:
            x1, y1 = x1 + dx * t, y1 + dy * t
    return (px - x1) ** 2 + (py - y1) ** 2


def polylabel(polygon, precision=0.02):
    """Largest inscribed-circle centre — a robust interior label point."""
    import heapq

    min_x = min(p[0] for p in polygon[0])
    min_y = min(p[1] for p in polygon[0])
    max_x = max(p[0] for p in polygon[0])
    max_y = max(p[1] for p in polygon[0])
    w, h = max_x - min_x, max_y - min_y
    cell = min(w, h)
    if cell == 0:
        return [(min_x + max_x) / 2, (min_y + max_y) / 2]
    r = cell / 2

    class Cell:
        __slots__ = ("x", "y", "h", "d", "mx")

        def __init__(self, x, y, hh):
            self.x, self.y, self.h = x, y, hh
            self.d = _point_to_poly_dist(x, y, polygon)
            self.mx = self.d + self.h * math.sqrt(2)

        def __lt__(self, o):
            return self.mx > o.mx

    heap = []
    x = min_x
    while x < max_x:
        y = min_y
        while y < max_y:
            heapq.heappush(heap, Cell(x + r, y + r, r))
            y += cell
        x += cell
    # centroid seed
    best = Cell((min_x + max_x) / 2, (min_y + max_y) / 2, 0)
    while heap:
        c = heapq.heappop(heap)
        if c.d > best.d:
            best = c
        if c.mx - best.d <= precision:
            continue
        hh = c.h / 2
        for dx, dy in ((-hh, -hh), (hh, -hh), (-hh, hh), (hh, hh)):
            heapq.heappush(heap, Cell(c.x + dx, c.y + dy, hh))
    return [round(best.x, 3), round(best.y, 3)]


def main():
    data = json.load(open(SRC))
    states = []
    for f in data["features"]:
        name = f["properties"]["NAME_1"]
        rings = []
        largest = None
        largest_area = 0.0
        for ring in polygons_of(f["geometry"]):
            simp = rdp([[round(x, 3), round(y, 3)] for x, y in ring], SIMPLIFY_TOL)
            if len(simp) < 4:
                continue
            if simp[0] != simp[-1]:
                simp.append(simp[0])
            rings.append(simp)
            a = ring_area(simp)
            if a > largest_area:
                largest_area, largest = a, simp
        if not rings:
            continue
        label = polylabel([largest]) if largest else None
        states.append({
            "name": name,
            "label": RENAME.get(name, name),
            "labelPoint": label,
            "area": round(largest_area, 4),
            "rings": rings,
        })
    out = {"type": "india_states", "source": "DataMeet Admin2 (Survey of India aligned, POK-inclusive), simplified",
           "count": len(states), "states": states}
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    import os
    print("states:", len(states), "bytes:", os.path.getsize(OUT))
    # sanity: label points inside bounds
    for s in states[:5]:
        print(" ", s["name"], "label", s["labelPoint"], "rings", len(s["rings"]))


if __name__ == "__main__":
    main()
