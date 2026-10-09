// The 3D "Tree of Life" model: positions and relationships derived entirely
// from the phylogeny API (the same data as the 2D page).
//
// Encoding (what space means):
//   height       time: a node sits at its age, so the root is at the bottom and
//                the living families form the top layer. Extinct groups end at
//                their last fossil. This is the only axis with a quantity on it.
//   angle        branching order: every clade owns a contiguous sector, so close
//                relatives stand side by side.
//   distance     from the central axis: topological depth (tips on the rim).
// Straight-line distance between two points in the scene is NOT genetic
// distance; relationships are read from the branches.

import * as d3 from 'd3'
import { formatAge } from '../phylogenyLayout.js'
import { majorClade } from '../phylogenyStyle.js'
import {
  PLAIN_NAMES, capitalise, cladeStory, familyStory, list, relativesPhrase, relativesWord, speciesCountLine, whenPhrase,
} from '../phylo/narrative.js'

export const WORLD = { radius: 150, height: 300, gap: 0.08 }

// Plain-language names for clades that exist in the data (only these get
// exhibit labels); shared with the 2D page.
export const EXHIBIT_NAMES = PLAIN_NAMES

// Stops for the "Explore evolution" journey and the museum tour. Only nodes
// present in the data are used; captions are generated from the data.
const JOURNEY = [
  'Squamata', 'Gekkota', 'Scinciformata', 'Lacertoidea', 'Amphisbaenia', 'Toxicofera',
  'Iguania', 'Anguimorpha', 'Serpentes', 'Elapoidea',
]
const MUSEUM_TOUR = [
  'Sphenodontidae', 'Dibamidae', 'Gekkonidae', 'Scincidae', 'Lacertidae', 'Amphisbaenidae',
  'Chamaeleonidae', 'Varanidae', 'Pythonidae', 'Viperidae', 'Elapidae',
]

function seeded(id, salt) {
  const x = Math.sin(id * 12.9898 + salt * 78.233) * 43758.5453
  return x - Math.floor(x)
}

export function buildWorld(data) {
  const root = d3.hierarchy(data, (d) => (d.children && d.children.length ? d.children : null))
  root.count()
  d3.cluster().size([1, 1]).separation(() => 1)(root)

  const rootAge = root.data.age_ma ?? 1
  const heightOf = (age) => WORLD.height * (1 - (age ?? 0) / rootAge)
  const span = Math.PI * 2 * (1 - WORLD.gap)

  const nodes = new Map()
  root.each((node) => {
    const d = node.data
    const angle = node.x * span
    const r = WORLD.radius * node.y
    const h = heightOf(d.age_ma)
    nodes.set(d.id, {
      id: d.id,
      node,
      data: d,
      angle,
      r,
      pos: [r * Math.cos(angle), h, r * Math.sin(angle)],
      clade: majorClade(node),
      tip: !node.children,
    })
  })

  const links = []
  root.links().forEach(({ source, target }) => {
    const parent = nodes.get(source.data.id)
    const child = nodes.get(target.data.id)
    const d = target.data
    // A group with a first fossil after the split: a "ghost" lineage up to the
    // first fossil, then its fossil range.
    const firstH = d.kind === 'group' && d.first_appearance_ma != null ? heightOf(d.first_appearance_ma) : null
    const end = firstH != null && firstH > parent.pos[1] + 0.1 ? [child.pos[0], firstH, child.pos[2]] : child.pos
    links.push({
      id: d.id,
      from: parent.pos,
      to: end,
      ghost: end !== child.pos,
      weight: (target.value || 1) / (root.value || 1),
      clade: child.clade,
      sinuous: child.clade.name === 'Serpentes' ? 1.6 : 1,
      jitter: [seeded(d.id, 1) - 0.5, seeded(d.id, 2) - 0.5],
    })
  })

  const ranges = []
  const uncertainty = []
  for (const item of nodes.values()) {
    const d = item.data
    if (item.tip && d.kind === 'group' && d.first_appearance_ma != null) {
      ranges.push({ id: d.id, from: [item.pos[0], heightOf(d.first_appearance_ma), item.pos[2]], to: item.pos, clade: item.clade })
    }
    if (!item.tip && d.age_ci_low != null && d.age_ci_high != null) {
      uncertainty.push({
        id: d.id,
        from: [item.pos[0], heightOf(d.age_ci_high), item.pos[2]],
        to: [item.pos[0], heightOf(d.age_ci_low), item.pos[2]],
      })
    }
  }

  const byName = new Map()
  for (const item of nodes.values()) if (item.data.name) byName.set(item.data.name, item)

  return {
    root,
    rootAge,
    nodes,
    links,
    ranges,
    uncertainty,
    byName,
    heightOf,
    journey: JOURNEY.map((name) => byName.get(name)).filter(Boolean),
    museumTour: MUSEUM_TOUR.map((name) => byName.get(name)).filter(Boolean),
  }
}

export function exhibitName(data) {
  return EXHIBIT_NAMES[data.name] ?? null
}

function nameOf(node) {
  const plain = EXHIBIT_NAMES[node.data.name]
  return plain ? `${plain} (${node.data.name})` : node.data.name
}

// The highest named clades inside an unnamed subtree.
function topNamedClades(node) {
  const out = []
  for (const child of node.children ?? []) {
    if (!child.children) continue
    if (child.data.name) out.push(child)
    else out.push(...topNamedClades(child))
  }
  return out
}

// A readable description of a subtree: its name, else the named clades in it,
// else its families.
export function describe(node) {
  if (node.data.name) return nameOf(node)
  const named = topNamedClades(node)
  if (named.length) return named.slice(0, 3).map(nameOf).join(' and ') + (named.length > 3 ? ' and others' : '')
  const tips = node.leaves()
  return tips.slice(0, 3).map((t) => t.data.name).join(', ') + (tips.length > 3 ? ' and others' : '')
}

export function familyCount(node) {
  return node.leaves().filter((leaf) => leaf.data.kind === 'family').length
}

function namedAncestorAbove(node, minSize) {
  for (let current = node.parent; current; current = current.parent) {
    if (current.data.name && current.leaves().length >= minSize) return current
  }
  return null
}

// The Evolutionary Neighborhood of a selected node: an exploration aid built
// from the tree's nesting, not a measurement of distance.
export function neighbourhood(world, id) {
  const item = world.nodes.get(id)
  if (!item) return null
  const node = item.node
  const self = new Set(node.descendants().map((n) => n.data.id))
  const zone1 = new Set()
  for (const sister of node.parent ? node.parent.children.filter((c) => c !== node) : []) {
    sister.each((n) => zone1.add(n.data.id))
  }
  const sisterSize = node.parent ? node.parent.leaves().length : 0
  const broader = namedAncestorAbove(node.parent ?? node, sisterSize + 1) ?? node.parent?.parent ?? null
  const zone2 = new Set()
  broader?.each((n) => {
    if (!self.has(n.data.id) && !zone1.has(n.data.id)) zone2.add(n.data.id)
  })
  const squamata = world.byName.get('Squamata')?.node
  const outer = squamata && node.ancestors().includes(squamata) ? squamata : world.root
  const zone3 = new Set()
  outer.each((n) => {
    const nid = n.data.id
    if (!self.has(nid) && !zone1.has(nid) && !zone2.has(nid)) zone3.add(nid)
  })
  const lineageIds = new Set(node.ancestors().map((n) => n.data.id))
  return {
    node,
    self,
    zone1,
    zone2,
    zone3,
    lineage: lineageIds,
    sisters: node.parent ? node.parent.children.filter((c) => c !== node) : [],
    broader,
    outer,
  }
}

export function mrca(a, b) {
  const above = new Set(b.ancestors())
  return a.ancestors().find((n) => above.has(n)) ?? null
}

// Shared evolutionary context of two selected nodes.
export function comparison(world, idA, idB) {
  const a = world.nodes.get(idA)?.node
  const b = world.nodes.get(idB)?.node
  if (!a || !b) return null
  const shared = mrca(a, b)
  const named = shared && (shared.data.name ? shared : shared.ancestors().find((n) => n.data.name))
  const pathIds = new Set()
  for (const end of [a, b]) {
    for (let current = end; current && current !== shared; current = current.parent) pathIds.add(current.data.id)
  }
  if (shared) pathIds.add(shared.data.id)
  const cladeIds = new Set(named ? named.descendants().map((n) => n.data.id) : [])
  return { a, b, shared, named, pathIds, cladeIds }
}

// The splits met when following a node back to the root.
export function lineageSteps(world, id) {
  const node = world.nodes.get(id)?.node
  if (!node) return []
  return node
    .ancestors()
    .slice(1)
    .filter((step) => step.data.name || step.children.length > 1)
    .map((step) => ({
      id: step.data.id,
      title: step.data.name || 'Unnamed split',
      age: step.data.age_ma,
      parts: step.children.map((child) => describe(child)),
    }))
}

// A caption for a clade stop, from the data only.
export function cladeCaption(node) {
  const d = node.data
  return { title: EXHIBIT_NAMES[d.name] ?? d.name, subtitle: EXHIBIT_NAMES[d.name] ? d.name : null, lines: cladeStory(node) }
}

// The one fact shown on a specimen plaque: who it is closest to, and when they
// parted, derived from the tree.
export function specimenFact(node) {
  const sisters = node.parent ? node.parent.children.filter((c) => c !== node) : []
  if (!sisters.length) return null
  const age = node.parent.data.age_ma
  const when = age != null ? ` The two lineages parted about ${formatAge(age)} million years ago, ${whenPhrase(age, node)}.` : ''
  return `${capitalise(`its ${relativesWord(sisters)}`)} are ${list(sisters.map(relativesPhrase))}.${when}`
}

export function familyCaption(node) {
  const d = node.data
  const species = d.representative_species
  const lines = [speciesCountLine(d), ...familyStory(node)].filter(Boolean)
  return {
    title: d.name,
    subtitle: species ? `${species.common_name ? `${species.common_name} · ` : ''}${species.scientific_name}` : null,
    lines,
  }
}

// What to emphasise, as levels per node id (4 strongest .. 0 faint):
//   one selection  -> 4 itself, 3 its lineage and closest relatives,
//                     2 its broader clade, 1 the rest of Squamata, 0 the rest
//   two selections -> 4 both and the paths to their last shared ancestor,
//                     2 the smallest named clade holding both, 1 Squamata
//   hover only     -> a light lift of the node, its lineage and relatives
export function emphasisFor(world, { selectedId, compareId, hoverId }) {
  if (selectedId != null && compareId != null) {
    const c = comparison(world, selectedId, compareId)
    if (!c) return null
    const levels = new Map()
    const squamata = world.byName.get('Squamata')?.node
    const outer = squamata && [c.a, c.b].every((n) => n.ancestors().includes(squamata)) ? squamata : world.root
    outer.each((n) => levels.set(n.data.id, 1))
    c.cladeIds.forEach((id) => levels.set(id, 2))
    c.pathIds.forEach((id) => levels.set(id, 4))
    for (const end of [c.a, c.b]) end.each((n) => levels.set(n.data.id, 4))
    const pathTo = (end) => {
      const ids = []
      for (let current = end; current && current !== c.shared; current = current.parent) ids.push(current.data.id)
      return ids
    }
    return {
      levels, accent: c.pathIds, dimOthers: true, forced: [c.a.data.id, c.b.data.id],
      pulsePaths: [pathTo(c.a), pathTo(c.b)], connections: null,
    }
  }
  if (selectedId != null) {
    const n = neighbourhood(world, selectedId)
    if (!n) return null
    const levels = new Map()
    n.zone3.forEach((id) => levels.set(id, 1))
    n.zone2.forEach((id) => levels.set(id, 2))
    n.zone1.forEach((id) => levels.set(id, 3))
    n.lineage.forEach((id) => levels.set(id, 3))
    n.self.forEach((id) => levels.set(id, 4))
    const relativeTips = n.sisters.flatMap((s) => s.leaves().map((leaf) => leaf.data.id))
    const pulse = n.node.ancestors().filter((a) => a.parent).map((a) => a.data.id)
    return {
      levels,
      accent: new Set([...n.lineage, ...n.self]),
      dimOthers: true,
      forced: [selectedId, ...relativeTips.slice(0, 6)],
      pulsePaths: [pulse],
      connections: n.node.children ? null : { from: selectedId, to: relativeTips.slice(0, 10) },
    }
  }
  if (hoverId != null) {
    const n = neighbourhood(world, hoverId)
    if (!n) return null
    const levels = new Map()
    n.zone1.forEach((id) => levels.set(id, 3))
    n.lineage.forEach((id) => levels.set(id, 3))
    n.self.forEach((id) => levels.set(id, 4))
    return { levels, accent: n.lineage, dimOthers: false, forced: [hoverId] }
  }
  return null
}

// "Zoom from life to tree": the context of what the camera is looking at.
export function scaleTrail(world, nearestId, distance) {
  const item = world.nodes.get(nearestId)
  if (!item) return { level: 'tree', trail: ['Reptiles'] }
  const named = item.node
    .ancestors()
    .reverse()
    .filter((n) => EXHIBIT_NAMES[n.data.name])
    .map((n) => EXHIBIT_NAMES[n.data.name])
  const species = item.data.representative_species
  if (distance > 430) return { level: 'tree', trail: ['Reptiles'] }
  if (distance > 200) return { level: 'lineages', trail: named }
  if (distance > 85) return { level: 'families', trail: [...named, item.data.name] }
  return {
    level: 'species',
    trail: [...named, item.data.name, species?.common_name || species?.scientific_name].filter(Boolean),
  }
}

// Search families, species (common or scientific name) and named clades.
export function searchWorld(world, query) {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const results = []
  for (const item of world.nodes.values()) {
    const d = item.data
    const species = d.representative_species
    const fields = [d.name, EXHIBIT_NAMES[d.name], species?.scientific_name, species?.common_name].filter(Boolean)
    const hit = fields.find((f) => f.toLowerCase().includes(q))
    if (!hit) continue
    results.push({
      id: d.id,
      label: d.name || hit,
      detail: item.tip ? species?.common_name || species?.scientific_name || (d.extinct ? 'extinct group' : '') : 'clade',
      rank: d.name?.toLowerCase().startsWith(q) ? 0 : 1,
    })
  }
  return results.sort((a, b) => a.rank - b.rank || a.label.localeCompare(b.label)).slice(0, 12)
}
