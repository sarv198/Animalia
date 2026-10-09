// Why birds are reptiles, told from the tree itself: the ages of the splits
// between birds, crocodilians, turtles, lizards and tuatara come from the
// data, and the small diagram is drawn from those same nodes.
import { formatAge } from '../phylogenyLayout.js'
import { findNamed, whenPhrase } from './narrative.js'
import './shared.css'

function mrca(a, b) {
  const seen = new Set(a.ancestors())
  return b.ancestors().find((n) => seen.has(n)) ?? null
}

const W = 360
const H = 176
const LEFT = 44 // room for the age labels left of the nodes
const RIGHT = 196 // x of the present day
const LABEL_X = RIGHT + 8

export default function BirdsPanel({ node }) {
  const croc = findNamed(node, 'Crocodylia')
  const turtles = findNamed(node, 'Testudines')
  const squamates = findNamed(node, 'Squamata')
  const tuatara = findNamed(node, 'Sphenodontidae')
  if (!croc || !turtles || !squamates || !tuatara) return null

  const archosaurs = mrca(node, croc)
  const archelosaurs = mrca(archosaurs, turtles)
  const lepidosaurs = mrca(squamates, tuatara)
  const sauria = mrca(croc, squamates)
  const birdCroc = archosaurs.data.age_ma
  const crocLizard = sauria.data.age_ma
  const inDinosaurs = node.ancestors().some((n) => n.data.name === 'Dinosauria')
  const citation = node.ancestors().at(-1).data.citation

  // Time-scaled sketch: x is age (oldest left), leaves at the present.
  const oldest = crocLizard * 1.04
  const x = (age) => LEFT + (1 - age / oldest) * (RIGHT - LEFT)
  const leaves = [
    { key: 'birds', label: 'Birds', y: 18, bird: true },
    { key: 'croc', label: 'Crocodilians', y: 44 },
    { key: 'turtles', label: 'Turtles', y: 70 },
    { key: 'squamates', label: 'Lizards & snakes', y: 110 },
    { key: 'tuatara', label: 'Tuatara', y: 136 },
  ]
  const y = Object.fromEntries(leaves.map((l) => [l.key, l.y]))
  const arch = { age: birdCroc, y: (y.birds + y.croc) / 2 }
  const archelo = { age: archelosaurs.data.age_ma, y: (arch.y + y.turtles) / 2 }
  const lepido = { age: lepidosaurs.data.age_ma, y: (y.squamates + y.tuatara) / 2 }
  const root = { age: crocLizard, y: (archelo.y + lepido.y) / 2 }
  const elbow = (parent, childAge, childY) => `M${x(parent.age)},${parent.y} V${childY} H${x(childAge)}`
  const branches = [
    { d: elbow(arch, 0, y.birds), bird: true },
    { d: elbow(arch, 0, y.croc) },
    { d: elbow(archelo, arch.age, arch.y), bird: true },
    { d: elbow(archelo, 0, y.turtles) },
    { d: elbow(lepido, 0, y.squamates) },
    { d: elbow(lepido, 0, y.tuatara) },
    { d: elbow(root, archelo.age, archelo.y), bird: true },
    { d: elbow(root, lepido.age, lepido.y) },
  ]
  const bracketX = W - 46

  return (
    <section className="card-section birds-panel">
      <h3>Why birds are reptiles</h3>
      <p>
        {inDinosaurs ? 'In this tree, birds sit inside the dinosaurs, and their' : 'Their'} closest living relatives
        are the crocodilians. Birds and crocodilians last shared an ancestor about{' '}
        <strong>{formatAge(birdCroc)} million years ago</strong>, {whenPhrase(birdCroc, node)}. Crocodilians and lizards
        last shared one much earlier, about <strong>{formatAge(crocLizard)} million years ago</strong>. So a crocodile
        is more closely related to a pigeon than to any lizard.
      </p>
      <svg className="birds-tree" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Diagram: birds and crocodilians split about ${formatAge(birdCroc)} million years ago, inside the reptile branch that began about ${formatAge(crocLizard)} million years ago.`}
      >
        {branches.map((b, i) => (
          <path key={i} d={b.d} className={b.bird ? 'bt-branch bird' : 'bt-branch'} />
        ))}
        {[arch, root].map((n) => (
          <g key={n.age}>
            <circle cx={x(n.age)} cy={n.y} r="3" className="bt-node" />
            <text x={x(n.age) - 6} y={n.y + 3} className="bt-age" textAnchor="end">{formatAge(n.age)} Ma</text>
          </g>
        ))}
        {leaves.map((l) => (
          <text key={l.key} x={LABEL_X} y={l.y + 4} className={l.bird ? 'bt-leaf bird' : 'bt-leaf'}>{l.label}</text>
        ))}
        {/* traditional "reptiles": everything but the birds */}
        <path d={`M${bracketX - 4},${y.croc - 6} h4 V${y.tuatara + 6} h-4`} className="bt-bracket partial" />
        <text x={bracketX + 9} y={(y.croc + y.tuatara) / 2} className="bt-bracket-label" transform={`rotate(90 ${bracketX + 9} ${(y.croc + y.tuatara) / 2})`} textAnchor="middle">
          traditional
        </text>
        {/* the whole branch */}
        <path d={`M${bracketX + 20},${y.birds - 6} h4 V${y.tuatara + 6} h-4`} className="bt-bracket whole" />
        <text x={bracketX + 33} y={(y.birds + y.tuatara) / 2} className="bt-bracket-label whole" transform={`rotate(90 ${bracketX + 33} ${(y.birds + y.tuatara) / 2})`} textAnchor="middle">
          Reptiles
        </text>
        <text x={LEFT - 10} y={H - 6} className="bt-axis">older</text>
        <text x={RIGHT} y={H - 6} className="bt-axis" textAnchor="end">today</text>
      </svg>
      <p>
        In a classification based on ancestry, a named group has to be a complete branch: one ancestor and all of its
        descendants. The ancestor shared by crocodilians, turtles, lizards and snakes is also an ancestor of birds, so
        &ldquo;reptiles&rdquo; without birds would be a branch with one twig cut off. That is why biologists who classify
        by ancestry count birds as reptiles, even though birds were traditionally given a class of their own, Aves.
      </p>
      {citation && <p className="card-source">On defining Reptilia as a branch: {citation}</p>}
    </section>
  )
}
