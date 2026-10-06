// Species sections shared by the 2D card and the 3D page.
import { useState } from 'react'
import { IUCN_LABELS, STATUS } from '../phylogenyStyle.js'

export function SpeciesPhotos({ species }) {
  const [index, setIndex] = useState(0)
  const images = species.images || []
  const image = images[index]
  if (!image) return <p className="card-muted card-nophoto">No openly licensed photo found.</p>
  return (
    <figure className="card-photo">
      <a href={image.page_url || image.url} target="_blank" rel="noreferrer">
        <img
          src={image.url}
          alt={`${species.scientific_name}${species.common_name ? ` (${species.common_name})` : ''}`}
          referrerPolicy="no-referrer"
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
              className={i === index ? 'thumb active' : 'thumb'}
              onClick={() => setIndex(i)}
              aria-label={`Photo ${i + 1} of ${images.length}`}
            >
              <img src={img.thumbnail_url || img.url} alt="" loading="lazy" referrerPolicy="no-referrer" />
            </button>
          ))}
        </div>
      )}
    </figure>
  )
}

export function Conservation({ species }) {
  return (
    <section className="card-section">
      <h3>Conservation status</h3>
      {species.iucn_category ? (
        <>
          <p>
            <span className="iucn-pill">{species.iucn_category}</span> {IUCN_LABELS[species.iucn_category]}
          </p>
          <p className="card-source">
            IUCN Red List category as listed on{' '}
            {species.wikipedia_url ? (
              <a href={species.wikipedia_url} target="_blank" rel="noreferrer">Wikipedia</a>
            ) : (
              'Wikipedia'
            )}
            {species.iucn_assessment_year ? ` (assessment ${species.iucn_assessment_year})` : ''}.
          </p>
        </>
      ) : (
        <p className="card-muted">Not listed on Wikipedia.</p>
      )}
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
    </section>
  )
}
