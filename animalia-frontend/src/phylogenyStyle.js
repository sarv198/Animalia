// Visual language for the phylogeny: a natural-history exhibit palette.
//
// Major clades take eight earth-toned categorical slots in tree order (top to
// bottom), so neighbouring branches always get adjacent slots. The set was
// checked with the dataviz palette validator against the stage surface
// (#13120f): every check passes, worst adjacent colour-blind separation
// dE 8.9. Lineages outside these clades share a neutral stone ink. Labels and
// the key carry identity, never colour alone.

export const MAJOR_CLADES = [
  { name: 'Serpentes', label: 'Snakes', color: '#4d8fd6' },
  { name: 'Iguania', label: 'Iguanians', color: '#c86f45' },
  { name: 'Anguimorpha', label: 'Anguimorphs', color: '#239e82' },
  { name: 'Lacertoidea', label: 'Lacertoids & amphisbaenians', color: '#b58a22' },
  { name: 'Scinciformata', label: 'Skinks & allies', color: '#c4708c' },
  { name: 'Gekkota', label: 'Geckos', color: '#7d9a3f' },
  { name: 'Testudines', label: 'Turtles', color: '#8a7cdb' },
  { name: 'Archosauria', label: 'Archosaurs (crocodiles, dinosaurs, birds)', color: '#cf6a60' },
]

export const OTHER = {
  name: null,
  label: 'Other lineages (tuatara, Dibamidae, mesosaurs)',
  color: '#8d8677',
}

// Earth, bone and stone inks.
export const INK = {
  bone: '#ece6d6',
  limestone: '#c9c1ad',
  sandstone: '#a89d84',
  stone: '#7d7565',
  mixedBranch: '#6b6457',
  highlight: '#f4ecd8',
  amber: '#e2b65a',
}

// Reserved status colours: always shown with a symbol and words, never alone.
export const STATUS = {
  flagged: { color: '#e2a93b', symbol: '⚑', label: 'Placement flagged' },
  unknown: { color: '#9b937f', symbol: '?', label: 'Placement unknown' },
}

// Clades drawn as major evolutionary divisions (heavier labels and nodes).
export const MAJOR_DIVISIONS = new Set([
  'Reptilia', 'Sauria', 'Lepidosauria', 'Archelosauria', 'Archosauria', 'Squamata',
  'Testudines', 'Crocodylia', 'Avemetatarsalia', 'Dinosauria',
  ...MAJOR_CLADES.map((clade) => clade.name),
])

const BY_NAME = new Map(MAJOR_CLADES.map((clade) => [clade.name, clade]))

// The major clade a node belongs to: the nearest ancestor-or-self named in
// MAJOR_CLADES, else OTHER. `node` is a d3 hierarchy node.
export function majorClade(node) {
  for (let current = node; current; current = current.parent) {
    const hit = BY_NAME.get(current.data.name)
    if (hit) return hit
  }
  return OTHER
}

// Geological periods (ICS boundaries, Ma), oldest first, each with a stratum
// tone for the background layers.
export const PERIODS = [
  { name: 'Carboniferous', start: 358.9, end: 298.9, tone: '#1b1913' },
  { name: 'Permian', start: 298.9, end: 251.9, tone: '#1e1a14' },
  { name: 'Triassic', start: 251.9, end: 201.4, tone: '#1f1913' },
  { name: 'Jurassic', start: 201.4, end: 145.0, tone: '#191b15' },
  { name: 'Cretaceous', start: 145.0, end: 66.0, tone: '#1c1c16' },
  { name: 'Paleogene', start: 66.0, end: 23.03, tone: '#1e1b15' },
  { name: 'Neogene', start: 23.03, end: 2.58, tone: '#1b1a15' },
  { name: 'Quaternary', start: 2.58, end: 0, tone: '#1f1d17' },
]

export function periodAt(age) {
  return PERIODS.find((period) => age <= period.start && age >= period.end) ?? PERIODS[0]
}

export const IUCN_LABELS = {
  LC: 'Least Concern',
  NT: 'Near Threatened',
  VU: 'Vulnerable',
  EN: 'Endangered',
  CR: 'Critically Endangered',
  EW: 'Extinct in the Wild',
  EX: 'Extinct',
  DD: 'Data Deficient',
}

// IUCN categories on a warm-to-cool scale: the most threatened are red and
// orange, the least concern cool blue. Text colour is chosen for contrast;
// the category code and name are always shown beside the colour.
export const IUCN_ORDER = ['LC', 'NT', 'VU', 'EN', 'CR', 'EW', 'EX']
export const IUCN_COLORS = {
  EX: { fill: '#5c1f33', ink: '#ece6d6' },
  EW: { fill: '#8f2d4f', ink: '#ece6d6' },
  CR: { fill: '#e04a3c', ink: '#13120f' },
  EN: { fill: '#ee8a3c', ink: '#13120f' },
  VU: { fill: '#e2b65a', ink: '#13120f' },
  NT: { fill: '#67b7a4', ink: '#13120f' },
  LC: { fill: '#5b9bd9', ink: '#13120f' },
  DD: { fill: '#9a9282', ink: '#13120f' },
}
