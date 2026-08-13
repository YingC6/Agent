<template>
  <div class="preferences-container">
    <div class="page-header">
      <h2>🎯 我的偏好</h2>
      <p class="subtitle">AI 会根据这些偏好生成更贴合你的行程。支持三类:偏好(喜欢)、避开(不喜欢)、预算(约束)。</p>
    </div>

    <a-card class="add-card">
      <a-form layout="inline">
        <a-form-item label="类型">
          <a-select v-model:value="form.memory_type" style="width: 120px">
            <a-select-option value="preference">偏好</a-select-option>
            <a-select-option value="avoidance">避开</a-select-option>
            <a-select-option value="budget">预算</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="内容">
          <a-input
            v-model:value="form.content"
            placeholder="例如:喜欢博物馆、避开购物、预算2000元内"
            style="width: 360px"
            @press-enter="handleAdd"
          />
        </a-form-item>
        <a-form-item label="重要度">
          <a-rate v-model:value="form.importance" :count="5" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" :loading="adding" @click="handleAdd">添加</a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <a-card class="list-card" title="已有偏好" :loading="loading">
      <a-empty v-if="!preferences.length" description="暂无偏好,添加后 AI 会自动参考" />
      <a-list v-else :data-source="preferences" item-layout="horizontal">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta>
              <template #title>
                <a-tag :color="typeColor(item.memory_type)">{{ typeLabel(item.memory_type) }}</a-tag>
                <span class="content-text">{{ displayContent(item) }}</span>
              </template>
              <template #description>
                <a-rate :value="item.importance" :count="5" disabled />
                <span class="updated-at">更新于 {{ formatDate(item.updated_at) }}</span>
              </template>
            </a-list-item-meta>
            <template #actions>
              <a-button type="link" size="small" @click="openEdit(item)">编辑</a-button>
              <a-popconfirm title="确定删除该偏好?" @confirm="handleDelete(item.id)">
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </a-card>

    <a-modal v-model:open="showEdit" title="编辑偏好" @ok="handleEdit">
      <a-form layout="vertical">
        <a-form-item label="内容">
          <a-input v-model:value="editForm.content" />
        </a-form-item>
        <a-form-item label="重要度">
          <a-rate v-model:value="editForm.importance" :count="5" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { listPreferences, createPreference, updatePreference, deletePreference } from '@/services/api'
import type { UserPreference, PreferenceType } from '@/types'

const preferences = ref<UserPreference[]>([])
const loading = ref(false)
const adding = ref(false)
const showEdit = ref(false)
const form = ref<{ memory_type: PreferenceType; content: string; importance: number }>({
  memory_type: 'preference',
  content: '',
  importance: 3
})
const editForm = ref<{ id: number; content: string; importance: number }>({ id: 0, content: '', importance: 3 })

const typeLabel = (t: PreferenceType) => ({ preference: '偏好', avoidance: '避开', budget: '预算' })[t]
const typeColor = (t: PreferenceType) => ({ preference: 'green', avoidance: 'red', budget: 'gold' })[t]
// 数据库存储时已带前缀(偏好:/避开:/预算:),展示时去掉前缀只显示用户输入部分
const displayContent = (item: UserPreference) => {
  const prefix = { preference: '偏好：', avoidance: '避开：', budget: '预算：' }[item.memory_type]
  return item.content.startsWith(prefix) ? item.content.slice(prefix.length) : item.content
}
const formatDate = (iso: string) => new Date(iso).toLocaleString('zh-CN')

const load = async () => {
  loading.value = true
  try {
    preferences.value = await listPreferences()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '加载偏好失败')
  } finally {
    loading.value = false
  }
}

const handleAdd = async () => {
  if (!form.value.content.trim()) {
    message.warning('请输入偏好内容')
    return
  }
  adding.value = true
  try {
    await createPreference({
      memory_type: form.value.memory_type,
      content: form.value.content.trim(),
      importance: form.value.importance
    })
    message.success('偏好已添加')
    form.value.content = ''
    await load()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '添加失败')
  } finally {
    adding.value = false
  }
}

const openEdit = (item: UserPreference) => {
  editForm.value = { id: item.id, content: displayContent(item), importance: item.importance }
  showEdit.value = true
}

const handleEdit = async () => {
  if (!editForm.value.content.trim()) {
    message.warning('内容不能为空')
    return
  }
  try {
    await updatePreference(editForm.value.id, {
      content: editForm.value.content.trim(),
      importance: editForm.value.importance
    })
    message.success('已更新')
    showEdit.value = false
    await load()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '更新失败')
  }
}

const handleDelete = async (id: number) => {
  try {
    await deletePreference(id)
    message.success('已删除')
    await load()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.preferences-container {
  max-width: 960px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 600;
  color: #333;
}

.subtitle {
  color: #666;
  font-size: 14px;
  margin: 0;
}

.add-card {
  margin-bottom: 20px;
}

.list-card .content-text {
  margin-left: 8px;
  font-size: 15px;
  color: #333;
}

.updated-at {
  margin-left: 12px;
  color: #999;
  font-size: 12px;
}
</style>
