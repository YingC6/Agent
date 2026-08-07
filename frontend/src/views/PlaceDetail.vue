<template>
  <div class="detail-page">
    <a-spin :spinning="loading">
      <a-card v-if="place" class="detail-card" :bordered="false">
        <a-button type="link" @click="router.push('/discover')">← 返回发现</a-button>
        <div class="hero">
          <div class="cover"><img v-if="place.photo_url" :src="place.photo_url" :alt="place.name" /><span v-else>📍</span></div>
          <div>
            <a-tag color="blue">{{ place.type || '兴趣点' }}</a-tag>
            <h1>{{ place.name }}</h1>
            <p>{{ place.city }} {{ place.address }}</p>
            <p v-if="place.tel">电话：{{ place.tel }}</p>
            <a-rate :value="place.rating" disabled allow-half /><span class="rating">{{ place.rating || '暂无评分' }} · {{ place.review_count }} 条评价</span>
            <div class="actions"><a-button :type="place.is_favorited ? 'primary' : 'default'" @click="favorite">{{ place.is_favorited ? '已收藏' : '收藏' }}（{{ place.favorite_count }}）</a-button><a-button :type="place.is_checked_in ? 'primary' : 'default'" @click="checkinVisible = true">{{ place.is_checked_in ? '已打卡' : '打卡' }}（{{ place.checkin_count }}）</a-button></div>
          </div>
        </div>
        <a-divider />
        <h2>旅行者评价</h2>
        <a-card size="small" class="composer"><a-rate v-model:value="reviewForm.rating" /><a-textarea v-model:value="reviewForm.content" :rows="3" placeholder="分享你的体验" /><a-button type="primary" :loading="reviewing" @click="submitReview">发布评价</a-button></a-card>
        <a-list :data-source="place.reviews"><template #renderItem="{ item }"><a-list-item><a-list-item-meta :title="`${item.author} · ${item.rating} 星`" :description="new Date(item.created_at).toLocaleString()" /><div>{{ item.content || '该用户给出了评分' }}</div></a-list-item></template><template #empty><a-empty description="还没有评价" /></template></a-list>
      </a-card>
    </a-spin>
    <a-modal v-model:open="checkinVisible" title="地点打卡" :confirm-loading="checkingIn" @ok="submitCheckin"><a-textarea v-model:value="checkinNote" :rows="4" placeholder="记录此刻的旅行感受" /></a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { checkinPoi, getCommunityPoi, getPoiPhoto, reviewPoi, togglePoiFavorite } from '@/services/api'
import type { PoiDetail } from '@/types'

const route = useRoute()
const router = useRouter()
const place = ref<PoiDetail | null>(null)
const loading = ref(false)
const reviewing = ref(false)
const checkingIn = ref(false)
const checkinVisible = ref(false)
const checkinNote = ref('')
const reviewForm = reactive({ rating: 5, content: '' })
const poiId = () => String(route.params.poiId)
const loadPlace = async () => { loading.value = true; try { const detail = await getCommunityPoi(poiId()); place.value = { ...detail, photo_url: await getPoiPhoto(detail.name) } } catch (error: any) { message.error(error.response?.data?.detail || '加载地点详情失败'); router.push('/discover') } finally { loading.value = false } }
const updateSummary = (summary: Pick<PoiDetail, 'rating' | 'review_count' | 'favorite_count' | 'checkin_count' | 'is_favorited' | 'is_checked_in'>) => { if (place.value) Object.assign(place.value, summary) }
const favorite = async () => { try { updateSummary(await togglePoiFavorite(poiId())); } catch (error: any) { message.error(error.response?.data?.detail || '操作失败') } }
const submitCheckin = async () => { checkingIn.value = true; try { updateSummary(await checkinPoi(poiId(), checkinNote.value)); message.success('打卡成功'); checkinVisible.value = false; checkinNote.value = '' } catch (error: any) { message.error(error.response?.data?.detail || '打卡失败') } finally { checkingIn.value = false } }
const submitReview = async () => { reviewing.value = true; try { const result = await reviewPoi(poiId(), reviewForm); updateSummary(result.summary); if (place.value && result.review) { const index = place.value.reviews.findIndex((item) => item.id === result.review?.id); if (index >= 0) place.value.reviews.splice(index, 1, result.review); else place.value.reviews.unshift(result.review) }; message.success('评价已发布'); reviewForm.content = '' } catch (error: any) { message.error(error.response?.data?.detail || '发布评价失败') } finally { reviewing.value = false } }
onMounted(loadPlace)
</script>

<style scoped>
.detail-page { min-height: calc(100vh - 112px); padding: 32px; background: linear-gradient(135deg, #f5f7fa 0%, #e8eefc 100%); }.detail-card { max-width: 1100px; margin: 0 auto; border-radius: 18px; box-shadow: 0 20px 60px rgba(15, 23, 42, .08); }.hero { display: flex; gap: 28px; padding: 20px 0; }.cover { flex: 0 0 280px; height: 210px; display: flex; justify-content: center; align-items: center; overflow: hidden; background: linear-gradient(135deg, #dbeafe, #e0e7ff); font-size: 64px; border-radius: 12px; }.cover img { width: 100%; height: 100%; object-fit: cover; }.hero h1 { margin: 12px 0 8px; }.hero p, .rating { color: #64748b; }.rating { margin-left: 12px; }.actions { display: flex; gap: 12px; margin-top: 24px; }.composer { margin-bottom: 18px; }.composer :deep(.ant-input) { margin: 12px 0; } @media (max-width: 576px) { .detail-page { padding: 16px; }.hero { flex-direction: column; }.cover { flex-basis: auto; width: 100%; } }
</style>
