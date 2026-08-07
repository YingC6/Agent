<template>
  <div class="knowledge-page">
    <a-card class="knowledge-card" :bordered="false">
      <template #title>
        <div class="title-row">
          <div>
            <div class="title">旅行知识库</div>
            <div class="subtitle">管理员可导入 Markdown 攻略，高评分行程会自动沉淀为经验</div>
          </div>
          <a-button type="primary" @click="showImport = true">导入 Markdown</a-button>
        </div>
      </template>

      <a-space class="filters" wrap>
        <a-input v-model:value="city" placeholder="按城市筛选" allow-clear style="width: 220px" />
        <a-select v-model:value="source" allow-clear placeholder="来源" style="width: 180px">
          <a-select-option value="markdown">Markdown 攻略</a-select-option>
          <a-select-option value="rated_trip">高评分行程</a-select-option>
        </a-select>
        <a-button type="primary" @click="loadKnowledge">查询</a-button>
      </a-space>

      <a-list :loading="loading" :data-source="items" item-layout="vertical">
        <template #renderItem="{ item }">
          <a-list-item>
            <template #actions>
              <a-popconfirm title="确定删除这条知识吗？" @confirm="removeKnowledge(item.id)">
                <a class="danger">删除</a>
              </a-popconfirm>
            </template>
            <a-list-item-meta>
              <template #title>{{ item.title }}</template>
              <template #description>
                {{ item.city || '不限城市' }} · {{ item.days || '不限' }} 天 · {{ sourceText(item.source) }} · 使用 {{ item.usage_count }} 次
              </template>
            </a-list-item-meta>
            <div class="tags">
              <a-tag v-for="theme in item.themes" :key="theme" color="blue">{{ theme }}</a-tag>
              <a-tag v-for="keyword in item.keywords.slice(0, 8)" :key="keyword">{{ keyword }}</a-tag>
              <a-tag v-if="item.rating" color="gold">评分 {{ item.rating }}</a-tag>
            </div>
            <div class="content">{{ item.content }}</div>
          </a-list-item>
        </template>
        <template #empty>
          <a-empty description="暂无知识条目" />
        </template>
      </a-list>
    </a-card>

    <a-modal v-model:open="showImport" title="导入 Markdown 攻略" :confirm-loading="importing" width="760px" @ok="submitImport">
      <a-alert type="info" show-icon class="tip" message="可使用 front matter：title、city、days、themes、keywords。" />
      <a-textarea v-model:value="markdown" :rows="14" placeholder="---&#10;title: 成都三日轻松美食攻略&#10;city: 成都&#10;days: 3&#10;themes: 美食,休闲&#10;keywords: 宽窄巷子,锦里,火锅&#10;---&#10;# 成都三日轻松美食攻略" />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { deleteKnowledge, importMarkdownKnowledge, listKnowledge } from '@/services/api'
import type { KnowledgeItem } from '@/types'

const loading = ref(false)
const importing = ref(false)
const showImport = ref(false)
const city = ref('')
const source = ref<string | undefined>()
const markdown = ref('')
const items = ref<KnowledgeItem[]>([])

const sourceText = (value: string) => {
  const map: Record<string, string> = {
    markdown: 'Markdown 攻略',
    rated_trip: '高评分行程'
  }
  return map[value] || value
}

const loadKnowledge = async () => {
  loading.value = true
  try {
    items.value = await listKnowledge({ city: city.value || undefined, source: source.value })
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '加载知识库失败')
  } finally {
    loading.value = false
  }
}

const submitImport = async () => {
  if (!markdown.value.trim()) {
    message.warning('请输入 Markdown 内容')
    return
  }
  importing.value = true
  try {
    await importMarkdownKnowledge(markdown.value)
    message.success('导入成功')
    showImport.value = false
    markdown.value = ''
    await loadKnowledge()
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '导入失败')
  } finally {
    importing.value = false
  }
}

const removeKnowledge = async (id: number) => {
  try {
    await deleteKnowledge(id)
    message.success('删除成功')
    await loadKnowledge()
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '删除失败')
  }
}

onMounted(() => loadKnowledge())
</script>

<style scoped>
.knowledge-page {
  min-height: calc(100vh - 112px);
  padding: 32px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8eefc 100%);
}

.knowledge-card {
  max-width: 1100px;
  margin: 0 auto;
  border-radius: 18px;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.08);
}

.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.title {
  font-size: 22px;
  font-weight: 700;
}

.subtitle {
  margin-top: 4px;
  color: #64748b;
  font-size: 14px;
}

.filters {
  margin-bottom: 24px;
}

.tags {
  margin-bottom: 12px;
}

.content {
  max-height: 120px;
  overflow: hidden;
  color: #475569;
  line-height: 1.7;
  white-space: pre-wrap;
}

.tip {
  margin-bottom: 12px;
}

.danger {
  color: #ff4d4f;
}
</style>
