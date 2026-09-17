#!/usr/bin/env python3
"""Pure-Python reader for the DataMeet Admin2 shapefile (WGS84 Polygon, type 5)
+ its DBF (field ST_NM). Emits a GeoJSON-like FeatureCollection of state/UT
polygons with the POK-inclusive geometry (Survey-of-India-aligned), so the
existing build_states.py can simplify it into the SVG map asset. No GDAL/geopandas.

Local build tool for the map asset only; touches nothing scientific.
Source: DataMeet — https://github.com/datameet/maps (States/Admin2.*).
"""
import json
import struct
import sys

SHP = "/tmp/datameet/Admin2.shp"
DBF = "/tmp/datameet/Admin2.dbf"
OUT = "/tmp/datameet/admin2.geojson"


def read_dbf(path):
    with open(path, "rb") as f:
        hdr = f.read(32)
        nrec = struct.unpack("<I", hdr[4:8])[0]
        hlen = struct.unpack("<H", hdr[8:10])[0]
        rlen = struct.unpack("<H", hdr[10:12])[0]
        fields = []
        pos = 32
        while True:
            fd = f.read(32)
            if fd[0:1] == b"\r" or len(fd) < 32:
                break
            name = fd[0:11].split(b"\x00")[0].decode("latin1")
            flen = fd[16]
            fields.append((name, flen))
            pos += 32
        # records start after the 0x0D terminator
        f.seek(hlen)
        recs = []
        for _ in range(nrec):
            raw = f.read(rlen)
            if not raw or raw[0:1] == b"\x1a":
                break
            off = 1  # deletion flag
            row = {}
            for name, flen in fields:
                val = raw[off:off + flen].decode("latin1").strip()
                row[name] = val
                off += flen
            recs.append(row)
    return recs


def read_shp_polygons(path):
    """Yield list-of-rings (each ring: list of [lon,lat]) per record, type 5."""
    with open(path, "rb") as f:
        f.read(100)  # header
        out = []
        while True:
            rh = f.read(8)
            if len(rh) < 8:
                break
            rlen = struct.unpack(">i", rh[4:8])[0] * 2
            data = f.read(rlen)
            if len(data) < 4:
                break
            shptype = struct.unpack("<i", data[0:4])[0]
            if shptype != 5:  # only Polygon
                out.append([])
                continue
            # box(4d) numParts(i) numPoints(i) parts(numParts i) points(numPoints 2d)
            numparts = struct.unpack("<i", data[36:40])[0]
            numpoints = struct.unpack("<i", data[40:44])[0]
            p = 44
            parts = list(struct.unpack("<%di" % numparts, data[p:p + 4 * numparts]))
            p += 4 * numparts
            coords = struct.unpack("<%dd" % (2 * numpoints), data[p:p + 16 * numpoints])
            rings = []
            parts.append(numpoints)
            for i in range(numparts):
                s, e = parts[i], parts[i + 1]
                ring = [[coords[2 * j], coords[2 * j + 1]] for j in range(s, e)]
                rings.append(ring)
            out.append(rings)
    return out


def main():
    recs = read_dbf(DBF)
    geoms = read_shp_polygons(SHP)
    if len(recs) != len(geoms):
        print(f"WARN: {len(recs)} dbf recs vs {len(geoms)} shp geoms", file=sys.stderr)
    feats = []
    n = min(len(recs), len(geoms))
    for i in range(n):
        name = recs[i].get("ST_NM", "").strip()
        rings = geoms[i]
        if not name or not rings:
            continue
        feats.append({
            "type": "Feature",
            "properties": {"NAME_1": name},  # build_states.py reads NAME_1
            # emit each ring as its own polygon so multi-part states (islands,
            # exclaves) are all retained by polygons_of() in build_states.py.
            "geometry": {"type": "MultiPolygon", "coordinates": [[r] for r in rings]},
        })
    fc = {"type": "FeatureCollection", "features": feats}
    json.dump(fc, open(OUT, "w"))
    names = sorted(set(f["properties"]["NAME_1"] for f in feats))
    print("features:", len(feats), "distinct states:", len(names))
    print("Telangana:", "Telangana" in names, "| Andhra Pradesh:", "Andhra Pradesh" in names)
    print("J&K variants:", [x for x in names if "ashmir" in x or "adakh" in x or "aksai" in x.lower()])
    # J&K northern extent
    for f in feats:
        if "ashmir" in f["properties"]["NAME_1"] or "adakh" in f["properties"]["NAME_1"]:
            ys = [pt[1] for r in f["geometry"]["coordinates"] for pt in r]
            print(f"  {f['properties']['NAME_1']}: max lat {round(max(ys),2)}")
    print("names:", names)


if __name__ == "__main__":
    main()
