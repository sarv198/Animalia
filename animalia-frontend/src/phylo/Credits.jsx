import { useEffect, useState } from 'react'
import { fetchSources } from '../api.js'

// Sources and required attributions. The Reptile Database asks for its
// citation in the project's credits; photo credits sit beside each photo.
export default function Credits({ onClose }) {
  const [sources, setSources] = useState([])

  useEffect(() => {
    let cancelled = false
    fetchSources()
      .then((rows) => {
        if (!cancelled) setSources(rows)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const version = (name) => sources.find((s) => s.name === name)?.version

  return (
    <div className="credits-backdrop" role="presentation" onClick={onClose}>
      <section
        className="credits"
        role="dialog"
        aria-modal="true"
        aria-labelledby="credits-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" className="card-close" onClick={onClose} aria-label="Close credits">×</button>
        <h2 id="credits-title">Sources &amp; credits</h2>

        <h3>How the tree is built</h3>
        <ul>
          <li>
            Branching order of living families: the Open Tree of Life synthetic tree
            {version('Open Tree of Life') ? ` (${version('Open Tree of Life')})` : ''},{' '}
            <a href="https://tree.opentreeoflife.org" target="_blank" rel="noreferrer">tree.opentreeoflife.org</a>.
          </li>
          <li>
            Deep relationships and extinct groups: a curated backbone, each relationship cited to the
            published literature (shown in the details of each group).
          </li>
          <li>
            Divergence dates: TimeTree 5{version('TimeTree 5') ? ` (data version ${version('TimeTree 5')})` : ''} —
            Kumar et al. 2022, Mol Biol Evol 39:msac174,{' '}
            <a href="https://timetree.org" target="_blank" rel="noreferrer">timetree.org</a>; fossil dates curated
            from the literature and checked against the Paleobiology Database.
          </li>
          <li>
            Family names and membership:{' '}
            <cite>
              Uetz, P., Freed, P., Aguilar, R., Reyes, F., Kudera, J. &amp; Hošek, J. (eds.) The Reptile Database,{' '}
              <a href="http://www.reptile-database.org" target="_blank" rel="noreferrer">http://www.reptile-database.org</a>.
            </cite>
            {version('The Reptile Database') ? ` Checklist release ${version('The Reptile Database')}.` : ''} Only
            taxonomic facts are used; no Reptile Database photos or text appear on this site.
          </li>
        </ul>

        <h3>Species information</h3>
        <ul>
          <li>
            Photos: Wikimedia Commons and GBIF (mostly iNaturalist), used under their open licences. Each photo
            is credited beside it with its creator, licence and source.
          </li>
          <li>
            Conservation status: the IUCN Red List category as listed on each species' Wikipedia page. For
            official assessments see{' '}
            <a href="https://www.iucnredlist.org" target="_blank" rel="noreferrer">the IUCN Red List</a>.
          </li>
          <li>
            Identifiers and links: GBIF, Catalogue of Life, Open Tree of Life, Wikipedia.
          </li>
        </ul>
        <p className="credits-note">A non-commercial project.</p>
      </section>
    </div>
  )
}
