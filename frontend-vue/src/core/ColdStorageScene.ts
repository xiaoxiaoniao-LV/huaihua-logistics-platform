/**冷链基地 3D 数字孪生场景核心类。
 *
 * 职责：
 *  - 管理 Three.js 场景/相机/渲染器/控制器/光照
 *  - 加载外部 GLB 模型（外部模型优先，无模型时回退程序化几何体）
 *  - 维护「冷链箱/设备 → 业务实体」的映射（userData 存 resource_id/device_id）
 *  - Raycaster 点击拾取，通知 Vue 层弹出设备数据面板
 *  - 资源状态变化时刷新冷链箱颜色
 *
 * 设计参考：smart-warehouse 的 WarehouseScene.ts（场景核心独立于 Vue 组件）。
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import {
  MODEL_BASE,
  MODEL_PATH_MAP,
  STATUS_COLOR,
  PERF_BUDGET,
  DEFAULT_CAMERA,
} from '@/config/scene'

/** 资源项（与 resources store 的 item 结构对齐） */
export interface ResourceItem {
  id: number
  name: string
  type: string
  status: string
  price?: number | null
  location?: string | null
}

/** 设备实时数据（IoT 最新值） */
export interface DeviceTelemetry {
  device_code: string
  temperature?: number | null
  humidity?: number | null
  longitude?: number | null
  latitude?: number | null
  recorded_at?: string
}

/** 拾取回调：点击 3D 对象时触发，返回业务实体信息 */
export interface PickResult {
  resource_id: number
  device_code?: string
  name: string
  type: string
  status: string
  position: THREE.Vector3 // 世界坐标，用于弹窗定位
}

type PickCallback = (result: PickResult | null) => void

export class ColdStorageScene {
  private canvas: HTMLCanvasElement
  private scene!: THREE.Scene
  /** 相机（public，供弹窗组件做屏幕投影） */
  camera!: THREE.PerspectiveCamera
  private renderer!: THREE.WebGLRenderer
  private controls!: OrbitControls
  private animId = 0

  private coldBoxGroup = new THREE.Group() // 所有冷链箱的父组
  private modelCache = new Map<string, THREE.Group>() // 已加载的模型缓存
  private warehouseShell: THREE.Object3D | null = null // 程序化仓库外壳（有真实模型时移除）
  private pickableDevices: THREE.Object3D[] = [] // 仓库模型内的设备节点（可点击）

  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()
  private pickedObject: THREE.Object3D | null = null

  private resources: ResourceItem[] = []
  private telemetryMap = new Map<string, DeviceTelemetry>() // device_code -> 最新数据

  private onPick: PickCallback | null = null
  private resizeHandler?: () => void

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas
  }

  /** 初始化场景（在 onMounted 调用） */
  init() {
    this.buildScene()
    this.buildLights()
    this.buildGround()
    this.buildWarehouseShell()
    this.loadExternalModels() // 异步加载外部模型，失败不影响 fallback
    this.updateColdBoxes() // 先用程序化占位
    this.bindPointerEvents()
    this.startLoop()
  }

  /** 注册拾取回调 */
  setPickCallback(cb: PickCallback) {
    this.onPick = cb
  }

  /** 更新资源列表（触发冷链箱重建+颜色刷新） */
  setResources(resources: ResourceItem[]) {
    this.resources = resources.slice(0, PERF_BUDGET.maxColdBoxes)
    this.updateColdBoxes()
  }

  /** 更新设备实时数据（驱动标签/颜色） */
  setTelemetry(list: DeviceTelemetry[]) {
    this.telemetryMap.clear()
    list.forEach((d) => this.telemetryMap.set(d.device_code, d))
    this.updateDeviceLabels()
  }

  /** 资源状态变化时调用（增量刷新颜色，不重建） */
  refreshColors() {
    this.coldBoxGroup.children.forEach((child) => {
      const rid = child.userData.resource_id as number | undefined
      const res = this.resources.find((r) => r.id === rid)
      if (res) {
        this.applyStatusColor(child, res.status)
      }
    })
  }

  /** 销毁（onUnmounted 调用） */
  dispose() {
    cancelAnimationFrame(this.animId)
    this.unbindPointerEvents()
    this.controls?.dispose()
    this.renderer?.dispose()
    this.scene?.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose()
        const mat = obj.material
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
        else mat.dispose()
      }
    })
  }

  // ===================== 场景构建 =====================

  private buildScene() {
    this.scene = new THREE.Scene()
    this.scene.background = null
    this.scene.fog = new THREE.FogExp2(0x050d1f, 0.015)

    this.camera = new THREE.PerspectiveCamera(
      50,
      this.canvas.clientWidth / this.canvas.clientHeight,
      0.1,
      500,
    )
    this.camera.position.set(...DEFAULT_CAMERA.position)

    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: true, alpha: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, PERF_BUDGET.pixelRatio))
    this.renderer.setSize(this.canvas.clientWidth, this.canvas.clientHeight, false)
    this.renderer.shadowMap.enabled = PERF_BUDGET.enableShadow
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.2

    this.controls = new OrbitControls(this.camera, this.canvas)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.minDistance = 10
    this.controls.maxDistance = 90
    this.controls.maxPolarAngle = Math.PI / 2 - 0.05
    this.controls.target.set(...DEFAULT_CAMERA.target)

    // 冷链箱父组必须先挂到场景，否则后续 group.add 会把箱子从场景摘走
    this.scene.add(this.coldBoxGroup)
  }

  private buildLights() {
    this.scene.add(new THREE.AmbientLight(0x409eff, 0.4))

    const sun = new THREE.DirectionalLight(0xffffff, 1.2)
    sun.position.set(15, 25, 10)
    sun.castShadow = PERF_BUDGET.enableShadow
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.camera.left = -30
    sun.shadow.camera.right = 30
    sun.shadow.camera.top = 30
    sun.shadow.camera.bottom = -30
    this.scene.add(sun)

    const rim1 = new THREE.PointLight(0x00e5ff, 1.5, 60)
    rim1.position.set(-10, 8, -8)
    this.scene.add(rim1)

    const rim2 = new THREE.PointLight(0x00ff88, 1, 50)
    rim2.position.set(10, 6, 8)
    this.scene.add(rim2)
  }

  private buildGround() {
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(80, 80),
      new THREE.MeshStandardMaterial({ color: 0x0a1a36, metalness: 0.7, roughness: 0.3 }),
    )
    ground.rotation.x = -Math.PI / 2
    ground.receiveShadow = true
    this.scene.add(ground)

    const grid = new THREE.GridHelper(80, 40, 0x00e5ff, 0x1a3a5a)
    ;(grid.material as THREE.Material).opacity = 0.2
    ;(grid.material as THREE.Material).transparent = true
    grid.position.y = 0.01
    this.scene.add(grid)
  }

  /** 程序化仓库外壳（fallback，真实模型加载后会被移除） */
  private buildWarehouseShell() {
    const shell = new THREE.Group()
    shell.name = 'FallbackShell'

    // 中心冷链仓库主体
    const warehouse = new THREE.Mesh(
      new THREE.BoxGeometry(6, 5, 4),
      new THREE.MeshStandardMaterial({ color: 0x1e4a7a, metalness: 0.6, roughness: 0.3 }),
    )
    warehouse.position.set(0, 2.5, -4)
    warehouse.castShadow = true
    warehouse.receiveShadow = true
    shell.add(warehouse)

    const topLight = new THREE.Mesh(
      new THREE.BoxGeometry(6.4, 0.15, 4.4),
      new THREE.MeshStandardMaterial({ color: 0x00e5ff, emissive: 0x00e5ff, emissiveIntensity: 1.2 }),
    )
    topLight.position.set(0, 5.1, -4)
    shell.add(topLight)

    // 围墙
    const pillarGeo = new THREE.BoxGeometry(0.4, 4, 0.4)
    const pillarMat = new THREE.MeshStandardMaterial({
      color: 0x1a4a6a, metalness: 0.5, roughness: 0.4, transparent: true, opacity: 0.65,
    })
    ;[[-7, 0], [7, 0], [-7, -8], [7, -8]].forEach(([x, z]) => {
      const p = new THREE.Mesh(pillarGeo, pillarMat)
      p.position.set(x, 2, z)
      p.castShadow = true
      shell.add(p)
    })

    this.warehouseShell = shell
    this.scene.add(shell)
  }

  // ===================== 外部模型加载 =====================

  /** 加载外部 GLB 模型（带 Draco 压缩支持），失败则继续用程序化 fallback */
  private async loadExternalModels() {
    const draco = new DRACOLoader()
    draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/')
    const loader = new GLTFLoader()
    loader.setDRACOLoader(draco)

    for (const [type, relPath] of Object.entries(MODEL_PATH_MAP)) {
      const url = `${MODEL_BASE}${relPath}`
      try {
        const gltf = await loader.loadAsync(url)
        const model = gltf.scene
        // 给模型所有 mesh 开启阴影
        model.traverse((obj) => {
          if (obj instanceof THREE.Mesh) {
            obj.castShadow = PERF_BUDGET.enableShadow
            obj.receiveShadow = true
          }
        })
        if (type === 'warehouse') {
          // 仓库模型作为场景主体：替换程序化外壳，并登记内部设备节点
          if (this.warehouseShell) {
            this.scene.remove(this.warehouseShell)
            this.warehouseShell = null
          }
          this.applyStructureTransparency(model)
          this.registerDeviceNodes(model)
          this.scene.add(model)
        } else {
          this.modelCache.set(type, model)
        }
        console.info(
          `[3D] 模型加载成功: ${type} <- ${url} 尺寸 ${this.describeModel(model)}`,
        )
      } catch {
        // 静默失败，回退程序化几何体
        console.warn(`[3D] 模型加载失败，使用程序化 fallback: ${type} (${url})`)
      }
    }
    // 模型加载完成后重建冷链箱（用真实模型替换占位）
    this.updateColdBoxes()
  }

  /** 模型尺寸与 mesh 数量，便于替换为真实模型后核对包围盒。 */
  private describeModel(model: THREE.Object3D): string {
    const box = new THREE.Box3().setFromObject(model)
    const size = box.getSize(new THREE.Vector3())
    let meshCount = 0
    model.traverse((obj) => {
      if (obj instanceof THREE.Mesh) meshCount += 1
    })
    return `${size.x.toFixed(2)}×${size.y.toFixed(2)}×${size.z.toFixed(2)}m，mesh ${meshCount}`
  }

  /** 把仓库外壳（Structure_*）调成半透明，便于从外部看到库内冷链箱。
   *  月台、货架、冷库、设备等保持不透明，保留实体质感。 */
  private applyStructureTransparency(warehouse: THREE.Object3D) {
    warehouse.traverse((obj) => {
      if (!(obj instanceof THREE.Mesh)) return
      if (!obj.name.startsWith('Structure_')) return
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
      mats.forEach((m) => {
        const mat = m as THREE.MeshStandardMaterial
        if (!mat) return
        mat.transparent = true
        mat.opacity = 0.28
        mat.depthWrite = false
        mat.side = THREE.DoubleSide
        // 半透明墙体不再投射阴影，避免整片压暗库内
        obj.castShadow = false
      })
    })
  }

  /** 把仓库模型里以 Device_ 开头的节点登记为可拾取设备（拆解到设备层） */
  private registerDeviceNodes(warehouse: THREE.Object3D) {
    this.pickableDevices = []
    warehouse.traverse((obj) => {
      if (!obj.name.startsWith('Device_')) return
      obj.userData.device_code = obj.name
      obj.userData.name = obj.name
      obj.userData.type = 'equipment'
      obj.userData.status = 'available'
      obj.userData.isDevice = true
      this.pickableDevices.push(obj)
    })
  }

  // ===================== 冷链箱管理 =====================

  /** 根据资源列表重建冷链箱（外部模型优先，无模型用几何体） */
  private updateColdBoxes() {
    // 清旧（只清组内子节点，组本身保留在场景中）
    this.coldBoxGroup.clear()

    // 仓库建筑本身由 warehouse.glb 承载，不再作为独立物件摆放在场地中
    const items = this.resources.filter((r) => r.type !== 'warehouse')

    // 布局：仓库内部两排 × 多列（仓库footprint 24 x 16，可用区 x∈[-9.5,9.5], z∈[-6,6]）
    const cols = 6
    const gapX = 2.8
    const gapZ = 3.2
    items.forEach((r, i) => {
      const box = this.createColdBox(r)
      const col = i % cols
      const row = Math.floor(i / cols)
      const x = (col - (cols - 1) / 2) * gapX
      const z = -5.5 + row * gapZ
      box.position.set(x, 0, z)
      // 写入业务 ID，供拾取时回溯
      box.userData.resource_id = r.id
      box.userData.name = r.name
      box.userData.type = r.type
      box.userData.status = r.status
      this.applyStatusColor(box, r.status)
      // 只挂到 coldBoxGroup（该组已加入场景），不要再 scene.add 以免被摘下
      this.coldBoxGroup.add(box)
    })
  }

  /** 创建单个物件（优先用缓存的 GLB 模型，否则用几何体）。
   *  返回的 Object3D 原点位于底面中心，便于统一按地面高度摆放。 */
  private createColdBox(r: ResourceItem): THREE.Object3D {
    const cached = this.modelCache.get(r.type)
    if (cached) {
      // GLB 模型自身原点即底面中心，直接克隆
      return cached.clone()
    }
    // fallback：程序化盒子，包一层 Group 使其原点也在底面
    const holder = new THREE.Group()
    const geo = new THREE.BoxGeometry(1.6, 1.2, 1.2)
    const mat = new THREE.MeshStandardMaterial({
      color: 0x409eff, metalness: 0.3, roughness: 0.5,
      emissive: 0x409eff, emissiveIntensity: 0.15,
    })
    const mesh = new THREE.Mesh(geo, mat)
    mesh.name = 'Body'
    mesh.position.y = 0.6
    mesh.castShadow = true
    mesh.receiveShadow = true
    holder.add(mesh)
    return holder
  }

  /** 按资源状态着色：只染主箱体（Body），保留制冷机组/面板等原材质 */
  private applyStatusColor(obj: THREE.Object3D, status: string) {
    const color = STATUS_COLOR[status] || 0x409eff
    const targets: THREE.Mesh[] = []
    obj.traverse((child) => {
      if (child instanceof THREE.Mesh && child.name.startsWith('Body')) targets.push(child)
    })
    // 没有 Body 节点时退化为整体着色
    if (targets.length === 0) {
      obj.traverse((child) => {
        if (child instanceof THREE.Mesh) targets.push(child)
      })
    }
    targets.forEach((mesh) => {
      const mat = mesh.material as THREE.MeshStandardMaterial
      if (!mat?.color) return
      mat.color.setHex(color)
      mat.emissive?.setHex(color)
      mat.emissiveIntensity = 0.18
    })
  }

  // ===================== 设备数据标签 =====================

  /** 更新设备数据（目前驱动颜色，后续可加 Sprite 标签） */
  private updateDeviceLabels() {
    // 预留：根据 telemetryMap 更新冷链箱上的温度标签 Sprite
    // 当前阶段先用颜色体现异常，标签在 AnchoredPopup 中展示
  }

  // ===================== 拾取交互 =====================

  private bindPointerEvents() {
    this.canvas.addEventListener('click', this.onPointerClick)
    this.resizeHandler = () => this.onResize()
    window.addEventListener('resize', this.resizeHandler)
  }

  private unbindPointerEvents() {
    this.canvas.removeEventListener('click', this.onPointerClick)
    if (this.resizeHandler) window.removeEventListener('resize', this.resizeHandler)
  }

  private onPointerClick = (event: MouseEvent) => {
    const rect = this.canvas.getBoundingClientRect()
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

    this.raycaster.setFromCamera(this.pointer, this.camera)
    const candidates = [...this.coldBoxGroup.children, ...this.pickableDevices]
    const hits = this.raycaster.intersectObjects(candidates, true)

    if (hits.length > 0) {
      // 从命中的 mesh 向上找到承载业务信息的节点（resource_id 或 device_code）
      let target: THREE.Object3D | null = hits[0].object
      while (target && !('resource_id' in target.userData) && !('device_code' in target.userData)) {
        target = target.parent
      }
      if (target) {
        this.pickedObject = target
        const worldPos = new THREE.Vector3()
        target.getWorldPosition(worldPos)
        this.onPick?.({
          resource_id: target.userData.resource_id ?? 0,
          device_code: target.userData.device_code,
          name: target.userData.name ?? '',
          type: target.userData.type ?? '',
          status: target.userData.status ?? '',
          position: worldPos,
        })
        return
      }
    }
    // 点空了
    this.pickedObject = null
    this.onPick?.(null)
  }

  private onResize() {
    if (!this.canvas || !this.camera || !this.renderer) return
    const w = this.canvas.clientWidth
    const h = this.canvas.clientHeight
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(w, h, false)
  }

  // ===================== 渲染循环 =====================

  private startLoop() {
    const animate = () => {
      this.animId = requestAnimationFrame(animate)
      this.controls.update()
      this.renderer.render(this.scene, this.camera)
    }
    animate()
  }
}
