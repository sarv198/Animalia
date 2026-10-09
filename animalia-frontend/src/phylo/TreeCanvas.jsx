import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import {
  MARGIN,
  ROW,
  layoutTree,
  lineage,
  lineageTrail,
  neighbourhood,
  relativeTipIds,
  subtreeBox,
} from '../phylogenyLayout.js'
import { INK, MAJOR_DIVISIONS, PERIODS, STATUS, periodAt } from '../phylogenyStyle.js'
import { displayName } from './labels.js'

const PANEL_WIDTH = 440
const MIN_LAYOUT_WIDTH = 980
const KEEP_VISIBLE = 180 // px of the tree that always stays on screen
const TIP_LABEL_ROOM = 150 // family names to the right of the tips
const TRACE_STEP_S = 0.16

// Opacity for living tips while the time lens approaches the present.
function presentFade(lensAge) {
  if (lensAge == null || lensAge <= 0) return 1
  return 0
}

export default function TreeCanvas({
  ref,
  model,
  view,
  hoverId,
  selectedId,
  focusMode,
  traceToken,
  lensAge,
  onHover,
  onSelect,
  onLensChange,
}) {
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [transform, setTransform] = useState(d3.zoomIdentity)
  const svgRef = useRef(null)
  const zoomRef = useRef(null)

  const stageRef = useCallback((stage) => {
    if (!stage) return undefined
    const measure = () => setSize({ width: stage.clientWidth, height: stage.clientHeight })
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(stage)
    return () => observer.disconnect()
  }, [])

  const geometry = useMemo(
    () => (size.width > 0 ? layoutTree(model, Math.max(size.width, MIN_LAYOUT_WIDTH), view) : null),
    [model, size.width, view],
  )
  const ready = geometry != null

  // Zoom and pan. The wheel pans (like a page); ctrl/cmd + wheel or a pinch zooms.
  // Panning stops before the tree leaves the screen: part of it (not just the
  // empty margin or a blank corner of its box) always stays in view, at any zoom.
  useEffect(() => {
    const svg = svgRef.current
    if (!ready || !svg || !geometry) return undefined
    const tree = {
      x0: MARGIN.left,
      x1: geometry.width - MARGIN.right + TIP_LABEL_ROOM,
      y0: MARGIN.top,
      y1: geometry.height - MARGIN.bottom,
    }
    // Points along every branch, in the zoomed layer's coordinates.
    const points = []
    for (const { source, target } of model.root.links()) {
      const a = geometry.positions.get(source.data.id)
      const b = geometry.positions.get(target.data.id)
      const endX = b.barEnd ?? b.x
      for (let i = 0; i <= 4; i++) {
        points.push([MARGIN.left + a.x + ((endX - a.x) * i) / 4, MARGIN.top + b.y])
        points.push([MARGIN.left + a.x, MARGIN.top + a.y + ((b.y - a.y) * i) / 4])
      }
    }
    const showsTree = (t, [[vx0, vy0], [vx1, vy1]]) => points.some(([px, py]) => {
      const x = t.applyX(px)
      const y = t.applyY(py)
      return x > vx0 + 30 && x < vx1 - 30 && y > vy0 + 30 && y < vy1 - 30
    })
    const clampToBox = (t, extent) => {
      const [[vx0, vy0], [vx1, vy1]] = extent
      const keepX = Math.min(KEEP_VISIBLE, (vx1 - vx0) * 0.3)
      const keepY = Math.min(KEEP_VISIBLE, (vy1 - vy0) * 0.3)
      let { x, y } = t
      const left = x + tree.x0 * t.k
      const right = x + tree.x1 * t.k
      const top = y + tree.y0 * t.k
      const bottom = y + tree.y1 * t.k
      if (right < vx0 + keepX) x += vx0 + keepX - right
      else if (left > vx1 - keepX) x -= left - (vx1 - keepX)
      if (bottom < vy0 + keepY) y += vy0 + keepY - bottom
      else if (top > vy1 - keepY) y -= top - (vy1 - keepY)
      return x === t.x && y === t.y ? t : d3.zoomIdentity.translate(x, y).scale(t.k)
    }
    // A move that would leave only blank space on screen goes only as far as
    // it can while some of the tree is still showing.
    const constrain = (t, extent) => {
      const boxed = clampToBox(t, extent)
      if (showsTree(boxed, extent)) return boxed
      const current = d3.zoomTransform(svg)
      if (!showsTree(current, extent)) return boxed
      const at = (f) => d3.zoomIdentity
        .translate(current.x + (boxed.x - current.x) * f, current.y + (boxed.y - current.y) * f)
        .scale(current.k + (boxed.k - current.k) * f)
      let lo = 0
      let hi = 1
      for (let i = 0; i < 10; i++) {
        const mid = (lo + hi) / 2
        if (showsTree(at(mid), extent)) lo = mid
        else hi = mid
      }
      return at(lo)
    }
    const zoom = d3
      .zoom()
      .scaleExtent([0.2, 4])
      .constrain(constrain)
      .filter((event) => (event.type === 'wheel' ? event.ctrlKey || event.metaKey : !event.button))
      .on('zoom', (event) => setTransform(event.transform))
    const selection = d3.select(svg).call(zoom).on('dblclick.zoom', null)
    zoom.translateBy(selection, 0, 0) // pull the current view back in bounds (e.g. after a layout change)
    zoomRef.current = { zoom, selection }
    const onWheel = (event) => {
      if (event.ctrlKey || event.metaKey) return
      event.preventDefault()
      const k = d3.zoomTransform(svg).k
      zoom.translateBy(selection, -event.deltaX / k, -event.deltaY / k)
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      svg.removeEventListener('wheel', onWheel)
      selection.on('.zoom', null)
      zoomRef.current = null
    }
  }, [ready, geometry, model])

  const animateTo = useCallback(
    (box, { maxScale = 1.6, leaveRoomForPanel = false } = {}) => {
      const zoomer = zoomRef.current
      if (!zoomer || !geometry) return
      const roomRight = leaveRoomForPanel && size.width > 960 ? PANEL_WIDTH : 0
      const width = Math.max(size.width - roomRight, 200)
      const boxWidth = box.x1 - box.x0
      const boxHeight = box.y1 - box.y0
      const k = Math.max(0.2, Math.min(maxScale, (width - 40) / boxWidth, (size.height - 40) / boxHeight))
      const tx = (width - boxWidth * k) / 2 - (box.x0 + MARGIN.left) * k
      const ty = (size.height - boxHeight * k) / 2 - (box.y0 + MARGIN.top) * k
      zoomer.selection
        .transition()
        .duration(950)
        .ease(d3.easeCubicInOut)
        .call(zoomer.zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(k))
    },
    [geometry, size],
  )

  useImperativeHandle(
    ref,
    () => ({
      showWholeTree() {
        if (!geometry) return
        animateTo(
          { x0: -MARGIN.left + 10, x1: geometry.width - MARGIN.left, y0: -MARGIN.top + 10, y1: geometry.innerHeight + 30 },
          { maxScale: 1 },
        )
      },
      focusOn(node, { wide = false } = {}) {
        if (!geometry) return
        const target = wide ? neighbourhood(node) : node.children ? node : neighbourhood(node)
        animateTo(subtreeBox(target, geometry.positions), { leaveRoomForPanel: true })
      },
      // Fit the whole path from the root to this node, to follow it backwards.
      focusLineage(node) {
        if (!geometry) return
        const ys = lineageTrail(node).map((step) => geometry.positions.get(step.data.id).y)
        const tip = geometry.positions.get(node.data.id)
        animateTo(
          { x0: -20, x1: (tip.barEnd ?? tip.x) + 210, y0: Math.min(...ys) - ROW, y1: Math.max(...ys) + ROW },
          { leaveRoomForPanel: true, maxScale: 1.2 },
        )
      },
    }),
    [animateTo, geometry],
  )

  const focusNode = model.byId.get(hoverId ?? selectedId) ?? null
  const highlight = useMemo(() => {
    if (!focusNode) return null
    const lit = lineage(focusNode)
    const near = new Set()
    if (focusMode === 'relatives' && hoverId == null) {
      neighbourhood(focusNode).each((node) => near.add(node.data.id))
    } else if (focusNode.children) {
      focusNode.each((node) => lit.add(node.data.id))
    } else {
      for (const id of relativeTipIds(focusNode)) {
        for (const node of lineageTrail(model.byId.get(id))) {
          if (node === focusNode.parent) break
          near.add(node.data.id)
        }
      }
    }
    return { lit, near }
  }, [focusNode, focusMode, hoverId, model])

  const traceOrder = useMemo(() => {
    const selected = model.byId.get(selectedId)
    if (!selected || traceToken === 0) return null
    const order = new Map()
    lineageTrail(selected).forEach((node, index) => order.set(node.data.id, index))
    return order
  }, [model, selectedId, traceToken])

  if (!geometry) return <div className="tree-stage" ref={stageRef} />

  const { positions, links, scale, innerWidth, innerHeight } = geometry
  const nodes = model.root.descendants()
  const k = transform.k
  const familyLabelOpacity = k < 0.45 ? 0 : k < 0.75 ? (k - 0.45) / 0.3 : 1
  const lensOn = scale && lensAge != null && lensAge > 0
  const lensX = lensOn ? scale(lensAge) : null
  const currentPeriod = lensOn ? periodAt(lensAge) : null
  const tone = (id) => {
    if (!highlight) return 'normal'
    if (highlight.lit.has(id)) return 'lit'
    if (highlight.near.has(id)) return 'near'
    return 'dim'
  }

  function hoverAt(event, id) {
    const box = svgRef.current.getBoundingClientRect()
    onHover({ id, x: event.clientX - box.left, y: event.clientY - box.top })
  }

  function startLensDrag(event) {
    event.stopPropagation()
    const svg = svgRef.current
    svg.setPointerCapture(event.pointerId)
    const move = (moveEvent) => {
      const box = svg.getBoundingClientRect()
      const [x] = transform.invert([moveEvent.clientX - box.left, moveEvent.clientY - box.top])
      const age = scale.invert(x - MARGIN.left)
      onLensChange(Math.min(Math.max(age, 0), scale.domain()[0]))
    }
    const up = () => {
      svg.removeEventListener('pointermove', move)
      svg.removeEventListener('pointerup', up)
    }
    svg.addEventListener('pointermove', move)
    svg.addEventListener('pointerup', up)
  }

  const treeLayer = (
    <>
      <g className="links" fill="none">
        {links.map((link) => {
          const state = tone(link.id)
          const order = traceOrder?.get(link.id)
          return (
            <path
              key={order != null ? `${link.id}-trace-${traceToken}` : link.id}
              d={link.d}
              className={`branch ${state}${order != null ? ' tracing' : ''}`}
              stroke={state === 'lit' ? INK.highlight : model.color.get(link.id)}
              strokeWidth={state === 'lit' ? link.width + 1.2 : link.width}
              strokeDasharray={link.ghost ? '3 5' : order != null ? '1 1' : undefined}
              pathLength={order != null && !link.ghost ? 1 : undefined}
              style={order != null ? { animationDelay: `${order * TRACE_STEP_S}s` } : undefined}
            />
          )
        })}
      </g>

      {scale && (
        <g className="ranges">
          {nodes.map((node) => {
            const d = node.data
            const pos = positions.get(d.id)
            if (pos.barStart !== undefined) {
              return (
                <line
                  key={`bar-${d.id}`}
                  x1={pos.barStart}
                  x2={pos.barEnd}
                  y1={pos.y}
                  y2={pos.y}
                  className={`range-bar ${tone(d.id)}`}
                  stroke={model.color.get(d.id)}
                />
              )
            }
            if (node.children && d.age_ci_low != null && d.age_ci_high != null) {
              return (
                <line
                  key={`ci-${d.id}`}
                  x1={scale(d.age_ci_high)}
                  x2={scale(d.age_ci_low)}
                  y1={pos.y}
                  y2={pos.y}
                  className={`ci-line ${tone(d.id)}`}
                />
              )
            }
            return null
          })}
        </g>
      )}

      <g className="clades">
        {nodes
          .filter((node) => node.children)
          .map((node) => {
            const d = node.data
            const pos = positions.get(d.id)
            const major = MAJOR_DIVISIONS.has(d.name)
            const order = traceOrder?.get(d.id)
            const fontSize = major ? 11.5 / Math.min(k, 1) : 10.5
            return (
              <g key={d.id} transform={`translate(${pos.x},${pos.y})`} className={`clade ${tone(d.id)}`}>
                <circle
                  r={major ? 4 : 2.4}
                  fill={model.color.get(d.id)}
                  className={major ? 'clade-dot major' : 'clade-dot'}
                />
                {d.name && (
                  <text
                    x={-7}
                    y={-7}
                    textAnchor="end"
                    fontSize={fontSize}
                    className={`${major ? 'clade-label major' : 'clade-label'}${order != null ? ' tracing-label' : ''}${d.id === selectedId ? ' selected' : ''}`}
                    style={order != null ? { animationDelay: `${order * TRACE_STEP_S}s` } : undefined}
                    opacity={!major && familyLabelOpacity === 0 ? 0 : undefined}
                  >
                    {d.name}
                  </text>
                )}
                <circle
                  r={10 / Math.min(k, 1)}
                  className="hit"
                  tabIndex={0}
                  role="button"
                  aria-label={`${displayName(d)}, details`}
                  onMouseMove={(event) => hoverAt(event, d.id)}
                  onClick={() => onSelect(d.id)}
                  onKeyDown={(event) => event.key === 'Enter' && onSelect(d.id)}
                />
              </g>
            )
          })}
      </g>
    </>
  )

  return (
    <div className="tree-stage" ref={stageRef}>
      <svg
        ref={svgRef}
        className="phylo-svg"
        width={size.width}
        height={size.height}
        role="img"
        aria-label="Phylogenetic tree of reptile families. Drag to pan, scroll to move, ctrl and scroll to zoom."
        onMouseLeave={() => onHover(null)}
      >
        <defs>
          <clipPath id="photo-clip" clipPathUnits="objectBoundingBox">
            <circle cx="0.5" cy="0.5" r="0.5" />
          </clipPath>
          {lensOn && (
            <>
              <linearGradient id="lens-fade" gradientUnits="userSpaceOnUse" x1={lensX - 90} x2={lensX} y1="0" y2="0">
                <stop offset="0" stopColor="#fff" stopOpacity="1" />
                <stop offset="1" stopColor="#fff" stopOpacity="0" />
              </linearGradient>
              <mask id="lens-mask" maskUnits="userSpaceOnUse" x={-MARGIN.left} y={-MARGIN.top} width={innerWidth + MARGIN.left + MARGIN.right} height={innerHeight + MARGIN.top + MARGIN.bottom}>
                <rect x={-MARGIN.left} y={-MARGIN.top} width={innerWidth + MARGIN.left + MARGIN.right} height={innerHeight + MARGIN.top + MARGIN.bottom} fill="url(#lens-fade)" />
              </mask>
            </>
          )}
        </defs>

        <g transform={transform.toString()}>
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {scale && (
              <g className="strata">
                {PERIODS.filter((p) => p.end < scale.domain()[0]).map((period) => {
                  const x0 = scale(Math.min(period.start, scale.domain()[0]))
                  const x1 = scale(period.end)
                  const current = currentPeriod?.name === period.name
                  return (
                    <g key={period.name}>
                      <rect x={x0} y={-MARGIN.top + 18} width={Math.max(x1 - x0, 0)} height={innerHeight + MARGIN.top + MARGIN.bottom - 30} fill={period.tone}>
                        <title>{`${period.name} (${period.start} to ${period.end} million years ago)`}</title>
                      </rect>
                      <line x1={x1} x2={x1} y1={-MARGIN.top + 18} y2={innerHeight + 30} className="stratum-edge" />
                      {(x1 - x0) * k > period.name.length * 8 + 16 && (
                        <text
                          x={(x0 + x1) / 2}
                          y={-58}
                          textAnchor="middle"
                          fontSize={11 / Math.min(k, 1)}
                          className={current ? 'period-label current' : 'period-label'}
                        >
                          {period.name}
                        </text>
                      )}
                    </g>
                  )
                })}
                {scale.ticks(Math.max(3, Math.round(8 * Math.min(k, 1)))).map((tick) => (
                  <g key={tick} transform={`translate(${scale(tick)},0)`}>
                    <line y1={-34} y2={innerHeight + 10} className="tick-line" />
                    <text y={-38} textAnchor="middle" className="tick-label" fontSize={10.5 / Math.min(k, 1)}>{tick}</text>
                    <text y={innerHeight + 28} textAnchor="middle" className="tick-label" fontSize={10.5 / Math.min(k, 1)}>{tick}</text>
                  </g>
                ))}
                <text x={innerWidth} y={-78} textAnchor="end" className="axis-title">
                  Millions of years ago
                </text>
                {model.events
                  .filter((event) => event.age > 0 && event.text !== 'last common ancestor')
                  .map((event) => (
                    <path
                      key={`${event.title}-${event.age}`}
                      d="M0,-4L4,0L0,4L-4,0Z"
                      transform={`translate(${scale(event.age)},-22)`}
                      className={lensOn && lensAge <= event.age ? 'event-mark passed' : 'event-mark'}
                    >
                      <title>{`${event.title}: ${event.text} (~${Math.round(event.age)} Ma)`}</title>
                    </path>
                  ))}
              </g>
            )}

            <g mask={lensOn ? 'url(#lens-mask)' : undefined}>{treeLayer}</g>

            <g className="tips">
              {nodes
                .filter((node) => !node.children)
                .map((node) => {
                  const d = node.data
                  const pos = positions.get(d.id)
                  const state = tone(d.id)
                  const isSelected = d.id === selectedId
                  const isFocus = d.id === (hoverId ?? selectedId)
                  const tipX = pos.barEnd ?? pos.x
                  const image = d.representative_species?.image
                  const showPhoto = isFocus && image
                  const flag = STATUS[d.placement_status]
                  let lensOpacity = presentFade(lensAge)
                  if (lensOn && d.kind === 'group' && d.first_appearance_ma != null && lensAge <= d.first_appearance_ma) {
                    lensOpacity = 1
                  }
                  const labelOpacity = Math.min(lensOpacity, state === 'dim' ? 0.32 : familyLabelOpacity || (isFocus ? 1 : 0))
                  return (
                    <g key={d.id} className={`tip ${state}${isSelected ? ' selected' : ''}`} style={{ opacity: lensOpacity }}>
                      {isSelected && (
                        <rect x={-MARGIN.left} y={pos.y - ROW / 2} width={innerWidth + MARGIN.left + MARGIN.right} height={ROW} className="row-selected" />
                      )}
                      <circle cx={tipX} cy={pos.y} r={isFocus ? 5 : 3.6} fill={model.color.get(d.id)} className="tip-dot" />
                      {showPhoto && (
                        // Outer group positions; inner group animates (a CSS
                        // transform on the same element would replace the position).
                        <g transform={`translate(${tipX + 22},${pos.y})`}>
                          <g className="tip-photo">
                            <circle r={19} className="tip-photo-ring" stroke={model.color.get(d.id)} />
                            <image
                              href={image.thumbnail_url || image.url}
                              x={-17}
                              y={-17}
                              width={34}
                              height={34}
                              preserveAspectRatio="xMidYMid slice"
                              clipPath="url(#photo-clip)"
                            />
                          </g>
                        </g>
                      )}
                      <text
                        x={tipX + (showPhoto ? 48 : 10)}
                        y={pos.y}
                        dy="0.32em"
                        className={`tip-label${isSelected ? ' selected' : ''}`}
                        opacity={labelOpacity}
                      >
                        {displayName(d)}
                        {flag && (
                          <tspan dx={6} fill={flag.color} className="tip-flag">
                            {flag.symbol}
                          </tspan>
                        )}
                      </text>
                      <rect
                        x={Math.min(pos.barStart ?? pos.x, pos.x) - 6}
                        y={pos.y - ROW / 2}
                        width={tipX - Math.min(pos.barStart ?? pos.x, pos.x) + 230}
                        height={ROW}
                        className="hit"
                        tabIndex={lensOpacity ? 0 : -1}
                        role="button"
                        aria-label={`${displayName(d)}, details`}
                        onMouseMove={(event) => hoverAt(event, d.id)}
                        onClick={() => onSelect(d.id)}
                        onKeyDown={(event) => event.key === 'Enter' && onSelect(d.id)}
                      />
                    </g>
                  )
                })}
            </g>

            {lensOn && (
              <g className="lens" transform={`translate(${lensX},0)`}>
                <line y1={-46} y2={innerHeight + 34} className="lens-line" />
                <g transform="translate(0,-46)" className="lens-handle" onPointerDown={startLensDrag}>
                  <circle r={9 / Math.min(k, 1)} />
                  <text y={-14 / Math.min(k, 1)} textAnchor="middle" fontSize={12 / Math.min(k, 1)}>
                    {`${Math.round(lensAge)} Ma`}
                  </text>
                </g>
              </g>
            )}
          </g>
        </g>
      </svg>
    </div>
  )
}
