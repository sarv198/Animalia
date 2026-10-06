import '@fontsource-variable/fraunces'
import { useEffect, useRef, useState } from 'react'
import { API_BASE_URL, fetchPhylogeny } from '../api.js'
import { buildModel } from '../phylogenyLayout.js'
import Credits from '../phylo/Credits.jsx'
import DetailCard from '../phylo/DetailCard.jsx'
import FamilyTable from '../phylo/FamilyTable.jsx'
import HoverCard from '../phylo/HoverCard.jsx'
import Key from '../phylo/Key.jsx'
import TimeLens from '../phylo/TimeLens.jsx'
import TreeCanvas from '../phylo/TreeCanvas.jsx'
import './Phylogeny.css'

const VIEWS = [
  { id: 'time', label: 'Time-scaled' },
  { id: 'branching', label: 'Branching order' },
  { id: 'table', label: 'Table' },
]
const PLAY_SECONDS = 60 // the whole history, root to present

export default function Phylogeny() {
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [model, setModel] = useState(null)
  const [view, setView] = useState('time')
  const [selectedId, setSelectedId] = useState(null)
  const [hover, setHover] = useState(null) // { id, x, y }
  const [focusMode, setFocusMode] = useState(null) // null | 'relatives'
  const [traceToken, setTraceToken] = useState(0)
  const [lensAge, setLensAge] = useState(null) // null = whole tree, no lens
  const [playing, setPlaying] = useState(false)
  const [rewinding, setRewinding] = useState(false)
  const [showCredits, setShowCredits] = useState(false)
  const treeRef = useRef(null)
  const frameRef = useRef(null)
  const rewindTimer = useRef(null)

  useEffect(() => {
    let cancelled = false
    fetchPhylogeny()
      .then((data) => {
        if (cancelled) return
        setModel(buildModel(data))
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message || 'Could not reach the API')
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const onKey = (event) => {
      if (event.key !== 'Escape') return
      setShowCredits(false)
      setSelectedId(null)
      setFocusMode(null)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      cancelAnimationFrame(frameRef.current)
      clearTimeout(rewindTimer.current)
    }
  }, [])

  const rootAge = model?.root.data.age_ma ?? 0
  const selected = model && selectedId != null ? model.byId.get(selectedId) : null
  const hovered = model && hover ? model.byId.get(hover.id) : null

  function select(id) {
    setSelectedId(id)
    setFocusMode(null)
    setTraceToken(0)
    setHover(null)
    if (view !== 'table') treeRef.current?.focusOn(model.byId.get(id))
  }

  function wholeTree() {
    setSelectedId(null)
    setFocusMode(null)
    treeRef.current?.showWholeTree()
  }

  function trace() {
    setTraceToken((token) => token + 1)
    setFocusMode(null)
    treeRef.current?.focusLineage(selected)
  }

  function exploreRelatives() {
    setFocusMode('relatives')
    treeRef.current?.focusOn(selected, { wide: true })
  }

  function exploreFamily() {
    const families = model.leaves.filter(
      (leaf) => leaf.data.kind === 'family' && leaf.data.representative_species?.image && leaf.data.id !== selectedId,
    )
    const pick = families[Math.floor(Math.random() * families.length)]
    if (view === 'table') setView('time')
    select(pick.data.id)
  }

  function stopPlaying() {
    cancelAnimationFrame(frameRef.current)
    setPlaying(false)
  }

  function togglePlay() {
    if (playing) {
      stopPlaying()
      return
    }
    const from = lensAge == null || lensAge <= 0 ? rootAge : lensAge
    const duration = (PLAY_SECONDS * 1000 * from) / rootAge
    let started = null // the first frame's timestamp
    setPlaying(true)
    setLensAge(from)
    const step = (now) => {
      started ??= now
      const age = from * (1 - (now - started) / duration)
      if (age <= 0) {
        setLensAge(0) // the present: every living family settles into view
        setPlaying(false)
        return
      }
      setLensAge(age)
      frameRef.current = requestAnimationFrame(step)
    }
    frameRef.current = requestAnimationFrame(step)
  }

  function scrub(age) {
    stopPlaying()
    if (lensAge != null && age > lensAge + 0.25) {
      // Going back in time: the stage briefly takes on a deep-time tint.
      setRewinding(true)
      clearTimeout(rewindTimer.current)
      rewindTimer.current = setTimeout(() => setRewinding(false), 700)
    }
    setLensAge(age)
  }

  function exitLens() {
    stopPlaying()
    setLensAge(null)
  }

  function changeView(next) {
    setView(next)
    setHover(null)
    if (next !== 'time') exitLens()
  }

  return (
    <div className="phylo-page">
      <header className="phylo-header">
        <div className="phylo-titles">
          <p className="phylo-eyebrow">
            Reptilia{model ? ` · ${Math.round(rootAge)} million years of evolution` : ''}
          </p>
          <h1>Reptile phylogeny</h1>
          <p className="phylo-caption">
            How reptile families are related and when their lineages split. Branching order from the
            Open Tree of Life plus a cited backbone for deep and extinct groups; ages from TimeTree 5
            and the fossil record. Each family is placed by one representative species.
          </p>
        </div>
        <nav className="phylo-controls" aria-label="Tree controls">
          <div className="phylo-views" role="tablist" aria-label="View">
            {VIEWS.map((option) => (
              <button
                key={option.id}
                type="button"
                role="tab"
                aria-selected={view === option.id}
                className={view === option.id ? 'phylo-view active' : 'phylo-view'}
                onClick={() => changeView(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
          {status === 'ready' && (
            <>
              <button type="button" className="phylo-action" onClick={exploreFamily}>
                Explore a family
              </button>
              {view !== 'table' && (
                <button type="button" className="phylo-action" onClick={wholeTree}>
                  Whole tree
                </button>
              )}
            </>
          )}
          <button type="button" className="phylo-action quiet" onClick={() => setShowCredits(true)}>
            Sources &amp; credits
          </button>
        </nav>
      </header>

      {status === 'loading' && <p className="phylo-status">Loading the tree…</p>}
      {status === 'error' && (
        <p className="phylo-status phylo-error" role="alert">
          Could not reach the Animalia API at {API_BASE_URL}. {error}
        </p>
      )}

      {status === 'ready' && model && (
        <div className={`phylo-stage${rewinding ? ' rewinding' : ''}${lensAge === 0 ? ' present' : ''}`}>
          {view === 'table' ? (
            <>
              <FamilyTable model={model} selectedId={selectedId} onSelect={select} />
              <Key timeScaled={false} />
            </>
          ) : (
            <>
              <TreeCanvas
                ref={treeRef}
                model={model}
                view={view}
                hoverId={hover?.id ?? null}
                selectedId={selectedId}
                focusMode={focusMode}
                traceToken={traceToken}
                lensAge={view === 'time' ? lensAge : null}
                onHover={setHover}
                onSelect={select}
                onLensChange={scrub}
              />
              <Key timeScaled={view === 'time'} />
              {view === 'time' && (
                <TimeLens
                  rootAge={rootAge}
                  lensAge={lensAge}
                  playing={playing}
                  events={model.events}
                  onPlay={togglePlay}
                  onScrub={scrub}
                  onExit={exitLens}
                />
              )}
              {hovered && hover && hover.id !== selectedId && (
                <HoverCard node={hovered} x={hover.x} y={hover.y} stageWidth={window.innerWidth} />
              )}
            </>
          )}
          {selected && (
            <DetailCard
              key={selected.data.id}
              node={selected}
              traceToken={traceToken}
              onClose={() => {
                setSelectedId(null)
                setFocusMode(null)
              }}
              onSelect={select}
              onTrace={trace}
              onRelatives={exploreRelatives}
              onWholeTree={wholeTree}
              treeActions={view !== 'table'}
            />
          )}
        </div>
      )}

      {showCredits && <Credits onClose={() => setShowCredits(false)} />}
    </div>
  )
}
