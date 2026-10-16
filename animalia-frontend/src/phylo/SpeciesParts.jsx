// Species sections shared by the 2D card and the 3D page.
import { useState } from 'react'
import { IUCN_COLORS, IUCN_LABELS, IUCN_ORDER, STATUS } from '../phylogenyStyle.js'
import { speciesCountLine } from './narrative.js'
import { photoSrcSet, photoUrl } from './photos.js'
import { OPENTREE_STANDING, isReptileDatabaseFamily } from './reptileDatabase.js'
import './shared.css'

export function SpeciesPhotos({ species }) {
  const [index, setIndex] = useState(0)
  const [failed, setFailed] = useState(() => new Set())
  // A photo whose host does not deliver it is dropped; the next one shows.
  const images = (species.images || []).filter((img) => !failed.has(img.url))
  const image = images[Math.min(index, images.length - 1)]
  const drop = (url) => setFailed((current) => new Set(current).add(url))
  if (!image) return <p className="card-muted card-nophoto">No openly licensed photo found.</p>
  return (
    <figure className="card-photo">
      <a href={image.page_url || image.url} target="_blank" rel="noreferrer">
        <img
          key={image.url}
          src={photoUrl(image, 'medium')}
          srcSet={photoSrcSet(image)}
          sizes="(max-width: 960px) 100vw, 440px"
          fetchPriority="high"
          decoding="async"
          alt={`${species.scientific_name}${species.common_name ? ` (${species.common_name})` : ''}`}
          referrerPolicy="no-referrer"
          onError={() => drop(image.url)}
        />
      </a>
      <figcaption>
        Photo: {image.creator || 'unknown'} ·{' '}
        {image.licence_url ? (
          <a href={image.licence_url} target="_blank" rel="noreferrer">{image.licence}</a>
        ) : (
          image.licence
        )}{' '}
        · via{' '}
        {image.page_url ? (
          <a href={image.page_url} target="_blank" rel="noreferrer">{image.source}</a>
        ) : (
          image.source
        )}
      </figcaption>
      {images.length > 1 && (
        <div className="thumbs" role="list">
          {images.map((img, i) => (
            <button
              key={img.url}
              type="button"
              role="listitem"
              className={img === image ? 'thumb active' : 'thumb'}
              onClick={() => setIndex(i)}
              aria-label={`Photo ${i + 1} of ${images.length}`}
            >
              <img
                src={photoUrl(img, 'small')}
                alt=""
                loading="lazy"
                decoding="async"
                referrerPolicy="no-referrer"
                onError={() => drop(img.url)}
              />
            </button>
          ))}
        </div>
      )}
    </figure>
  )
}

// Shown only when the species has a listed category.
export function Conservation({ species }) {
  if (!species.iucn_category) return null
  return (
    <section className="card-section">
      <h3>Conservation status</h3>
      <p>
        <IucnPill category={species.iucn_category} /> {IUCN_LABELS[species.iucn_category]}
      </p>
      <IucnScale category={species.iucn_category} />
      <p className="card-source">
        IUCN Red List category as listed on{' '}
        {species.wikipedia_url ? (
          <a href={species.wikipedia_url} target="_blank" rel="noreferrer">Wikipedia</a>
        ) : (
          'Wikipedia'
        )}
        {species.iucn_assessment_year ? ` (assessment ${species.iucn_assessment_year})` : ''}.
      </p>
    </section>
  )
}

export function SpeciesLinks({ species }) {
  const links = [
    species.wikipedia_url && { label: 'Wikipedia', href: species.wikipedia_url },
    species.gbif_taxon_id && { label: 'GBIF', href: `https://www.gbif.org/species/${species.gbif_taxon_id}` },
    species.ott_id && { label: 'Open Tree of Life', href: `https://tree.opentreeoflife.org/opentree/argus/ottol@${species.ott_id}` },
    species.col_taxon_id && { label: 'Catalogue of Life', href: `https://www.catalogueoflife.org/data/taxon/${species.col_taxon_id}` },
  ].filter(Boolean)
  return (
    <section className="card-section">
      <h3>More about this species</h3>
      <ul className="card-links">
        {links.map((link) => (
          <li key={link.label}>
            <a href={link.href} target="_blank" rel="noreferrer">{link.label}</a>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function Placement({ data }) {
  const flag = STATUS[data.placement_status]
  return (
    <section className="card-section">
      <h3>Placement in the tree</h3>
      <p>
        {flag ? (
          <span className="status-pill" style={{ color: flag.color, borderColor: flag.color }}>
            {flag.symbol} {flag.label}
          </span>
        ) : (
          <span className="status-pill confirmed">✓ Confirmed</span>
        )}
      </p>
      {data.note && <p className="card-note">{data.note}</p>}
      <ReptileDatabaseNote data={data} />
    </section>
  )
}

export function IucnPill({ category }) {
  const color = IUCN_COLORS[category]
  return (
    <span
      className={`iucn-pill iucn-${category}`}
      style={color ? { background: color.fill, color: color.ink, borderColor: color.fill } : undefined}
    >
      {category}
    </span>
  )
}

// Where the category sits between Least Concern and Extinct.
function IucnScale({ category }) {
  if (!IUCN_ORDER.includes(category)) return null
  return (
    <ol className="iucn-scale" aria-hidden="true">
      {IUCN_ORDER.map((code) => (
        <li
          key={code}
          className={code === category ? 'current' : undefined}
          style={{ '--iucn': IUCN_COLORS[code].fill, '--iucn-ink': IUCN_COLORS[code].ink }}
        >
          {code}
        </li>
      ))}
    </ol>
  )
}

// How many living species the family has, set apart so it is easy to spot.
export function SpeciesCount({ data }) {
  const line = speciesCountLine(data)
  return line ? <p className="species-count">{line}</p> : null
}

// A short description from Wikipedia, plus where the group lives, credited
// as the licence requires.
export function WikiSummary({ summary, heading = 'About this group' }) {
  if (!summary) return null
  const otherArticle = summary.range_text && summary.range_url !== summary.url
  // The range gets its own line, so it is not repeated in the summary.
  let text = summary.text
  for (const sentence of (summary.range_text || '').split(/(?<=[.!?])\s+/)) {
    if (sentence && text.includes(sentence)) text = text.replace(sentence, '').replace(/\s{2,}/g, ' ').trim()
  }
  return (
    <section className="card-section wiki-summary">
      <h3>{heading}</h3>
      {text && <p>{text}</p>}
      {summary.range_text && (
        <p className="wiki-range">
          <span className="wiki-range-label">
            {summary.range_scope === 'species' ? `Range (${summary.range_title})` : 'Range'}
          </span>{' '}
          {summary.range_text}
        </p>
      )}
      <p className="card-source">
        Adapted from Wikipedia,{' '}
        <a href={summary.url} target="_blank" rel="noreferrer">{summary.title}</a>
        {otherArticle && (
          <>
            {' and '}
            <a href={summary.range_url} target="_blank" rel="noreferrer">{summary.range_title}</a>
          </>
        )}
        {', '}
        <a href={summary.licence_url} target="_blank" rel="noreferrer">{summary.licence}</a>
      </p>
    </section>
  )
}

export function ReptileDatabaseChip({ data }) {
  if (!isReptileDatabaseFamily(data)) return null
  return (
    <span className="rd-chip" title={`${OPENTREE_STANDING[data.opentree_family]} Recognized as a family by The Reptile Database.`}>
      Reptile Database family
    </span>
  )
}

export function ReptileDatabaseNote({ data }) {
  if (!isReptileDatabaseFamily(data)) return null
  return (
    <p className="rd-note">
      {OPENTREE_STANDING[data.opentree_family]} It is recognized as a family by The Reptile Database; its species
      are placed in the tree by Open Tree.
    </p>
  )
}
