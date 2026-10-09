// The 3D rendering engine for the Tree of Life page (plain three.js).
//
// It draws what worldModel.js computes and never changes it: positions come
// from the phylogeny (height = time, angle = branching order). The engine adds
// presentation only: emphasis, labels, camera moves, subtle motion.

import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { CSS2DObject, CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js'
import { MAJOR_DIVISIONS, PERIODS, STATUS } from '../phylogenyStyle.js'
import { WORLD, exhibitName } from './worldModel.js'

const BACKGROUND = 0x13120f
const BONE = new THREE.Color(0xece6d6)
const SANDSTONE = new THREE.Color(0xa89d84)
const AMBER = new THREE.Color(0xe2b65a)
const FAMILY_LABEL_DISTANCE = 190
const PORTRAIT_DISTANCE = 85
const NEAR_DISTANCE = 200 // time column recedes inside this
const TOP_MARGIN = 40 // the scale trail sits along the top of the stage
const MAX_PORTRAITS = 8
const OPACITY = { 4: 1, 3: 0.95, 2: 0.62, 1: 0.26, 0: 0.06 }
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)

function vec(p) {
  return new THREE.Vector3(p[0], p[1], p[2])
}

function muted(hex) {
  return new THREE.Color(hex).lerp(SANDSTONE, 0.32)
}

function auraTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const ctx = canvas.getContext('2d')
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
  gradient.addColorStop(0, 'rgba(255,255,255,1)')
  gradient.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 128, 128)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

export default class TreeWorld {
  constructor(container, world, { reducedMotion = false, onHover, onSelect, onScale } = {}) {
    this.container = container
    this.world = world
    this.reducedMotion = reducedMotion
    this.callbacks = { onHover, onSelect, onScale }
    this.dirty = true
    this.tween = null
    this.pulses = []
    this.connections = null
    this.levels = null
    this.accent = null
    this.hoveredId = null
    this.forcedLabels = new Set()
    this.pointer = { ndc: new THREE.Vector2(), moved: false, x: 0, y: 0, down: null }
    this.frame = 0
    this.inset = 0
    this.insetTarget = 0
    this.clock = new THREE.Clock()

    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.domElement.className = 'world-canvas'
    container.appendChild(this.renderer.domElement)

    this.labelRenderer = new CSS2DRenderer()
    this.labelRenderer.domElement.className = 'world-labels'
    container.appendChild(this.labelRenderer.domElement)

    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(BACKGROUND)
    this.scene.fog = new THREE.FogExp2(BACKGROUND, 0.0021)

    this.camera = new THREE.PerspectiveCamera(42, 1, 1, 5000)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.zoomToCursor = true
    this.controls.minDistance = 6
    this.controls.maxDistance = 1200
    this.controls.addEventListener('change', () => {
      this.dirty = true
    })

    this.scene.add(new THREE.HemisphereLight(0xf4ecd8, 0x1b1a16, 1.1))
    const sun = new THREE.DirectionalLight(0xffe7c2, 0.9)
    sun.position.set(200, 400, 150)
    this.scene.add(sun)

    this.tree = new THREE.Group()
    this.scene.add(this.tree)
    this.buildBranches()
    this.buildNodes()
    this.buildTime()
    this.buildAuras()
    this.buildParticles()
    this.buildLabels()

    this.raycaster = new THREE.Raycaster()
    this.bindEvents()
    this.resize()
    this.resetView(false)
    this.loop = this.loop.bind(this)
    this.raf = requestAnimationFrame(this.loop)
  }

  // ---------------------------------------------------------------- building

  buildBranches() {
    this.branches = new Map()
    for (const link of this.world.links) {
      const from = vec(link.from)
      const to = vec(link.to)
      const dy = to.y - from.y
      // Rise from the parent, then sweep out to the child. Height increases
      // monotonically along the curve, so it never misstates an age.
      const wobble = 3 * link.sinuous
      const c1 = new THREE.Vector3(from.x + link.jitter[0] * wobble, from.y + dy * 0.55, from.z + link.jitter[1] * wobble)
      const c2 = new THREE.Vector3(to.x - link.jitter[1] * wobble, from.y + dy * 0.45, to.z + link.jitter[0] * wobble)
      const curve = new THREE.CubicBezierCurve3(from, c1, c2, to)
      const base = muted(link.clade.color)
      let object
      if (link.ghost) {
        const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(40))
        const material = new THREE.LineDashedMaterial({ color: base, dashSize: 2, gapSize: 2.4, transparent: true, opacity: 0.7 })
        object = new THREE.Line(geometry, material)
        object.computeLineDistances()
      } else {
        const radius = 0.32 + 2.4 * Math.sqrt(link.weight)
        const geometry = new THREE.TubeGeometry(curve, 24, radius, 7, false)
        const material = new THREE.MeshStandardMaterial({
          color: base, roughness: 0.82, metalness: 0, transparent: true, opacity: 0.85,
          emissive: base, emissiveIntensity: 0.06,
        })
        object = new THREE.Mesh(geometry, material)
      }
      this.tree.add(object)
      this.branches.set(link.id, { object, base, curve, ghost: link.ghost })
    }

    this.rangeBars = new Map()
    for (const range of this.world.ranges) {
      const curve = new THREE.LineCurve3(vec(range.from), vec(range.to))
      const material = new THREE.MeshStandardMaterial({ color: muted(range.clade.color), roughness: 0.7, transparent: true, opacity: 0.9 })
      const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 4, 1.5, 8, false), material)
      this.tree.add(mesh)
      this.rangeBars.set(range.id, mesh)
    }

    const points = []
    for (const span of this.world.uncertainty) points.push(vec(span.from), vec(span.to))
    this.uncertainty = new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: BONE, transparent: true, opacity: 0.22 }),
    )
    this.tree.add(this.uncertainty)
  }

  buildNodes() {
    const tips = [...this.world.nodes.values()].filter((n) => n.tip)
    const inner = [...this.world.nodes.values()].filter((n) => !n.tip)
    this.tipItems = tips
    this.innerItems = inner

    const tipGeometry = new THREE.OctahedronGeometry(1.5, 0)
    this.tipMesh = new THREE.InstancedMesh(tipGeometry, new THREE.MeshBasicMaterial({ toneMapped: false }), tips.length)
    this.innerMesh = new THREE.InstancedMesh(
      new THREE.IcosahedronGeometry(1, 1),
      new THREE.MeshStandardMaterial({ color: BONE, roughness: 0.6, emissive: SANDSTONE, emissiveIntensity: 0.2 }),
      inner.length,
    )
    this.tipColors = tips.map((n) => new THREE.Color(n.clade.color).lerp(BONE, 0.35))
    this.tipMesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(tips.length * 3), 3)
    this.tree.add(this.tipMesh, this.innerMesh)

    // Bigger invisible proxies make small nodes easy to point at.
    const pickMaterial = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false })
    this.tipPick = new THREE.InstancedMesh(new THREE.SphereGeometry(4.2, 8, 6), pickMaterial, tips.length)
    this.innerPick = new THREE.InstancedMesh(new THREE.SphereGeometry(3.2, 8, 6), pickMaterial, inner.length)
    this.tree.add(this.tipPick, this.innerPick)

    const m = new THREE.Matrix4()
    inner.forEach((n, i) => {
      const s = MAJOR_DIVISIONS.has(n.data.name) ? 2.1 : n.data.name ? 1.3 : 0.85
      m.compose(vec(n.pos), new THREE.Quaternion(), new THREE.Vector3(s, s, s))
      this.innerMesh.setMatrixAt(i, m)
      m.compose(vec(n.pos), new THREE.Quaternion(), new THREE.Vector3(1, 1, 1))
      this.innerPick.setMatrixAt(i, m)
    })
    tips.forEach((n, i) => {
      m.compose(vec(n.pos), new THREE.Quaternion(), new THREE.Vector3(1, 1, 1))
      this.tipPick.setMatrixAt(i, m)
    })
    this.applyNodeStyles()
  }

  buildTime() {
    const { height, radius } = WORLD
    const rootAge = this.world.rootAge
    const gapAngle = Math.PI * 2 * (1 - WORLD.gap / 2)
    const columnR = radius * 1.3
    const cx = Math.cos(gapAngle) * columnR
    const cz = Math.sin(gapAngle) * columnR
    this.timeGroup = new THREE.Group()

    for (const period of PERIODS) {
      if (period.end >= rootAge) continue
      const boundary = this.world.heightOf(period.end)
      if (period.end > 0) {
        const disc = new THREE.Mesh(
          new THREE.CircleGeometry(radius * 1.28, 72),
          new THREE.MeshBasicMaterial({ color: 0xc9c1ad, transparent: true, opacity: 0.018, side: THREE.DoubleSide, depthWrite: false }),
        )
        disc.rotation.x = -Math.PI / 2
        disc.position.y = boundary
        const rim = new THREE.LineLoop(
          new THREE.BufferGeometry().setFromPoints(
            Array.from({ length: 96 }, (_, i) => {
              const a = (i / 96) * Math.PI * 2
              return new THREE.Vector3(Math.cos(a) * radius * 1.28, boundary, Math.sin(a) * radius * 1.28)
            }),
          ),
          new THREE.LineBasicMaterial({ color: 0xc9c1ad, transparent: true, opacity: 0.1 }),
        )
        this.timeGroup.add(disc, rim)
      }
      const mid = this.world.heightOf((Math.min(period.start, rootAge) + period.end) / 2)
      const tall = this.world.heightOf(period.end) - this.world.heightOf(Math.min(period.start, rootAge))
      if (tall < 12) continue
      const label = document.createElement('div')
      label.className = 'world-period'
      label.textContent = period.name
      const object = new CSS2DObject(label)
      object.position.set(cx * 1.04, mid, cz * 1.04)
      this.timeGroup.add(object)
    }

    const column = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(cx, 0, cz), new THREE.Vector3(cx, height, cz)]),
      new THREE.LineBasicMaterial({ color: 0xa89d84, transparent: true, opacity: 0.45 }),
    )
    this.timeGroup.add(column)
    for (let age = 0; age <= rootAge; age += 50) {
      const tick = document.createElement('div')
      tick.className = 'world-tick'
      tick.textContent = age === 0 ? 'today' : `${age} Ma`
      const object = new CSS2DObject(tick)
      object.position.set(cx * 0.97, this.world.heightOf(age), cz * 0.97)
      this.timeGroup.add(object)
    }
    this.scene.add(this.timeGroup)
  }

  buildAuras() {
    const texture = auraTexture()
    this.auras = []
    for (const item of this.world.nodes.values()) {
      if (!item.clade.name || item.data.name !== item.clade.name) continue
      const leaves = item.node.leaves().map((leaf) => this.world.nodes.get(leaf.data.id))
      const mean = leaves.reduce((acc, n) => acc.add(vec(n.pos)), new THREE.Vector3()).divideScalar(leaves.length)
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({ map: texture, color: new THREE.Color(item.clade.color), transparent: true, opacity: 0.05, depthWrite: false, blending: THREE.AdditiveBlending }),
      )
      const size = 40 + Math.sqrt(leaves.length) * 22
      sprite.scale.set(size, size, 1)
      sprite.position.copy(mean)
      this.tree.add(sprite)
      this.auras.push({ sprite, clade: item.clade.name })
    }
  }

  buildParticles() {
    const count = 520
    const positions = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const a = Math.random() * Math.PI * 2
      const r = Math.sqrt(Math.random()) * WORLD.radius * 1.5
      positions[i * 3] = Math.cos(a) * r
      positions[i * 3 + 1] = Math.random() * WORLD.height * 1.15 - 10
      positions[i * 3 + 2] = Math.sin(a) * r
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    this.particles = new THREE.Points(
      geometry,
      new THREE.PointsMaterial({ color: 0xece6d6, size: 0.75, transparent: true, opacity: 0.22, depthWrite: false }),
    )
    this.scene.add(this.particles)
  }

  buildLabels() {
    this.cladeLabels = new Map()
    const leaders = []
    for (const item of this.world.nodes.values()) {
      const plain = exhibitName(item.data)
      if (!plain || item.tip) continue
      // Landmark labels float above their clade's region (broader clades
      // higher); a faint leader line ties each one to the clade's actual node.
      // The root keeps its label at the root.
      const nested = item.node.ancestors().filter((a) => a !== item.node && exhibitName(a.data)).length
      let anchor = vec(item.pos).add(new THREE.Vector3(0, 7, 0))
      if (item.node.parent) {
        const leaves = item.node.leaves().map((leaf) => vec(this.world.nodes.get(leaf.data.id).pos))
        const mean = leaves.reduce((acc, p) => acc.add(p), new THREE.Vector3()).divideScalar(leaves.length)
        const outward = new THREE.Vector3(mean.x, 0, mean.z).multiplyScalar(1.12)
        anchor = new THREE.Vector3(outward.x, WORLD.height + 44 - nested * 14, outward.z)
        leaders.push(anchor.clone().add(new THREE.Vector3(0, -4, 0)), vec(item.pos))
      }
      const el = document.createElement('div')
      el.className = 'world-plaque'
      el.innerHTML = `<span class="plaque-name"></span><span class="plaque-sci"></span>`
      el.children[0].textContent = plain
      el.children[1].textContent = item.data.name
      const object = new CSS2DObject(el)
      object.position.copy(anchor)
      this.tree.add(object)
      this.cladeLabels.set(item.id, { el, object, nested, crowded: false })
    }
    this.leaders = new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(leaders),
      new THREE.LineBasicMaterial({ color: 0xc9c1ad, transparent: true, opacity: 0.1 }),
    )
    this.tree.add(this.leaders)

    this.familyLabels = new Map()
    this.portraits = new Map()
    for (const item of this.tipItems) {
      const el = document.createElement('div')
      el.className = 'world-family'
      const flag = STATUS[item.data.placement_status]
      el.textContent = (item.data.extinct ? '† ' : '') + item.data.name + (flag ? ` ${flag.symbol}` : '')
      const object = new CSS2DObject(el)
      const out = new THREE.Vector3(Math.cos(item.angle), 0, Math.sin(item.angle)).multiplyScalar(5)
      object.position.set(item.pos[0] + out.x, item.pos[1] + 3, item.pos[2] + out.z)
      this.tree.add(object)
      this.familyLabels.set(item.id, { el, object, visible: false })
    }
  }

  portraitFor(item) {
    let portrait = this.portraits.get(item.id)
    if (portrait) return portrait
    const species = item.data.representative_species
    const image = species?.image
    if (!image) return null
    const el = document.createElement('figure')
    el.className = 'world-portrait'
    const img = document.createElement('img')
    img.alt = species.common_name || species.scientific_name
    img.loading = 'lazy'
    img.referrerPolicy = 'no-referrer'
    img.src = image.thumbnail_url || image.url
    const caption = document.createElement('figcaption')
    const common = document.createElement('span')
    common.className = 'portrait-common'
    common.textContent = species.common_name || ''
    const sci = document.createElement('em')
    sci.textContent = species.scientific_name
    const family = document.createElement('span')
    family.className = 'portrait-family'
    const flag = STATUS[item.data.placement_status]
    family.textContent = item.data.name + (flag ? ` ${flag.symbol}` : '')
    const credit = document.createElement('small')
    credit.textContent = `${image.creator || 'unknown'} · ${image.licence}`
    caption.append(common, sci, family, credit)
    el.append(img, caption)
    const object = new CSS2DObject(el)
    object.position.set(item.pos[0], item.pos[1] + 13, item.pos[2])
    object.visible = false
    this.tree.add(object)
    portrait = { el, object }
    this.portraits.set(item.id, portrait)
    return portrait
  }

  // ---------------------------------------------------------------- emphasis

  // levels: Map(id -> 0..4) or null; dimOthers: whether unlisted ids fade.
  setEmphasis({ levels = null, accent = null, dimOthers = true, forced = [] } = {}) {
    this.levels = levels
    this.dimOthers = dimOthers
    this.accent = accent
    this.forcedLabels = new Set(forced)
    for (const [id, branch] of this.branches) {
      const level = levels?.get(id)
      const material = branch.object.material
      const lit = accent?.has(id)
      material.color.copy(branch.base)
      if (lit) material.color.lerp(AMBER, 0.55)
      material.opacity = level != null ? OPACITY[level] : levels && dimOthers ? OPACITY[0] : branch.ghost ? 0.7 : 0.85
      if (material.emissive) {
        material.emissive.copy(material.color)
        material.emissiveIntensity = lit ? 0.4 : 0.06
      }
    }
    for (const [id, bar] of this.rangeBars) {
      const level = levels?.get(id)
      bar.material.opacity = level != null ? OPACITY[level] : levels && dimOthers ? OPACITY[0] : 0.9
    }
    this.uncertainty.material.opacity = levels && dimOthers ? 0.08 : 0.22
    for (const [id, label] of this.cladeLabels) {
      const level = levels?.get(id)
      label.el.dataset.level = level != null ? level : levels && dimOthers ? 0 : 'n'
    }
    for (const aura of this.auras) aura.sprite.material.opacity = levels && dimOthers ? 0.025 : 0.05
    this.applyNodeStyles()
    this.updateLabels(true)
    this.dirty = true
  }

  applyNodeStyles() {
    const m = new THREE.Matrix4()
    const color = new THREE.Color()
    this.tipItems.forEach((item, i) => {
      const level = this.levels?.get(item.id)
      const dim = this.levels && this.dimOthers && level == null
      let scale = 1
      color.copy(this.tipColors[i])
      if (level === 4) {
        scale = 2.3
        color.lerp(AMBER, 0.5)
      } else if (level === 3) {
        scale = 1.45
        color.lerp(BONE, 0.35)
      } else if (dim || level === 0) {
        color.multiplyScalar(0.18)
        scale = 0.8
      } else if (level === 1) {
        color.multiplyScalar(0.45)
      }
      if (item.id === this.hoveredId) scale *= 1.5
      m.compose(vec(item.pos), new THREE.Quaternion(), new THREE.Vector3(scale, scale, scale))
      this.tipMesh.setMatrixAt(i, m)
      this.tipMesh.setColorAt(i, color)
    })
    this.tipMesh.instanceMatrix.needsUpdate = true
    this.tipMesh.instanceColor.needsUpdate = true
  }

  setHovered(id) {
    if (this.hoveredId === id) return
    this.hoveredId = id
    this.applyNodeStyles()
    this.updateLabels(true)
    this.dirty = true
  }

  // Thin arcs from the selected family to its closest relatives (temporary).
  setConnections(fromId, toIds) {
    if (this.connections) {
      this.tree.remove(this.connections)
      this.connections.geometry.dispose()
      this.connections.material.dispose()
      this.connections = null
    }
    if (fromId == null || !toIds?.length) {
      this.dirty = true
      return
    }
    const from = vec(this.world.nodes.get(fromId).pos)
    const points = []
    for (const id of toIds) {
      const to = vec(this.world.nodes.get(id).pos)
      const mid = from.clone().add(to).multiplyScalar(0.5)
      mid.y += 10 + from.distanceTo(to) * 0.25
      const curve = new THREE.QuadraticBezierCurve3(from, mid, to)
      const pts = curve.getPoints(24)
      for (let i = 0; i < pts.length - 1; i++) points.push(pts[i], pts[i + 1])
    }
    this.connections = new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: AMBER, transparent: true, opacity: 0.0 }),
    )
    this.connections.userData.fadeIn = true
    this.tree.add(this.connections)
    this.dirty = true
  }

  // Pulses flowing from a family back toward its ancestors.
  setPulsePaths(paths) {
    for (const pulse of this.pulses) {
      this.tree.remove(pulse.points)
      pulse.points.geometry.dispose()
      pulse.points.material.dispose()
    }
    this.pulses = []
    if (this.reducedMotion || !paths?.length) {
      this.dirty = true
      return
    }
    for (const ids of paths) {
      const curves = []
      for (const id of ids) {
        const branch = this.branches.get(id)
        if (branch) curves.push(branch.curve)
      }
      if (!curves.length) continue
      // Sample each branch child -> parent, in order from the tip upward.
      const samples = []
      for (const curve of curves) {
        for (let i = 24; i >= 0; i--) samples.push(curve.getPoint(i / 24))
      }
      const count = 5
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3))
      const points = new THREE.Points(
        geometry,
        new THREE.PointsMaterial({ color: AMBER, size: 3.2, transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending }),
      )
      this.tree.add(points)
      this.pulses.push({ points, samples, count, offset: Math.random() })
    }
    this.dirty = true
  }

  setMuseum(on) {
    this.labelRenderer.domElement.classList.toggle('museum', on)
    this.dirty = true
  }

  // ---------------------------------------------------------------- camera

  flyTo(position, target, duration = 1100) {
    const dur = this.reducedMotion ? 250 : duration
    return new Promise((resolve) => {
      this.tween?.resolve()
      this.tween = {
        fromPos: this.camera.position.clone(),
        toPos: position.clone(),
        fromTarget: this.controls.target.clone(),
        toTarget: target.clone(),
        start: performance.now(),
        duration: dur,
        resolve,
      }
      this.controls.enabled = false
      this.dirty = true
    })
  }

  // How far back a sphere of this radius fits the view, on the narrower axis
  // (portrait phones are narrower than they are tall).
  fitDistance(radius) {
    const vertical = THREE.MathUtils.degToRad(this.camera.fov) / 2
    const horizontal = Math.atan(Math.tan(vertical) * this.camera.aspect)
    return radius / Math.sin(Math.min(vertical, horizontal))
  }

  // Frame a set of nodes, viewed from outside their sector and a little above.
  frameIds(ids, { duration, distanceScale = 1 } = {}) {
    const points = ids.map((id) => vec(this.world.nodes.get(id).pos))
    const sphere = new THREE.Sphere().setFromPoints(points)
    const center = sphere.center
    const radius = Math.max(sphere.radius, 18)
    const outward = new THREE.Vector3(center.x, 0, center.z)
    if (outward.lengthSq() < 1) outward.set(0, 0, 1)
    outward.normalize()
    const dir = outward.multiplyScalar(0.88).add(new THREE.Vector3(0, 0.48, 0)).normalize()
    const distance = this.fitDistance(radius) * 1.1 * distanceScale
    // Aim a little low so the tips (and their labels) clear the top edge.
    const aim = center.clone().add(new THREE.Vector3(0, radius * 0.12, 0))
    return this.flyTo(aim.clone().add(dir.multiplyScalar(distance)), aim, duration)
  }

  focusNode(id, { duration } = {}) {
    const item = this.world.nodes.get(id)
    if (!item) return Promise.resolve()
    if (!item.tip) return this.frameIds(item.node.descendants().map((n) => n.data.id), { duration })
    const pos = vec(item.pos)
    const outward = new THREE.Vector3(Math.cos(item.angle), 0, Math.sin(item.angle))
    const camera = pos.clone().add(outward.multiplyScalar(52)).add(new THREE.Vector3(0, 16, 0))
    return this.flyTo(camera, pos.clone().add(new THREE.Vector3(0, 4, 0)), duration)
  }

  focusNeighbourhood(ids) {
    return this.frameIds(ids, { distanceScale: 0.9 })
  }

  resetView(animated = true) {
    const squamata = this.world.byName.get('Squamata')
    const ids = (squamata ? squamata.node : this.world.root).descendants().map((n) => n.data.id)
    if (!animated) {
      const points = ids.map((id) => vec(this.world.nodes.get(id).pos))
      const sphere = new THREE.Sphere().setFromPoints(points)
      this.controls.target.copy(sphere.center)
      this.camera.position.copy(sphere.center).add(new THREE.Vector3(0, 0.55, 1).normalize().multiplyScalar(this.fitDistance(sphere.radius) * 0.95))
      this.controls.update()
      return Promise.resolve()
    }
    return this.frameIds(ids, { distanceScale: 1.15 })
  }

  // A slow, wide approach for the museum entrance.
  async cinematicEntrance() {
    const all = [...this.world.nodes.keys()]
    const points = all.map((id) => vec(this.world.nodes.get(id).pos))
    const sphere = new THREE.Sphere().setFromPoints(points)
    this.controls.target.copy(sphere.center)
    this.camera.position.copy(sphere.center).add(new THREE.Vector3(0.3, 0.35, 1).normalize().multiplyScalar(sphere.radius * 5))
    this.controls.update()
    await this.frameIds(all, { duration: 3800, distanceScale: 1.05 })
  }

  // ---------------------------------------------------------------- events

  bindEvents() {
    const canvas = this.renderer.domElement
    this.onPointerMove = (event) => {
      const box = canvas.getBoundingClientRect()
      this.pointer.ndc.set(((event.clientX - box.left) / box.width) * 2 - 1, -((event.clientY - box.top) / box.height) * 2 + 1)
      this.pointer.x = event.clientX - box.left
      this.pointer.y = event.clientY - box.top
      this.pointer.moved = true
    }
    this.onPointerDown = (event) => {
      this.pointer.down = { x: event.clientX, y: event.clientY }
    }
    this.onPointerUp = (event) => {
      const down = this.pointer.down
      this.pointer.down = null
      if (!down || Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) return
      this.onPointerMove(event)
      const id = this.pick()
      this.callbacks.onSelect?.(id, { shift: event.shiftKey })
    }
    this.onPointerLeave = () => {
      this.pointer.moved = false
      if (this.hoveredId != null) {
        this.setHovered(null)
        this.callbacks.onHover?.(null)
      }
    }
    canvas.addEventListener('pointermove', this.onPointerMove)
    canvas.addEventListener('pointerdown', this.onPointerDown)
    canvas.addEventListener('pointerup', this.onPointerUp)
    canvas.addEventListener('pointerleave', this.onPointerLeave)
    this.resizeObserver = new ResizeObserver(() => this.resize())
    this.resizeObserver.observe(this.container)
    this.onVisibility = () => {
      if (!document.hidden) this.dirty = true
    }
    document.addEventListener('visibilitychange', this.onVisibility)
  }

  pick() {
    this.raycaster.setFromCamera(this.pointer.ndc, this.camera)
    const hits = this.raycaster.intersectObjects([this.tipPick, this.innerPick], false)
    if (!hits.length) return null
    const hit = hits[0]
    const list = hit.object === this.tipPick ? this.tipItems : this.innerItems
    return list[hit.instanceId]?.id ?? null
  }

  // Space taken by a side panel: the view centre shifts left of it, so what
  // the camera frames is not hidden behind the panel.
  setInset(pixels) {
    this.insetTarget = pixels
    this.dirty = true
  }

  applyInset() {
    const width = this.container.clientWidth
    const height = this.container.clientHeight
    if (!width || !height) return
    if (this.inset > 0.5) this.camera.setViewOffset(width, height, this.inset / 2, 0, width, height)
    else this.camera.clearViewOffset()
    this.camera.updateProjectionMatrix()
  }

  resize() {
    const width = this.container.clientWidth
    const height = this.container.clientHeight
    if (!width || !height) return
    this.camera.aspect = width / height
    this.applyInset()
    this.renderer.setSize(width, height)
    this.labelRenderer.setSize(width, height)
    this.dirty = true
  }

  // ---------------------------------------------------------------- per frame

  updateLabels(force = false) {
    if (!force && this.frame % 8 !== 0) return
    const camera = this.camera.position
    const candidates = []
    for (const item of this.tipItems) {
      const label = this.familyLabels.get(item.id)
      const distance = camera.distanceTo(vec(item.pos))
      const level = this.levels?.get(item.id)
      const show = item.id === this.hoveredId || this.forcedLabels.has(item.id) || (level != null && level >= 3) || distance < FAMILY_LABEL_DISTANCE
      if (show !== label.visible) {
        label.visible = show
        label.el.classList.toggle('visible', show)
      }
      label.el.dataset.level = level != null ? level : this.levels && this.dimOthers ? 0 : 'n'
      candidates.push({ item, distance })
    }
    // Portraits: the nearest few, plus whatever is hovered or selected.
    const wanted = new Set()
    candidates
      .filter((c) => c.distance < PORTRAIT_DISTANCE)
      .sort((a, b) => a.distance - b.distance)
      .slice(0, MAX_PORTRAITS)
      .forEach((c) => wanted.add(c.item.id))
    if (this.hoveredId != null) wanted.add(this.hoveredId)
    for (const id of this.forcedLabels) wanted.add(id)
    for (const item of this.tipItems) {
      const show = wanted.has(item.id) && this.world.nodes.get(item.id).tip
      const portrait = show ? this.portraitFor(item) : this.portraits.get(item.id)
      if (!portrait) continue
      if (portrait.object.visible !== show) {
        portrait.object.visible = show
        portrait.el.classList.toggle('visible', show)
        // The portrait caption carries the family name meanwhile.
        this.familyLabels.get(item.id)?.el.classList.toggle('with-portrait', show)
      }
    }
    this.declutterLabels()
    if (this.callbacks.onScale) {
      const target = this.controls.target
      let nearest = null
      let best = Infinity
      for (const item of this.tipItems) {
        const d = target.distanceTo(vec(item.pos))
        if (d < best) {
          best = d
          nearest = item
        }
      }
      const distance = camera.distanceTo(target)
      this.labelRenderer.domElement.classList.toggle('near', distance < NEAR_DISTANCE)
      const key = `${nearest?.id}-${Math.round(distance / 20)}`
      if (key !== this.scaleKey) {
        this.scaleKey = key
        this.callbacks.onScale({ nearestId: nearest?.id ?? null, distance })
      }
    }
  }

  // Labels that would overlap on screen give way. Portraits first (hovered,
  // then selected, then nearest), then family names, then landmark plaques
  // (emphasised, then broader); hidden ones reappear as the camera moves.
  declutterLabels() {
    const width = this.renderer.domElement.clientWidth
    const height = this.renderer.domElement.clientHeight
    if (!width || !height) return
    const camera = this.camera.position
    const projected = new THREE.Vector3()
    const placed = []
    const place = (object, el, pad, fallback) => {
      object.getWorldPosition(projected).project(this.camera)
      const x = (projected.x * 0.5 + 0.5) * width
      const y = (-projected.y * 0.5 + 0.5) * height
      const w = el.offsetWidth || fallback[0]
      const h = el.offsetHeight || fallback[1]
      const box = { left: x - w / 2 - pad, right: x + w / 2 + pad, top: y - h / 2 - pad / 2, bottom: y + h / 2 + pad / 2 }
      const offStage = projected.z > 1 || box.top < TOP_MARGIN || box.bottom > height || box.left < 0 || box.right > width
      const crowded = offStage || placed.some((o) => box.left < o.right && box.right > o.left && box.top < o.bottom && box.bottom > o.top)
      if (!crowded) placed.push(box)
      return crowded
    }
    const rank = (id) => (id === this.hoveredId ? 0 : this.levels?.get(id) === 4 ? 1 : 2)
    const portraits = [...this.portraits.entries()]
      .filter(([, portrait]) => portrait.object.visible)
      .map(([id, portrait]) => ({ id, portrait, distance: camera.distanceTo(vec(this.world.nodes.get(id).pos)) }))
      .sort((a, b) => rank(a.id) - rank(b.id) || a.distance - b.distance)
    for (const { id, portrait } of portraits) {
      // The hovered portrait always shows.
      const crowded = place(portrait.object, portrait.el, 2, [110, 130]) && id !== this.hoveredId
      portrait.el.classList.toggle('crowded', crowded)
      this.familyLabels.get(id)?.el.classList.toggle('with-portrait', !crowded)
    }
    const families = this.tipItems
      .map((item) => ({ item, label: this.familyLabels.get(item.id) }))
      .filter(({ label }) => label.visible)
      .map((entry) => ({ ...entry, distance: camera.distanceTo(vec(entry.item.pos)) }))
      .sort((a, b) => (this.levels?.get(b.item.id) ?? -1) - (this.levels?.get(a.item.id) ?? -1) || a.distance - b.distance)
    for (const { item, label } of families) {
      // A name sitting under its own portrait is already clear of the others.
      if (label.el.classList.contains('with-portrait')) {
        label.el.classList.remove('crowded')
        continue
      }
      const crowded = place(label.object, label.el, 3, [80, 16]) && item.id !== this.hoveredId
      label.el.classList.toggle('crowded', crowded)
    }
    const plaques = [...this.cladeLabels.entries()].sort(([idA, a], [idB, b]) => {
      const la = this.levels?.get(idA) ?? -1
      const lb = this.levels?.get(idB) ?? -1
      return lb - la || a.nested - b.nested
    })
    for (const [, label] of plaques) {
      const crowded = place(label.object, label.el, 4, [120, 30])
      if (crowded !== label.crowded) {
        label.crowded = crowded
        label.el.classList.toggle('crowded', crowded)
      }
    }
  }

  loop(now) {
    this.raf = requestAnimationFrame(this.loop)
    if (document.hidden) return
    this.frame += 1
    const t = this.clock.getElapsedTime()

    if (this.inset !== this.insetTarget) {
      const step = (this.insetTarget - this.inset) * (this.reducedMotion ? 1 : 0.12)
      this.inset = Math.abs(step) < 0.5 ? this.insetTarget : this.inset + step
      this.applyInset()
      this.dirty = true
    }

    if (this.tween) {
      const k = Math.min((now - this.tween.start) / this.tween.duration, 1)
      const e = easeInOut(k)
      this.camera.position.lerpVectors(this.tween.fromPos, this.tween.toPos, e)
      this.controls.target.lerpVectors(this.tween.fromTarget, this.tween.toTarget, e)
      if (k >= 1) {
        const done = this.tween.resolve
        this.tween = null
        this.controls.enabled = true
        done()
      }
      this.dirty = true
    }
    if (this.controls.update()) this.dirty = true

    const animate = !this.reducedMotion
    if (animate) {
      // Almost imperceptible life: a slow drift of motes, a breath of sway.
      this.particles.rotation.y = t * 0.006
      this.particles.position.y = Math.sin(t * 0.15) * 1.2
      this.tree.rotation.y = Math.sin(t * 0.05) * 0.0035
      for (const pulse of this.pulses) {
        const attr = pulse.points.geometry.attributes.position
        for (let i = 0; i < pulse.count; i++) {
          const u = (t * 0.22 + pulse.offset + i / pulse.count) % 1
          const p = pulse.samples[Math.floor(u * (pulse.samples.length - 1))]
          attr.setXYZ(i, p.x, p.y, p.z)
        }
        attr.needsUpdate = true
      }
      if (this.connections?.userData.fadeIn) {
        const material = this.connections.material
        material.opacity = Math.min(material.opacity + 0.01, 0.45)
        if (material.opacity >= 0.45) this.connections.userData.fadeIn = false
      }
    } else if (this.connections) {
      this.connections.material.opacity = 0.45
    }

    if (this.pointer.moved && !this.pointer.down) {
      this.pointer.moved = false
      const id = this.pick()
      if (id !== this.hoveredId) {
        this.setHovered(id)
        this.callbacks.onHover?.(id == null ? null : { id, x: this.pointer.x, y: this.pointer.y })
      }
    }

    // Ambient motion renders at half rate; anything the user does renders at full rate.
    const ambientFrame = animate && this.frame % 2 === 0
    if (!this.dirty && !ambientFrame) return
    this.dirty = false
    this.updateLabels()
    this.renderer.render(this.scene, this.camera)
    this.labelRenderer.render(this.scene, this.camera)
  }

  dispose() {
    cancelAnimationFrame(this.raf)
    this.tween?.resolve()
    const canvas = this.renderer.domElement
    canvas.removeEventListener('pointermove', this.onPointerMove)
    canvas.removeEventListener('pointerdown', this.onPointerDown)
    canvas.removeEventListener('pointerup', this.onPointerUp)
    canvas.removeEventListener('pointerleave', this.onPointerLeave)
    document.removeEventListener('visibilitychange', this.onVisibility)
    this.resizeObserver.disconnect()
    this.controls.dispose()
    this.scene.traverse((object) => {
      object.geometry?.dispose()
      const material = object.material
      if (Array.isArray(material)) material.forEach((m) => m.dispose())
      else material?.dispose()
    })
    this.renderer.dispose()
    canvas.remove()
    this.labelRenderer.domElement.remove()
  }
}
