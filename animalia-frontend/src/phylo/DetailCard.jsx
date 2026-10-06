import { closestRelatives, formatAge, lineageTrail } from '../phylogenyLayout.js'
import { majorClade } from '../phylogenyStyle.js'
import { ageRange, displayName } from './labels.js'
import { Conservation, Placement, SpeciesLinks, SpeciesPhotos } from './SpeciesParts.jsx'
import { useSpecies } from './useSpecies.js'

export default function DetailCard({
  node, traceToken, treeActions = true, onClose, onSelect, onTrace, onRelatives, onWholeTree,
}) {
  const d = node.data
  const kind = d.kind === 'family' ? 'Family' : d.kind === 'group' ? 'Group' : 'Clade'
  const { species, state } = useSpecies(d.kind === 'family' ? d.representative_species?.id : null)
  return (
    <aside className="detail-card" aria-live="polite">
      <button type="button" className="card-close" onClick={onClose} aria-label="Close details">
        ×
      </button>
      {d.kind === 'family' ? (
        <FamilyHead node={node} kind={kind} species={species} state={state} />
      ) : (
        <header className="card-head">
          <p className="card-kicker">
            {kind}
            {d.kind !== 'clade' && ` · ${majorClade(node).name || 'Other lineage'}`}
          </p>
          <h2 className="card-title">{displayName(d)}</h2>
        </header>
      )}

      {treeActions && (
        <div className="card-actions">
          <button type="button" onClick={onTrace}>Trace this lineage</button>
          <button type="button" onClick={onRelatives}>Explore relatives</button>
          <button type="button" onClick={onWholeTree}>Whole tree</button>
        </div>
      )}

      {d.kind === 'family' && <Emergence node={node} />}
      {d.kind === 'group' && <GroupDetails node={node} />}
      {d.kind === 'clade' && <CladeDetails node={node} />}
      <Relatives node={node} onSelect={onSelect} />
      <LineageTrail node={node} traceToken={traceToken} onSelect={onSelect} />
      {d.kind === 'family' && state === 'ready' && species && <Conservation species={species} />}
      {d.kind === 'family' && <Placement data={d} />}
      {d.kind === 'family' && state === 'ready' && species && <SpeciesLinks species={species} />}
    </aside>
  )
}

function FamilyHead({ node, kind, species, state }) {
  const d = node.data
  return (
    <>
      {state === 'ready' && species && <SpeciesPhotos species={species} />}
      <header className="card-head">
        <p className="card-kicker">
          {kind} {d.name} · {majorClade(node).name || 'Other lineage'}
        </p>
        <h2 className="card-title">{d.representative_species?.common_name || d.representative_species?.scientific_name}</h2>
        <p className="card-scientific">
          <em>{d.representative_species?.scientific_name}</em>
          <span className="card-role"> — representative species of {d.name}</span>
        </p>
      </header>
      {state === 'loading' && <p className="card-muted">Loading species…</p>}
      {state === 'error' && <p className="phylo-error">Could not load this species.</p>}
    </>
  )
}

function Emergence({ node }) {
  const parent = node.parent?.data
  if (!parent) return null
  const range = ageRange(parent)
  return (
    <section className="card-section">
      <h3>When it emerged</h3>
      <p>
        Its lineage split from its closest relatives about <strong>{formatAge(node.data.stem_age_ma)}</strong>{' '}
        million years ago{range ? ` (95% range ${range})` : ''}.
      </p>
      <p className="card-source">
        Date: {parent.age_source}
        {parent.age_study_count ? `, ${parent.age_study_count} studies` : ''}
        {parent.age_citation ? ` — ${parent.age_citation}` : ''}
      </p>
    </section>
  )
}

function GroupDetails({ node }) {
  const d = node.data
  return (
    <>
      <section className="card-section">
        <h3>Fossil record</h3>
        {d.extinct ? (
          <p>
            First fossils about <strong>{formatAge(d.first_appearance_ma)}</strong> million years ago; last about{' '}
            <strong>{formatAge(d.last_appearance_ma)}</strong> million years ago.
          </p>
        ) : (
          <p>
            Oldest fossils about <strong>{formatAge(d.first_appearance_ma)}</strong> million years ago; still living
            today.
          </p>
        )}
        {d.age_citation && <p className="card-source">Dates: {d.age_citation}</p>}
      </section>
      <Emergence node={node} />
      <section className="card-section">
        <h3>About this group</h3>
        {d.placement_uncertain && <p className="card-note">Its position in the tree is debated.</p>}
        {d.anapsid_skull && <p className="card-note">Has an anapsid skull (no openings behind the eye).</p>}
        {d.note && <p className="card-note">{d.note}</p>}
        {d.citation && <p className="card-source">Placement: {d.citation}</p>}
      </section>
    </>
  )
}

function CladeDetails({ node }) {
  const d = node.data
  const tips = node.leaves()
  const range = ageRange(d)
  let adjustment = null
  if (d.age_adjusted && d.age_source === 'interpolated') {
    adjustment = `TimeTree's estimate (${formatAge(d.age_unadjusted_ma)} Ma) clashed with better-supported estimates and was set aside, so this age is interpolated.`
  } else if (d.age_adjusted) {
    adjustment = `Raised from ${formatAge(d.age_unadjusted_ma)} Ma so that it is not younger than a group inside it.`
  }
  return (
    <>
      <section className="card-section">
        <h3>Common ancestor of</h3>
        <p>
          {tips.length} {tips.length === 1 ? 'family' : 'families and groups'}, e.g.{' '}
          {tips.slice(0, 4).map((tip) => tip.data.name).join(', ')}
          {tips.length > 4 ? '…' : ''}
        </p>
      </section>
      <section className="card-section">
        <h3>When it lived</h3>
        <p>
          About <strong>{formatAge(d.age_ma)}</strong> million years ago{range ? ` (95% range ${range})` : ''}.
        </p>
        <p className="card-source">
          Date: {d.age_source}
          {d.age_study_count ? `, ${d.age_study_count} studies` : ''}
          {d.age_citation ? ` — ${d.age_citation}` : ''}
        </p>
        {adjustment && <p className="card-note">{adjustment}</p>}
      </section>
      {(d.note || d.citation || d.anapsid_skull || d.placement_uncertain) && (
        <section className="card-section">
          <h3>Notes</h3>
          {d.anapsid_skull && <p className="card-note">Has an anapsid skull (no openings behind the eye).</p>}
          {d.note && <p className="card-note">{d.note}</p>}
          {d.citation && <p className="card-source">{d.name ? 'Name and placement' : 'Placement'}: {d.citation}</p>}
        </section>
      )}
    </>
  )
}

function relativeName(node) {
  if (!node.children) return node.data.name
  const tips = node.leaves()
  if (node.data.name) return `${node.data.name} (${tips.length})`
  return `${tips.slice(0, 2).map((tip) => tip.data.name).join(', ')}${tips.length > 2 ? ` + ${tips.length - 2} more` : ''}`
}

// Who sits on the other side of the nearest split, and when they parted.
function Relatives({ node, onSelect }) {
  const sisters = closestRelatives(node)
  if (!sisters.length) return null
  return (
    <section className="card-section">
      <h3>Closest relatives</h3>
      <ul className="relatives">
        {sisters.map((sister) => (
          <li key={sister.data.id}>
            <button type="button" onClick={() => onSelect(sister.data.id)}>{relativeName(sister)}</button>
          </li>
        ))}
      </ul>
      <p className="card-source">
        Shared ancestor about {formatAge(node.parent.data.age_ma)} million years ago.
      </p>
    </section>
  )
}

// The path back to the root, revealed step by step when traced.
function LineageTrail({ node, traceToken, onSelect }) {
  const trail = lineageTrail(node).slice(1).filter((step) => step.data.name)
  if (!trail.length) return null
  return (
    <section className="card-section">
      <h3>Lineage</h3>
      <ol className="trail" key={traceToken}>
        {trail.map((step, index) => (
          <li key={step.data.id} style={{ animationDelay: `${index * 0.16}s` }}>
            <button type="button" onClick={() => onSelect(step.data.id)}>{step.data.name}</button>
            <span>~{formatAge(step.data.age_ma)} Ma</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
