#!/usr/bin/env python3
"""
Dayton Parcel Server
Serves parcel GeoJSON from a local shapefile, filtered by bounding box.
Also serves the pre-built zoning GeoJSON layer.

Requirements: GDAL command-line tools (ogr2ogr) on PATH.
  macOS:  brew install gdal
  Ubuntu: apt install gdal-bin

Usage:
  python3 server.py          # default port 8001
  python3 server.py 9000     # custom port

Endpoints:
  GET /parcels?bbox=minLon,minLat,maxLon,maxLat
  GET /zoning          — full Dayton zoning layer (pre-built zoning.geojson)
  GET /health
"""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
HERE = os.path.dirname(os.path.abspath(__file__))
SHAPEFILE = os.path.join(HERE, "parcels.shp")
ZONING_FILE = os.path.join(HERE, "zoning.geojson")
MAX_FEATURES = 3000

# Cache the zoning GeoJSON in memory on first request
_zoning_cache = None

# Fields to pull from the shapefile
SELECT_FIELDS = ",".join([
    "TAXPINNO",
    "LOC_NBR",
    "LOC_DIR",
    "LOC_STREET",
    "LOC_SUFFIX",
    "LOC_ZIP",
    "ACREAGE",
    "PARCEL_USE",
    "PARCEL_U_1",
    "SHAPE_STAr",   # area in Ohio State Plane sq ft — convert to acres in post-process
])

# Ohio rough bounding box for basic input validation
OHIO_BBOX = (-85.0, 38.2, -80.5, 42.4)


def build_address(props):
    """Construct a readable address from component fields."""
    num    = props.get("LOC_NBR") or ""
    dirc   = props.get("LOC_DIR") or ""
    street = props.get("LOC_STREET") or ""
    suffix = props.get("LOC_SUFFIX") or ""
    zipcd  = props.get("LOC_ZIP") or ""

    # LOC_NBR comes back as a float string (e.g. "142.00000000") — strip decimals
    if num:
        try:
            num = str(int(float(num)))
        except (ValueError, TypeError):
            num = str(num).strip()

    parts = [p.strip() for p in [num, dirc, street, suffix] if p.strip()]
    addr  = " ".join(parts)
    if not addr:
        return None
    if zipcd:
        addr += f", DAYTON OH {zipcd}"
    return addr.title().replace(" Oh ", " OH ")


def compute_acres(props):
    """
    Derive acreage. Prefer the ACREAGE field; fall back to SHAPE_STAr (sq ft in
    Ohio State Plane US survey feet) converted to acres.
    """
    raw = props.get("ACREAGE") or ""
    try:
        v = float(raw)
        if 0 < v < 10000:
            return round(v, 3)
    except (ValueError, TypeError):
        pass

    shape_area = props.get("SHAPE_STAr") or ""
    try:
        sq_ft = float(shape_area)
        if sq_ft > 0:
            return round(sq_ft / 43560, 3)
    except (ValueError, TypeError):
        pass

    return None


def enrich_feature(feature):
    """Post-process a GeoJSON feature: compute derived fields, drop raw components."""
    props = feature.get("properties") or {}

    address = build_address(props)
    acres   = compute_acres(props)

    feature["properties"] = {
        "TAXPINNO":   props.get("TAXPINNO"),
        "ADDRESS":    address,
        "ZIP":        props.get("LOC_ZIP"),
        "ACRES":      acres,
        "SQFT":       round(acres * 43560) if acres else None,
        "PARCEL_USE": props.get("PARCEL_USE") or None,
        "USE_DESC":   props.get("PARCEL_U_1") or None,
    }
    return feature


class ParcelHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        status = args[1] if len(args) > 1 else "?"
        print(f"  {args[0]}  →  {status}", flush=True)

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self.send_json(200, {"status": "ok", "shapefile": SHAPEFILE, "zoning": ZONING_FILE})
            return

        if parsed.path == "/zoning":
            global _zoning_cache
            if _zoning_cache is None:
                try:
                    with open(ZONING_FILE, "rb") as f:
                        _zoning_cache = f.read()
                except OSError as e:
                    self.send_json(500, {"error": f"Could not read zoning file: {e}"})
                    return
            self.send_response(200)
            self.send_header("Content-Type", "application/geo+json")
            self.send_header("Content-Length", str(len(_zoning_cache)))
            self._cors()
            self.end_headers()
            self.wfile.write(_zoning_cache)
            return

        if parsed.path != "/parcels":
            self.send_json(404, {"error": "Not found. Use /parcels?bbox=minLon,minLat,maxLon,maxLat"})
            return

        params = parse_qs(parsed.query)
        bbox_str = params.get("bbox", [None])[0]

        if not bbox_str:
            self.send_json(400, {"error": "bbox parameter required (minLon,minLat,maxLon,maxLat)"})
            return

        try:
            parts = bbox_str.split(",")
            if len(parts) != 4:
                raise ValueError("need 4 values")
            minlon, minlat, maxlon, maxlat = map(float, parts)
            ox1, oy1, ox2, oy2 = OHIO_BBOX
            if not (ox1 <= minlon < maxlon <= ox2) or not (oy1 <= minlat < maxlat <= oy2):
                raise ValueError("outside Ohio bounds")
        except ValueError as exc:
            self.send_json(400, {"error": f"Invalid bbox: {exc}"})
            return

        cmd = [
            "ogr2ogr",
            "-f", "GeoJSON",
            "/vsistdout/",
            "-t_srs", "EPSG:4326",
            "-spat", str(minlon), str(minlat), str(maxlon), str(maxlat),
            "-spat_srs", "EPSG:4326",
            "-select", SELECT_FIELDS,
            "-limit", str(MAX_FEATURES),
            SHAPEFILE,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            self.send_json(504, {"error": "Query timed out — try a smaller bounding box"})
            return

        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")
            print(f"ogr2ogr error: {err}", file=sys.stderr)
            self.send_json(500, {"error": f"ogr2ogr failed: {err[:200]}"})
            return

        try:
            geojson = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.send_json(500, {"error": f"Failed to parse GeoJSON: {exc}"})
            return

        geojson["features"] = [enrich_feature(f) for f in geojson.get("features", [])]
        geojson["_count"] = len(geojson["features"])
        geojson["_capped"] = geojson["_count"] >= MAX_FEATURES

        body = json.dumps(geojson).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/geo+json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)


def main():
    if not os.path.exists(SHAPEFILE):
        print(f"ERROR: Shapefile not found at {SHAPEFILE}")
        sys.exit(1)

    try:
        subprocess.run(["ogr2ogr", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: ogr2ogr not found. Install GDAL:  brew install gdal")
        sys.exit(1)

    server = HTTPServer(("localhost", PORT), ParcelHandler)
    print(f"Parcel server  →  http://localhost:{PORT}")
    print(f"Shapefile      →  {SHAPEFILE}")
    print(f"Zoning         →  {ZONING_FILE}")
    print(f"Parcels        →  /parcels?bbox=minLon,minLat,maxLon,maxLat")
    print(f"Zoning layer   →  /zoning")
    print(f"Health check   →  /health")
    print("Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
