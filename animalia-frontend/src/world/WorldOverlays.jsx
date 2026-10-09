import { useState } from 'react'
import { formatAge } from '../phylogenyLayout.js'
import { STATUS } from '../phylogenyStyle.js'
import { ageSummary, displayName, photoCredit } from '../phylo/labels.js'
import { stepWhen, whenPhrase } from '../phylo/narrative.js'
import { EXHIBIT_NAMES, familyCount, scaleTrail, searchWorld, specimenFact } from './worldModel.js'

export function SearchBox({ world, onSelect }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const results = searchWorld(world, query)
  return (
    <div className="world-search">
      <label className="sr-only" htmlFor="world-search">Find a family, species or clade</label>
      <input
        id="world-search"
        type="search"
        placeholder="Find a family, animal or clade"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && query.trim() && (
        <ul className="world-results" role="listbox">
          {results.length === 0 && <li className="world-muted">No matches</li>}
          {results.map((result) => (
            <li key={result.id}>
              <button
                type="button"
                onMouseDown={(event) => {
                  event.preventDefault()
                  setQuery('')
                  setOpen(false)
                  onSelect(result.id)
                }}
              >
                <span>{result.label}</span>
                <small>{result.detail}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const LEVEL_NAMES = { tree: 'The tree', lineages: 'Lineages', families: 'Families', species: 'Species' }

// "From life to tree": what scale the camera is at, and where.
export function ScaleTrail({ world, scale }) {
  if (!scale) return null
  const { level, trail } = scaleTrail(world, scale.nearestId, scale.distance)
  return (
    <nav className="world-scale" aria-label="Current scale">
      <span className="scale-level">{LEVEL_NAMES[level]}</span>
      {trail.map((step, index) => (
        <span key={`${step}-${index}`} className="scale-step">
          {index > 0 && <span className="scale-sep">›</span>}
          {step}
        </span>
      ))}
    </nav>
  )
}

// The small card that appears when the pointer finds something.
export function DiscoveryChip({ world, hover, museum, stageWidth }) {
  const item = world.nodes.get(hover.id)
  if (!item) return null
  const d = item.data
  const species = d.kind === 'family' ? d.representative_species : null
  const flip = hover.x > stageWidth - 320
  const fact = museum && d.kind === 'family' ? specimenFact(item.node) : null
  return (
    <div
      className={museum ? 'world-chip plaque' : 'world-chip'}
      style={{ left: flip ? hover.x - 296 : hover.x + 18, top: hover.y + 18 }}
      role="status"
    >
      {d.kind === 'family' ? (
        <>
          <p className="chip-family">{d.name}</p>
          {species?.common_name && <p className="chip-common">{species.common_name}</p>}
          <p className="chip-sci">{species?.scientific_name}</p>
          {STATUS[d.placement_status] && (
            <p className="chip-flag" style={{ color: STATUS[d.placement_status].color }}>
              {STATUS[d.placement_status].symbol} {STATUS[d.placement_status].label}
            </p>
          )}
          {fact && <p className="chip-fact">{fact}</p>}
          {species?.image && <p className="chip-credit">{photoCredit(species.image)}</p>}
          <p className="chip-hint">Click to explore its relatives →</p>
        </>
      ) : (
        <>
          <p className="chip-family">{displayName(d)}</p>
          {EXHIBIT_NAMES[d.name] && <p className="chip-common">{EXHIBIT_NAMES[d.name]}</p>}
          <p className="chip-sci-plain">{ageSummary(d)}</p>
          {d.kind === 'clade' && <p className="chip-sci-plain">{familyCount(item.node)} families</p>}
          <p className="chip-hint">Click to explore →</p>
        </>
      )}
    </div>
  )
}

// Narration for a tour stop, with skip back/forward and exit.
export function TourBar({ caption, index, total, paused, onPrev, onNext, onPause, onExit, label }) {
  return (
    <div className="world-tour" role="region" aria-label={label}>
      <p className="tour-kicker">{label} · {index + 1} of {total}</p>
      <h2 key={caption.title}>{caption.title}{caption.subtitle && <span> · {caption.subtitle}</span>}</h2>
      {caption.lines.map((line) => <p key={line} className="tour-line">{line}</p>)}
      <div className="tour-controls">
        <button type="button" onClick={onPrev} disabled={index === 0} aria-label="Previous stop">←</button>
        <button type="button" onClick={onPause}>{paused ? 'Resume' : 'Pause'}</button>
        <button type="button" onClick={onNext} aria-label="Next stop">→</button>
        <button type="button" onClick={onExit}>Exit</button>
      </div>
    </div>
  )
}

// Following a lineage back toward the root, one split at a time.
export function FollowBar({ world, follow, onExit }) {
  const step = follow.steps[follow.index]
  const stepNode = step ? world.nodes.get(step.id)?.node : null
  return (
    <div className="world-tour follow" role="region" aria-label="Follow lineage">
      <p className="tour-kicker">
        Following the lineage of {follow.originName} · {follow.done ? 'arrived at the root' : `step ${Math.max(follow.index, 0) + 1} of ${follow.steps.length}`}
      </p>
      {step ? (
        <>
          <h2 key={step.id}>
            {step.title}
            {step.age != null && <span> · {stepWhen(step.age, stepNode)}</span>}
          </h2>
          <p className="tour-line">Splits into: {step.parts.join('  |  ')}</p>
        </>
      ) : (
        <h2>Setting out…</h2>
      )}
      <div className="tour-controls">
        <button type="button" onClick={onExit}>{follow.done ? 'Back to the family' : 'Stop'}</button>
      </div>
    </div>
  )
}

// The museum entrance: a title over the whole structure, from the data.
export function MuseumIntro({ world, onTour, onFree }) {
  const squamata = world.byName.get('Squamata')
  const age = squamata?.data.age_ma
  return (
    <div className="museum-intro" role="dialog" aria-label="Museum mode">
      <p className="museum-eyebrow">An exhibit of reptile evolution</p>
      <h1>Squamata</h1>
      {squamata && (
        <p className="museum-sub">
          Lizards, snakes and amphisbaenians: {familyCount(squamata.node)} families in this tree, all descended
          from one ancestor that lived about {formatAge(age)} million years ago, {whenPhrase(age, squamata.node)}.
        </p>
      )}
      <p className="museum-hint">Height is time: the deepest branches are the oldest.</p>
      <div className="museum-actions">
        <button type="button" className="primary" onClick={onTour}>Begin guided tour</button>
        <button type="button" onClick={onFree}>Explore freely</button>
      </div>
    </div>
  )
}
