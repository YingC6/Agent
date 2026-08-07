<template>
  <div class="community-page">
    <a-card class="community-card" :bordered="false">
      <template #title><div><div class="title">旅行社区</div><div class="subtitle">浏览公开动态，为喜欢的旅行分享点赞并参与讨论</div></div></template>
      <a-card v-if="auth.isLogin" size="small" class="composer">
        <a-textarea v-model:value="postContent" :rows="3" placeholder="分享你的旅行见闻、攻略或心得" />
        <div class="composer-actions"><a-input v-model:value="poiId" allow-clear placeholder="可选：关联 POI ID" /><a-button type="primary" :loading="posting" @click="submitPost">发布动态</a-button></div>
      </a-card>
      <a-alert v-else class="login-hint" type="info" show-icon message="登录后可发布动态、点赞和评论" />
      <a-spin :spinning="loading">
        <a-list :data-source="posts">
          <template #renderItem="{ item }">
            <a-list-item class="post-item">
              <div class="post-header"><strong>{{ item.author }}</strong><span>{{ new Date(item.created_at).toLocaleString() }}</span></div>
              <p class="post-content">{{ item.content }}</p>
              <a-button v-if="auth.isLogin" type="link" :class="{ active: item.is_liked }" @click="likePost(item)">{{ item.is_liked ? '已点赞' : '点赞' }} {{ item.like_count }}</a-button>
              <span v-else class="post-stat">点赞 {{ item.like_count }}</span>
              <a-button type="link" @click="toggleComments(item)">评论 {{ item.comment_count }}</a-button>
              <div v-if="expandedPostId === item.id" class="comments"><a-spin :spinning="loadingPostId === item.id"><div v-for="comment in item.comments || []" :key="comment.id" class="comment"><strong>{{ comment.author }}</strong>：{{ comment.content }}</div><a-empty v-if="!(item.comments || []).length" :image-style="{ height: '32px' }" description="暂无公开评论" /></a-spin><div v-if="auth.isLogin" class="comment-composer"><a-input v-model:value="commentDrafts[item.id]" placeholder="写下你的评论" @pressEnter="submitComment(item)" /><a-button :loading="commentingPostId === item.id" @click="submitComment(item)">评论</a-button></div></div>
            </a-list-item>
          </template>
          <template #empty><a-empty description="暂无公开动态" /></template>
        </a-list>
      </a-spin>
      <div v-if="total > pageSize" class="pagination"><a-pagination v-model:current="page" :total="total" :page-size="pageSize" @change="loadPosts" /></div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { createCommunityPost, createPostComment, getCommunityPost, listCommunityPosts, togglePostLike } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { CommunityPost } from '@/types'

const auth = useAuthStore()
const loading = ref(false)
const posting = ref(false)
const page = ref(1)
const total = ref(0)
const pageSize = 20
const posts = ref<CommunityPost[]>([])
const postContent = ref('')
const poiId = ref('')
const expandedPostId = ref<number | null>(null)
const loadingPostId = ref<number | null>(null)
const commentingPostId = ref<number | null>(null)
const commentDrafts = reactive<Record<number, string>>({})
const loadPosts = async (nextPage = page.value) => { loading.value = true; try { page.value = nextPage; const result = await listCommunityPosts({ page: page.value, page_size: pageSize }); posts.value = result.items; total.value = result.total } catch (error: any) { message.error(error.response?.data?.detail || '加载社区动态失败') } finally { loading.value = false } }
const submitPost = async () => { if (!postContent.value.trim()) { message.warning('请输入动态内容'); return }; posting.value = true; try { const result = await createCommunityPost({ content: postContent.value.trim(), poi_id: poiId.value.trim() || undefined }); message.success(result.status === 'approved' ? '动态已发布' : '动态已提交审核'); postContent.value = ''; poiId.value = ''; await loadPosts(1) } catch (error: any) { message.error(error.response?.data?.detail || '发布动态失败') } finally { posting.value = false } }
const likePost = async (post: CommunityPost) => { try { await togglePostLike(post.id); await loadPosts() } catch (error: any) { message.error(error.response?.data?.detail || '点赞操作失败') } }
const toggleComments = async (post: CommunityPost) => { if (expandedPostId.value === post.id) { expandedPostId.value = null; return }; expandedPostId.value = post.id; loadingPostId.value = post.id; try { const detail = await getCommunityPost(post.id); const index = posts.value.findIndex((item) => item.id === post.id); if (index >= 0) posts.value[index] = detail } catch (error: any) { message.error(error.response?.data?.detail || '加载评论失败') } finally { loadingPostId.value = null } }
const submitComment = async (post: CommunityPost) => { const content = commentDrafts[post.id]?.trim(); if (!content) { message.warning('请输入评论内容'); return }; commentingPostId.value = post.id; try { await createPostComment(post.id, content); message.success('评论已发布'); commentDrafts[post.id] = ''; const detail = await getCommunityPost(post.id); const index = posts.value.findIndex((item) => item.id === post.id); if (index >= 0) posts.value[index] = detail } catch (error: any) { message.error(error.response?.data?.detail || '发布评论失败') } finally { commentingPostId.value = null } }
onMounted(loadPosts)
</script>

<style scoped>
.community-page { min-height: calc(100vh - 112px); padding: 32px; background: linear-gradient(135deg, #f5f7fa 0%, #e8eefc 100%); }.community-card { max-width: 900px; margin: 0 auto; border-radius: 18px; box-shadow: 0 20px 60px rgba(15, 23, 42, .08); }.title { font-size: 22px; font-weight: 700; }.subtitle, .post-header span { color: #64748b; }.composer { margin: 12px 0 24px; }.composer-actions, .comment-composer { display: flex; gap: 12px; margin-top: 12px; }.post-item { display: block; }.post-header { display: flex; justify-content: space-between; gap: 16px; }.post-content { white-space: pre-wrap; margin: 12px 0 4px; }.active { color: #1677ff; }.comments { margin-top: 12px; padding: 12px; border-radius: 8px; background: #f8fafc; }.comment { padding: 6px 0; }.pagination { margin-top: 24px; text-align: right; } @media (max-width: 576px) { .community-page { padding: 16px; }.composer-actions, .comment-composer { flex-direction: column; } }
</style>
