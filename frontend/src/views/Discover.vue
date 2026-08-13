<template>
  <div class="discover-page">
    <a-card class="discover-card" :bordered="false">
      <template #title>
        <div><div class="title">发现地点</div><div class="subtitle">直接搜索高德实时 POI，查看地点详情并参与旅行者互动</div></div>
      </template>
      <a-row :gutter="12" class="filters">
        <a-col :xs="24" :md="10"><a-input-search v-model:value="keyword" allow-clear placeholder="搜索景点、餐厅或关键词" enter-button="搜索" @search="loadPois" /></a-col>
        <a-col :xs="24" :md="7"><a-input v-model:value="city" allow-clear placeholder="城市，如北京" @pressEnter="loadPois" /></a-col>
        <a-col :xs="24" :md="7"><a-button @click="resetFilters">重置筛选</a-button></a-col>
      </a-row>
      <a-spin :spinning="loading">
        <a-row v-if="pois.length" :gutter="[20, 20]">
          <a-col v-for="poi in pois" :key="poi.poi_id" :xs="24" :sm="12" :lg="8">
            <a-card hoverable class="place-card" @click="router.push({ name: 'PlaceDetail', params: { poiId: poi.poi_id } })">
              <div class="cover"><img v-if="poi.photo_url" :src="poi.photo_url" :alt="poi.name" /><span v-else>📍</span></div>
              <a-tag color="blue">{{ poi.type || '兴趣点' }}</a-tag>
              <h3>{{ poi.name }}</h3>
              <p class="address">{{ poi.city }} {{ poi.address }}</p>
              <span v-if="poi.tel" class="tel">电话：{{ poi.tel }}</span>
              <a-button class="add-trip-button" type="primary" block @click.stop="addToTrip(poi)">加入待规划地点</a-button>
            </a-card>
          </a-col>
        </a-row>
        <a-empty v-else description="输入关键词后搜索实时地点" />
      </a-spin>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { getPoiPhoto, searchCommunityPois } from '@/services/api'
import { useTripStore } from '@/stores/trip'
import type { CommunityPoi } from '@/types'

const router = useRouter()
const tripStore = useTripStore()
const loading = ref(false)
const keyword = ref('')
const city = ref('')
const pois = ref<CommunityPoi[]>([])

const loadPois = async () => {
  if (!keyword.value.trim()) { message.warning('请输入搜索关键词'); return }
  loading.value = true
  try {
    const results = await searchCommunityPois({ keywords: keyword.value.trim(), city: city.value.trim() || undefined })
    pois.value = await Promise.all(results.map(async (poi) => ({ ...poi, photo_url: await getPoiPhoto(poi.name) })))
  } catch (error: any) { message.error(error.response?.data?.detail || '搜索地点失败') } finally { loading.value = false }
}
const addToTrip = (poi: CommunityPoi) => {
  tripStore.addPendingPoi(poi)
  message.success(`已将“${poi.name}”加入待规划地点`)
}
const resetFilters = () => { keyword.value = ''; city.value = ''; pois.value = [] }
</script>

<style scoped>
.add-trip-button { margin-top: 14px; }.discover-page { min-height: calc(100vh - 112px); padding: 32px; background: linear-gradient(135deg, #f5f7fa 0%, #e8eefc 100%); }.discover-card { max-width: 1200px; margin: 0 auto; border-radius: 18px; box-shadow: 0 20px 60px rgba(15, 23, 42, .08); }.title { font-size: 22px; font-weight: 700; }.subtitle, .address, .tel { color: #64748b; }.filters { margin: 12px 0 24px; }.place-card { height: 100%; border-radius: 14px; }.cover { height: 130px; margin: -24px -24px 16px; display: flex; justify-content: center; align-items: center; overflow: hidden; background: linear-gradient(135deg, #dbeafe, #e0e7ff); font-size: 42px; }.cover img { width: 100%; height: 100%; object-fit: cover; }.place-card h3 { margin: 12px 0 8px; }.address { min-height: 42px; margin: 0 0 8px; }.tel { font-size: 13px; } @media (max-width: 576px) { .discover-page { padding: 16px; } }
</style>
