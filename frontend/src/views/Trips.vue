<template>
  <div class="trips-page">
    <a-card class="trips-card" :bordered="false">
      <template #title>
        <div class="title-row">
          <div>
            <div class="title">我的行程</div>
            <div class="subtitle">登录后生成的行程会自动保存到这里</div>
          </div>
          <a-button type="primary" @click="router.push('/')">创建新行程</a-button>
        </div>
      </template>

      <a-input-search
        v-model:value="keyword"
        placeholder="按城市搜索"
        enter-button="搜索"
        allow-clear
        class="search"
        @search="loadTrips(1)"
      />

      <a-list :loading="loading" :data-source="trips" item-layout="vertical">
        <template #renderItem="{ item }">
          <a-list-item>
            <template #actions>
              <a @click="openTrip(item)">查看详情</a>
              <a @click="openRating(item)">{{ item.rating ? '修改评分' : '评分' }}</a>
              <a-popconfirm title="确定删除这个行程吗？" @confirm="removeTrip(item.id)">
                <a class="danger">删除</a>
              </a-popconfirm>
            </template>
            <a-list-item-meta>
              <template #title>
                <a @click="openTrip(item)">{{ item.title }}</a>
              </template>
              <template #description>
                {{ item.city }} · {{ item.start_date }} 至 {{ item.end_date }} · {{ item.travel_days }} 天 · {{ sourceText(item.source) }}
              </template>
            </a-list-item-meta>
            <div class="suggestion">{{ item.plan.overall_suggestions }}</div>
            <a-tag v-if="item.rating" color="gold" class="rating-tag">我的评分：{{ item.rating.rating }} 星</a-tag>
          </a-list-item>
        </template>
        <template #empty>
          <a-empty description="暂无保存的行程" />
        </template>
      </a-list>

      <div class="pagination" v-if="total > pageSize">
        <a-pagination v-model:current="page" :total="total" :page-size="pageSize" @change="loadTrips" />
      </div>
    </a-card>

    <a-modal v-model:open="ratingVisible" title="行程评分" :confirm-loading="ratingLoading" @ok="submitRating">
      <a-rate v-model:value="ratingForm.rating" />
      <a-textarea v-model:value="ratingForm.comment" :rows="4" placeholder="写一句这次行程的优点或改进建议" class="rating-comment" />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { deleteTrip, listTrips, rateTrip } from '@/services/api'
import { useTripStore } from '@/stores/trip'
import type { TripRecord } from '@/types'

const router = useRouter()
const tripStore = useTripStore()
const loading = ref(false)
const keyword = ref('')
const trips = ref<TripRecord[]>([])
const page = ref(1)
const pageSize = 10
const total = ref(0)
const ratingVisible = ref(false)
const ratingLoading = ref(false)
const currentTrip = ref<TripRecord | null>(null)
const ratingForm = ref({ rating: 5, comment: '' })

const sourceText = (source: string) => {
  const sourceMap: Record<string, string> = {
    ai: 'AI 生成',
    optimized: 'AI 优化'
  }
  return sourceMap[source] || source
}

const loadTrips = async (nextPage = page.value) => {
  loading.value = true
  try {
    page.value = nextPage
    const data = await listTrips({ keyword: keyword.value || undefined, page: page.value, page_size: pageSize })
    trips.value = data.items
    total.value = data.total
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '加载行程失败')
  } finally {
    loading.value = false
  }
}

const openTrip = (trip: TripRecord) => {
  tripStore.setPlan(trip.plan)
  tripStore.setConversation(null)
  sessionStorage.setItem('tripId', String(trip.id))
  router.push('/result')
}

const openRating = (trip: TripRecord) => {
  currentTrip.value = trip
  ratingForm.value = {
    rating: trip.rating?.rating || 5,
    comment: trip.rating?.comment || ''
  }
  ratingVisible.value = true
}

const submitRating = async () => {
  if (!currentTrip.value) return
  ratingLoading.value = true
  try {
    await rateTrip(currentTrip.value.id, ratingForm.value)
    message.success('评分已保存')
    ratingVisible.value = false
    await loadTrips(page.value)
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '评分失败')
  } finally {
    ratingLoading.value = false
  }
}

const removeTrip = async (id: number) => {
  try {
    await deleteTrip(id)
    message.success('已删除')
    await loadTrips(page.value)
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '删除失败')
  }
}

onMounted(() => loadTrips())
</script>

<style scoped>
.trips-page {
  min-height: calc(100vh - 112px);
  padding: 32px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8eefc 100%);
}

.trips-card {
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

.search {
  max-width: 420px;
  margin-bottom: 24px;
}

.suggestion {
  color: #475569;
  line-height: 1.7;
}

.rating-tag {
  margin-top: 12px;
}

.rating-comment {
  margin-top: 16px;
}

.danger {
  color: #ff4d4f;
}

.pagination {
  margin-top: 24px;
  text-align: right;
}
</style>
