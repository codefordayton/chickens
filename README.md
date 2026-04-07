# Can I Have Chickens Here? 🐔🐇

A civic tech demo for **Code for Dayton** that lets you click any parcel in Dayton,
see its zoning district, and ask an AI whether you can keep backyard chickens or
rabbits there.

*"It's the week after Easter. I have chickens and bunnies. Can I keep them?"*

---

## What it does

- Displays all 272,000+ Montgomery County parcels colored by Dayton zoning district
- Click any parcel → see address, zone code, lot size
- Click **"Ask about chickens & bunnies 🐔🐇"** → Claude answers in plain English

## Quick start

**Requirements:** Python 3, [GDAL](https://gdal.org/) (`brew install gdal` on Mac)

```bash
# Clone / download this folder, then:

# Terminal 1 — parcel data server
python3 server.py

# Terminal 2 — static file server
python3 -m http.server 8000
```

Open **http://localhost:8000**, paste a Claude API key in the top-right field, and
click any parcel on the map.

*Get a free Claude API key at [console.anthropic.com](https://console.anthropic.com)*

---

## How it works

```
parcels.shp          zoning.geojson
(272K parcels,  +    (749 Dayton zone
county auditor)       polygons, pre-built)
      │                     │
      └─────── server.py ───┘
                   │
              index.html
            (Leaflet map +
             Claude API call)
```

**`server.py`** is a plain Python stdlib server that uses `ogr2ogr` to query the
shapefile by bounding box, so only parcels in your current map view are loaded.

**`index.html`** is the entire frontend — no framework, no build step.

**`ordinance.js`** contains the relevant Dayton zoning ordinance text that gets
included in every Claude prompt.

---

## Data sources

| Dataset | Source | Date |
|---------|--------|------|
| Parcel polygons (`parcels.shp`) | [Montgomery County GIS Downloads](https://www.mcohio.org/631/GIS-Downloads) | 2026-04-02 |
| Zoning districts (`SHAPEFILE_ZONING/`) | [Montgomery County GIS Downloads](https://www.mcohio.org/631/GIS-Downloads) | 2022-02-01 — all jurisdictions |
| Ordinance text | Municode (secondary sources) | ~2024 |
| Base map | OpenStreetMap | live |

**The shapefiles are not included in this repo** — download them from
[Montgomery County GIS Downloads](https://www.mcohio.org/631/GIS-Downloads)
and place `parcels.shp` (+ sidecar files) and the zoning shapefile folder
(`SHAPEFILE_ZONING/`) in the project root.

**Note:** The parcel shapefile is the county auditor's file — it tracks ownership
and tax data, not zoning. Zoning comes from the separate planning department
shapefile in `SHAPEFILE_ZONING/`.

After downloading both shapefiles, rebuild `zoning.geojson` to include all Montgomery County jurisdictions:

```bash
ogr2ogr -f GeoJSON zoning.geojson \
  -t_srs EPSG:4326 \
  -select 'ZONE_CODE,ZONE_DESC,ZONE_JAREA' \
  SHAPEFILE_ZONING/Zoning.shp
```

---

## Dayton zone codes

Dayton uses its own zone system (not the traditional R-1/R-2 you may know):

| Code | Name | Chickens |
|------|------|---------|
| SR-1 | Suburban Residential 1 | ✓ Permitted (with permit) |
| SR-2 | Suburban Residential 2 | ✓ Permitted (with permit) |
| MR-5 | Mature Residential 5 | ✓ Permitted (with permit) |
| ER-3 | Eclectic Residential 3 | ⚠ Conditional |
| ER-4 | Eclectic Residential 4 | ⚠ Conditional |
| CBD, SGC, I-1, I-2… | Commercial / Industrial | ✗ Not permitted |

Key rules: max **4 hens**, **no roosters**, **permit required**, coop must be
25 ft from a neighbor's door or window.

*Always verify with the City of Dayton Zoning Division: (937) 333-3910*

---

## Hackathon stretch goals

Good tasks for meetup participants to pick up:

- **Address search** — add a search box using the free [Nominatim](https://nominatim.org/) geocoder
- **More animals** — expand the prompt to cover goats, ducks, bees
- **Springfield, OH** — Ivan's idea; add their parcel data and ordinance
- **Compare zones** — table showing rules across all residential districts side-by-side
- **Shareable URL** — encode selected parcel in the URL hash
- **Other cities** — the zoning shapefile covers all of Montgomery County;
  Kettering, Huber Heights, Centerville, etc. each have their own zone codes

---

## Disclaimer

The ordinance text in `ordinance.js` is an educational summary for demonstration
purposes. It may not reflect the most current rules. Always verify with the
City of Dayton before making decisions.

Official source: https://library.municode.com/oh/dayton/codes/code_of_ordinances
