# CLAUDE.md — Can I Have Chickens Here?

Civic tech demo for Code for Dayton. Lets a user click any parcel in Dayton,
see its zoning district, and ask Claude whether they can keep backyard chickens
or rabbits there.

## How to run

```bash
# Terminal 1 — local parcel + zoning API (requires GDAL)
python3 server.py

# Terminal 2 — static file server (required for ES module imports)
python3 -m http.server 8000

# Open http://localhost:8000
```

The page asks for a Claude API key. It's stored in `localStorage` and never
hardcoded. The server must be running for parcels to load; zoning still shows
without it (served from `zoning.geojson`).

## File map

| File | Purpose |
|------|---------|
| `index.html` | Entire frontend — map, panel, AI call. No build step. |
| `ordinance.js` | ES module export of Dayton zoning ordinance text used in the Claude prompt. |
| `server.py` | Python stdlib HTTP server. Wraps `ogr2ogr` to serve parcel GeoJSON by bounding box. No pip installs needed — only requires GDAL on PATH. |
| `zoning.geojson` | Pre-built Dayton zoning polygons (WGS84). Generated once from `SHAPEFILE_ZONING/Zoning.shp`. Served by `server.py` at `/zoning`. |
| `parcels.shp` (+ sidecar) | Montgomery County Auditor parcel shapefile. 272,973 features, EPSG:3735 (Ohio State Plane South, US survey feet). |
| `SHAPEFILE_ZONING/Zoning.shp` | Montgomery County zoning shapefile. 3,627 features, same CRS. City of Dayton subset exported to `zoning.geojson`. |
| `sample_parcels.csv` | 50 sample parcels from central Dayton for reference/testing. |

## Architecture

```
Browser                        server.py (port 8001)
  │                                │
  ├─ GET /zoning ─────────────────▶│ reads zoning.geojson (memory-cached)
  │◀─ 749 Dayton zone polygons ────┤
  │                                │
  ├─ GET /parcels?bbox=... ───────▶│ runs ogr2ogr subprocess
  │◀─ GeoJSON (≤3000 parcels) ─────┤  with -spat -spat_srs EPSG:4326
  │                                │  constructs ADDRESS from components
  │                                │  computes ACRES from SHAPE_STAr
  │
  ├─ POST api.anthropic.com/v1/messages
  │  (direct browser call with anthropic-dangerous-direct-browser-calls header)
```

**Layer order on map:**
1. OSM base tiles
2. Zoning polygons (`zoningLayer`) — colored by zone code, tooltip on hover
3. Parcel outlines (`parcelLayer`) — transparent fill, thin stroke; only loaded at zoom ≥ 15
4. Selected parcel — highlighted with blue stroke

**Zone lookup:** On parcel click, uses the parcel's bounding-box center for a
point-in-polygon check against the 749 in-memory zoning features (ray-casting).
This is why `selectedLayer` must be nulled out BEFORE `clearLayers()` — otherwise
Leaflet's `bringToFront()` can re-append a detached SVG element to the canvas.

## Data quirks

### Parcel shapefile (`parcels.shp`)
- CRS: EPSG:3735 — NAD83 / Ohio State Plane South, US survey feet
- **No zoning field.** This is the county auditor's file (tax/ownership), not the planning dept.
- Address is split across `LOC_NBR`, `LOC_DIR`, `LOC_STREET`, `LOC_SUFFIX`. `LOC_FADDRE` is mostly null.
- `LOC_CITY` and `PARCEL_USE` are sparse. `LOC_ZIP` is reliable.
- `SHAPE_STAr` = lot area in Ohio State Plane sq ft. Divide by 43,560 for acres.
- `ACREAGE` field exists but is often null; `SHAPE_STAr` is the reliable source.
- Spatial index (`.sbn`/`.sbx`) is present — `ogr2ogr -spat` queries are fast.

### Zoning shapefile (`SHAPEFILE_ZONING/Zoning.shp`)
- CRS: EPSG:3735 — same as parcels (no re-projection needed for spatial join)
- 3,627 features covering all of Montgomery County
- Key fields: `ZONE_CODE`, `ZONE_DESC`, `ZONE_JAREA` (jurisdiction), `ZONE_COLOR`
- Filter `ZONE_JAREA='DAYTON'` → 749 features, 26 distinct zone codes
- Dayton uses its own system: SR-1, SR-2, MR-5, ER-3, ER-4, MH, SMF, MMF, EMF,
  SNC, MNC, ENC, SGC, MGC, EGC, CBD, UBD, BP, MX, CI, OS, I-1, I-2, AIRPORT, WO, T
- **Not** the traditional R-1/R-2/B-1 system; those appear in other county jurisdictions.

### Regenerating zoning.geojson
```bash
ogr2ogr -f GeoJSON zoning.geojson \
  -where "ZONE_JAREA='DAYTON'" \
  -t_srs EPSG:4326 \
  -select 'ZONE_CODE,ZONE_DESC,ZONE_JAREA' \
  SHAPEFILE_ZONING/Zoning.shp
```

## Ordinance text
`ordinance.js` is an educational summary from secondary sources (Municode + community
sites). It reflects rules as of early 2024. Key rules embedded:
- Max 4 hens, no roosters, permit required
- Coop must be 25 ft from neighbor's door/window
- SR-1/SR-2 permitted; ER-3 conditional; ER-4+ not permitted
- Domestic rabbits: up to 4 outdoors without special permit

Verify against current Municode before any production use:
https://library.municode.com/oh/dayton/codes/code_of_ordinances

## Extending at a hackathon

Good first tasks for participants:
- Add address search (Nominatim/OSM geocoder — free, no key)
- Expand beyond chickens: add goats, ducks, bees to the prompt
- Add Springfield, OH parcel + ordinance data
- Add a "compare zones" table across all residential districts
- Encode selected parcel in URL for shareable links
- Add the county's other municipalities (Kettering, Huber Heights, etc.)
  — their zone codes differ; see `ZONE_JAREA` values in the zoning shapefile

## Known limitations
- Ordinance text is from secondary sources, not verified line-by-line against current Municode
- `parcels.shp` is the 2026-04-02 snapshot; `Zoning.shp` is 2022-02-01
- Parcel address construction (`LOC_NBR + LOC_DIR + LOC_STREET + LOC_SUFFIX`) can
  produce odd results for parcels with non-standard addressing (e.g., "-1" street numbers
  on right-of-way parcels)
- Zone lookup uses bounding-box center, not true centroid — fails for L-shaped parcels
  that straddle a zone boundary
