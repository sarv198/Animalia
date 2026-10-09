// Where a family lives: its range (GARD 1.7, the union of its species' ranges),
// the representative species' own range, or, when neither exists, where GBIF
// has records of the representative species. Shared by both pages.
import * as d3 from 'd3'
import { useEffect, useMemo, useState } from 'react'
import { feature } from 'topojson-client'
import './shared.css'

const WIDTH = 360
const HEIGHT = 190
const PAD = 8
const MIN_SPAN = [44, 26] // degrees: keep some context around small ranges
const GBIF_TILE = 'https://api.gbif.org/v2/map/occurrence/density/0/{x}/0@1x.png'
// Wild records only: no fossils, no captive animals.
const GBIF_RECORDS = [
  'HUMAN_OBSERVATION', 'PRESERVED_SPECIMEN', 'MACHINE_OBSERVATION', 'MATERIAL_SAMPLE', 'OBSERVATION', 'OCCURRENCE',
]
const GARD_URL = 'https://doi.org/10.5061/dryad.9cnp5hqmb'

let landPromise = null
function loadLand() {
  landPromise ??= import('world-atlas/land-110m.json').then((m) => feature(m.default, m.default.objects.land))
  return landPromise
}

function useLand() {
  const [land, setLand] = useState(null)
  useEffect(() => {
    let cancelled = false
    loadLand().then((data) => {
      if (!cancelled) setLand(data)
    })
    return () => {
      cancelled = true
    }
  }, [])
  return land
}

// d3 treats a counter-clockwise outer ring as "everything outside it".
function d3Winding(geojson) {
  if (d3.geoArea(geojson) <= 2 * Math.PI) return geojson
  const flip = (rings) => rings.map((ring) => [...ring].reverse())
  if (geojson.type === 'Polygon') return { ...geojson, coordinates: flip(geojson.coordinates) }
  if (geojson.type === 'MultiPolygon') return { ...geojson, coordinates: geojson.coordinates.map(flip) }
  return geojson
}

function viewFor(geojson) {
  const world = { type: 'MultiPoint', coordinates: [[-180, -58], [180, 84]] }
  if (!geojson) return world
  const [[w, s], [e, n]] = d3.geoBounds(geojson)
  if (e < w || e - w > 300) return world // crosses the antimeridian or spans the globe
  const cx = (w + e) / 2
  const cy = (s + n) / 2
  const hx = Math.max((e - w) * 0.6, MIN_SPAN[0] / 2)
  const hy = Math.max((n - s) * 0.6, MIN_SPAN[1] / 2)
  return {
    type: 'MultiPoint',
    coordinates: [[Math.max(cx - hx, -180), Math.max(cy - hy, -85)], [Math.min(cx + hx, 180), Math.min(cy + hy, 85)]],
  }
}

function gbifTileUrl(x, taxonKey) {
  const params = new URLSearchParams({ srs: 'EPSG:4326', taxonKey, style: 'classic.poly', bin: 'hex', hexPerTile: 22 })
  GBIF_RECORDS.forEach((basis) => params.append('basisOfRecord', basis))
  return `${GBIF_TILE.replace('{x}', x)}?${params}`
}

export default function RangeMap({ profile, familyName, species }) {
  const land = useLand()
  const options = [
    profile.family_range && { key: 'family', label: `${familyName} family` },
    profile.species_range && { key: 'species', label: species?.common_name || species?.scientific_name || 'Species' },
  ].filter(Boolean)
  const [chosen, setChosen] = useState(null)
  const mode = options.find((o) => o.key === chosen)?.key ?? options[0]?.key ?? (profile.occurrences ? 'gbif' : null)
  const range = mode === 'family' ? profile.family_range : mode === 'species' ? profile.species_range : null
  const shape = useMemo(() => (range ? d3Winding(range.geojson) : null), [range])

  const projection = useMemo(
    () => d3.geoEquirectangular().fitExtent([[PAD, PAD], [WIDTH - PAD, HEIGHT - PAD]], viewFor(shape)),
    [shape],
  )
  if (!mode) return null
  const path = d3.geoPath(projection)
  const graticule = d3.geoGraticule10()
  const common = species?.common_name
  const sci = species?.scientific_name

  let caption
  if (mode === 'family') {
    const { species_mapped: mapped, species_total: total } = range
    caption = total
      ? `Combined range of ${mapped} of the ${total} species of ${familyName}.${mapped < total ? ' Species without a mapped range (including any marine species) are not shown.' : ''}`
      : `Combined range of ${mapped} species of ${familyName}.`
  } else if (mode === 'species') {
    caption = `Range of the ${common || sci}${common ? ` (${sci})` : ''}, the species representing ${familyName} here.`
  } else {
    caption = `No range map covers this family, so this shows where GBIF has records of the ${common || sci}${common ? ` (${sci})` : ''}. Records can include errors, strays and introduced animals; fossil and captive records are left out.`
  }
  const label = mode === 'gbif' ? `Map of GBIF records of ${sci}` : `Range map: ${caption}`

  return (
    <section className="card-section range-section">
      <h3>Where it lives</h3>
      {options.length > 1 && (
        <div className="range-toggle" role="group" aria-label="Map shows">
          {options.map((o) => (
            <button key={o.key} type="button" aria-pressed={mode === o.key} onClick={() => setChosen(o.key)}>
              {o.label}
            </button>
          ))}
        </div>
      )}
      <svg className="range-map" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label}>
        <rect className="range-sea" width={WIDTH} height={HEIGHT} />
        <path className="range-graticule" d={path(graticule)} />
        {land && <path className="range-land" d={path(land)} />}
        {mode === 'gbif'
          ? [0, 1].map((x) => {
            const [x0, y0] = projection([x === 0 ? -180 : 0, 90])
            const [x1, y1] = projection([x === 0 ? 0 : 180, -90])
            return (
              <image
                key={x}
                className="range-records"
                href={gbifTileUrl(x, profile.occurrences.gbif_taxon_key)}
                x={x0}
                y={y0}
                width={x1 - x0}
                height={y1 - y0}
                preserveAspectRatio="none"
              />
            )
          })
          : <path className="range-area" d={path(shape)} />}
      </svg>
      <p className="range-caption">{caption}</p>
      <p className="card-source">
        {mode === 'gbif' ? (
          <>
            Occurrence records:{' '}
            <a href={`https://www.gbif.org/species/${profile.occurrences.gbif_taxon_key}`} target="_blank" rel="noreferrer">
              GBIF.org
            </a>
          </>
        ) : (
          <>
            Ranges:{' '}
            <a href={GARD_URL} target="_blank" rel="noreferrer">GARD 1.7</a> (Roll &amp; Meiri 2022, CC0), simplified for display.
          </>
        )}
      </p>
    </section>
  )
}
