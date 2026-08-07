<template>
  <div class="admin-page">
    <a-card class="admin-card" :bordered="false">
      <template #title><div><div class="title">社区审核与统计</div><div class="subtitle">处理待审核帖子并查看社区互动概况</div></div></template>
      <a-spin :spinning="loading">
        <a-row :gutter="16" class="stats">
          <a-col :xs="12" :md="6"><a-statistic title="待审帖子" :value="stats.posts.pending" /></a-col>
          <a-col :xs="12" :md="6"><a-statistic title="已发布评论" :value="stats.comments.approved" /></a-col>
          <a-col :xs="12" :md="6"><a-statistic title="地点评价" :value="stats.poi_interactions.reviews" /></a-col>
          <a-col :xs="12" :md="6"><a-statistic title="地点打卡" :value="stats.poi_interactions.checkins" /></a-col>
        </a-row>
        <a-descriptions bordered size="small" :column="2" class="details">
          <a-descriptions-item label="帖子">总计 {{ stats.posts.total }} · 已通过 {{ stats.posts.approved }} · 已拒绝 {{ stats.posts.rejected }}</a-descriptions-item>
          <a-descriptions-item label="评论">总计 {{ stats.comments.total }} · 已发布 {{ stats.comments.approved }} · 已拒绝 {{ stats.comments.rejected }}</a-descriptions-item>
          <a-descriptions-item label="收藏数">{{ stats.poi_interactions.favorites }}</a-descriptions-item>
          <a-descriptions-item label="点赞数">{{ stats.poi_interactions.likes }}</a-descriptions-item>
        </a-descriptions>
        <a-tabs>
          <a-tab-pane key="posts" :tab="`待审帖子（${posts.total}）`">
            <a-list :data-source="posts.items" :loading="loading">
              <template #renderItem="{ item }"><a-list-item><template #actions><a-button type="link" @click="moderate(item.id, 'approved')">通过</a-button><a-button type="link" danger @click="moderate(item.id, 'rejected')">拒绝</a-button></template><a-list-item-meta :title="item.author" :description="new Date(item.created_at).toLocaleString()" /><div class="content">{{ item.content }}</div><a-tag v-if="item.poi_id" color="blue">地点 ID：{{ item.poi_id }}</a-tag></a-list-item></template>
              <template #empty><a-empty description="暂无待审核帖子" /></template>
            </a-list>
          </a-tab-pane>
        </a-tabs>
      </a-spin>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { getCommunityStats, listPendingPosts, moderatePost } from '@/services/api'
import type { CommunityStats, ModerationPost, PageResult } from '@/types'

const loading = ref(false)
const stats = reactive<CommunityStats>({ posts: { total: 0, pending: 0, approved: 0, rejected: 0 }, comments: { total: 0, pending: 0, approved: 0, rejected: 0 }, poi_interactions: { favorites: 0, checkins: 0, reviews: 0, likes: 0 } })
const posts = reactive<PageResult<ModerationPost>>({ items: [], total: 0 })

const loadData = async () => {
  loading.value = true
  try {
    const [nextStats, nextPosts] = await Promise.all([getCommunityStats(), listPendingPosts()])
    Object.assign(stats, nextStats)
    Object.assign(posts, nextPosts)
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '加载审核数据失败')
  } finally {
    loading.value = false
  }
}

const moderate = async (id: number, status: 'approved' | 'rejected') => {
  try {
    await moderatePost(id, status)
    message.success(status === 'approved' ? '已通过审核' : '已拒绝')
    await loadData()
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '审核操作失败')
  }
}

onMounted(loadData)
</script>

<style scoped>
.admin-page { min-height: calc(100vh - 112px); padding: 32px; background: linear-gradient(135deg, #f5f7fa 0%, #e8eefc 100%); }
.admin-card { max-width: 1100px; margin: 0 auto; border-radius: 18px; box-shadow: 0 20px 60px rgba(15, 23, 42, .08); }
.title { font-size: 22px; font-weight: 700; }.subtitle { margin-top: 4px; color: #64748b; font-size: 14px; }.stats { margin-bottom: 20px; }.details { margin-bottom: 20px; }.content { margin-bottom: 8px; white-space: pre-wrap; color: #334155; }
@media (max-width: 576px) { .admin-page { padding: 16px; } }
</style>
