<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  createResource, deleteResource, listResources, updateResource, type Resource,
} from '@/api/resources'
import { useAuthStore } from '@/stores/auth'
import AppModal from '@/components/common/AppModal.vue'
import { apiError } from '@/utils/error'

const auth = useAuthStore()

const typeLabels: Record<string, string> = {
  warehouse: '仓库', cold_box: '冷链箱', vehicle: '运力', equipment: '设备',
}
const statusLabels: Record<string, string> = {
  available: '已上架', booked: '已预约', pending: '待审核', offline: '已下架',
}
const statusTag: Record<string, string> = {
  available: 'tag-green', booked: 'tag-orange', pending: 'tag-blue', offline: 'tag-red',
}

const items = ref<Resource[]>([])
const loading = ref(false)
const actionError = ref('')

const mine = computed(() => items.value.filter((r) => r.user_id === auth.user?.id))

async function load() {
  loading.value = true
  try {
    const { data } = await listResources({ page_size: 200 })
    items.value = data
  } finally {
    loading.value = false
  }
}

// ---------- 新增 / 编辑 ----------
const editing = ref<Resource | null>(null)
const showForm = ref(false)
const submitting = ref(false)
const formError = ref('')

const form = reactive({
  type: 'cold_box',
  name: '',
  location: '',
  price: '',
  price_unit: '元/天',
  description: '',
})

function openCreate() {
  editing.value = null
  formError.value = ''
  form.type = 'cold_box'
  form.name = ''
  form.location = ''
  form.price = ''
  form.price_unit = '元/天'
  form.description = ''
  showForm.value = true
}

function openEdit(r: Resource) {
  editing.value = r
  formError.value = ''
  form.type = r.type
  form.name = r.name
  form.location = r.location || ''
  form.price = r.price != null ? String(r.price) : ''
  form.price_unit = r.price_unit || '元/天'
  form.description = r.description || ''
  showForm.value = true
}

async function submitForm() {
  formError.value = ''
  if (!form.name.trim()) {
    formError.value = '请填写资源名称'
    return
  }
  submitting.value = true
  try {
    const payload = {
      type: form.type,
      name: form.name.trim(),
      location: form.location || null,
      price: form.price ? form.price : null,
      price_unit: form.price_unit || null,
      description: form.description || null,
    }
    if (editing.value) {
      await updateResource(editing.value.id, payload)
    } else {
      // 新发布的资源为待审核状态，需管理员审核通过后才会上架
      await createResource(payload)
    }
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = apiError(e, '保存失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 上架 / 下架 / 删除 ----------
async function toggleStatus(r: Resource) {
  actionError.value = ''
  try {
    await updateResource(r.id, { status: r.status === 'available' ? 'offline' : 'available' })
    await load()
  } catch (e) {
    actionError.value = apiError(e, '操作失败')
  }
}

async function removeResource(r: Resource) {
  if (!window.confirm(`确认删除资源「${r.name}」？该操作不可恢复。`)) return
  actionError.value = ''
  try {
    await deleteResource(r.id)
    await load()
  } catch (e) {
    actionError.value = apiError(e, '删除失败')
  }
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  await load()
})
</script>

<template>
  <div class="page-scroll">
    <div class="toolbar">
      <span class="muted" style="font-size: 12px">我发布的资源共 {{ mine.length }} 个</span>
      <span class="spacer"></span>
      <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
      <button class="btn btn-sm" @click="openCreate">发布资源</button>
    </div>

    <div v-if="actionError" class="error-text">{{ actionError }}</div>

    <div class="panel">
      <table class="table">
        <thead>
          <tr>
            <th>资源名称</th>
            <th>类型</th>
            <th>位置</th>
            <th>价格</th>
            <th>状态</th>
            <th style="width: 210px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in mine" :key="r.id">
            <td>{{ r.name }}</td>
            <td class="muted">{{ typeLabels[r.type] || r.type }}</td>
            <td class="muted">{{ r.location || '-' }}</td>
            <td class="mono" style="color: var(--accent-orange)">
              {{ r.price != null ? `¥${r.price}/${r.price_unit || '天'}` : '-' }}
            </td>
            <td>
              <span class="tag" :class="statusTag[r.status] || 'tag-blue'">
                {{ statusLabels[r.status] || r.status }}
              </span>
            </td>
            <td>
              <button class="btn btn-ghost btn-sm" @click="openEdit(r)">编辑</button>
              <button
                v-if="r.status === 'available' || r.status === 'offline'"
                class="btn btn-ghost btn-sm"
                @click="toggleStatus(r)"
              >
                {{ r.status === 'available' ? '下架' : '上架' }}
              </button>
              <span v-if="r.status === 'pending'" class="muted" style="font-size: 11px">
                等待管理员审核
              </span>
              <button
                v-if="r.status !== 'booked'"
                class="btn btn-danger btn-sm"
                @click="removeResource(r)"
              >
                删除
              </button>
            </td>
          </tr>
          <tr v-if="!mine.length">
            <td colspan="6">
              <div class="empty">{{ loading ? '加载中…' : '还没有发布资源，点击右上角「发布资源」' }}</div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppModal v-if="showForm" :title="editing ? '编辑资源' : '发布资源'" @close="showForm = false">
      <div class="field-row">
        <div class="field">
          <label class="field-label">资源类型</label>
          <select v-model="form.type" class="select">
            <option v-for="(label, key) in typeLabels" :key="key" :value="key">{{ label }}</option>
          </select>
        </div>
        <div class="field">
          <label class="field-label">资源名称</label>
          <input v-model="form.name" class="input" placeholder="如：CW-05 冷链箱位" />
        </div>
      </div>

      <div class="field">
        <label class="field-label">位置</label>
        <input v-model="form.location" class="input" placeholder="如：怀化A区" />
      </div>

      <div class="field-row">
        <div class="field">
          <label class="field-label">价格</label>
          <input v-model="form.price" class="input" type="number" min="0" step="0.01" placeholder="如：120" />
        </div>
        <div class="field">
          <label class="field-label">计价单位</label>
          <input v-model="form.price_unit" class="input" placeholder="如：元/天" />
        </div>
      </div>

      <div class="field">
        <label class="field-label">描述（选填）</label>
        <textarea v-model="form.description" class="textarea" placeholder="温区、尺寸等补充说明" />
      </div>

      <div class="error-text">{{ formError }}</div>
      <div v-if="!editing" class="field-hint">提交后需管理员审核通过，才会在资源市场上架</div>

      <template #footer>
        <button class="btn btn-ghost" @click="showForm = false">取消</button>
        <button class="btn" :disabled="submitting" @click="submitForm">
          {{ submitting ? '保存中…' : editing ? '保存' : '提交审核' }}
        </button>
      </template>
    </AppModal>
  </div>
</template>
