import * as d3 from 'd3'
import { INK, majorClade } from './phylogenyStyle.js'

export const ROW = 26
// left leaves room for the root's name, which sits left of its node.
export const MARGIN = { top: 92, right: 260, bottom: 56, left: 84 }
const MIN_INNER_WIDTH = 640

// Wrap the API tree once: hierarchy, lookup by id, colour per node.
export function buildModel(data) {
  const root = d3.hierarchy(data, (d) => (d.children && d.children.length ? d.children : null))
  const byId = new Map()
  const color = new Map()
  root.eachAfter((node) => {
    byId.set(node.data.id, node)
    if (!node.children) {
      color.set(node.data.id, majorClade(node).color)
      return
    }
    // A branch takes its clade's colour only if everything below shares it.
    const colors = new Set(node.children.map((child) => color.get(child.data.id)))
    color.set(node.data.id, colors.size === 1 ? [...colors][0] : INK.mixedBranch)
  })
  root.count() // node.value = number of tips below: drives branch weight
  const leaves = root.leaves()
  return { root, byId, color, leaves, events: timelineEvents(root) }
}

// One curved branch: it leaves the parent vertically and bends smoothly into
// the horizontal, so the split still sits exactly at the parent's position
// (its age, in the time view). Longer drops sweep more widely.
function branchPath(px, py, cx, cy) {
  const drop = Math.abs(cy - py)
  const sweep = Math.min(Math.max(drop * 0.55, 10), 48, Math.max(cx - px, 0))
  return `M${px},${py}C${px},${cy} ${px},${cy} ${px + sweep},${cy}L${cx},${cy}`
}

// Screen positions for one view. `mode` is 'time' or 'branching'. Vertical
// positions come from the tree layout and are the same in both views, so
// switching views only moves things sideways.
export function layoutTree(model, width, mode) {
  const { root, leaves } = model
  const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, MIN_INNER_WIDTH)
  const innerHeight = Math.max(leaves.length - 1, 1) * ROW
  d3.cluster().size([innerHeight, innerWidth]).separation(() => 1)(root)

  const rootAge = root.data.age_ma ?? 0
  const scale = d3.scaleLinear().domain([rootAge, 0]).range([0, innerWidth])
  const xOf = (node) => (mode === 'time' ? scale(node.data.age_ma ?? 0) : node.y)

  const positions = new Map()
  root.each((node) => {
    const d = node.data
    const pos = { x: xOf(node), y: node.x }
    if (mode === 'time' && !node.children && d.kind === 'group') {
      // A collapsed group: a solid bar for its fossil range (to today if alive),
      // reached by a dashed "ghost lineage" from where it split off.
      const start = d.first_appearance_ma ?? node.parent?.data.age_ma ?? d.age_ma
      pos.barStart = scale(start)
      pos.barEnd = scale(d.age_ma ?? 0)
    }
    positions.set(d.id, pos)
  })

  const total = root.value || 1
  const links = root.links().map(({ source, target }) => {
    const from = positions.get(source.data.id)
    const to = positions.get(target.data.id)
    const endX = to.barStart ?? to.x
    return {
      id: target.data.id,
      d: branchPath(from.x, from.y, endX, to.y),
      ghost: to.barStart !== undefined && Math.abs(endX - from.x) > 0.5,
      // Heavier strokes for lineages that carry more of the tree.
      width: 0.8 + 2.6 * Math.sqrt((target.value || 1) / total),
    }
  })

  return {
    width: innerWidth + MARGIN.left + MARGIN.right,
    height: innerHeight + MARGIN.top + MARGIN.bottom,
    innerWidth,
    innerHeight,
    scale: mode === 'time' ? scale : null,
    positions,
    links,
  }
}

export function formatAge(age) {
  if (age == null) return '—'
  if (age === 0) return 'today'
  return age >= 100 ? `${Math.round(age)}` : `${Number(age.toFixed(1))}`
}

// Ancestors of a node (including itself), as a Set of ids, for path highlights.
export function lineage(node) {
  const ids = new Set()
  for (let current = node; current; current = current.parent) ids.add(current.data.id)
  return ids
}

// Ancestors from the node up to the root, nearest first (the trail to trace).
export function lineageTrail(node) {
  const trail = []
  for (let current = node; current; current = current.parent) trail.push(current)
  return trail
}

// Closest relatives: everything on the other side of the node's nearest split.
export function closestRelatives(node) {
  if (!node.parent) return []
  return node.parent.children.filter((child) => child !== node)
}

// Ids of the node's closest relatives' tips (to illuminate them).
export function relativeTipIds(node) {
  const ids = new Set()
  for (const sister of closestRelatives(node)) {
    for (const leaf of sister.leaves()) ids.add(leaf.data.id)
  }
  return ids
}

// The neighbourhood "Explore relatives" shows: two splits up from a tip (or
// the clade itself), never the whole tree.
export function neighbourhood(node) {
  if (node.children) return node
  return node.parent?.parent ?? node.parent ?? node
}

// Bounding box (tree coordinates) of a subtree, with room for tip labels.
export function subtreeBox(subtree, positions) {
  let x0 = Infinity
  let x1 = -Infinity
  let y0 = Infinity
  let y1 = -Infinity
  subtree.each((node) => {
    const pos = positions.get(node.data.id)
    if (!pos) return
    x0 = Math.min(x0, pos.barStart ?? pos.x, pos.x)
    x1 = Math.max(x1, pos.barEnd ?? pos.x, pos.x)
    y0 = Math.min(y0, pos.y)
    y1 = Math.max(y1, pos.y)
  })
  return { x0, x1: x1 + 210, y0: y0 - ROW, y1: y1 + ROW }
}

// Moments the time lens can narrate, all derived from the data: named common
// ancestors, first and last fossils of groups, and the present.
function timelineEvents(root) {
  const events = []
  const lastByAge = new Map()
  root.each((node) => {
    const d = node.data
    if (node.children && d.name && d.age_ma != null) {
      events.push({ age: d.age_ma, id: d.id, title: d.name, text: 'last common ancestor' })
    }
    if (!node.children && d.kind === 'group' && d.first_appearance_ma != null) {
      events.push({
        age: d.first_appearance_ma, id: d.id, title: d.name,
        text: d.extinct ? 'first fossils' : 'oldest fossils (still living today)',
      })
    }
    if (!node.children && d.extinct && d.last_appearance_ma != null) {
      const names = lastByAge.get(d.last_appearance_ma) ?? []
      names.push(d.name)
      lastByAge.set(d.last_appearance_ma, names)
    }
  })
  for (const [age, names] of lastByAge) {
    events.push({ age, id: null, title: names.join(', '), text: 'last fossils' })
  }
  const families = root.leaves().filter((leaf) => leaf.data.kind === 'family')
  const livingGroups = root.leaves().filter((leaf) => leaf.data.kind === 'group' && !leaf.data.extinct)
  const groups = livingGroups.map((leaf) => leaf.data.name).join(', ')
  events.push({
    age: 0, id: null, title: 'The present',
    text: `${families.length} living reptile families${groups ? `, and ${groups}` : ''}`,
  })
  return events.sort((a, b) => b.age - a.age)
}
