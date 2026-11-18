/**数字孪生舞台：园区 → 货位 → 设备三级可视化。
 *
 * 与旧版的区别：不再把节点摆成网格盒子，而是加载真实 GLB 场景：
 *  - 园区级加载 park_{hi|lite}.glb，楼栋按 Anchor_Building_xx 定位
 *  - 货位级加载 coldroom_{hi|lite}.glb，货位按 Anchor_Slot_RxxCxxLxSx 定位
 *  - 货位上的冷链箱复用 coldbox 模型，按状态着色
 *  - 设备级沿用库房模型，聚焦到设备锚点并高亮
 *
 * 前端依赖的命名契约：Body_ 着色层、Device_ 可点击设备、Anchor_ 标签锚点。
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'
import { MODEL_BASE, PERF_BUDGET, SCENE_COLOR, resolvePerfBudget } from '@/config/scene'
import { hexToNumber, theme } from '@/config/theme'
import { slotCode } from '@/utils/labels'

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
  model_ref?: string | null
  transform?: Record<string, any> | null
  bindings: TwinBindingLite[]
  children: TwinNodeLite[]
}

export type TwinStageKind = 'park' | 'coldroom'

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
  site: '园区', zone: '库区', building: '冷库', floor: '楼层',
  room: '库房', rack: '货架', slot: '货位', device: '设备',
}

type PickCallback = (nodeKey: string | null) => void

interface NodeVisual {
  node: TwinNodeLite
  group: THREE.Group
  anchor: THREE.Vector3
  pick: THREE.Mesh
  ring: THREE.Mesh | null
  ringMat: THREE.MeshBasicMaterial | null
  labelObj: CSS2DObject
  labelEl: HTMLDivElement
  bodyMats: THREE.MeshStandardMaterial[]
  beaconMats: THREE.MeshBasicMaterial[]
  baseScale: number
  disposables: Array<THREE.BufferGeometry | THREE.Material>
}

interface CamTween {
  t0: number
  dur: number
  fromPos: THREE.Vector3
  toPos: THREE.Vector3
  fromTarget: THREE.Vector3
  toTarget: THREE.Vector3
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
  private pickTargets: THREE.Mesh[] = []
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()
  private onPick: PickCallback | null = null
  private resizeHandler?: () => void
  private selectedKey: string | null = null
  private hoveredKey: string | null = null
  private clock = new THREE.Clock()

  private composer: EffectComposer | null = null
  private bloomPass: UnrealBloomPass | null = null
  private budget = resolvePerfBudget()
  private lod: 'hi' | 'lite' = resolvePerfBudget().pixelRatio < 2 ? 'lite' : 'hi'
  private selectedBeam: THREE.Mesh | null = null
  // 浏览模式：单击不下钻，只保留拖拽/缩放/双击聚焦，避免误触
  private interactionMode: 'browse' | 'operate' = 'browse'
  private downX = 0
  private downY = 0
  private rowSignLabels: CSS2DObject[] = []

  // 真实模型
  private stageKind: TwinStageKind | null = null
  private stageRoot: THREE.Group | null = null
  private stageCache = new Map<string, THREE.Group>()
  private anchors = new Map<string, THREE.Vector3>()
  private coldboxModel: THREE.Group | null = null
  private stageToken = 0
  private sun: THREE.DirectionalLight | null = null

  private defaultCamPos = new THREE.Vector3(140, 170, 210)
  private defaultTarget = new THREE.Vector3(0, 2, 0)
  private fly: CamTween | null = null

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas
  }

  init() {
    this.scene = new THREE.Scene()
    this.scene.fog = new THREE.FogExp2(SCENE_COLOR.background, 0.0012)

    const w = this.canvas.clientWidth || 800
    const h = this.canvas.clientHeight || 600
    // 园区地块 200×160m，近裁面要小、远裁面要大
    this.camera = new THREE.PerspectiveCamera(46, w / h, 0.5, 1600)
    this.camera.position.copy(this.defaultCamPos)

    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: true, alpha: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, this.budget.pixelRatio))
    this.renderer.setSize(w, h, false)
    this.renderer.shadowMap.enabled = PERF_BUDGET.enableShadow
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 0.86

    // 给金属材质一点环境反射，暗场里不发黑
    const pmrem = new THREE.PMREMGenerator(this.renderer)
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    this.scene.environment = envTex
    this.scene.environmentIntensity = 0.2
    pmrem.dispose()

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
    this.controls.maxDistance = 520
    this.controls.maxPolarAngle = Math.PI / 2 - 0.03
    this.controls.target.copy(this.defaultTarget)

    this.buildLights()
    this.buildGround()
    this.scene.add(this.nodeGroup)

    this.setupPostProcessing()
    this.bindEvents()
    this.startLoop()
  }

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
      Math.min(this.budget.bloom.strength, 0.3),
      this.budget.bloom.radius,
      Math.max(this.budget.bloom.threshold, 0.86),
    )
    this.composer.addPass(bloom)
    this.composer.addPass(new OutputPass())
    this.bloomPass = bloom
  }

  setPickCallback(cb: PickCallback) {
    this.onPick = cb
  }

  /** 切换三级场景：kind 决定加载哪个 GLB，nodes 是当前层级的节点 */
  async setStage(kind: TwinStageKind, nodes: TwinNodeLite[]) {
    const token = ++this.stageToken

    if (kind !== this.stageKind) {
      const root = await this.loadStageModel(kind)
      if (!root || token !== this.stageToken) return
      this.installStage(root, kind)
    }

    if (nodes.some((n) => n.node_type === 'slot') && !this.coldboxModel) {
      await this.loadColdbox()
      if (token !== this.stageToken) return
    }

    if (token !== this.stageToken) return
    this.rebuildNodes(nodes)
    this.snapToDefaultView()
    this.applyStageTint()
  }

  /** 同一场景内只刷新颜色与铭牌，不重建模型 */
  updateValues(nodes: TwinNodeLite[]) {
    const byKey = new Map(nodes.map((n) => [n.node_key, n]))
    this.visuals.forEach((v) => {
      const next = byKey.get(v.node.node_key)
      if (!next) return
      v.node = next
      const color = TWIN_STATUS_COLOR[next.status] ?? TWIN_STATUS_COLOR.unknown
      v.ringMat?.color.setHex(color)
      v.bodyMats.forEach((m) => {
        m.emissive.setHex(color)
        m.emissiveIntensity = next.status === 'alarm' ? 0.85 : 0.28
      })
      v.beaconMats.forEach((m) => m.color.setHex(color))
      this.fillLabel(v.labelEl, next, color)
    })
    this.applyStageTint()
    this.setSelected(this.selectedKey)
    this.refreshLabels()
  }

  setSelected(nodeKey: string | null) {
    this.selectedKey = nodeKey
    let picked: NodeVisual | null = null
    this.visuals.forEach((v) => {
      const on = v.node.node_key === nodeKey
      if (v.ringMat) v.ringMat.opacity = on ? 0.95 : v.node.status === 'alarm' ? 0.75 : 0.4
      v.group.scale.setScalar(on ? v.baseScale * 1.04 : v.baseScale)
      if (on) picked = v
    })
    this.updateBeam(picked)
    this.refreshLabels()
  }

  /** 相机飞到某个节点，用于左右栏联动与双击聚焦 */
  focusNode(nodeKey: string) {
    const v = this.visuals.find((item) => item.node.node_key === nodeKey)
    if (!v) return
    const type = v.node.node_type
    const dist = type === 'building' ? 70 : type === 'device' ? 9 : 13
    const dir = this.camera.position.clone().sub(this.controls.target).normalize()
    dir.y = Math.max(dir.y, 0.55)
    dir.normalize()
    const toPos = v.anchor.clone().addScaledVector(dir, dist)
    const toTarget = v.anchor.clone()
    toTarget.y += type === 'building' ? 5 : 0.8
    this.flyTo(toPos, toTarget, 0.85)
  }

  resetView() {
    this.flyTo(this.defaultCamPos, this.defaultTarget, 0.85)
  }

  /** 当前层级节点数量，供外部判断是否为空 */
  get nodeCount() {
    return this.visuals.length
  }

  // ===================== 模型 =====================

  private async loadStageModel(kind: TwinStageKind): Promise<THREE.Group | null> {
    const key = `${kind}_${this.lod}`
    const cached = this.stageCache.get(key)
    if (cached) return cached
    try {
      const gltf = await new GLTFLoader().loadAsync(`${MODEL_BASE}/${key}.glb`)
      const root = gltf.scene
      root.name = `stage_${key}`
      this.prepareModel(root)
      root.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.castShadow = PERF_BUDGET.enableShadow
          obj.receiveShadow = PERF_BUDGET.enableShadow
        }
      })
      this.stageCache.set(key, root)
      return root
    } catch (e) {
      console.error(`[TwinLevelScene] 模型加载失败 ${key}`, e)
      return null
    }
  }

  private async loadColdbox(): Promise<void> {
    const key = `coldbox_${this.lod}`
    const cached = this.stageCache.get(key)
    if (cached) {
      this.coldboxModel = cached
      return
    }
    try {
      const gltf = await new GLTFLoader().loadAsync(`${MODEL_BASE}/${key}.glb`)
      const root = gltf.scene
      this.prepareModel(root)
      root.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.castShadow = PERF_BUDGET.enableShadow
          obj.receiveShadow = PERF_BUDGET.enableShadow
        }
      })
      this.stageCache.set(key, root)
      this.coldboxModel = root
    } catch (e) {
      console.error('[TwinLevelScene] 冷链箱模型加载失败', e)
    }
  }

  /** 压暗 GLB 的浅色材质，贴近大屏暗色科技基调，避免白模过曝 */
  private prepareModel(root: THREE.Group) {
    const seen = new Set<THREE.Material>()
    const tint = new THREE.Color(0x0b2036)
    root.traverse((obj) => {
      if (!(obj instanceof THREE.Mesh)) return
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
      mats.forEach((mat) => {
        if (!(mat instanceof THREE.MeshStandardMaterial) || seen.has(mat)) return
        seen.add(mat)
        mat.color.multiplyScalar(0.52)
        mat.color.lerp(tint, 0.16)
        mat.roughness = THREE.MathUtils.clamp(mat.roughness + 0.1, 0, 1)
        mat.envMapIntensity = 0.45
        // 灯带自发光强度 2.5~3，直接压到 0.9，避免整屏泛白
        if (mat.emissive && mat.emissive.r + mat.emissive.g + mat.emissive.b > 0.05) {
          mat.emissiveIntensity = Math.min(mat.emissiveIntensity, 0.9)
        }
        mat.needsUpdate = true
      })
    })
  }

  private installStage(root: THREE.Group, kind: TwinStageKind) {
    this.clearRowSigns()
    if (this.stageRoot) this.scene.remove(this.stageRoot)
    this.stageRoot = root
    this.stageKind = kind
    this.scene.add(root)
    root.updateMatrixWorld(true)

    this.anchors.clear()
    root.traverse((obj) => {
      if (!obj.name.startsWith('Anchor_')) return
      this.anchors.set(obj.name, new THREE.Vector3().setFromMatrixPosition(obj.matrixWorld))
    })
    this.buildRowSigns(kind)

    const box = new THREE.Box3().setFromObject(root)
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    const span = Math.max(size.x, size.z, 20)

    this.scene.fog = new THREE.FogExp2(SCENE_COLOR.background, kind === 'park' ? 0.0011 : 0.0055)

    const fov = (this.camera.fov * Math.PI) / 180
    const dist = (span / 2 / Math.tan(fov / 2)) * (kind === 'park' ? 1.02 : 0.92)
    const dir = new THREE.Vector3(0.58, 0.66, 0.8).normalize()
    this.defaultTarget.set(center.x, kind === 'park' ? 2 : 3.5, center.z)
    this.defaultCamPos.copy(this.defaultTarget).addScaledVector(dir, dist)

    this.controls.minDistance = kind === 'park' ? 14 : 5
    this.controls.maxDistance = dist * 2.6
    this.camera.near = kind === 'park' ? 0.5 : 0.3
    this.camera.far = dist * 6
    this.camera.updateProjectionMatrix()

    if (this.sun) {
      const s = Math.max(40, span * 0.7)
      this.sun.position.set(s * 0.6, s * 0.9, s * 0.55)
      const cam = this.sun.shadow.camera
      cam.left = -s
      cam.right = s
      cam.top = s
      cam.bottom = -s
      cam.near = 1
      cam.far = s * 4
      cam.updateProjectionMatrix()
    }

    // 园区地面比库房大得多，按场景调整网格可见范围
    const grid = this.scene.getObjectByName('twin-grid')
    if (grid) grid.visible = kind === 'park'
  }

  /** 排端编号牌：冷库场景常显，随 GLB 里的 Anchor_RowSign_Rxx 定位 */
  private buildRowSigns(kind: TwinStageKind) {
    this.clearRowSigns()
    if (kind !== 'coldroom' || !this.stageRoot) return
    this.anchors.forEach((pos, name) => {
      const m = /^Anchor_RowSign_R(\d{2})$/.exec(name)
      if (!m) return
      const el = document.createElement('div')
      el.className = 'twin-row-sign'
      el.textContent = `${m[1]} 排`
      el.style.cssText = [
        'padding:2px 9px', 'border-radius:4px',
        'background:rgba(255,196,0,.92)', 'color:#1a1200',
        'font-size:12px', 'font-weight:700', 'letter-spacing:1px',
        'font-variant-numeric:tabular-nums',
        'border:1px solid rgba(0,0,0,.35)',
        'box-shadow:0 0 12px rgba(255,196,0,.35)',
        'pointer-events:none', 'white-space:nowrap',
      ].join(';')
      const label = new CSS2DObject(el)
      label.position.copy(pos)
      this.stageRoot!.add(label)
      this.rowSignLabels.push(label)
    })
  }

  private clearRowSigns() {
    this.rowSignLabels.forEach((label) => {
      ;(label.element as HTMLElement).remove()
      label.parent?.remove(label)
    })
    this.rowSignLabels = []
  }

  // ===================== 场景 =====================

  private buildLights() {
    this.scene.add(new THREE.HemisphereLight(0x9fd8ff, 0x081727, 0.42))
    this.scene.add(new THREE.AmbientLight(hexToNumber(theme.color.accent.blue), 0.18))

    const sun = new THREE.DirectionalLight(0xffffff, 1.0)
    sun.position.set(90, 130, 80)
    sun.castShadow = PERF_BUDGET.enableShadow
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.bias = -0.0006
    sun.shadow.camera.left = -120
    sun.shadow.camera.right = 120
    sun.shadow.camera.top = 120
    sun.shadow.camera.bottom = -120
    sun.shadow.camera.near = 1
    sun.shadow.camera.far = 400
    this.scene.add(sun)
    this.sun = sun

    const rim = new THREE.PointLight(SCENE_COLOR.accent, 0.9, 220)
    rim.position.set(-70, 55, -60)
    this.scene.add(rim)
  }

  private buildGround() {
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(170, 96),
      new THREE.MeshStandardMaterial({ color: 0x061726, metalness: 0.5, roughness: 0.62 }),
    )
    ground.rotation.x = -Math.PI / 2
    ground.position.y = -0.02
    ground.receiveShadow = true
    ground.name = 'twin-ground'
    this.scene.add(ground)

    const grid = new THREE.GridHelper(340, 68, SCENE_COLOR.accent, SCENE_COLOR.grid)
    ;(grid.material as THREE.Material).opacity = 0.16
    ;(grid.material as THREE.Material).transparent = true
    grid.position.y = 0.01
    grid.name = 'twin-grid'
    this.scene.add(grid)
  }

  // ===================== 节点 =====================

  private rebuildNodes(nodes: TwinNodeLite[]) {
    this.clearNodeVisuals()
    nodes.forEach((node) => {
      const anchor = this.resolveAnchor(node)
      const visual = this.createVisual(node, anchor)
      this.visuals.push(visual)
      this.nodeGroup.add(visual.group)
      this.pickTargets.push(visual.pick)
    })
    this.refreshLabels()
    this.setSelected(this.selectedKey)
  }

  private resolveAnchor(node: TwinNodeLite): THREE.Vector3 {
    const t = node.transform || {}
    const anchorName = typeof t.anchor === 'string' ? t.anchor : ''
    const hit = anchorName ? this.anchors.get(anchorName) : null
    if (hit) return hit.clone()
    return new THREE.Vector3(Number(t.x) || 0, Number(t.y) || 0, Number(t.z) || 0)
  }

  private createVisual(node: TwinNodeLite, anchor: THREE.Vector3): NodeVisual {
    const color = TWIN_STATUS_COLOR[node.status] ?? TWIN_STATUS_COLOR.unknown
    const group = new THREE.Group()
    group.position.copy(anchor)
    group.userData.node_key = node.node_key
    const disposables: Array<THREE.BufferGeometry | THREE.Material> = []
    const bodyMats: THREE.MeshStandardMaterial[] = []
    const beaconMats: THREE.MeshBasicMaterial[] = []

    const isBuilding = node.node_type === 'building' || node.node_type === 'site'
    const isDevice = node.node_type === 'device'
    let ring: THREE.Mesh | null = null
    let ringMat: THREE.MeshBasicMaterial | null = null
    let labelY = 2.4
    let pick: THREE.Mesh

    if (isBuilding) {
      // 冷库/常温仓：屋顶光环 + 竖向光柱 + 可点击包围盒
      const ringGeo = new THREE.RingGeometry(4.6, 5.4, 64)
      ringMat = new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.55, side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending, depthWrite: false,
      })
      ring = new THREE.Mesh(ringGeo, ringMat)
      ring.rotation.x = -Math.PI / 2
      group.add(ring)

      const beamH = 10
      const beamGeo = new THREE.CylinderGeometry(2.2, 3.4, beamH, 24, 1, true)
      const beamMat = new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.1, side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending, depthWrite: false,
      })
      const beam = new THREE.Mesh(beamGeo, beamMat)
      beam.position.y = beamH / 2
      group.add(beam)
      disposables.push(ringGeo, ringMat, beamGeo, beamMat)

      const coreGeo = new THREE.SphereGeometry(0.7, 16, 16)
      const coreMat = new THREE.MeshBasicMaterial({ color })
      const core = new THREE.Mesh(coreGeo, coreMat)
      core.position.y = 0.4
      group.add(core)
      bodyMats.length = 0
      beaconMats.push(coreMat)
      disposables.push(coreGeo, coreMat)

      labelY = 11

      const pickGeo = new THREE.BoxGeometry(60, 15, 44)
      pick = new THREE.Mesh(pickGeo, this.invisibleMaterial())
      pick.position.y = -8
      disposables.push(pickGeo)
      group.add(pick)
    } else if (isDevice) {
      // 设备：冷链箱上方的信号球 + 天线
      group.position.set(anchor.x, anchor.y + 2.2, anchor.z)
      const mastGeo = new THREE.CylinderGeometry(0.045, 0.045, 1.1, 8)
      const mastMat = new THREE.MeshBasicMaterial({ color })
      const mast = new THREE.Mesh(mastGeo, mastMat)
      mast.position.y = 0.55
      group.add(mast)

      const bulbGeo = new THREE.SphereGeometry(0.3, 16, 16)
      const bulbMat = new THREE.MeshBasicMaterial({ color })
      const bulb = new THREE.Mesh(bulbGeo, bulbMat)
      bulb.position.y = 1.2
      group.add(bulb)
      beaconMats.push(mastMat, bulbMat)
      disposables.push(mastGeo, mastMat, bulbGeo, bulbMat)

      const haloGeo = new THREE.RingGeometry(0.55, 0.72, 40)
      ringMat = new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.7, side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending, depthWrite: false,
      })
      ring = new THREE.Mesh(haloGeo, ringMat)
      ring.rotation.x = -Math.PI / 2
      group.add(ring)
      disposables.push(haloGeo, ringMat)

      labelY = 1.9

      const pickGeo = new THREE.SphereGeometry(1.5, 12, 12)
      pick = new THREE.Mesh(pickGeo, this.invisibleMaterial())
      disposables.push(pickGeo)
      group.add(pick)
    } else {
      // 货位：真实冷链箱 + 地面状态环
      if (this.coldboxModel) {
        const box = this.cloneColdbox()
        box.traverse((obj) => {
          if (!(obj instanceof THREE.Mesh)) return
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
          const cloned = mats.map((m) => {
            const copy = m.clone() as THREE.MeshStandardMaterial
            disposables.push(copy)
            if (obj.name.startsWith('Body_') && copy.emissive) {
              copy.emissive.setHex(color)
              copy.emissiveIntensity = node.status === 'alarm' ? 0.85 : 0.3
              bodyMats.push(copy)
            }
            return copy
          })
          obj.material = Array.isArray(obj.material) ? cloned : cloned[0]
          obj.castShadow = PERF_BUDGET.enableShadow
          obj.receiveShadow = PERF_BUDGET.enableShadow
        })
        group.add(box)
      } else {
        const fallbackGeo = new THREE.BoxGeometry(1.2, 1.6, 1.0)
        const fallbackMat = new THREE.MeshStandardMaterial({
          color: 0x16354f, emissive: color, emissiveIntensity: 0.3, metalness: 0.3, roughness: 0.5,
        })
        const fallback = new THREE.Mesh(fallbackGeo, fallbackMat)
        fallback.position.y = 0.8
        group.add(fallback)
        bodyMats.push(fallbackMat)
        disposables.push(fallbackGeo, fallbackMat)
      }

      const ringGeo = new THREE.RingGeometry(0.72, 0.92, 40)
      ringMat = new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.45, side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending, depthWrite: false,
      })
      ring = new THREE.Mesh(ringGeo, ringMat)
      ring.rotation.x = -Math.PI / 2
      ring.position.y = 0.03
      group.add(ring)
      disposables.push(ringGeo, ringMat)

      labelY = 2.3

      const pickGeo = new THREE.BoxGeometry(1.8, 2.2, 1.6)
      pick = new THREE.Mesh(pickGeo, this.invisibleMaterial())
      pick.position.y = 0.9
      disposables.push(pickGeo)
      group.add(pick)
    }

    pick.userData.node_key = node.node_key

    const label = this.createLabel(node, color)
    label.position.y = labelY
    group.add(label)

    group.traverse((obj) => {
      obj.userData.node_key = node.node_key
    })

    return {
      node, group, anchor, pick, ring, ringMat,
      labelObj: label,
      labelEl: label.element as HTMLDivElement,
      bodyMats, beaconMats,
      baseScale: 1,
      disposables,
    }
  }

  private cloneColdbox(): THREE.Group {
    const clone = this.coldboxModel!.clone(true)
    // 共享几何体、克隆材质，避免 24 个货位互相串色
    return clone
  }

  private invisibleMaterial() {
    return new THREE.MeshBasicMaterial({
      transparent: true, opacity: 0, depthWrite: false, colorWrite: false,
    })
  }

  /** 园区模型里的 Body_Status_xx 按楼栋状态着色 */
  private applyStageTint() {
    if (this.stageKind !== 'park' || !this.stageRoot) return
    const buildings = this.visuals.filter(
      (v) => v.node.node_type === 'building' && v.node.model_ref === 'coldroom',
    )
    buildings.forEach((v, index) => {
      const obj = this.stageRoot!.getObjectByName(
        `Body_Status_${String(index + 1).padStart(2, '0')}`,
      )
      if (!obj) return
      const color = TWIN_STATUS_COLOR[v.node.status] ?? TWIN_STATUS_COLOR.unknown
      obj.traverse((m) => {
        if (!(m instanceof THREE.Mesh)) return
        const mat = m.material
        if (mat instanceof THREE.MeshStandardMaterial) {
          mat.emissive.setHex(color)
          mat.emissiveIntensity = v.node.status === 'alarm' ? 0.7 : 0.22
        }
      })
    })
    const ambient = this.stageRoot.getObjectByName('Body_Status_Ambient')
    const ambientNode = this.visuals.find((v) => v.node.node_key === 'bld_ambient')
    if (ambient && ambientNode) {
      const color = TWIN_STATUS_COLOR[ambientNode.node.status] ?? TWIN_STATUS_COLOR.unknown
      ambient.traverse((m) => {
        if (!(m instanceof THREE.Mesh)) return
        const mat = m.material
        if (mat instanceof THREE.MeshStandardMaterial) {
          mat.emissive.setHex(color)
          mat.emissiveIntensity = 0.18
        }
      })
    }
  }

  private createLabel(node: TwinNodeLite, color: number): CSS2DObject {
    const el = document.createElement('div')
    el.className = 'twin-node-label'
    this.fillLabel(el, node, color)
    return new CSS2DObject(el)
  }

  private fillLabel(el: HTMLDivElement, node: TwinNodeLite, color: number) {
    const hex = '#' + color.toString(16).padStart(6, '0')
    el.style.cssText = [
      'min-width:120px', 'max-width:210px', 'padding:6px 10px',
      'border-radius:8px', 'background:rgba(4,16,34,.86)',
      `border:1px solid ${hex}`, 'box-shadow:0 0 14px rgba(0,229,255,.16)',
      'backdrop-filter:blur(6px)', 'pointer-events:none', 'font-family:inherit',
      'text-align:left', 'transition:border-color .2s',
    ].join(';')
    el.innerHTML = ''

    const title = document.createElement('div')
    title.textContent = node.name
    title.style.cssText = 'font-size:12px;font-weight:600;color:#e6f4ff;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'
    el.appendChild(title)

    const meta = document.createElement('div')
    const badge = TWIN_STATUS_TEXT[node.status] || node.status
    const code = node.node_type === 'slot' ? slotCode(node.transform?.anchor as string) : ''
    meta.textContent = code
      ? `货位 ${code} · ${badge}`
      : `${NODE_TYPE_LABEL[node.node_type] || node.node_type} · ${badge}`
    meta.style.cssText = `font-size:10px;color:${hex};margin-top:2px;letter-spacing:.4px`
    el.appendChild(meta)

    const values = node.bindings.filter((b) => b.value !== null).slice(0, 2)
    values.forEach((b) => {
      const row = document.createElement('div')
      const shown = typeof b.value === 'boolean' ? (b.value ? '开' : '关') : `${b.value}${b.unit || ''}`
      row.textContent = `${b.name} ${shown}`
      row.style.cssText = `font-size:10px;color:${theme.color.accent.cyan};margin-top:2px;font-variant-numeric:tabular-nums`
      el.appendChild(row)
    })

    if (!values.length && node.children.length) {
      const row = document.createElement('div')
      row.textContent = `${node.children.length} 个下级`
      row.style.cssText = `font-size:10px;color:${theme.color.text.muted};margin-top:2px`
      el.appendChild(row)
    }
  }

  /** 楼栋/设备常显，货位只在告警、悬停、选中时显示，避免 24 个铭牌互相遮挡 */
  private refreshLabels() {
    this.visuals.forEach((v) => {
      const n = v.node
      const always = n.node_type === 'building' || n.node_type === 'site' || n.node_type === 'device'
      const attention = n.status === 'alarm' || n.status === 'offline' || n.status === 'degraded'
      v.labelObj.visible = always || attention
        || n.node_key === this.selectedKey || n.node_key === this.hoveredKey
    })
  }

  private updateBeam(v: NodeVisual | null) {
    if (this.selectedBeam) {
      this.selectedBeam.parent?.remove(this.selectedBeam)
      this.selectedBeam.geometry.dispose()
      ;(this.selectedBeam.material as THREE.Material).dispose()
      this.selectedBeam = null
    }
    if (!v) return
    const height = v.node.node_type === 'building' ? 18 : v.node.node_type === 'device' ? 3 : 4
    const beam = new THREE.Mesh(
      new THREE.CylinderGeometry(0.6, 1.1, height, 20, 1, true),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(theme.color.accent.cyan),
        transparent: true, opacity: 0.22, side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending, depthWrite: false,
      }),
    )
    beam.position.y = height / 2
    beam.renderOrder = 2
    v.group.add(beam)
    this.selectedBeam = beam
  }

  private clearNodeVisuals() {
    this.selectedBeam = null
    this.visuals.forEach((v) => {
      v.labelEl.remove()
      v.disposables.forEach((d) => d.dispose())
      v.group.clear()
    })
    this.nodeGroup.clear()
    this.visuals = []
    this.pickTargets = []
    this.hoveredKey = null
  }

  // ===================== 相机 =====================

  private snapToDefaultView() {
    this.fly = null
    this.camera.position.copy(this.defaultCamPos)
    this.controls.target.copy(this.defaultTarget)
    this.controls.update()
  }

  private flyTo(pos: THREE.Vector3, target: THREE.Vector3, dur = 0.8) {
    this.fly = {
      t0: performance.now(),
      dur: dur * 1000,
      fromPos: this.camera.position.clone(),
      toPos: pos.clone(),
      fromTarget: this.controls.target.clone(),
      toTarget: target.clone(),
    }
  }

  // ===================== 交互 =====================

  private bindEvents() {
    this.canvas.addEventListener('pointerdown', this.onPointerDown)
    this.canvas.addEventListener('click', this.onClick)
    this.canvas.addEventListener('dblclick', this.onDblClick)
    this.canvas.addEventListener('pointermove', this.onPointerMove)
    this.canvas.addEventListener('pointerleave', this.onPointerLeave)
    this.resizeHandler = () => this.onResize()
    window.addEventListener('resize', this.resizeHandler)
  }

  private unbindEvents() {
    this.canvas.removeEventListener('pointerdown', this.onPointerDown)
    this.canvas.removeEventListener('click', this.onClick)
    this.canvas.removeEventListener('dblclick', this.onDblClick)
    this.canvas.removeEventListener('pointermove', this.onPointerMove)
    this.canvas.removeEventListener('pointerleave', this.onPointerLeave)
    if (this.resizeHandler) window.removeEventListener('resize', this.resizeHandler)
  }

  private pickAt(event: MouseEvent): string | null {
    if (!this.pickTargets.length) return null
    const rect = this.canvas.getBoundingClientRect()
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const hits = this.raycaster.intersectObjects(this.pickTargets, false)
    if (!hits.length) return null
    return (hits[0].object.userData.node_key as string) ?? null
  }

  /** 浏览模式单击不触发下钻；操作模式才响应单击选点 */
  setInteractionMode(mode: 'browse' | 'operate') {
    this.interactionMode = mode
    this.canvas.style.cursor = 'grab'
  }

  private onPointerDown = (event: PointerEvent) => {
    this.downX = event.clientX
    this.downY = event.clientY
  }

  private onClick = (event: MouseEvent) => {
    // 拖动旋转后松手会补发 click，位移超过阈值直接丢弃，避免误触下钻
    if (Math.hypot(event.clientX - this.downX, event.clientY - this.downY) > 6) return
    // 双击的第二下不再当作单击，避免下钻后误选到下一层节点
    if (event.detail > 1) return
    if (this.interactionMode === 'browse') return
    this.onPick?.(this.pickAt(event))
  }

  private onDblClick = (event: MouseEvent) => {
    if (Math.hypot(event.clientX - this.downX, event.clientY - this.downY) > 6) return
    const key = this.pickAt(event)
    if (key) this.focusNode(key)
  }

  private onPointerMove = (event: MouseEvent) => {
    if (!this.pickTargets.length) return
    const key = this.pickAt(event)
    if (key === this.hoveredKey) return
    this.hoveredKey = key
    this.canvas.style.cursor = key && this.interactionMode === 'operate' ? 'pointer' : 'grab'
    this.refreshLabels()
  }

  private onPointerLeave = () => {
    if (!this.hoveredKey) return
    this.hoveredKey = null
    this.canvas.style.cursor = 'grab'
    this.refreshLabels()
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
      const now = performance.now()
      const t = this.clock.getElapsedTime()

      if (this.fly) {
        const k = Math.min(1, (now - this.fly.t0) / this.fly.dur)
        const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2
        this.camera.position.lerpVectors(this.fly.fromPos, this.fly.toPos, e)
        this.controls.target.lerpVectors(this.fly.fromTarget, this.fly.toTarget, e)
        if (k >= 1) this.fly = null
      }

      this.visuals.forEach((v) => {
        if (v.node.status === 'alarm' && v.ringMat) {
          v.ringMat.opacity = 0.45 + Math.abs(Math.sin(t * 2.4)) * 0.5
        }
        if (v.node.node_type === 'device') {
          v.group.position.y = v.anchor.y + 2.2 + Math.sin(t * 1.6) * 0.08
        }
      })

      if (this.selectedBeam) {
        (this.selectedBeam.material as THREE.MeshBasicMaterial).opacity =
          0.14 + Math.abs(Math.sin(t * 1.6)) * 0.16
      }

      this.controls.update()
      if (this.composer) this.composer.render()
      else this.renderer.render(this.scene, this.camera)
      this.labelRenderer.render(this.scene, this.camera)
    }
    animate()
  }

  dispose() {
    cancelAnimationFrame(this.animId)
    this.unbindEvents()
    this.clearRowSigns()
    this.clearNodeVisuals()
    this.composer?.dispose()
    this.composer = null
    this.bloomPass = null
    this.controls?.dispose()
    this.renderer?.dispose()
    this.labelRenderer?.domElement?.remove()
    this.stageCache.forEach((root) => {
      root.traverse((obj) => {
        if (!(obj instanceof THREE.Mesh)) return
        obj.geometry.dispose()
        const m = obj.material
        if (Array.isArray(m)) m.forEach((x) => x.dispose())
        else m?.dispose()
      })
    })
    this.stageCache.clear()
    this.scene?.traverse((obj) => {
      if (!(obj instanceof THREE.Mesh)) return
      if (obj.name.startsWith('twin-')) {
        obj.geometry.dispose()
        const m = obj.material
        if (Array.isArray(m)) m.forEach((x) => x.dispose())
        else m?.dispose()
      }
    })
  }
}
