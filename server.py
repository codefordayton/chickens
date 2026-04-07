#!/usr/bin/env python3
"""
Multi-county parcel and zoning server.

Montgomery County: reads from local shapefiles via ogr2ogr.
Clark County:      proxies the Clark County Ohio ArcGIS REST services (no local files needed).

Requirements (Montgomery County only): GDAL command-line tools on PATH.
  macOS:  brew install gdal
  Ubuntu: apt install gdal-bin

Usage:
  python3 server.py          # default port 8001
  python3 server.py 9000     # custom port

Endpoints:
  GET /parcels?bbox=minLon,minLat,maxLon,maxLat[&county=montgomery|clark]
  GET /zoning[?county=montgomery|clark]
  GET /health
"""

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
HERE = os.path.dirname(os.path.abspath(__file__))

# ── Montgomery County (local shapefiles) ──────────────────────────────────────
MC_SHAPEFILE   = os.path.join(HERE, "parcels.shp")
MC_ZONING_FILE = os.path.join(HERE, "zoning.geojson")
MC_MAX_FEATURES = 3000
MC_SELECT_FIELDS = ",".join([
    "TAXPINNO", "LOC_NBR", "LOC_DIR", "LOC_STREET", "LOC_SUFFIX",
    "LOC_ZIP", "ACREAGE", "PARCEL_USE", "PARCEL_U_1", "SHAPE_STAr",
])

# ── Clark County (ArcGIS REST — no local files needed) ───────────────────────
CC_PARCEL_SERVICE = "https://ago.clarkcountyohio.gov/ccoarcgis/rest/services/WMAS/Parcels_GCS/MapServer/1"
CC_ZONING_SERVICE = "https://ago.clarkcountyohio.gov/ccoarcgis/rest/services/WMAS/City_Zoning/MapServer/0"
CC_MAX_FEATURES   = 2000

# Ohio rough bounding box for basic input validation
OHIO_BBOX = (-85.0, 38.2, -80.5, 42.4)

# ── In-memory caches ──────────────────────────────────────────────────────────
_mc_zoning_cache = None   # raw bytes from zoning.geojson
_cc_zoning_cache = None   # normalized bytes fetched from ArcGIS


# ── Montgomery County helpers ─────────────────────────────────────────────────

def mc_build_address(props):
    """Construct a readable address from Montgomery County component fields."""
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
        addr += f", OH {zipcd}"
    return addr.title().replace(" Oh ", " OH ")


def mc_compute_acres(props):
    """Derive acreage from Montgomery County fields.
    Prefers ACREAGE; falls back to SHAPE_STAr (sq ft in Ohio State Plane)."""
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


def mc_enrich_feature(feature):
    """Normalize a Montgomery County ogr2ogr GeoJSON feature."""
    props = feature.get("properties") or {}
    address = mc_build_address(props)
    acres   = mc_compute_acres(props)
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


# ── Clark County helpers ──────────────────────────────────────────────────────

def cc_enrich_parcel(feature):
    """Normalize a Clark County ArcGIS parcel feature."""
    props = feature.get("properties") or {}

    acres = None
    try:
        v = float(props.get("ACRES") or 0)
        if 0 < v < 10000:
            acres = round(v, 3)
    except (ValueError, TypeError):
        pass

    address = (props.get("ADDRESSUNI") or "").strip() or None
    if address:
        address = address.title().replace(" Oh ", " OH ")

    feature["properties"] = {
        "TAXPINNO":   props.get("PIN"),
        "ADDRESS":    address,
        "ZIP":        props.get("ZipCodeFirst5") or None,
        "ACRES":      acres,
        "SQFT":       round(acres * 43560) if acres else None,
        "PARCEL_USE": None,
        "USE_DESC":   None,
    }
    return feature


def cc_enrich_zoning(feature):
    """Normalize a Clark County ArcGIS zoning feature to match the
    ZONE_CODE / ZONE_DESC / ZONE_JAREA schema the client expects."""
    props = feature.get("properties") or {}
    zone_raw = (props.get("Zone") or "").strip()
    # Strip the "CITY " prefix Clark County uses: "CITY RS-5" → "RS-5"
    zone_code = zone_raw[5:] if zone_raw.startswith("CITY ") else zone_raw
    feature["properties"] = {
        "ZONE_CODE":  zone_code,
        "ZONE_DESC":  (props.get("Zonedesc") or "").strip(),
        "ZONE_JAREA": "SPRINGFIELD",
    }
    return feature


def fetch_arcgis(url, timeout=20):
    """Fetch JSON from an ArcGIS REST endpoint using only stdlib."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "cfd-zoning-chickens/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── HTTP handler ──────────────────────────────────────────────────────────────

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

    def send_geojson(self, data: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "application/geo+json")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        county = params.get("county", ["montgomery"])[0].lower()

        if parsed.path == "/health":
            self.send_json(200, {
                "status": "ok",
                "montgomery": {
                    "shapefile": MC_SHAPEFILE,
                    "shapefile_exists": os.path.exists(MC_SHAPEFILE),
                    "zoning": MC_ZONING_FILE,
                    "zoning_exists": os.path.exists(MC_ZONING_FILE),
                },
                "clark": {
                    "parcel_service": CC_PARCEL_SERVICE,
                    "zoning_service": CC_ZONING_SERVICE,
                },
            })
            return

        if parsed.path == "/zoning":
            if county == "clark":
                self._clark_zoning()
            else:
                self._montgomery_zoning()
            return

        if parsed.path != "/parcels":
            self.send_json(404, {"error": "Not found. Use /parcels?bbox=minLon,minLat,maxLon,maxLat[&county=montgomery|clark]"})
            return

        # ── Validate bbox ──────────────────────────────────────────────────────
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

        if county == "clark":
            self._clark_parcels(minlon, minlat, maxlon, maxlat)
        else:
            self._montgomery_parcels(minlon, minlat, maxlon, maxlat)

    # ── Montgomery County ──────────────────────────────────────────────────────

    def _montgomery_zoning(self):
        global _mc_zoning_cache
        if _mc_zoning_cache is None:
            try:
                with open(MC_ZONING_FILE, "rb") as f:
                    _mc_zoning_cache = f.read()
            except OSError as e:
                self.send_json(500, {"error": f"Could not read zoning file: {e}"})
                return
        self.send_geojson(_mc_zoning_cache)

    def _montgomery_parcels(self, minlon, minlat, maxlon, maxlat):
        cmd = [
            "ogr2ogr",
            "-f", "GeoJSON",
            "/vsistdout/",
            "-t_srs", "EPSG:4326",
            "-spat", str(minlon), str(minlat), str(maxlon), str(maxlat),
            "-spat_srs", "EPSG:4326",
            "-select", MC_SELECT_FIELDS,
            "-limit", str(MC_MAX_FEATURES),
            MC_SHAPEFILE,
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

        geojson["features"] = [mc_enrich_feature(f) for f in geojson.get("features", [])]
        geojson["_count"]   = len(geojson["features"])
        geojson["_capped"]  = geojson["_count"] >= MC_MAX_FEATURES
        self.send_geojson(json.dumps(geojson).encode())

    # ── Clark County ───────────────────────────────────────────────────────────

    def _clark_zoning(self):
        global _cc_zoning_cache
        if _cc_zoning_cache is None:
            url = (
                f"{CC_ZONING_SERVICE}/query"
                "?where=1%3D1"
                "&outFields=Zone%2CZonedesc"
                "&f=geojson"
                "&outSR=4326"
                "&resultRecordCount=5000"
            )
            try:
                data = fetch_arcgis(url)
                data["features"] = [cc_enrich_zoning(f) for f in data.get("features", [])]
                _cc_zoning_cache = json.dumps(data).encode()
            except Exception as e:
                self.send_json(502, {"error": f"Clark County zoning service unavailable: {e}"})
                return
        self.send_geojson(_cc_zoning_cache)

    def _clark_parcels(self, minlon, minlat, maxlon, maxlat):
        geometry = json.dumps({
            "xmin": minlon, "ymin": minlat,
            "xmax": maxlon, "ymax": maxlat,
            "spatialReference": {"wkid": 4326},
        })
        qs = urllib.parse.urlencode({
            "geometry":          geometry,
            "geometryType":      "esriGeometryEnvelope",
            "inSR":              "4326",
            "spatialRel":        "esriSpatialRelIntersects",
            "outFields":         "PIN,ACRES,ADDRESSUNI,CityName,ZipCodeFirst5",
            "f":                 "geojson",
            "outSR":             "4326",
            "resultRecordCount": CC_MAX_FEATURES,
        })
        url = f"{CC_PARCEL_SERVICE}/query?{qs}"

        try:
            data = fetch_arcgis(url)
        except Exception as e:
            self.send_json(502, {"error": f"Clark County parcel service unavailable: {e}"})
            return

        data["features"] = [cc_enrich_parcel(f) for f in data.get("features", [])]
        data["_count"]   = len(data["features"])
        data["_capped"]  = data["_count"] >= CC_MAX_FEATURES
        self.send_geojson(json.dumps(data).encode())


# ── Startup ───────────────────────────────────────────────────────────────────

def main():
    mc_ok = os.path.exists(MC_SHAPEFILE)
    if not mc_ok:
        print(f"WARNING: Montgomery County shapefile not found at {MC_SHAPEFILE}")
        print("         Montgomery County parcels will be unavailable.")

    gdal_ok = True
    try:
        subprocess.run(["ogr2ogr", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        gdal_ok = False
        print("WARNING: ogr2ogr not found — Montgomery County parcels unavailable.")
        print("         Install GDAL:  brew install gdal")

    if not mc_ok and not gdal_ok:
        print("         Clark County (Springfield) will still work via ArcGIS REST.")

    server = HTTPServer(("localhost", PORT), ParcelHandler)
    print(f"\nServer         →  http://localhost:{PORT}")
    print(f"Montgomery Co  →  /parcels?bbox=...&county=montgomery  (ogr2ogr + {MC_SHAPEFILE})")
    print(f"Clark Co       →  /parcels?bbox=...&county=clark       (ArcGIS REST, live)")
    print(f"Zoning         →  /zoning?county=[montgomery|clark]")
    print(f"Health         →  /health")
    print("Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
