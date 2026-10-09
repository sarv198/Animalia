// Readable descriptions of families, clades and relationships, written from
// the data only: ages and relatives from the tree, species counts from The
// Reptile Database, the geological time scale (ICS chart, 2023), and fossil
// dates for dinosaurs from the tree's own curated backbone. Shared by the 2D
// and 3D pages. No sentence states anything the data does not hold.
import { formatAge } from '../phylogenyLayout.js'

// Plain-English names for well-known clades (labels only; the relationships
// come from the data).
export const PLAIN_NAMES = {
  Reptilia: 'Reptiles',
  Lepidosauria: 'Lepidosaurs',
  Squamata: 'Squamates',
  Serpentes: 'Snakes',
  Iguania: 'Iguanians',
  Anguimorpha: 'Anguimorphs',
  Lacertoidea: 'Lacertoids',
  Amphisbaenia: 'Amphisbaenians',
  Scinciformata: 'Skinks & allies',
  Gekkota: 'Geckos',
  Testudines: 'Turtles',
  Crocodylia: 'Crocodilians',
  Archosauria: 'Archosaurs',
  Dinosauria: 'Dinosaurs',
  Aves: 'Birds',
}

// Subdivisions of the geological time scale (ICS International
// Chronostratigraphic Chart), oldest first: [name, start, end] in Ma.
const INTERVALS = [
  ['Early Carboniferous', 358.9, 323.4],
  ['Late Carboniferous', 323.4, 298.9],
  ['Early Permian', 298.9, 273.01],
  ['Middle Permian', 273.01, 259.51],
  ['Late Permian', 259.51, 251.9],
  ['Early Triassic', 251.9, 247.2],
  ['Middle Triassic', 247.2, 237],
  ['Late Triassic', 237, 201.4],
  ['Early Jurassic', 201.4, 174.7],
  ['Middle Jurassic', 174.7, 161.5],
  ['Late Jurassic', 161.5, 145],
  ['Early Cretaceous', 145, 100.5],
  ['Late Cretaceous', 100.5, 66],
  ['Paleocene', 66, 56],
  ['Eocene', 56, 33.9],
  ['Oligocene', 33.9, 23.03],
  ['Miocene', 23.03, 5.333],
  ['Pliocene', 5.333, 2.58],
  ['Pleistocene', 2.58, 0.0117],
  ['Holocene', 0.0117, 0],
]

export function intervalAt(age) {
  if (age == null) return null
  return INTERVALS.find(([, start, end]) => age <= start && age >= end)?.[0] ?? null
}

const indexes = new WeakMap()
function byName(root) {
  if (!indexes.has(root)) {
    const map = new Map()
    root.each((n) => n.data.name && map.set(n.data.name, n))
    indexes.set(root, map)
  }
  return indexes.get(root)
}

export function findNamed(node, name) {
  return byName(node.ancestors().at(-1)).get(name) ?? null
}

// When the dinosaurs appear and when the non-avian ones vanish, read from the
// tree: the age of Dinosauria's common ancestor and the last fossils of the
// extinct dinosaur groups.
function dinosaurSpan(node) {
  const dinosaurs = findNamed(node, 'Dinosauria')
  if (!dinosaurs?.data.age_ma) return null
  const ends = dinosaurs.descendants().map((n) => n.data.last_appearance_ma).filter((v) => v != null)
  return { start: dinosaurs.data.age_ma, end: ends.length ? Math.max(...ends) : null }
}

// "in the Middle Jurassic, in the age of the dinosaurs"
export function whenPhrase(age, node) {
  if (age == null) return ''
  const interval = intervalAt(age)
  let phrase = interval ? `in the ${interval}` : ''
  const dinos = node ? dinosaurSpan(node) : null
  if (dinos) {
    if (age > dinos.start) phrase += ', before the first dinosaurs'
    else if (dinos.end != null && age > dinos.end) phrase += ', in the age of the dinosaurs'
    else if (dinos.end != null && dinos.end - age <= 10) {
      phrase += `, ${age >= dinos.end - 1 ? 'right after' : 'within ten million years of'} the extinction that ended the non-avian dinosaurs`
    }
  }
  return phrase
}

export function plainName(name) {
  return PLAIN_NAMES[name] ?? null
}

// "snakes (Serpentes)" / "Lanthanotidae, home of the earless monitor lizard"
export function nameOf(node, { lower = false } = {}) {
  const d = node.data
  if (!d.name) return null
  const plain = PLAIN_NAMES[d.name]
  if (plain) return `${lower ? plain.toLowerCase() : plain} (${d.name})`
  const animal = d.representative_species?.common_name
  return animal ? `${d.name} (the ${animal} family)` : d.name
}

function familyTotal(node) {
  return node.leaves().filter((leaf) => leaf.data.kind === 'family').length
}

function topNamed(node) {
  const out = []
  const visit = (n) => {
    if (n.data.name) out.push(n)
    else (n.children || []).forEach(visit)
  }
  ;(node.children || []).forEach(visit)
  return out
}

// A phrase for whoever sits on the other side of a split.
export function relativesPhrase(node) {
  if (!node.children) return nameOf(node) ?? 'an unnamed lineage'
  if (node.data.name) return `the ${familyTotal(node)} families of ${nameOf(node, { lower: true })}`
  const named = topNamed(node)
  const shown = (named.length ? named : node.leaves()).slice(0, 3).map((n) => nameOf(n, { lower: true }) ?? n.data.name)
  const total = familyTotal(node)
  return `a group of ${total} ${total === 1 ? 'family' : 'families'} including ${list(shown)}`
}

export function list(items) {
  if (items.length <= 1) return items[0] ?? ''
  return `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`
}

// "closest living relatives" only when every one of them is living.
export function relativesWord(sisters) {
  const extinct = sisters.some((sister) => sister.leaves().some((leaf) => leaf.data.extinct))
  return extinct ? 'closest relatives' : 'closest living relatives'
}

function sistersOf(node) {
  return node.parent ? node.parent.children.filter((c) => c !== node) : []
}

function years(age) {
  return `${formatAge(age)} million years`
}

// A family, told through its animal and its history.
// "Bipedidae family contains 3 living species." (The Reptile Database count.)
export function speciesCountLine(data) {
  if (!data.species_count) return null
  return `${data.name} family contains ${data.species_count.toLocaleString()} living species.`
}

export function familyStory(node) {
  const d = node.data
  const lines = []
  const sisters = sistersOf(node)
  if (node.parent && d.stem_age_ma != null) {
    const when = whenPhrase(d.stem_age_ma, node)
    lines.push(
      `Its lineage has been on its own path for about ${years(d.stem_age_ma)}. It split from its ${relativesWord(sisters)}, ${list(sisters.map(relativesPhrase))}, ${when}.`,
    )
  }
  return lines
}

// A clade: what it holds, when its ancestor lived, who its neighbours are.
export function cladeStory(node) {
  const d = node.data
  const lines = []
  const total = familyTotal(node)
  const label = nameOf(node) ?? 'This unnamed branch'
  if (d.age_ma != null) {
    lines.push(
      `${label} began with a single ancestor that lived about ${years(d.age_ma)} ago, ${whenPhrase(d.age_ma, node)}. Its descendants make up ${total} ${total === 1 ? 'family' : 'families'} in this tree.`,
    )
  } else {
    lines.push(`${label} holds ${total} ${total === 1 ? 'family' : 'families'} in this tree.`)
  }
  const sisters = sistersOf(node)
  if (sisters.length) lines.push(`${capitalise(`its ${relativesWord(sisters)}`)} are ${list(sisters.map(relativesPhrase))}.`)
  return lines
}

function animalOf(node) {
  const species = node.data.representative_species
  if (species?.common_name) return `the ${species.common_name}`
  return nameOf(node, { lower: true }) ?? 'this lineage'
}

function pathBetween(end, shared) {
  const steps = []
  for (let current = end.parent; current && current !== shared; current = current.parent) {
    if (current.data.name) steps.push(current)
  }
  return steps
}

// Two lineages and the ancestor they share.
export function pairStory(a, b, shared) {
  if (!shared) return []
  const lines = []
  const sharedName = shared.data.name ? nameOf(shared, { lower: true }) : null
  const age = shared.data.age_ma
  lines.push(
    `${capitalise(animalOf(a))} and ${animalOf(b)} last shared an ancestor about ${years(age)} ago, ${whenPhrase(age, shared)}.` +
      (sharedName ? ` That ancestor gave rise to ${sharedName}, ${familyTotal(shared)} families in this tree.` : ''),
  )
  const pathA = pathBetween(a, shared)
  const pathB = pathBetween(b, shared)
  const route = (end, path) => (path.length
    ? `${animalOf(end)}'s line passed through ${list(path.slice().reverse().map((n) => nameOf(n, { lower: true })))}`
    : `${animalOf(end)}'s line branched off directly`)
  lines.push(`Since then they have evolved apart: ${route(a, pathA)}, while ${route(b, pathB)}.`)
  return lines
}

export function capitalise(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text
}

// "Split ... in the Early Cretaceous" for a lineage step.
export function stepWhen(age, node) {
  if (age == null) return ''
  return `about ${years(age)} ago, ${whenPhrase(age, node)}`
}
