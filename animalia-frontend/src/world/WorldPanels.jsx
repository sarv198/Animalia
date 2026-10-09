import { formatAge } from '../phylogenyLayout.js'
import { majorClade } from '../phylogenyStyle.js'
import BirdsPanel from '../phylo/BirdsPanel.jsx'
import { ageRange, dateSource, displayName } from '../phylo/labels.js'
import { cladeStory, familyStory, pairStory } from '../phylo/narrative.js'
// Range maps are hidden for now; the component is kept for later.
// import RangeMap from '../phylo/RangeMap.jsx'
import { Conservation, Placement, SpeciesCount, SpeciesLinks, SpeciesPhotos, WikiSummary } from '../phylo/SpeciesParts.jsx'
import { useProfile } from '../phylo/useProfile.js'
import { useSpecies } from '../phylo/useSpecies.js'
import { EXHIBIT_NAMES, comparison, describe, familyCount, neighbourhood } from './worldModel.js'

function cladeLabel(node) {
  const clade = majorClade(node)
  if (!clade.name) return 'Other lineage'
  const plain = EXHIBIT_NAMES[clade.name]
  return plain ? `${plain} (${clade.name})` : clade.name
}

// The selected family, clade or group: the animal leads, relationships follow.
export function SelectionCard({ world, id, museum, onSelect, onFollow, onCompare, onFocus, onClose }) {
  const item = world.nodes.get(id)
  const d = item.data
  const { species, state } = useSpecies(d.kind === 'family' ? d.representative_species?.id : null)
  const n = neighbourhood(world, id)
  const { profile } = useProfile(d.name)

  return (
    <aside className="world-card" aria-live="polite">
      <button type="button" className="world-close" onClick={onClose} aria-label="Close">×</button>
      {d.kind === 'family' && state === 'ready' && species && <SpeciesPhotos species={species} />}
      <header className="world-card-head">
        <p className="world-kicker">
          {d.kind === 'family' ? 'Family' : d.kind === 'group' ? 'Group' : 'Clade'} · {cladeLabel(item.node)}
        </p>
        {d.kind === 'family' ? (
          <>
            <h2>{d.representative_species?.common_name || d.representative_species?.scientific_name}</h2>
            <p className="world-sci">
              <em>{d.representative_species?.scientific_name}</em>, the representative species of <strong>{d.name}</strong>
            </p>
          </>
        ) : (
          <h2>
            {displayName(d)}
            {EXHIBIT_NAMES[d.name] && <span className="world-plain"> · {EXHIBIT_NAMES[d.name]}</span>}
          </h2>
        )}
      </header>

      <div className="world-actions">
        <button type="button" onClick={onFollow}>{museum ? 'Explore lineage →' : 'Follow lineage'}</button>
        <button type="button" onClick={onCompare}>Compare with…</button>
        <button type="button" onClick={onFocus}>Focus</button>
      </div>

      {d.name === 'Aves' && <WikiSummary summary={profile?.summary} heading="About birds" />}
      {d.name === 'Aves' && <BirdsPanel node={item.node} />}
      {d.kind === 'family' && <Emerged node={item.node} />}
      {d.kind === 'family' && <WikiSummary summary={profile?.summary} heading={`About ${d.name}`} />}
      {/* Range map, hidden for now:
      {d.kind === 'family' && profile && (
        <RangeMap profile={profile} familyName={d.name} species={d.representative_species} />
      )}
      */}
      {d.kind === 'clade' && <CladeFacts node={item.node} />}
      {d.kind === 'group' && <GroupFacts node={item.node} />}
      {d.kind !== 'family' && d.name !== 'Aves' && (
        <WikiSummary summary={profile?.summary} heading={`About ${d.name || 'this group'}`} />
      )}
      {n && <Neighbourhood n={n} world={world} onSelect={onSelect} />}
      {d.kind === 'family' && <Placement data={d} />}
      {d.kind === 'family' && state === 'ready' && species && <Conservation species={species} />}
      {d.kind === 'family' && state === 'ready' && species && <SpeciesLinks species={species} />}
      {d.kind === 'family' && state === 'loading' && <p className="world-muted">Loading species…</p>}
    </aside>
  )
}

function Emerged({ node }) {
  const parent = node.parent?.data
  if (!parent) return null
  const range = ageRange(parent)
  return (
    <section className="world-section story">
      <h3>Its story</h3>
      <SpeciesCount data={node.data} />
      {familyStory(node).map((line) => <p key={line}>{line}</p>)}
      <p className="world-source">
        {range ? `Split date 95% range: ${range} million years ago. ` : ''}
        {dateSource(parent)}
      </p>
    </section>
  )
}

function CladeFacts({ node }) {
  const d = node.data
  const range = ageRange(d)
  return (
    <section className="world-section story">
      <h3>Its story</h3>
      {cladeStory(node).map((line) => <p key={line}>{line}</p>)}
      <p className="world-source">
        {range ? `Date 95% range: ${range} million years ago. ` : ''}
        {dateSource(d)}
      </p>
      {d.note && <p className="world-note">{d.note}</p>}
      {d.citation && <p className="world-source">{d.name ? 'Name and placement' : 'Placement'}: {d.citation}</p>}
    </section>
  )
}

function GroupFacts({ node }) {
  const d = node.data
  return (
    <section className="world-section">
      <h3>Fossil record</h3>
      {d.extinct ? (
        <p>
          First fossils about <strong>{formatAge(d.first_appearance_ma)}</strong> million years ago; last about{' '}
          <strong>{formatAge(d.last_appearance_ma)}</strong> million years ago.
        </p>
      ) : (
        <p>Oldest fossils about <strong>{formatAge(d.first_appearance_ma)}</strong> million years ago; still living today.</p>
      )}
      {d.age_citation && <p className="world-source">Dates: {d.age_citation}</p>}
      {d.placement_uncertain && <p className="world-note">Its position in the tree is debated.</p>}
      {d.anapsid_skull && <p className="world-note">Has an anapsid skull (no openings behind the eye).</p>}
      {d.note && <p className="world-note">{d.note}</p>}
      {d.citation && <p className="world-source">Placement: {d.citation}</p>}
    </section>
  )
}

function Chips({ nodes, onSelect, limit = 8 }) {
  const tips = nodes.flatMap((node) => (node.children ? node.leaves() : [node]))
  return (
    <ul className="world-chips">
      {tips.slice(0, limit).map((tip) => (
        <li key={tip.data.id}>
          <button type="button" onClick={() => onSelect(tip.data.id)}>{tip.data.name}</button>
        </li>
      ))}
      {tips.length > limit && <li className="world-more">+{tips.length - limit} more</li>}
    </ul>
  )
}

// Evolutionary Neighborhood: concentric zones drawn as a schematic, never in
// the 3D space, because they are not distances.
function Neighbourhood({ n, world, onSelect }) {
  const outerName = n.outer === world.root ? 'the rest of the tree' : 'the rest of Squamata'
  return (
    <section className="world-section">
      <h3>Evolutionary neighborhood</h3>
      <div className="hood">
        <svg viewBox="0 0 200 200" className="hood-rings" aria-hidden="true">
          <circle cx="100" cy="100" r="96" className="ring ring-3" />
          <circle cx="100" cy="100" r="68" className="ring ring-2" />
          <circle cx="100" cy="100" r="40" className="ring ring-1" />
          <circle cx="100" cy="100" r="12" className="ring-core" />
          <text x="100" y="62" textAnchor="middle">1</text>
          <text x="100" y="40" textAnchor="middle">2</text>
          <text x="100" y="13" textAnchor="middle">3</text>
        </svg>
        <ol className="hood-zones">
          <li>
            <strong>1 · Closest relatives</strong>
            <span>{n.sisters.map(describe).join('; ') || 'none'}</span>
            <Chips nodes={n.sisters} onSelect={onSelect} />
          </li>
          <li>
            <strong>2 · Broader clade</strong>
            <span>
              {n.broader ? `${describe(n.broader)}, ${familyCount(n.broader)} families` : 'none'}
            </span>
          </li>
          <li>
            <strong>3 · Beyond</strong>
            <span>{outerName} ({familyCount(n.outer)} families)</span>
          </li>
        </ol>
      </div>
      <p className="world-aid">
        An exploration aid showing how the tree nests, not a measure of genetic distance.
      </p>
    </section>
  )
}

// Two families side by side: what they share.
export function ComparePanel({ world, idA, idB, onSelect, onEnd }) {
  const c = comparison(world, idA, idB)
  if (!c) return null
  const shared = c.shared?.data
  const range = shared ? ageRange(shared) : null
  return (
    <aside className="world-compare" aria-live="polite">
      <p className="world-kicker">Shared evolutionary context</p>
      <h2>
        <button type="button" onClick={() => onSelect(idA)}>{c.a.data.name || 'Unnamed'}</button>
        <span>and</span>
        <button type="button" onClick={() => onSelect(idB)}>{c.b.data.name || 'Unnamed'}</button>
      </h2>
      <div className="story">
        {pairStory(c.a, c.b, c.shared).map((line) => <p key={line}>{line}</p>)}
      </div>
      {c.named && c.named.data !== shared && <p>Both belong to <strong>{describe(c.named)}</strong> ({familyCount(c.named)} families).</p>}
      {shared && (
        <p className="world-source">
          {range ? `Shared ancestor date 95% range: ${range} million years ago. ` : ''}
          {dateSource(shared)}
        </p>
      )}
      <button type="button" className="world-end" onClick={onEnd}>End comparison</button>
    </aside>
  )
}
