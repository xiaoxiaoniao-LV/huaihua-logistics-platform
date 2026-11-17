/**数字孪生分级舞台：园区 → 库区 → 库房 → 设备的四级三维下钻。
 *
 * 与 ColdStorageScene 的分工：
 *  - ColdStorageScene 面向「资源」演示（冷链箱/仓库模型）
 *  - TwinLevelScene 面向「孪生节点」，每一级只渲染该级节点，点击下钻
 *
 * 节点状态色、绑定测点值直接画在悬浮铭牌上，指挥室不需要点开就能看到温度。
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'
import { PERF_BUDGET, SCENE_COLOR, resolvePerfBudget } from '@/config/scene'
import { hexToNumber, theme } from '@/config/theme'

export interface TwinBindingLite {
  point_key: string
  name: string
  value: number | string | boolean | null
  unit: string | null
  quality: string
  device_code: string
}

export interface TwinNodeLite {
  node_key: string
  name: string
  node_type: string
  status: string
  bindings: TwinBindingLite[]
  children: TwinNodeLite[]
}

export const TWIN_STATUS_COLOR: Record<string, number> = {
  online: hexToNumber(theme.color.accent.green),
  unknown: hexToNumber(theme.color.status.pending),
  offline: hexToNumber(theme.color.status.offline),
  degraded: hexToNumber(theme.color.alert.warn),
  alarm: hexToNumber(theme.color.alert.critical),
  maintenance: hexToNumber(theme.color.accent.violet),
}

export const TWIN_STATUS_TEXT: Record<string, string> = {
  online: '在线',
  unknown: '待接入',
  offline: '离线',
  degraded: '数据异常',
  alarm: '告警',
  maintenance: '维护中',
}

const NODE_TYPE_LABEL: Record<string, string> = {
  site: '园区', zone: '库区', building: '库房', floor: '楼层',
  room: '库房', rack: '货架', device: '设备',
}

type PickCallback = (nodeKey: string | null) => void

interface NodeVisual {
  node: TwinNodeLite
  group: THREE.Group
  ring: THREE.Mesh
  labelEl: HTMLDivElement
  bodyMat: THREE.MeshStandardMaterial
  edgesMat: THREE.LineBasicMaterial
  baseY: number
}

export class TwinLevelScene {
  private canvas: HTMLCanvasElement
  private scene!: THREE.Scene
  camera!: THREE.PerspectiveCamera
  private renderer!: THREE.WebGLRenderer
  private labelRenderer!: CSS2DRenderer
  private controls!: OrbitControls
  private animId = 0

  private nodeGroup = new THREE.Group()
  private visuals: NodeVisual[] = []
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()
  private onPick: PickCallback | null = null
  private resizeHandler?: () => void
  private selectedKey: string | null = null
  private clock = new THREE.Clock()

  private composer: EffectComposer | null = null
  private bloomPass: UnrealBloomPass | null = null
  private budget = resolvePerfBudget()
  private selectedBeam: THREE.Mesh | null = null

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas
  }

  init() {
    this.scene = new THREE.Scene()
    this.scene.fog = new THREE.FogExp2(SCENE_COLOR.background, 0.018)

    const w = this.canvas.clientWidth || 800
    const h = this.canvas.clientHeight || 600
    this.camera = new THREE.PerspectiveCamera(48, w / h, 0.1, 400)
    this.camera.position.set(0, 26, 34)

    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: true, alpha: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, this.budget.pixelRatio))
    this.renderer.setSize(w, h, false)
    this.renderer.shadowMap.enabled = PERF_BUDGET.enableShadow
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.15

    this.labelRenderer = new CSS2DRenderer()
    this.labelRenderer.setSize(w, h)
    const dom = this.labelRenderer.domElement
    dom.style.position = 'absolute'
    dom.style.inset = '0'
    dom.style.pointerEvents = 'none'
    this.canvas.parentElement?.appendChild(dom)

    this.controls = new OrbitControls(this.camera, this.canvas)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.minDistance = 6
    this.controls.maxDistance = 140
    this.controls.maxPolarAngle = Math.PI / 2 - 0.04
    this.controls.target.set(0, 1.5, 0)

    this.buildLights()
    this.buildGround()
    this.scene.add(this.nodeGroup)

    this.setupPostProcessing()
    this.bindEvents()
    this.startLoop()
  }

  /** 泛光后处理：状态色/边框在深色场景中发光 */
  private setupPostProcessing() {
    if (!this.budget.bloom.enabled) return
    const w = this.canvas.clientWidth || 800
    const h = this.canvas.clientHeight || 600
    this.composer = new EffectComposer(this.renderer)
    this.composer.setPixelRatio(this.renderer.getPixelRatio())
    this.composer.setSize(w, h)
    this.composer.addPass(new RenderPass(this.scene, this.camera))

    const bloom = new UnrealBloomPass(
      new THREE.Vector2(w, h),
      this.budget.bloom.strength,
      this.budget.bloom.radius,
      this.budget.bloom.threshold,
    )
    this.composer.addPass(bloom)
    this.composer.addPass(new OutputPass())
    this.bloomPass = bloom
  }

  setPickCallback(cb: PickCallback) {
    this.onPick = cb
  }

  /** 渲染某一级的节点；nodes 为空时清空场景 */
  setNodes(nodes: TwinNodeLite[]) {
    this.clearNodes()
    if (!nodes.length) return

    const count = nodes.length
    const cols = Math.ceil(Math.sqrt(count))
    const rows = Math.ceil(count / cols)
    const gapX = 6.4
    const gapZ = 6.4

    nodes.forEach((node, i) => {
      const col = i % cols
      const row = Math.floor(i / cols)
      const x = (col - (cols - 1) / 2) * gapX
      const z = (row - (rows - 1) / 2) * gapZ
      const group = this.createNode(node, i)
      group.position.set(x, 0, z)
      this.nodeGroup.add(group)
      this.visuals.push({
        node,
        group,
        ring: group.userData.ring,
        labelEl: group.userData.labelEl,
        bodyMat: group.userData.bodyMat,
        edgesMat: group.userData.edgesMat,
        baseY: 0,
      })
    })

    this.frameCamera(cols * gapX, rows * gapZ, nodes)
  }

  /** 同层级内只刷新颜色与铭牌数值，不重建几何体 */
  updateValues(nodes: TwinNodeLite[]) {
    const byKey = new Map(nodes.map((n) => [n.node_key, n]))
    this.visuals.forEach((v) => {
      const next = byKey.get(v.node.node_key)
      if (!next) return
      v.node = next
      const color = TWIN_STATUS_COLOR[next.status] ?? TWIN_STATUS_COLOR.unknown
      v.bodyMat.color.setHex(color)
      v.bodyMat.emissive.setHex(color)
      v.bodyMat.emissiveIntensity = next.status === 'alarm' ? 0.55 : 0.22
      v.edgesMat.color.setHex(color)
      this.fillLabel(v.labelEl, next, color)
    })
    this.setSelected(this.selectedKey)
  }

  setSelected(nodeKey: string | null) {
    this.selectedKey = nodeKey
    let picked: NodeVisual | null = null
    this.visuals.forEach((v) => {
      const on = v.node.node_key === nodeKey
      const mat = v.ring.material as THREE.MeshBasicMaterial
      mat.opacity = on ? 0.95 : 0.35
      v.group.scale.setScalar(on ? 1.06 : 1)
      // 选中提亮，未选中回到基础自发光
      v.bodyMat.emissiveIntensity = on ? 1.15 : v.node.status === 'alarm' ? 0.55 : 0.22
      if (on) picked = v
    })
    this.updateBeam(picked)
  }

  /** 选中节点上方加一道呼吸光柱 */
  private updateBeam(v: NodeVisual | null) {
    if (this.selectedBeam) {
      this.selectedBeam.parent?.remove(this.selectedBeam)
      this.selectedBeam.geometry.dispose()
      ;(this.selectedBeam.material as THREE.Material).dispose()
      this.selectedBeam = null
    }
    if (!v) return
    const height = v.node.node_type === 'device'
      ? 1.0
      : 1.7 + Math.min(v.node.children.length, 4) * 0.22
    const beamHeight = height + 4
    const beam = new THREE.Mesh(
      new THREE.CylinderGeometry(1.05, 1.05, beamHeight, 24, 1, true),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(theme.color.accent.cyan),
        transparent: true,
        opacity: 0.2,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    )
    beam.position.y = beamHeight / 2
    beam.renderOrder = 2
    v.group.add(beam)
    this.selectedBeam = beam
  }

  dispose() {
    cancelAnimationFrame(this.animId)
    this.unbindEvents()
    this.clearNodes()
    this.composer?.dispose()
    this.composer = null
    this.bloomPass = null
    this.controls?.dispose()
    this.renderer?.dispose()
    this.labelRenderer?.domElement?.remove()
    this.scene?.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose()
        const m = obj.material
        if (Array.isArray(m)) m.forEach((x) => x.dispose())
        else m?.dispose()
      }
    })
  }

  // ===================== 场景 =====================

  private buildLights() {
    this.scene.add(new THREE.AmbientLight(hexToNumber(theme.color.accent.blue), 0.55))
    const sun = new THREE.DirectionalLight(0xffffff, 1.15)
    sun.position.set(18, 30, 14)
    sun.castShadow = PERF_BUDGET.enableShadow
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.camera.left = -40
    sun.shadow.camera.right = 40
    sun.shadow.camera.top = 40
    sun.shadow.camera.bottom = -40
    this.scene.add(sun)
    const rim = new THREE.PointLight(SCENE_COLOR.accent, 1.4, 90)
    rim.position.set(-16, 12, -14)
    this.scene.add(rim)
  }

  private buildGround() {
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(48, 64),
      new THREE.MeshStandardMaterial({ color: 0x07172e, metalness: 0.65, roughness: 0.35 }),
    )
    ground.rotation.x = -Math.PI / 2
    ground.receiveShadow = true
    this.scene.add(ground)

    const grid = new THREE.GridHelper(96, 48, SCENE_COLOR.accent, SCENE_COLOR.grid)
    ;(grid.material as THREE.Material).opacity = 0.22
    ;(grid.material as THREE.Material).transparent = true
    grid.position.y = 0.02
    this.scene.add(grid)

    const halo = new THREE.Mesh(
      new THREE.RingGeometry(46, 48, 96),
      new THREE.MeshBasicMaterial({ color: SCENE_COLOR.accent, transparent: true, opacity: 0.18, side: THREE.DoubleSide }),
    )
    halo.rotation.x = -Math.PI / 2
    halo.position.y = 0.03
    this.scene.add(halo)
  }

  // ===================== 节点 =====================

  private createNode(node: TwinNodeLite, index: number): THREE.Group {
    const color = TWIN_STATUS_COLOR[node.status] ?? TWIN_STATUS_COLOR.unknown
    const group = new THREE.Group()
    group.userData.node_key = node.node_key

    // 基座
    const base = new THREE.Mesh(
      new THREE.CylinderGeometry(1.9, 2.1, 0.16, 48),
      new THREE.MeshStandardMaterial({ color: 0x0e2b4d, metalness: 0.8, roughness: 0.25 }),
    )
    base.position.y = 0.08
    base.receiveShadow = true
    group.add(base)

    // 状态光环
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(2.0, 2.24, 64),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.35, side: THREE.DoubleSide }),
    )
    ring.rotation.x = -Math.PI / 2
    ring.position.y = 0.17
    group.add(ring)
    group.userData.ring = ring

    // 主体
    const isDevice = node.node_type === 'device'
    const height = isDevice ? 1.0 : 1.7 + Math.min(node.children.length, 4) * 0.22
    const bodyMat = new THREE.MeshStandardMaterial({
      color,
      metalness: 0.45,
      roughness: 0.22,
      transparent: true,
      opacity: isDevice ? 0.85 : 0.32,
      emissive: color,
      emissiveIntensity: node.status === 'alarm' ? 0.55 : 0.22,
    })
    const body = new THREE.Mesh(new THREE.BoxGeometry(2.4, height, 2.4), bodyMat)
    body.position.y = height / 2 + 0.18
    body.castShadow = true
    body.receiveShadow = true
    group.add(body)

    // 棱边，增强科技感
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(2.4, height, 2.4)),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.85 }),
    )
    edges.position.copy(body.position)
    group.add(edges)

    if (!isDevice) {
      // 顶层横梁 + 顶部发光条
      const top = new THREE.Mesh(
        new THREE.BoxGeometry(2.7, 0.1, 2.7),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.7 }),
      )
      top.position.y = height + 0.22
      group.add(top)
    } else {
      // 设备天线：示意在线信号
      const mast = new THREE.Mesh(
        new THREE.CylinderGeometry(0.03, 0.03, 1.1, 8),
        new THREE.MeshBasicMaterial({ color }),
      )
      mast.position.y = height + 0.8
      group.add(mast)
      const tip = new THREE.Mesh(
        new THREE.SphereGeometry(0.11, 12, 12),
        new THREE.MeshBasicMaterial({ color }),
      )
      tip.position.y = height + 1.36
      group.add(tip)
    }

    // 悬浮铭牌（DOM，保证中文清晰）
    const label = this.createLabel(node)
    label.position.y = height + (isDevice ? 2.0 : 1.35)
    group.add(label)

    group.userData.bodyMat = bodyMat
    group.userData.edgesMat = edges.material
    group.userData.labelEl = label.element

    // 轻微差异化悬浮，避免整排呆板
    group.userData.floatOffset = index * 0.7
    return group
  }

  private createLabel(node: TwinNodeLite): CSS2DObject {
    const el = document.createElement('div')
    el.className = 'twin-node-label'
    this.fillLabel(el, node, TWIN_STATUS_COLOR[node.status] ?? TWIN_STATUS_COLOR.unknown)
    return new CSS2DObject(el)
  }

  private fillLabel(el: HTMLDivElement, node: TwinNodeLite, color: number) {
    const hex = '#' + color.toString(16).padStart(6, '0')
    el.style.cssText = [
      'min-width:150px', 'max-width:220px', 'padding:8px 12px',
      'border-radius:8px', 'background:rgba(5,18,38,.82)',
      `border:1px solid ${hex}`, 'box-shadow:0 0 14px rgba(0,229,255,.18)',
      'backdrop-filter:blur(6px)', 'pointer-events:none', 'font-family:inherit',
      'text-align:left', 'transition:border-color .2s',
    ].join(';')
    el.innerHTML = ''

    const title = document.createElement('div')
    title.textContent = node.name
    title.style.cssText = `font-size:13px;font-weight:600;color:${theme.color.text.primary};line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis`
    el.appendChild(title)

    const meta = document.createElement('div')
    const badge = TWIN_STATUS_TEXT[node.status] || node.status
    meta.textContent = `${NODE_TYPE_LABEL[node.node_type] || node.node_type} · ${badge}`
    meta.style.cssText = `font-size:11px;color:#${color.toString(16).padStart(6, '0')};margin-top:2px;letter-spacing:.5px`
    el.appendChild(meta)

    const values = node.bindings.filter((b) => b.value !== null).slice(0, 2)
    values.forEach((b) => {
      const row = document.createElement('div')
      const shown = typeof b.value === 'boolean' ? (b.value ? '开' : '关') : `${b.value}${b.unit || ''}`
      row.textContent = `${b.name} ${shown}`
      row.style.cssText = `font-size:11px;color:${theme.color.accent.cyan};margin-top:3px;font-variant-numeric:tabular-nums`
      el.appendChild(row)
    })

    if (!values.length && node.children.length) {
      const row = document.createElement('div')
      row.textContent = `点击下钻 · ${node.children.length} 个下级`
      row.style.cssText = `font-size:11px;color:${theme.color.text.muted};margin-top:3px`
      el.appendChild(row)
    }
  }

  private clearNodes() {
    this.selectedBeam = null
    this.visuals.forEach((v) => {
      v.group.traverse((obj) => {
        if (obj instanceof CSS2DObject) obj.element.remove()
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose()
          const m = obj.material
          if (Array.isArray(m)) m.forEach((x) => x.dispose())
          else m?.dispose()
        }
      })
    })
    this.nodeGroup.clear()
    this.visuals = []
  }

  // ===================== 相机 =====================

  private frameCamera(width: number, depth: number, nodes: TwinNodeLite[]) {
    const span = Math.max(width, depth, 12)
    const distance = span * 1.15 + 12
    this.camera.position.set(distance * 0.45, distance * 0.78, distance * 0.9)
    this.controls.target.set(0, 1.4, 0)
    this.controls.maxDistance = Math.max(160, distance * 2.2)
    this.controls.update()
    // 设备层缩得更近，方便看铭牌
    if (nodes.every((n) => n.node_type === 'device')) {
      this.camera.position.multiplyScalar(0.62)
      this.controls.update()
    }
  }

  // ===================== 交互 =====================

  private bindEvents() {
    this.canvas.addEventListener('click', this.onClick)
    this.resizeHandler = () => this.onResize()
    window.addEventListener('resize', this.resizeHandler)
  }

  private unbindEvents() {
    this.canvas.removeEventListener('click', this.onClick)
    if (this.resizeHandler) window.removeEventListener('resize', this.resizeHandler)
  }

  private onClick = (event: MouseEvent) => {
    if (!this.visuals.length) return
    const rect = this.canvas.getBoundingClientRect()
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const hits = this.raycaster.intersectObjects(this.nodeGroup.children, true)
    if (!hits.length) {
      this.onPick?.(null)
      return
    }
    let target: THREE.Object3D | null = hits[0].object
    while (target && !target.userData.node_key) target = target.parent
    this.onPick?.(target?.userData.node_key ?? null)
  }

  private onResize() {
    const w = this.canvas.clientWidth
    const h = this.canvas.clientHeight
    if (!w || !h) return
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(w, h, false)
    this.composer?.setSize(w, h)
    this.bloomPass?.setSize(w, h)
    this.labelRenderer?.setSize(w, h)
  }

  private startLoop() {
    const animate = () => {
      this.animId = requestAnimationFrame(animate)
      const t = this.clock.getElapsedTime()
      this.visuals.forEach((v) => {
        v.group.position.y = Math.sin(t * 0.8 + v.group.userData.floatOffset) * 0.05
        if (v.node.status === 'alarm') {
          const mat = v.ring.material as THREE.MeshBasicMaterial
          mat.opacity = 0.35 + Math.abs(Math.sin(t * 2.2)) * 0.55
        }
      })
      if (this.selectedBeam) {
        (this.selectedBeam.material as THREE.MeshBasicMaterial).opacity =
          0.14 + Math.abs(Math.sin(t * 1.6)) * 0.18
      }
      this.controls.update()
      if (this.composer) this.composer.render()
      else this.renderer.render(this.scene, this.camera)
      this.labelRenderer.render(this.scene, this.camera)
    }
    animate()
  }
}
