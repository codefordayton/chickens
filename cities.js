/**
 * Per-city configuration for the Montgomery County zoning explorer.
 *
 * Each city entry drives:
 *   - Map center and default zoom
 *   - Which ZONE_JAREA value to filter from zoning.geojson
 *   - Zone code → display color and full name
 *   - Which zone codes allow/conditionally allow chickens & rabbits
 *   - Rule text shown in the info panel
 *   - Official source links
 *
 * To add a new city:
 *   1. Find its ZONE_JAREA value in the shapefile:
 *        ogr2ogr -f CSV /vsistdout/ -select 'ZONE_JAREA' SHAPEFILE_ZONING/Zoning.shp | sort -u
 *   2. Find its zone codes:
 *        ogr2ogr -f CSV /vsistdout/ -where "ZONE_JAREA='YOURVALUE'" \
 *          -select 'ZONE_CODE,ZONE_DESC' SHAPEFILE_ZONING/Zoning.shp | sort -u
 *   3. Copy a stub entry below and fill in the fields.
 *   4. Rebuild zoning.geojson to include the new city (see README).
 */

// ─────────────────────────────────────────────────────────────────────────────
// GENERIC ZONE COLOR FALLBACK
// Used for cities that don't have an explicit zoneColors map.
// Pattern-matches common Ohio zone code prefixes.
// ─────────────────────────────────────────────────────────────────────────────
export function genericZoneColor(code) {
  const c = (code || '').toUpperCase().replace(/[\s-]/g, '');
  if (/^(R\d|SR|MR|ER|RS|RL|RM|RH|RE|RA|SF|RSF|RA|RE|SFR)/.test(c)) return '#c8e6c9'; // residential
  if (/^(MF|RMF|HMF|APT|SMF|MMF|EMF)/.test(c))                       return '#fff9c4'; // multi-family
  if (/^(B\d|C\d|NC|GC|SC|CBD|UBD|MX|BN|BR|COM|OFFICE)/.test(c))    return '#ffe0b2'; // commercial
  if (/^(BP|BPARK|BUSPARK)/.test(c))                                   return '#ce93d8'; // business park
  if (/^(I\d|IND|LI|HI|MFG)/.test(c))                                 return '#ffcdd2'; // industrial
  if (/^(OS|PARK|GRN|AG|AGRI|CONS|OPEN)/.test(c))                     return '#b9f6ca'; // open space
  if (/^(CI|INST|PF|PUB)/.test(c))                                     return '#b3e5fc'; // civic/institutional
  if (/^(MH|MHOME)/.test(c))                                           return '#ffe082'; // manufactured home
  return '#e0e0e0';
}

// ─────────────────────────────────────────────────────────────────────────────
// CITY CONFIGS
// ─────────────────────────────────────────────────────────────────────────────
export const CITIES = [

  // ── DAYTON ─────────────────────────────────────────────────────────────────
  {
    id: 'dayton',
    name: 'Dayton',
    zoningFilter: 'DAYTON',   // matches ZONE_JAREA in shapefile
    center: [39.7589, -84.1916],
    zoom: 13,

    ordinanceKnown: true,

    zoneColors: {
      // Residential
      'SR-1': '#c8e6c9',  'SR-2': '#a5d6a7',  'MR-5': '#81c784',
      'ER-3': '#dcedc8',  'ER-4': '#f0f4c3',  'MH':   '#ffe082',
      // Multi-family
      'SMF':  '#fff9c4',  'MMF':  '#fff176',  'EMF':  '#ffee58',
      // Commercial
      'SNC':  '#ffe0b2',  'MNC':  '#ffcc80',  'ENC':  '#ffb74d',
      'SGC':  '#ff8a65',  'MGC':  '#ff7043',  'EGC':  '#f4511e',
      'CBD':  '#ef9a9a',  'UBD':  '#e57373',
      'BP':   '#ce93d8',  'MX':   '#ba68c8',
      // Civic / open space
      'CI':   '#b3e5fc',  'OS':   '#b9f6ca',
      'AIRPORT': '#cfd8dc', 'WO': '#d7ccc8',
      // Industrial
      'I-1':  '#ffcdd2',  'I-2':  '#ef9a9a',
      // Transitional
      'T':    '#e0e0e0',
    },

    zoneNames: {
      'SR-1': 'Suburban Residential 1',     'SR-2': 'Suburban Residential 2',
      'MR-5': 'Mature Residential 5',       'ER-3': 'Eclectic Residential 3',
      'ER-4': 'Eclectic Residential 4',     'MH':   'Manufactured Home District',
      'SMF':  'Suburban Multi-Family',      'MMF':  'Mature Multi-Family',
      'EMF':  'Eclectic Multi-Family',      'SNC':  'Suburban Neighborhood Commercial',
      'MNC':  'Mature Neighborhood Commercial', 'ENC': 'Eclectic Neighborhood Commercial',
      'SGC':  'Suburban General Commercial','MGC':  'Mature General Commercial',
      'EGC':  'Eclectic General Commercial','CBD':  'Central Business District',
      'UBD':  'Urban Business District',    'BP':   'Business Park',
      'MX':   'Mixed Use Hub District',     'CI':   'Campus-Institutional',
      'OS':   'Open Space',                 'AIRPORT': 'Airport',
      'WO':   'Well Head Operation',        'I-1':  'Light Industrial',
      'I-2':  'General Industrial',         'T':    'Transitional',
    },

    // Zones where chickens are outright permitted (with permit)
    chickenPermitted: ['SR-1', 'SR-2', 'MR-5'],
    // Zones where chickens require ZBA conditional use approval
    chickenConditional: ['ER-3', 'ER-4', 'MH', 'SMF', 'MMF', 'EMF'],
    // Everything else is not permitted

    chickenRules: [
      'Maximum <strong>4 hens</strong> — no roosters ever',
      '<strong>Permit required</strong> from the Zoning Division before acquiring birds',
      'Coop must be <strong>25 ft</strong> from any neighbor\'s door or window',
      'Min. 4 sq ft/bird inside coop; 10 sq ft/bird in outdoor run',
      'Fowl must be kept in an enclosed run — no free-roaming',
      'Personal use only; commercial egg sales prohibited',
    ],

    rabbitRules: [
      'Up to <strong>4 rabbits outdoors</strong> without a special permit',
      'Outdoor hutch must be <strong>5 ft</strong> from property lines',
      '<strong>Indoor rabbits:</strong> no numerical limit, no permit needed',
      'Commercial breeding requires a special use permit',
    ],

    sources: {
      name: 'City of Dayton Zoning Division',
      municode: 'https://library.municode.com/oh/dayton/codes/code_of_ordinances',
      municodeLabel: 'Ch. 91 (Animals) · Ch. 150 (Zoning)',
      zoning: 'https://www.daytonohio.gov/229/Zoning-Code-Map',
      phone: '(937) 333-3910',
    },
  },

  // ── KETTERING ──────────────────────────────────────────────────────────────
  // ZONE_JAREA value needs verification against the shapefile.
  // Zone codes need to be catalogued before filling in chickenPermitted etc.
  {
    id: 'kettering',
    name: 'Kettering',
    zoningFilter: 'KETTERING',  // verify with: ogrinfo on Zoning.shp
    center: [39.6895, -84.1688],
    zoom: 13,
    ordinanceKnown: false,
    sources: {
      name: 'Kettering Community Development',
      municode: null,   // fill in once verified
      municodeLabel: null,
      zoning: null,
      phone: null,
    },
  },

  // ── HUBER HEIGHTS ──────────────────────────────────────────────────────────
  {
    id: 'huber-heights',
    name: 'Huber Heights',
    zoningFilter: 'HUBER HEIGHTS',
    center: [39.8437, -84.1241],
    zoom: 13,
    ordinanceKnown: false,
    sources: {
      name: 'Huber Heights Planning & Zoning',
      municode: null,
      municodeLabel: null,
      zoning: null,
      phone: null,
    },
  },

  // ── CENTERVILLE ────────────────────────────────────────────────────────────
  {
    id: 'centerville',
    name: 'Centerville',
    zoningFilter: 'CENTERVILLE',
    center: [39.6345, -84.1535],
    zoom: 13,
    ordinanceKnown: false,
    sources: {
      name: 'Centerville Planning & Zoning',
      municode: null,
      municodeLabel: null,
      zoning: null,
      phone: null,
    },
  },

  // ── MIAMISBURG ─────────────────────────────────────────────────────────────
  {
    id: 'miamisburg',
    name: 'Miamisburg',
    zoningFilter: 'MIAMISBURG',
    center: [39.6426, -84.2894],
    zoom: 13,
    ordinanceKnown: false,
    sources: {
      name: 'Miamisburg Planning & Zoning',
      municode: null,
      municodeLabel: null,
      zoning: null,
      phone: null,
    },
  },

  // ── VANDALIA ───────────────────────────────────────────────────────────────
  {
    id: 'vandalia',
    name: 'Vandalia',
    zoningFilter: 'VANDALIA',
    center: [39.8912, -84.1994],
    zoom: 13,
    ordinanceKnown: false,
    sources: {
      name: 'Vandalia Planning & Zoning',
      municode: null,
      municodeLabel: null,
      zoning: null,
      phone: null,
    },
  },

  // ── TROTWOOD ───────────────────────────────────────────────────────────────
  {
    id: 'trotwood',
    name: 'Trotwood',
    zoningFilter: 'TROTWOOD',
    center: [39.7915, -84.3077],
    zoom: 13,
    ordinanceKnown: false,
    sources: {
      name: 'Trotwood Planning & Zoning',
      municode: null,
      municodeLabel: null,
      zoning: null,
      phone: null,
    },
  },

];

export const CITIES_BY_ID = Object.fromEntries(CITIES.map(c => [c.id, c]));
