import '@fontsource-variable/fraunces'
import { useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE_URL, fetchPhylogeny } from '../api.js'
import Credits from '../phylo/Credits.jsx'
import Key from '../phylo/Key.jsx'
import TreeWorld from '../world/TreeWorld.js'
import { ComparePanel, SelectionCard } from '../world/WorldPanels.jsx'
import { DiscoveryChip, FollowBar, MuseumIntro, ScaleTrail, SearchBox, TourBar } from '../world/WorldOverlays.jsx'
import { buildWorld, cladeCaption, emphasisFor, familyCaption, familyCount, lineageSteps } from '../world/worldModel.js'
import './TreeOfLife3D.css'

const DWELL_MS = 6500 // each tour stop
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export default function TreeOfLife3D() {
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [world, setWorld] = useState(null)
  const [hover, setHover] = useState(null) // { id, x, y }
  const [selectedId, setSelectedId] = useState(null)
  const [compareId, setCompareId] = useState(null)
  const [pickingCompare, setPickingCompare] = useState(false)
  const [scale, setScale] = useState(null)
  const [tour, setTour] = useState(null) // { kind, index, paused }
  const [follow, setFollow] = useState(null)
  const [museum, setMuseum] = useState(false)
  const [museumIntro, setMuseumIntro] = useState(false)
  const [showCredits, setShowCredits] = useState(false)
  const containerRef = useRef(null)
  const engineRef = useRef(null)
  const pickRef = useRef(() => {})
  const advanceRef = useRef(() => {})
  const followRun = useRef(0)
  const [reducedMotion] = useState(prefersReducedMotion)

  useEffect(() => {
    let cancelled = false
    fetchPhylogeny()
      .then((data) => {
        if (cancelled) return
        setWorld(buildWorld(data))
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

  // The engine lives for as long as the data does.
  useEffect(() => {
    if (!world || !containerRef.current) return undefined
    const engine = new TreeWorld(containerRef.current, world, {
      reducedMotion,
      onHover: setHover,
      onSelect: (id, options) => pickRef.current(id, options),
      onScale: setScale,
    })
    engineRef.current = engine
    return () => {
      engine.dispose()
      engineRef.current = null
    }
  }, [world, reducedMotion])

  // Selection and comparison drive emphasis, ancestry pulses and connections.
  useEffect(() => {
    const engine = engineRef.current
    if (!engine || !world) return
    const emphasis = emphasisFor(world, { selectedId, compareId })
    engine.setEmphasis(emphasis ?? {})
    engine.setPulsePaths(emphasis?.pulsePaths ?? [])
    engine.setConnections(emphasis?.connections?.from ?? null, emphasis?.connections?.to)
  }, [world, selectedId, compareId])

  // Hover lifts a lineage only when nothing is selected.
  const hoverId = hover?.id ?? null
  useEffect(() => {
    const engine = engineRef.current
    if (!engine || !world || selectedId != null) return
    engine.setEmphasis(emphasisFor(world, { hoverId }) ?? {})
  }, [world, hoverId, selectedId])

  useEffect(() => {
    engineRef.current?.setMuseum(museum)
  }, [museum])

  // On wide screens the side panel covers the right of the stage.
  const panelOpen = selectedId != null && !tour
  useEffect(() => {
    const wide = window.matchMedia('(min-width: 961px)').matches
    engineRef.current?.setInset(panelOpen && wide ? 420 : 0)
  }, [panelOpen, world])

  const tourStops = useMemo(() => {
    if (!world) return { journey: [], museum: [] }
    const squamata = world.byName.get('Squamata')
    const journey = world.journey.map((item) => ({ id: item.id, caption: cladeCaption(item.node) }))
    if (squamata) {
      journey.push({
        id: null,
        caption: {
          title: 'Modern diversity',
          subtitle: null,
          lines: [`Today: ${familyCount(squamata.node)} living squamate families in this tree, along the top of the structure.`],
        },
      })
    }
    const museumStops = world.museumTour.map((item) => ({ id: item.id, caption: familyCaption(item.node) }))
    return { journey, museum: museumStops }
  }, [world])

  function stopFollowing() {
    followRun.current += 1
    setFollow(null)
  }

  function select(id) {
    stopFollowing()
    setSelectedId(id)
    setCompareId(null)
    setPickingCompare(false)
    setHover(null)
    if (id != null) engineRef.current?.focusNode(id)
  }

  function onPick(id, { shift } = {}) {
    if (tour) return // the tour drives the camera; use its controls
    if (id == null) {
      if (!pickingCompare) select(null)
      return
    }
    if ((pickingCompare || shift) && selectedId != null && id !== selectedId) {
      setCompareId(id)
      setPickingCompare(false)
      const engine = engineRef.current
      if (engine && world) {
        const ids = [...world.nodes.get(selectedId).node.ancestors(), ...world.nodes.get(id).node.ancestors()].map((n) => n.data.id)
        engine.frameIds([...new Set([selectedId, id, ...ids.slice(0, 40)])])
      }
      return
    }
    select(id)
  }

  function goToStop(kind, index) {
    const stops = tourStops[kind]
    if (index < 0) return
    if (index >= stops.length) {
      setTour(null)
      return
    }
    const stop = stops[index]
    setTour({ kind, index, paused: false })
    setSelectedId(stop.id)
    setCompareId(null)
    setHover(null)
    if (stop.id == null) engineRef.current?.resetView()
    else engineRef.current?.focusNode(stop.id, { duration: 1600 })
  }

  // Keep the latest handlers reachable from the engine and the tour timer.
  useEffect(() => {
    pickRef.current = onPick
    advanceRef.current = goToStop
  })

  useEffect(() => {
    if (!tour || tour.paused) return undefined
    const timer = setTimeout(() => advanceRef.current(tour.kind, tour.index + 1), DWELL_MS)
    return () => clearTimeout(timer)
  }, [tour])

  function startTour(kind) {
    stopFollowing()
    setMuseumIntro(false)
    goToStop(kind, 0)
  }

  function exitTour() {
    setTour(null)
    setSelectedId(null)
    engineRef.current?.resetView()
  }

  async function followLineage() {
    const engine = engineRef.current
    if (!engine || selectedId == null) return
    const steps = lineageSteps(world, selectedId)
    const origin = world.nodes.get(selectedId).data
    const run = ++followRun.current
    setFollow({ steps, index: -1, originId: selectedId, originName: origin.name || 'this clade', done: false })
    for (let i = 0; i < steps.length; i++) {
      if (followRun.current !== run) return
      setFollow((current) => current && { ...current, index: i })
      await engine.focusNode(steps[i].id, { duration: 1300 })
      await wait(steps[i].title === 'Unnamed split' ? 500 : 1700)
    }
    if (followRun.current === run) setFollow((current) => current && { ...current, done: true })
  }

  function endFollow() {
    const origin = follow?.originId
    stopFollowing()
    if (origin != null) engineRef.current?.focusNode(origin)
  }

  function enterMuseum() {
    stopFollowing()
    setTour(null)
    setSelectedId(null)
    setCompareId(null)
    setMuseum(true)
    setMuseumIntro(true)
    engineRef.current?.cinematicEntrance()
  }

  function exploreFreely() {
    setMuseumIntro(false)
    setMuseum(false)
    setTour(null)
    engineRef.current?.resetView()
  }

  const tourLabel = tour?.kind === 'museum' ? 'Guided tour' : 'Explore evolution'
  const stop = tour ? tourStops[tour.kind][tour.index] : null

  return (
    <div className={`world-page${museum ? ' museum' : ''}`}>
      <header className="world-header">
        <div className="world-titles">
          <h1>Reptilia Family Tree</h1>
        </div>
        {status === 'ready' && world && (
          <div className="world-controls">
            <SearchBox world={world} onSelect={(id) => (pickingCompare ? onPick(id) : select(id))} />
            <button type="button" onClick={() => engineRef.current?.resetView()}>Reset view</button>
            {/* Focus selected: hidden for now (the card's own Focus button remains).
            <button type="button" onClick={() => selectedId != null && engineRef.current?.focusNode(selectedId)} disabled={selectedId == null}>
              Focus selected
            </button>
            */}
            <button type="button" onClick={() => startTour('journey')}>Explore evolution</button>
            {museum ? (
              <button type="button" onClick={exploreFreely}>Explore freely</button>
            ) : (
              <button type="button" onClick={enterMuseum}>Museum mode</button>
            )}
            <button type="button" className="quiet" onClick={() => setShowCredits(true)}>Sources &amp; credits</button>
          </div>
        )}
      </header>

      {status === 'loading' && <p className="world-status">Growing the tree…</p>}
      {status === 'error' && (
        <p className="world-status world-error" role="alert">
          Could not reach the data API at {API_BASE_URL}. {error}
        </p>
      )}

      <div className={`world-stage${panelOpen ? ' panel-open' : ''}${museumIntro ? ' intro' : ''}`}>
        {/* The engine owns this element (canvas + label layer); React owns the overlays. */}
        <div className="world-host" ref={containerRef} />
        {status === 'ready' && world && (
          <>
            <ScaleTrail world={world} scale={scale} />
            <div className="world-key">
              <p className="world-encoding">
                <strong>Height</strong> is time: the deepest branches are the oldest. <strong>Angle</strong> follows the
                branching order. Distance across the scene is not genetic distance.
              </p>
              <Key timeScaled startOpen={false} help="Drag to orbit · right-drag to pan · scroll to zoom · click a family or branch point" />
            </div>
            {pickingCompare && <p className="world-hint">Choose a second family or clade to compare with. Click it in the tree or search for it.</p>}
            {hover && hover.id !== selectedId && !tour && (
              <DiscoveryChip world={world} hover={hover} museum={museum} stageWidth={window.innerWidth} />
            )}
            {selectedId != null && !tour && compareId == null && (
              <SelectionCard
                key={selectedId}
                world={world}
                id={selectedId}
                museum={museum}
                onSelect={select}
                onFollow={followLineage}
                onCompare={() => setPickingCompare(true)}
                onFocus={() => engineRef.current?.focusNode(selectedId)}
                onClose={() => select(null)}
              />
            )}
            {selectedId != null && compareId != null && (
              <ComparePanel world={world} idA={selectedId} idB={compareId} onSelect={select} onEnd={() => setCompareId(null)} />
            )}
            {stop && (
              <TourBar
                label={tourLabel}
                caption={stop.caption}
                index={tour.index}
                total={tourStops[tour.kind].length}
                paused={tour.paused}
                onPrev={() => goToStop(tour.kind, tour.index - 1)}
                onNext={() => goToStop(tour.kind, tour.index + 1)}
                onPause={() => setTour({ ...tour, paused: !tour.paused })}
                onExit={exitTour}
              />
            )}
            {follow && !tour && <FollowBar world={world} follow={follow} onExit={endFollow} />}
            {museumIntro && <MuseumIntro world={world} onTour={() => startTour('museum')} onFree={exploreFreely} />}
          </>
        )}
      </div>
      {showCredits && <Credits onClose={() => setShowCredits(false)} />}
    </div>
  )
}
