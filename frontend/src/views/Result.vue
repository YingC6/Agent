<template>
  <div class="result-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <a-button class="back-button" size="large" @click="goBack">
        ← 返回首页
      </a-button>
      <a-space size="middle">
        <a-button v-if="!editMode" @click="showOptimize = true" type="primary">
          AI 优化
        </a-button>
        <a-button v-if="!editMode" @click="showConversation = true" type="default">
          AI 对话
        </a-button>
        <a-button v-if="!editMode" @click="toggleEditMode" type="default">
          ✏️ 编辑行程
        </a-button>
        <a-button v-else @click="saveChanges" type="primary">
          💾 保存修改
        </a-button>
        <a-button v-if="editMode" @click="cancelEdit" type="default">
          ❌ 取消编辑
        </a-button>

        <!-- 导出按钮 -->
        <a-dropdown v-if="!editMode">
          <template #overlay>
            <a-menu>
              <a-menu-item key="image" @click="exportAsImage">
                📷 导出为图片
              </a-menu-item>
              <a-menu-item key="pdf" @click="exportAsPDF">
                📄 导出为PDF
              </a-menu-item>
            </a-menu>
          </template>
          <a-button type="default">
            📥 导出行程 <DownOutlined />
          </a-button>
        </a-dropdown>
      </a-space>
    </div>

    <div v-if="tripPlan" class="result-layout">
      <div class="content-wrapper">
        <div class="side-nav">
          <a-affix :offset-top="80">
            <a-menu mode="inline" :selected-keys="[activeSection]" @click="scrollToSection">
              <a-menu-item key="overview"><span>📋 行程概览</span></a-menu-item>
              <a-menu-item key="budget" v-if="tripPlan.budget"><span>💰 预算明细</span></a-menu-item>
              <a-menu-item key="map"><span>📍 景点地图</span></a-menu-item>
              <a-sub-menu key="days" title="📅 每日行程">
                <a-menu-item v-for="(day, index) in tripPlan.days" :key="`day-${index}`">第{{ day.day_index + 1 }}天</a-menu-item>
              </a-sub-menu>
              <a-menu-item key="checklist" v-if="tripId"><span>🧳 出行清单</span></a-menu-item>
              <a-menu-item key="weather" v-if="tripPlan.weather_info && tripPlan.weather_info.length > 0"><span>🌤️ 天气信息</span></a-menu-item>
            </a-menu>
          </a-affix>
        </div>

        <div class="main-content">
        <!-- 顶部信息区:左侧概览+预算,右侧地图 -->
        <div class="top-info-section">
          <!-- 左侧:行程概览和预算明细 -->
          <div class="left-info">
            <!-- 行程概览 -->
            <a-card id="overview" :title="`${tripPlan.city}旅行计划`" :bordered="false" class="overview-card">
              <a-alert
                v-if="tripPlan.is_fallback"
                type="warning"
                show-icon
                message="当前展示的是备用行程"
                :description="tripPlan.warnings?.join('；') || 'AI 服务未能完成真实规划，请确认景点、路线和预算后再出行。'"
                class="plan-warning"
              />
              <div class="overview-content">
                <div class="info-item">
                  <span class="info-label">📅 日期:</span>
                  <span class="info-value">{{ tripPlan.start_date }} 至 {{ tripPlan.end_date }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">💡 建议:</span>
                  <span class="info-value">{{ tripPlan.overall_suggestions }}</span>
                </div>
                <div v-if="tripPlan.knowledge_refs?.length" class="info-item">
                  <span class="info-label">📚 参考攻略:</span>
                  <span class="info-value">
                    {{ (tripPlan.knowledge_refs || []).map((item) => item.title).join('、') }}
                  </span>
                </div>
              </div>
            </a-card>

            <a-card id="budget" v-if="tripPlan.budget" title="💰 预算明细" :bordered="false" class="budget-card">
              <div ref="budgetChartRef" class="budget-chart"></div>
              <div class="budget-grid">
                <div class="budget-item">
                  <div class="budget-label">景点门票</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_attractions }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">酒店住宿</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_hotels }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">餐饮费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_meals }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">交通费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_transportation }}</div>
                </div>
              </div>
              <div class="budget-total">
                <span class="total-label">预估总费用</span>
                <span class="total-value">¥{{ tripPlan.budget.total }}</span>
              </div>
            </a-card>
          </div>

          <!-- 右侧:地图 -->
          <div class="right-map">
            <a-card id="map" title="📍 景点地图" :bordered="false" class="map-card">
              <div id="amap-container" style="width: 100%; height: 100%"></div>
            </a-card>
          </div>
        </div>

        <!-- 每日行程:可折叠 -->
        <a-card title="📅 每日行程" :bordered="false" class="days-card">
          <a-collapse v-model:activeKey="activeDays" accordion>
            <a-collapse-panel
              v-for="(day, index) in tripPlan.days"
              :key="index"
              :id="`day-${index}`"
            >
              <template #header>
                <div class="day-header">
                  <span class="day-title">第{{ day.day_index + 1 }}天</span>
                  <span class="day-date">{{ day.date }}</span>
                  <a-tag v-if="day.comfort_level" color="blue">{{ day.comfort_level }}</a-tag>
                  <a-tag v-if="day.estimated_transit_minutes" color="cyan">通勤约 {{ day.estimated_transit_minutes }} 分钟</a-tag>
                </div>
              </template>

              <!-- 行程基本信息 -->
              <div class="day-info">
                <div class="info-row">
                  <span class="label">📝 行程描述:</span>
                  <span class="value">{{ day.description }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🚗 交通方式:</span>
                  <span class="value">{{ day.transportation }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🏨 住宿:</span>
                  <span class="value">{{ day.accommodation }}</span>
                </div>
              </div>

              <a-alert v-if="day.plan_b" class="plan-b-alert" type="info" show-icon :message="`备选方案：${day.plan_b}`" />

              <a-timeline v-if="day.route_segments?.length" class="route-timeline">
                <a-timeline-item v-for="segment in day.route_segments" :key="`${segment.origin}-${segment.destination}`">
                  {{ segment.origin }} → {{ segment.destination }} · {{ segment.route_type }} · {{ segment.distance_km }} km · 约 {{ segment.duration_minutes }} 分钟
                </a-timeline-item>
              </a-timeline>

              <!-- 景点安排 -->
              <a-divider orientation="left">🎯 景点安排</a-divider>
              <a-list
                :data-source="day.attractions"
                :grid="{ gutter: 16, column: 2 }"
              >
                <template #renderItem="{ item, index }">
                  <a-list-item>
                    <a-card :title="item.name" size="small" class="attraction-card">
                      <!-- 编辑模式下的操作按钮 -->
                      <template #extra v-if="editMode">
                        <a-space>
                          <a-button
                            size="small"
                            @click="moveAttraction(day.day_index, index, 'up')"
                            :disabled="index === 0"
                          >
                            ↑
                          </a-button>
                          <a-button
                            size="small"
                            @click="moveAttraction(day.day_index, index, 'down')"
                            :disabled="index === day.attractions.length - 1"
                          >
                            ↓
                          </a-button>
                          <a-button
                            size="small"
                            danger
                            @click="deleteAttraction(day.day_index, index)"
                          >
                            🗑️
                          </a-button>
                        </a-space>
                      </template>

                      <!-- 景点图片 -->
                      <div class="attraction-image-wrapper">
                        <img
                          :src="getAttractionImage(item.name, index)"
                          :alt="item.name"
                          class="attraction-image"
                          @error="handleImageError"
                        />
                        <div class="attraction-badge">
                          <span class="badge-number">{{ index + 1 }}</span>
                        </div>
                        <div v-if="item.ticket_price" class="price-tag">
                          ¥{{ item.ticket_price }}
                        </div>
                      </div>

                      <!-- 编辑模式下可编辑的字段 -->
                      <div v-if="editMode">
                        <p><strong>地址:</strong></p>
                        <a-input v-model:value="item.address" size="small" style="margin-bottom: 8px" />

                        <p><strong>游览时长(分钟):</strong></p>
                        <a-input-number v-model:value="item.visit_duration" :min="10" :max="480" size="small" style="width: 100%; margin-bottom: 8px" />

                        <p><strong>描述:</strong></p>
                        <a-textarea v-model:value="item.description" :rows="2" size="small" style="margin-bottom: 8px" />
                      </div>

                      <!-- 查看模式 -->
                      <div v-else>
                        <p><strong>地址:</strong> {{ item.address }}</p>
                        <p><strong>游览时长:</strong> {{ item.visit_duration }}分钟</p>
                        <p><strong>描述:</strong> {{ item.description }}</p>
                        <p v-if="item.rating"><strong>评分:</strong> {{ item.rating }}⭐</p>
                      </div>
                    </a-card>
                  </a-list-item>
                </template>
              </a-list>

              <!-- 酒店推荐 -->
              <a-divider v-if="day.hotel" orientation="left">🏨 住宿推荐</a-divider>
              <a-card v-if="day.hotel" size="small" class="hotel-card">
                <template #title>
                  <span class="hotel-title">{{ day.hotel.name }}</span>
                </template>
                <a-descriptions :column="2" size="small">
                  <a-descriptions-item label="地址">{{ day.hotel.address }}</a-descriptions-item>
                  <a-descriptions-item label="类型">{{ day.hotel.type }}</a-descriptions-item>
                  <a-descriptions-item label="价格范围">{{ day.hotel.price_range }}</a-descriptions-item>
                  <a-descriptions-item label="评分">{{ day.hotel.rating }}⭐</a-descriptions-item>
                  <a-descriptions-item label="距离" :span="2">{{ day.hotel.distance }}</a-descriptions-item>
                </a-descriptions>
              </a-card>

              <!-- 餐饮安排 -->
              <a-divider orientation="left">🍽️ 餐饮安排</a-divider>
              <a-descriptions :column="1" bordered size="small">
                <a-descriptions-item
                  v-for="meal in day.meals"
                  :key="meal.type"
                  :label="getMealLabel(meal.type)"
                >
                  {{ meal.name }}
                  <span v-if="meal.description"> - {{ meal.description }}</span>
                </a-descriptions-item>
              </a-descriptions>
            </a-collapse-panel>
          </a-collapse>
        </a-card>

        <!-- 出行清单 -->
        <a-card id="checklist" v-if="tripId" title="🧳 出行清单" :bordered="false" class="checklist-card">
          <template #extra>
            <a-space>
              <a-button type="primary" size="small" :loading="generatingChecklist" @click="handleGenerateChecklist">
                ✨ AI 生成
              </a-button>
              <a-button size="small" @click="showAddChecklist = true">
                ➕ 添加条目
              </a-button>
            </a-space>
          </template>
          <div v-if="checklistLoading" class="checklist-loading">
            <a-spin tip="加载清单中..." />
          </div>
          <div v-else-if="checklistResult">
            <a-progress
              :percent="checklistResult!.total ? Math.round(checklistResult!.checked_count / checklistResult!.total * 100) : 0"
              :format="() => `${checklistResult!.checked_count}/${checklistResult!.total}`"
              class="checklist-progress"
            />
            <a-empty v-if="!checklistResult!.total" description="清单为空,点击 AI 生成或手动添加">
              <template #image><div style="font-size: 48px;">🧳</div></template>
            </a-empty>
            <div v-else class="checklist-groups">
              <div v-for="(items, category) in checklistResult!.grouped" :key="category" class="checklist-group">
                <div class="checklist-group-title">{{ category }}</div>
                <a-list :data-source="items" size="small">
                  <template #renderItem="{ item }">
                    <a-list-item class="checklist-item">
                      <a-checkbox :checked="item.is_checked" @change="(e: any) => toggleChecklistItem(item, e.target.checked)">
                        <span :class="{ checked: item.is_checked }">{{ item.content }}</span>
                      </a-checkbox>
                      <template #actions>
                        <a-popconfirm title="确定删除该条目?" @confirm="removeChecklistItem(item.id)">
                          <a-button type="link" size="small" danger>删除</a-button>
                        </a-popconfirm>
                      </template>
                    </a-list-item>
                  </template>
                </a-list>
              </div>
            </div>
          </div>
        </a-card>

        <!-- 添加清单条目弹窗 -->
        <a-modal v-model:open="showAddChecklist" title="添加清单条目" @ok="handleAddChecklistItem">
          <a-form layout="vertical">
            <a-form-item label="分类">
              <a-select v-model:value="newChecklistItem.category">
                <a-select-option value="证件">证件</a-select-option>
                <a-select-option value="衣物">衣物</a-select-option>
                <a-select-option value="电子">电子</a-select-option>
                <a-select-option value="药品">药品</a-select-option>
                <a-select-option value="其他">其他</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="内容">
              <a-input v-model:value="newChecklistItem.content" placeholder="例如:身份证、充电宝" />
            </a-form-item>
          </a-form>
        </a-modal>

        <a-card id="weather" v-if="tripPlan.weather_info && tripPlan.weather_info.length > 0" title="天气信息" style="margin-top: 20px" :bordered="false">
        <a-list
          :data-source="tripPlan.weather_info"
          :grid="{ gutter: 16, column: 3 }"
        >
          <template #renderItem="{ item }">
            <a-list-item>
              <a-card size="small" class="weather-card">
                <div class="weather-date">{{ item.date }}</div>
                <div class="weather-info-row">
                  <span class="weather-icon">☀️</span>
                  <div>
                    <div class="weather-label">白天</div>
                    <div class="weather-value">{{ item.day_weather }} {{ item.day_temp }}°C</div>
                  </div>
                </div>
                <div class="weather-info-row">
                  <span class="weather-icon">🌙</span>
                  <div>
                    <div class="weather-label">夜间</div>
                    <div class="weather-value">{{ item.night_weather }} {{ item.night_temp }}°C</div>
                  </div>
                </div>
                <div class="weather-wind">
                  💨 {{ item.wind_direction }} {{ item.wind_power }}
                </div>
              </a-card>
            </a-list-item>
          </template>
        </a-list>
        </a-card>
      </div>
      </div>
    </div>

    <a-modal v-model:open="showConversation" title="AI 行程对话" width="760px" :footer="null">
      <a-select v-if="versions.length" v-model:value="selectedVersionId" class="version-select" @change="applyVersion">
        <a-select-option v-for="version in versions" :key="version.id" :value="version.id">版本 {{ version.version_number }} · {{ version.source }}</a-select-option>
      </a-select>
      <div class="message-list">
        <div v-for="item in conversation?.messages || []" :key="item.id" :class="['chat-message', item.role]">
          <div>{{ item.content }}</div>
          <small v-if="item.task_status === 'failed'">处理失败</small>
        </div>
        <div v-if="streamingContent" class="chat-message assistant streaming">{{ streamingContent }}<span class="streaming-cursor">▋</span></div>
      </div>
      <a-card v-if="conversationQueryResults.length" size="small" title="查询与参考结果" class="conversation-query-results">
        <div v-for="result in conversationQueryResults" :key="`${result.type}-${result.title}`" class="query-result">
          <strong>{{ result.title }}</strong>
          <template v-if="result.type === 'transport'">
            <div>距离 {{ formatDistance(result.data) }} · 预计 {{ formatDuration(result.data) }} · {{ formatRouteType(result.data) }}</div>
          </template>
          <template v-else-if="result.type === 'knowledge'">
            <div v-for="ref in result.data" :key="ref.id">{{ ref.title }}<span v-if="ref.city"> · {{ ref.city }}</span> · 匹配分 {{ ref.score }}</div>
          </template>
          <template v-else-if="Array.isArray(result.data)">
            <div v-for="poi in result.data" :key="poi.poi_id || poi.name">{{ poi.name }}<span v-if="poi.address"> · {{ poi.address }}</span></div>
          </template>
          <pre v-else>{{ JSON.stringify(result.data, null, 2) }}</pre>
        </div>
      </a-card>
      <a-textarea v-model:value="chatInput" :rows="4" :disabled="chatLoading || !tripId" placeholder="例如：第二天增加博物馆，预算控制在 2000 元内" @pressEnter="handleChatEnter" />
      <div v-if="pendingConversationChange" class="conversation-change-preview">
        <a-alert :message="pendingConversationChange.diff.summary" type="info" show-icon />
        <a-button type="primary" :loading="chatLoading" @click="handleConversationChange('confirm')">确认保存</a-button>
        <a-button :loading="chatLoading" @click="handleConversationChange('cancel')">放弃修改</a-button>
      </div>
      <a-button class="chat-send-button" type="primary" :loading="chatLoading" :disabled="!tripId" @click="sendChatMessage">发送</a-button>
      <div v-if="!tripId" class="chat-hint">请从“我的行程”打开已保存行程后使用多轮对话。</div>
    </a-modal>

    <a-modal v-model:open="showOptimize" title="AI 优化行程" :confirm-loading="optimizing" @ok="submitOptimize">
      <a-textarea
        v-model:value="optimizeInstruction"
        :rows="5"
        placeholder="例如：减少购物安排，增加博物馆；预算控制在 2000 元内；每天不要太赶。"
      />
    </a-modal>

    <!-- 优化差异预览弹窗 -->
    <a-modal
      v-model:open="showDiffPreview"
      title="优化变更预览"
      width="720px"
      :ok-text="'应用优化'"
      :cancel-text="'放弃'"
      :confirm-loading="applyingDiff"
      @ok="applyOptimizeResult"
    >
      <div v-if="pendingOptimize" class="diff-preview">
        <a-alert :message="pendingOptimize.diff.summary" type="info" show-icon class="diff-summary" />
        <div v-if="pendingOptimize.diff.budget_change" class="budget-change">
          <span>预算变化：</span>
          <span class="old">¥{{ pendingOptimize.diff.budget_change.old }}</span>
          <span>→</span>
          <span :class="pendingOptimize.diff.budget_change.delta > 0 ? 'new up' : 'new down'">¥{{ pendingOptimize.diff.budget_change.new }}</span>
          <span :class="pendingOptimize.diff.budget_change.delta > 0 ? 'delta up' : 'delta down'">
            ({{ pendingOptimize.diff.budget_change.delta > 0 ? '+' : '' }}{{ pendingOptimize.diff.budget_change.delta }})
          </span>
        </div>
        <a-empty v-if="!pendingOptimize.diff.days.length" description="无变更" />
        <a-collapse v-else :active-key="pendingOptimize.diff.days.map(d => d.day_index)" class="diff-collapse">
          <a-collapse-panel v-for="day in pendingOptimize.diff.days" :key="day.day_index" :header="`第 ${day.day_index + 1} 天`">
            <div v-if="day.added_attractions.length" class="diff-row">
              <a-tag color="green">新增景点</a-tag>
              <span>{{ day.added_attractions.join('、') }}</span>
            </div>
            <div v-if="day.removed_attractions.length" class="diff-row">
              <a-tag color="red">删除景点</a-tag>
              <span>{{ day.removed_attractions.join('、') }}</span>
            </div>
            <div v-if="day.moved_to.length" class="diff-row">
              <a-tag color="blue">移入景点</a-tag>
              <span>{{ day.moved_to.join('、') }}</span>
            </div>
            <div v-if="day.moved_from.length" class="diff-row">
              <a-tag color="orange">移出景点</a-tag>
              <span>{{ day.moved_from.join('、') }}</span>
            </div>
            <div v-if="day.modified_attractions.length" class="diff-modified">
              <div v-for="(change, idx) in day.modified_attractions" :key="idx" class="diff-row">
                <a-tag color="purple">修改</a-tag>
                <span>{{ change.name }} 的 {{ change.field }}：{{ change.old_value }} → {{ change.new_value }}</span>
              </div>
            </div>
            <div v-if="day.added_meals.length" class="diff-row">
              <a-tag color="green">新增餐饮</a-tag>
              <span>{{ day.added_meals.join('、') }}</span>
            </div>
            <div v-if="day.removed_meals.length" class="diff-row">
              <a-tag color="red">删除餐饮</a-tag>
              <span>{{ day.removed_meals.join('、') }}</span>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </div>
    </a-modal>

    <a-empty v-if="!tripPlan" description="没有找到旅行计划数据">
      <template #image>
        <div style="font-size: 80px;">🗺️</div>
      </template>
      <template #description>
        <span style="color: #999;">暂无旅行计划数据,请先创建行程</span>
      </template>
      <a-button type="primary" @click="goBack">返回首页创建行程</a-button>
    </a-empty>

    <!-- 回到顶部按钮 -->
    <a-back-top :visibility-height="300">
      <div class="back-top-button">
        ↑
      </div>
    </a-back-top>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownOutlined } from '@ant-design/icons-vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import * as echarts from 'echarts'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import { createConversation, getConversation, optimizeTrip, streamConversationMessage, confirmConversationChange, getChecklist, addChecklistItem, generateChecklist, updateChecklistItem, deleteChecklistItem } from '@/services/api'
import { useTripStore } from '@/stores/trip'
import type { Conversation, ConversationQueryResult, TripPlan, TripVersion, OptimizeResult, ChecklistResult, ChecklistCategory } from '@/types'

const router = useRouter()
const tripStore = useTripStore()
const tripPlan = ref<TripPlan | null>(null)
const editMode = ref(false)
const originalPlan = ref<TripPlan | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const activeSection = ref('overview')
const activeDays = ref<number[]>([0])
const budgetChartRef = ref<HTMLDivElement | null>(null)
const showOptimize = ref(false)
const showConversation = ref(false)
const optimizing = ref(false)
const optimizeInstruction = ref('')
const tripId = ref<number | null>(Number(sessionStorage.getItem('tripId')) || null)
const conversation = ref<Conversation | null>(tripStore.conversation)
const versions = ref<TripVersion[]>([])
const selectedVersionId = ref<number | undefined>()
const chatInput = ref('')
const chatLoading = ref(false)
const pendingConversationChange = ref<{ plan: TripPlan; diff: { summary: string; [key: string]: unknown } } | null>(null)
const streamingContent = ref('')
const conversationQueryResults = ref<ConversationQueryResult[]>([])
// 优化差异预览相关状态
const showDiffPreview = ref(false)
const pendingOptimize = ref<OptimizeResult | null>(null)
const applyingDiff = ref(false)
// 出行清单相关状态
const checklistResult = ref<ChecklistResult | null>(null)
const checklistLoading = ref(true)
const generatingChecklist = ref(false)
const showAddChecklist = ref(false)
const newChecklistItem = ref<{ category: ChecklistCategory | string; content: string }>({ category: '其他', content: '' })
let map: any = null
let budgetChart: echarts.ECharts | null = null

onMounted(async () => {
  const data = tripStore.currentPlan || JSON.parse(sessionStorage.getItem('tripPlan') || 'null')
  if (data) {
    tripPlan.value = data
    tripStore.setPlan(data)
    await initializeConversation()
    await loadAttractionPhotos()
    await loadChecklist()
    await nextTick()
    initBudgetChart()
    initMap()
  }
})

const initializeConversation = async () => {
  if (!tripId.value) return
  try {
    conversation.value = conversation.value?.trip_id === tripId.value ? await getConversation(conversation.value.id) : await createConversation(tripId.value)
    tripStore.setConversation(conversation.value)
    versions.value = conversation.value.versions || []
    const currentVersionId = conversation.value.current_version_id
    const activeVersion = conversation.value.messages.map(item => item.version_id).filter((id): id is number => Boolean(id)).at(-1)
    selectedVersionId.value = currentVersionId || activeVersion
  } catch (error: any) {
    message.error(error.response?.data?.detail || '初始化行程对话失败')
  }
}

const applyVersion = (versionId: number) => {
  const version = versions.value.find(item => item.id === versionId)
  if (!version) return
  const nextPlan = JSON.parse(JSON.stringify(version.plan)) as TripPlan
  tripPlan.value = nextPlan
  tripStore.setPlan(nextPlan)
  nextTick(() => {
    initBudgetChart()
    if (map) map.destroy()
    initMap()
  })
}

const sendChatMessage = async () => {
  if (!conversation.value || !chatInput.value.trim()) return
  chatLoading.value = true
  try {
    const content = chatInput.value.trim()
    streamingContent.value = ''
    const reply = await streamConversationMessage(conversation.value.id, content, {
      onMeta: (meta) => { conversationQueryResults.value = meta.query_results },
      onDelta: (delta) => { streamingContent.value += delta }
    })
    streamingContent.value = ''
    conversation.value = reply.conversation
    tripStore.setConversation(reply.conversation)
    versions.value = reply.trip.versions || versions.value
    selectedVersionId.value = reply.conversation.current_version_id
    pendingConversationChange.value = reply.pending_change || null
    conversationQueryResults.value = reply.query_results
    if (reply.message.version_id) applyVersion(reply.message.version_id)
    if (reply.pending_change?.plan && reply.pending_change.diff) {
      tripPlan.value = reply.pending_change.plan
      tripStore.setPlan(reply.pending_change.plan)
      await nextTick()
      initBudgetChart()
      if (map) map.destroy()
      initMap()
    }
    chatInput.value = ''
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '发送失败')
  } finally {
    chatLoading.value = false
  }
}

const handleConversationChange = async (action: 'confirm' | 'cancel') => {
  if (!conversation.value) return
  chatLoading.value = true
  try {
    const reply = await confirmConversationChange(conversation.value.id, action)
    conversation.value = reply.conversation
    tripStore.setConversation(reply.conversation)
    pendingConversationChange.value = null
    if (action === 'confirm') {
      versions.value = reply.trip?.versions || versions.value
      selectedVersionId.value = reply.conversation.current_version_id
      if (reply.trip?.plan) applyVersion(reply.conversation.current_version_id || 0)
      message.success('行程修改已保存')
    } else {
      const version = versions.value.find(item => item.id === selectedVersionId.value)
      if (version) {
        const restored = JSON.parse(JSON.stringify(version.plan)) as TripPlan
        tripPlan.value = restored
        tripStore.setPlan(restored)
        await nextTick()
        initBudgetChart()
        if (map) map.destroy()
        initMap()
      }
      message.info('已放弃候选修改')
    }
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '操作失败')
  } finally {
    chatLoading.value = false
  }
}

const formatDistance = (data: unknown) => {
  const value = (data as { distance_meters?: number }).distance_meters || 0
  return value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${value} m`
}
const formatDuration = (data: unknown) => `${Math.ceil(((data as { duration_seconds?: number }).duration_seconds || 0) / 60)} 分钟`
const formatRouteType = (data: unknown) => ({ walking: '步行', driving: '驾车', transit: '公共交通' }[(data as { route_type?: string }).route_type || 'transit'] || '公共交通')

const handleChatEnter = (event: KeyboardEvent) => {
  if (!event.shiftKey) {
    event.preventDefault()
    sendChatMessage()
  }
}

const goBack = () => {
  router.push('/')
}

// 滚动到指定区域
const scrollToSection = ({ key }: { key: string }) => {
  activeSection.value = key
  const element = document.getElementById(key)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

// 切换编辑模式
const toggleEditMode = () => {
  editMode.value = true
  // 保存原始数据用于取消编辑
  originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))
  message.info('进入编辑模式')
}

// 保存修改
const saveChanges = () => {
  editMode.value = false
  if (tripPlan.value) {
    tripStore.setPlan(tripPlan.value)
  }
  message.success('修改已保存')

  if (map) {
    map.destroy()
  }
  nextTick(() => {
    initBudgetChart()
    initMap()
  })
}

// 取消编辑
const cancelEdit = () => {
  if (originalPlan.value) {
    tripPlan.value = JSON.parse(JSON.stringify(originalPlan.value))
  }
  editMode.value = false
  message.info('已取消编辑')
}

// 删除景点
const deleteAttraction = (dayIndex: number, attrIndex: number) => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  if (day.attractions.length <= 1) {
    message.warning('每天至少需要保留一个景点')
    return
  }

  day.attractions.splice(attrIndex, 1)
  message.success('景点已删除')
}

// 移动景点顺序
const moveAttraction = (dayIndex: number, attrIndex: number, direction: 'up' | 'down') => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  const attractions = day.attractions

  if (direction === 'up' && attrIndex > 0) {
    [attractions[attrIndex], attractions[attrIndex - 1]] = [attractions[attrIndex - 1], attractions[attrIndex]]
  } else if (direction === 'down' && attrIndex < attractions.length - 1) {
    [attractions[attrIndex], attractions[attrIndex + 1]] = [attractions[attrIndex + 1], attractions[attrIndex]]
  }
}

const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = {
    breakfast: '早餐',
    lunch: '午餐',
    dinner: '晚餐',
    snack: '小吃'
  }
  return labels[type] || type
}

const initBudgetChart = () => {
  if (!budgetChartRef.value || !tripPlan.value?.budget) return
  budgetChart?.dispose()
  budgetChart = echarts.init(budgetChartRef.value)
  const budget = tripPlan.value.budget
  budgetChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [
      {
        name: '预算构成',
        type: 'pie',
        radius: ['42%', '70%'],
        center: ['50%', '44%'],
        data: [
          { name: '景点门票', value: budget.total_attractions },
          { name: '酒店住宿', value: budget.total_hotels },
          { name: '餐饮费用', value: budget.total_meals },
          { name: '交通费用', value: budget.total_transportation }
        ]
      }
    ]
  })
}

const submitOptimize = async () => {
  if (!tripPlan.value || !optimizeInstruction.value.trim()) {
    message.warning('请输入优化要求')
    return
  }
  optimizing.value = true
  try {
    const result = await optimizeTrip(tripPlan.value, optimizeInstruction.value)
    pendingOptimize.value = result
    showOptimize.value = false
    showDiffPreview.value = true
    optimizeInstruction.value = ''
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '优化失败')
  } finally {
    optimizing.value = false
  }
}

// 应用优化结果:用户在差异预览弹窗点击"应用优化"后执行
const applyOptimizeResult = async () => {
  if (!pendingOptimize.value) return
  applyingDiff.value = true
  try {
    const optimized = pendingOptimize.value.plan
    tripPlan.value = optimized
    tripStore.setPlan(optimized)
    // 优化后端创建了新行程记录,需同步更新 tripId 和 sessionStorage
    if (pendingOptimize.value.trip) {
      tripId.value = pendingOptimize.value.trip.id
      sessionStorage.setItem('tripId', String(pendingOptimize.value.trip.id))
      // 重置对话:新行程需要新的对话会话
      conversation.value = null
      tripStore.setConversation(null)
    }
    showDiffPreview.value = false
    pendingOptimize.value = null
    message.success('已应用优化后的行程')
    await nextTick()
    initBudgetChart()
    if (map) map.destroy()
    initMap()
    // 重新加载清单(行程内容变化后,清单可能需要重新生成)
    await loadChecklist()
    // 为新行程创建新的对话会话,否则用户打开 AI 对话弹窗时无法发送消息
    if (tripId.value) {
      await initializeConversation()
    }
  } catch (error: any) {
    message.error(error.message || '应用优化失败')
  } finally {
    applyingDiff.value = false
  }
}

// ===== 出行清单 =====
const loadChecklist = async () => {
  if (!tripId.value) return
  checklistLoading.value = true
  try {
    checklistResult.value = await getChecklist(tripId.value)
  } catch (error: any) {
    // 清单接口失败时静默处理,不阻塞行程展示
    console.warn('加载清单失败:', error)
    checklistResult.value = { items: [], grouped: {}, total: 0, checked_count: 0 }
  } finally {
    checklistLoading.value = false
  }
}

const handleGenerateChecklist = async () => {
  if (!tripId.value) return
  generatingChecklist.value = true
  try {
    const created = await generateChecklist(tripId.value)
    message.success(`AI 已生成 ${created.length} 个清单条目`)
    await loadChecklist()
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || 'AI 生成清单失败')
  } finally {
    generatingChecklist.value = false
  }
}

const handleAddChecklistItem = async () => {
  if (!tripId.value) return
  if (!newChecklistItem.value.content.trim()) {
    message.warning('请输入条目内容')
    return
  }
  try {
    await addChecklistItem(tripId.value, {
      category: newChecklistItem.value.category,
      content: newChecklistItem.value.content.trim(),
    })
    message.success('条目已添加')
    newChecklistItem.value = { category: '其他', content: '' }
    showAddChecklist.value = false
    await loadChecklist()
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '添加失败')
  }
}

const toggleChecklistItem = async (item: { id: number; is_checked: boolean }, checked: boolean) => {
  // 乐观更新:先改 UI,失败再回滚
  const original = item.is_checked
  item.is_checked = checked
  if (checklistResult.value) {
    checklistResult.value.checked_count += checked ? 1 : -1
  }
  try {
    await updateChecklistItem(item.id, { is_checked: checked })
  } catch (error: any) {
    item.is_checked = original
    if (checklistResult.value) {
      checklistResult.value.checked_count += original ? 1 : -1
    }
    message.error('更新失败,已回滚')
  }
}

const removeChecklistItem = async (itemId: number) => {
  try {
    await deleteChecklistItem(itemId)
    message.success('条目已删除')
    await loadChecklist()
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '删除失败')
  }
}

// 加载所有景点图片
const loadAttractionPhotos = async () => {
  if (!tripPlan.value) return

  const promises: Promise<void>[] = []

  tripPlan.value.days.forEach(day => {
    day.attractions.forEach(attraction => {
      const promise = fetch(`http://localhost:8000/api/poi/photo?name=${encodeURIComponent(attraction.name)}`)
        .then(res => res.json())
        .then(data => {
          if (data.success && data.data.photo_url) {
            attractionPhotos.value[attraction.name] = data.data.photo_url
          }
        })
        .catch(err => {
          console.error(`获取${attraction.name}图片失败:`, err)
        })

      promises.push(promise)
    })
  })

  await Promise.all(promises)
}

// 获取景点图片
const getAttractionImage = (name: string, index: number): string => {
  // 如果已加载真实图片,返回真实图片
  if (attractionPhotos.value[name]) {
    return attractionPhotos.value[name]
  }

  // 返回一个纯色占位图(避免跨域问题)
  const colors = [
    { start: '#667eea', end: '#764ba2' },
    { start: '#f093fb', end: '#f5576c' },
    { start: '#4facfe', end: '#00f2fe' },
    { start: '#43e97b', end: '#38f9d7' },
    { start: '#fa709a', end: '#fee140' }
  ]
  const colorIndex = index % colors.length
  const { start, end } = colors[colorIndex]

  // 使用base64编码避免中文问题
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
    <defs>
      <linearGradient id="grad${index}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:${start};stop-opacity:1" />
        <stop offset="100%" style="stop-color:${end};stop-opacity:1" />
      </linearGradient>
    </defs>
    <rect width="400" height="300" fill="url(#grad${index})"/>
    <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="24" font-weight="bold" fill="white">${name}</text>
  </svg>`

  return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
}

// 图片加载失败时的处理
const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  // 使用灰色占位图
  img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="300"%3E%3Crect width="400" height="300" fill="%23f0f0f0"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="%23999"%3E图片加载失败%3C/text%3E%3C/svg%3E'
}



// 导出为图片
const exportAsImage = async () => {
  try {
    message.loading({ content: '正在生成图片...', key: 'export', duration: 0 })

    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) {
      throw new Error('未找到内容元素')
    }

    // 创建一个独立的容器
    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5f7fa'
    exportContainer.style.padding = '20px'

    // 复制所有内容
    exportContainer.innerHTML = element.innerHTML

    // 处理地图截图
    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }

    // 移除所有ant-card类,替换为纯div
    const cards = exportContainer.querySelectorAll('.ant-card')
    cards.forEach((card) => {
      const cardEl = card as HTMLElement
      try {
        cardEl.className = '' // 移除所有类
        cardEl.style.setProperty('background-color', '#ffffff')
        cardEl.style.setProperty('border-radius', '12px')
        cardEl.style.setProperty('box-shadow', '0 4px 12px rgba(0, 0, 0, 0.1)')
        cardEl.style.setProperty('margin-bottom', '20px')
        cardEl.style.setProperty('overflow', 'hidden')
      } catch (err) {
        console.error('设置卡片样式失败:', err)
      }
    })

    // 处理卡片头部
    const cardHeads = exportContainer.querySelectorAll('.ant-card-head')
    cardHeads.forEach((head) => {
      const headEl = head as HTMLElement
      try {
        headEl.style.setProperty('background-color', '#667eea')
        headEl.style.setProperty('color', '#ffffff')
        headEl.style.setProperty('padding', '16px 24px')
        headEl.style.setProperty('font-size', '18px')
        headEl.style.setProperty('font-weight', '600')
      } catch (err) {
        console.error('设置卡片头部样式失败:', err)
      }
    })

    // 处理卡片内容
    const cardBodies = exportContainer.querySelectorAll('.ant-card-body')
    cardBodies.forEach((body) => {
      const bodyEl = body as HTMLElement
      bodyEl.style.setProperty('background-color', '#ffffff')
      bodyEl.style.setProperty('padding', '24px')
    })

    // 处理酒店卡片头部
    const hotelCards = exportContainer.querySelectorAll('.hotel-card')
    hotelCards.forEach((card) => {
      const head = card.querySelector('.ant-card-head') as HTMLElement
      if (head) {
        head.style.setProperty('background-color', '#1976d2')
      }
      (card as HTMLElement).style.setProperty('background-color', '#e3f2fd')
    })

    // 处理天气卡片
    const weatherCards = exportContainer.querySelectorAll('.weather-card')
    weatherCards.forEach((card) => {
      (card as HTMLElement).style.setProperty('background-color', '#e0f7fa')
    })

    // 处理预算总计
    const budgetTotal = exportContainer.querySelector('.budget-total')
    if (budgetTotal) {
      const el = budgetTotal as HTMLElement
      el.style.setProperty('background-color', '#667eea')
      el.style.setProperty('color', '#ffffff')
      el.style.setProperty('padding', '20px')
      el.style.setProperty('border-radius', '12px')
      el.style.setProperty('margin-bottom', '20px')
    }

    // 处理预算项
    const budgetItems = exportContainer.querySelectorAll('.budget-item')
    budgetItems.forEach((item) => {
      const el = item as HTMLElement
      el.style.setProperty('background-color', '#f5f7fa')
      el.style.setProperty('padding', '16px')
      el.style.setProperty('border-radius', '8px')
      el.style.setProperty('margin-bottom', '12px')
    })

    // 添加到body(隐藏)
    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)

    const canvas = await html2canvas(exportContainer, {
      backgroundColor: '#f5f7fa',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true
    })

    // 移除容器
    document.body.removeChild(exportContainer)

    // 转换为图片并下载
    const link = document.createElement('a')
    link.download = `旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()

    message.success({ content: '图片导出成功!', key: 'export' })
  } catch (error: any) {
    console.error('导出图片失败:', error)
    message.error({ content: `导出图片失败: ${error.message}`, key: 'export' })
  }
}

// 导出为PDF
const exportAsPDF = async () => {
  try {
    message.loading({ content: '正在生成PDF...', key: 'export', duration: 0 })

    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) {
      throw new Error('未找到内容元素')
    }

    // 创建一个独立的容器
    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5f7fa'
    exportContainer.style.padding = '20px'

    // 复制所有内容
    exportContainer.innerHTML = element.innerHTML

    // 处理地图截图
    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }

    // 移除所有ant-card类,替换为纯div
    const cards = exportContainer.querySelectorAll('.ant-card')
    cards.forEach((card) => {
      const cardEl = card as HTMLElement
      try {
        cardEl.className = ''
        cardEl.style.setProperty('background-color', '#ffffff')
        cardEl.style.setProperty('border-radius', '12px')
        cardEl.style.setProperty('box-shadow', '0 4px 12px rgba(0, 0, 0, 0.1)')
        cardEl.style.setProperty('margin-bottom', '20px')
        cardEl.style.setProperty('overflow', 'hidden')
      } catch (err) {
        console.error('设置卡片样式失败:', err)
      }
    })

    // 处理卡片头部
    const cardHeads = exportContainer.querySelectorAll('.ant-card-head')
    cardHeads.forEach((head) => {
      const headEl = head as HTMLElement
      try {
        headEl.style.setProperty('background-color', '#667eea')
        headEl.style.setProperty('color', '#ffffff')
        headEl.style.setProperty('padding', '16px 24px')
        headEl.style.setProperty('font-size', '18px')
        headEl.style.setProperty('font-weight', '600')
      } catch (err) {
        console.error('设置卡片头部样式失败:', err)
      }
    })

    // 处理卡片内容
    const cardBodies = exportContainer.querySelectorAll('.ant-card-body')
    cardBodies.forEach((body) => {
      const bodyEl = body as HTMLElement
      bodyEl.style.setProperty('background-color', '#ffffff')
      bodyEl.style.setProperty('padding', '24px')
    })

    // 处理酒店卡片头部
    const hotelCards = exportContainer.querySelectorAll('.hotel-card')
    hotelCards.forEach((card) => {
      const head = card.querySelector('.ant-card-head') as HTMLElement
      if (head) {
        head.style.setProperty('background-color', '#1976d2')
      }
      (card as HTMLElement).style.setProperty('background-color', '#e3f2fd')
    })

    // 处理天气卡片
    const weatherCards = exportContainer.querySelectorAll('.weather-card')
    weatherCards.forEach((card) => {
      (card as HTMLElement).style.setProperty('background-color', '#e0f7fa')
    })

    // 处理预算总计
    const budgetTotal = exportContainer.querySelector('.budget-total')
    if (budgetTotal) {
      const el = budgetTotal as HTMLElement
      el.style.setProperty('background-color', '#667eea')
      el.style.setProperty('color', '#ffffff')
      el.style.setProperty('padding', '20px')
      el.style.setProperty('border-radius', '12px')
      el.style.setProperty('margin-bottom', '20px')
    }

    // 处理预算项
    const budgetItems = exportContainer.querySelectorAll('.budget-item')
    budgetItems.forEach((item) => {
      const el = item as HTMLElement
      el.style.setProperty('background-color', '#f5f7fa')
      el.style.setProperty('padding', '16px')
      el.style.setProperty('border-radius', '8px')
      el.style.setProperty('margin-bottom', '12px')
    })

    // 添加到body(隐藏)
    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)

    const canvas = await html2canvas(exportContainer, {
      backgroundColor: '#f5f7fa',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true
    })

    // 移除容器
    document.body.removeChild(exportContainer)

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4'
    })

    const imgWidth = 210 // A4宽度(mm)
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    // 如果内容高度超过一页,分页处理
    let heightLeft = imgHeight
    let position = 0

    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= 297 // A4高度

    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= 297
    }

    pdf.save(`旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.pdf`)

    message.success({ content: 'PDF导出成功!', key: 'export' })
  } catch (error: any) {
    console.error('导出PDF失败:', error)
    message.error({ content: `导出PDF失败: ${error.message}`, key: 'export' })
  }
}

// 初始化地图
const initMap = async () => {
  try {
    const amapKey = import.meta.env.VITE_AMAP_WEB_JS_KEY
    if (!amapKey) return
    ;(window as any)._AMapSecurityConfig = {
      securityJsCode: import.meta.env.VITE_AMAP_SECURITY_KEY || ''
    }

    const AMap = await AMapLoader.load({
      key: amapKey,
      version: '2.0',
      plugins: ['AMap.Marker', 'AMap.Polyline', 'AMap.InfoWindow']
    })

    // 创建地图实例
    map = new AMap.Map('amap-container', {
      zoom: 12,
      center: [116.397128, 39.916527], // 默认中心点(北京)
      viewMode: '3D'
    })

    // 添加景点标记
    addAttractionMarkers(AMap)

    message.success('地图加载成功')
  } catch (error) {
    console.error('地图加载失败:', error)
    message.error('地图加载失败')
  }
}

// 添加景点标记
const addAttractionMarkers = (AMap: any) => {
  if (!tripPlan.value) return

  const markers: any[] = []
  const allAttractions: any[] = []

  // 收集所有景点
  tripPlan.value.days.forEach((day, dayIndex) => {
    day.attractions.forEach((attraction, attrIndex) => {
      if (attraction.location && attraction.location.longitude && attraction.location.latitude) {
        allAttractions.push({
          ...attraction,
          dayIndex,
          attrIndex
        })
      }
    })
  })

  // 创建标记
  allAttractions.forEach((attraction, index) => {
    const marker = new AMap.Marker({
      position: [attraction.location.longitude, attraction.location.latitude],
      title: attraction.name,
      label: {
        content: `<div style="background: #4CAF50; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">${index + 1}</div>`,
        offset: new AMap.Pixel(0, -30)
      }
    })

    // 创建信息窗口
    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding: 10px;">
          <h4 style="margin: 0 0 8px 0;">${attraction.name}</h4>
          <p style="margin: 4px 0;"><strong>地址:</strong> ${attraction.address}</p>
          <p style="margin: 4px 0;"><strong>游览时长:</strong> ${attraction.visit_duration}分钟</p>
          <p style="margin: 4px 0;"><strong>描述:</strong> ${attraction.description}</p>
          <p style="margin: 4px 0; color: #1890ff;"><strong>第${attraction.dayIndex + 1}天 景点${attraction.attrIndex + 1}</strong></p>
        </div>
      `,
      offset: new AMap.Pixel(0, -30)
    })

    // 点击标记显示信息窗口
    marker.on('click', () => {
      infoWindow.open(map, marker.getPosition())
    })

    markers.push(marker)
  })

  // 添加标记到地图
  map.add(markers)

  // 自动调整视野以包含所有标记
  if (allAttractions.length > 0) {
    map.setFitView(markers)
  }

  // 绘制路线
  drawRoutes(AMap, allAttractions)
}

// 绘制路线
const drawRoutes = (AMap: any, attractions: any[]) => {
  if (attractions.length < 2) return

  // 按天分组绘制路线
  const dayGroups: any = {}
  attractions.forEach(attr => {
    if (!dayGroups[attr.dayIndex]) {
      dayGroups[attr.dayIndex] = []
    }
    dayGroups[attr.dayIndex].push(attr)
  })

  // 为每天的景点绘制路线
  Object.values(dayGroups).forEach((dayAttractions: any) => {
    if (dayAttractions.length < 2) return

    const path = dayAttractions.map((attr: any) => [
      attr.location.longitude,
      attr.location.latitude
    ])

    const polyline = new AMap.Polyline({
      path: path,
      strokeColor: '#1890ff',
      strokeWeight: 4,
      strokeOpacity: 0.8,
      strokeStyle: 'solid',
      showDir: true // 显示方向箭头
    })

    map.add(polyline)
  })
}
</script>

<style scoped>
.result-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  padding: 40px 20px;
}

.page-header {
  max-width: 1200px;
  margin: 0 auto 30px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  animation: fadeInDown 0.6s ease-out;
}

.back-button {
  border-radius: 8px;
  font-weight: 500;
}

/* 内容布局 */
.result-layout {
  max-width: 1500px;
  margin: 0 auto;
}

.content-wrapper {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}


.version-select {
  width: 100%;
  margin-bottom: 12px;
}

.message-list {
  max-height: 420px;
  overflow-y: auto;
  margin-bottom: 12px;
}

.chat-message {
  padding: 10px 12px;
  border-radius: 10px;
  margin-bottom: 8px;
  white-space: pre-wrap;
  line-height: 1.5;
}

.chat-message.user {
  background: #e6f4ff;
  margin-left: 24px;
}

.chat-message.assistant {
  background: #f5f5f5;
  margin-right: 24px;
}

.chat-hint {
  color: #999;
  font-size: 12px;
  margin-top: 8px;
}

.conversation-query-results {
  margin-bottom: 12px;
}

.query-result {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
  line-height: 1.7;
}

.query-result:last-child {
  border-bottom: 0;
}

.query-result pre {
  margin: 6px 0 0;
  white-space: pre-wrap;
}

.streaming-cursor {
  animation: blink 0.9s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

.conversation-change-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.conversation-change-preview .ant-alert {
  flex: 1;
  min-width: 240px;
}

.content-wrapper {
  flex: 1;
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  gap: 24px;
}

.side-nav {
  width: 240px;
  flex-shrink: 0;
}

.side-nav :deep(.ant-menu) {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  background: white;
}

.side-nav :deep(.ant-menu-item) {
  margin: 4px 8px;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.side-nav :deep(.ant-menu-item-selected) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.side-nav :deep(.ant-menu-item:hover) {
  background: rgba(102, 126, 234, 0.1);
}

.main-content {
  flex: 1;
  min-width: 0;
}

/* 景点图片样式 */
.attraction-image-wrapper {
  position: relative;
  margin-bottom: 12px;
  border-radius: 8px;
  overflow: hidden;
}

.attraction-image {
  width: 100%;
  height: 200px;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.attraction-image-wrapper:hover .attraction-image {
  transform: scale(1.05);
}

.attraction-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.badge-number {
  font-size: 18px;
}

.price-tag {
  position: absolute;
  top: 12px;
  right: 12px;
  background: rgba(255, 77, 79, 0.9);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-weight: bold;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

/* 天气卡片样式 */
.weather-card {
  background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 100%);
  border: none !important;
  transition: all 0.3s ease;
}

.weather-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
}

.weather-date {
  font-size: 16px;
  font-weight: bold;
  color: #00796b;
  margin-bottom: 12px;
  text-align: center;
}

.weather-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.weather-icon {
  font-size: 24px;
}

.weather-label {
  font-size: 12px;
  color: #666;
}

.weather-value {
  font-size: 16px;
  font-weight: 600;
  color: #00796b;
}

.weather-wind {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(0, 121, 107, 0.2);
  text-align: center;
  color: #00796b;
  font-size: 14px;
}

/* 回到顶部按钮 */
.back-top-button {
  width: 50px;
  height: 50px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  transition: all 0.3s ease;
}

.back-top-button:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}

/* 酒店卡片样式 */
.hotel-card {
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border: none !important;
}

.hotel-card :deep(.ant-card-head) {
  background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
}

.hotel-title {
  color: white !important;
  font-weight: 600;
}

/* 顶部信息区布局 */
.top-info-section {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}

.left-info {
  flex: 0 0 400px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.right-map {
  flex: 1;
}

/* 行程概览卡片 */
.overview-card {
  height: fit-content;
}

.plan-warning {
  margin-bottom: 16px;
}

.overview-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 14px;
  font-weight: 600;
  color: #666;
}

.info-value {
  font-size: 15px;
  color: #333;
  line-height: 1.6;
}

/* 预算卡片 */
.budget-card {
  height: fit-content;
}

.budget-chart {
  width: 100%;
  height: 280px;
  margin-bottom: 12px;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.budget-item {
  text-align: center;
  padding: 12px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.budget-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.budget-value {
  font-size: 20px;
  font-weight: 700;
  color: #1890ff;
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  color: white;
}

.total-label {
  font-size: 16px;
  font-weight: 600;
}

.total-value {
  font-size: 28px;
  font-weight: 700;
}

/* 地图卡片 */
.map-card {
  height: 100%;
  min-height: 500px;
}

.map-card :deep(.ant-card-body) {
  height: calc(100% - 57px);
  padding: 0;
}

/* 每日行程卡片 */
.days-card {
  margin-top: 20px;
}

.day-header {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.day-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.day-date {
  font-size: 14px;
  color: #999;
}

.plan-b-alert {
  margin-bottom: 16px;
}

.route-timeline {
  margin: 16px 0 8px;
}

/* 出行清单样式 */
.checklist-card {
  margin-top: 20px;
}

.checklist-loading {
  text-align: center;
  padding: 40px 0;
}

.checklist-progress {
  margin-bottom: 20px;
}

.checklist-groups {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.checklist-group {
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  padding: 12px;
  border: 1px solid #e8e8e8;
}

.checklist-group-title {
  font-size: 14px;
  font-weight: 600;
  color: #667eea;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 2px solid #667eea;
}

.checklist-item {
  padding: 8px 4px !important;
}

.checklist-item .checked {
  text-decoration: line-through;
  color: #999;
}

/* 优化差异预览样式 */
.diff-preview {
  max-height: 60vh;
  overflow-y: auto;
}

.diff-summary {
  margin-bottom: 16px;
}

.budget-change {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  background: #fafafa;
  border-radius: 8px;
  font-size: 15px;
}

.budget-change .old {
  color: #999;
  text-decoration: line-through;
}

.budget-change .new.up {
  color: #f5222d;
  font-weight: 600;
}

.budget-change .new.down {
  color: #52c41a;
  font-weight: 600;
}

.budget-change .delta.up {
  color: #f5222d;
}

.budget-change .delta.down {
  color: #52c41a;
}

.diff-collapse {
  background: transparent;
}

.diff-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 14px;
  line-height: 1.6;
}

.diff-modified {
  margin-bottom: 8px;
}

.day-info {
  margin-bottom: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.info-row {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-row .label {
  font-weight: 600;
  color: #666;
  min-width: 100px;
}

.info-row .value {
  color: #333;
  flex: 1;
}

/* 卡片样式优化 */
:deep(.ant-card) {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  margin-bottom: 20px;
  transition: all 0.3s ease;
  animation: fadeInUp 0.6s ease-out;
}

:deep(.ant-card:hover) {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

:deep(.ant-card-head) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white !important;
  border-radius: 12px 12px 0 0;
  font-weight: 600;
}

:deep(.ant-card-head-title) {
  color: white !important;
  font-size: 18px;
}

:deep(.ant-card-head-title span) {
  color: white !important;
}

/* Collapse样式 */
:deep(.ant-collapse) {
  border: none;
  background: transparent;
}

:deep(.ant-collapse-item) {
  margin-bottom: 16px;
  border: 1px solid #e8e8e8;
  border-radius: 12px;
  overflow: hidden;
}

:deep(.ant-collapse-header) {
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  padding: 16px 20px !important;
  font-weight: 600;
}

:deep(.ant-collapse-content) {
  border-top: 1px solid #e8e8e8;
}

:deep(.ant-collapse-content-box) {
  padding: 20px;
}

/* 统计卡片样式 */
:deep(.ant-statistic-title) {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

:deep(.ant-statistic-content) {
  font-size: 24px;
  font-weight: 600;
  color: #1890ff;
}

/* 景点卡片样式 */
:deep(.ant-list-item) {
  transition: all 0.3s ease;
}

:deep(.ant-list-item:hover) {
  transform: scale(1.02);
}

/* 动画 */
@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .result-container {
    padding: 20px 10px;
  }

  .page-header {
    flex-direction: column;
    gap: 16px;
  }

  .content-wrapper {
    display: block;
  }

  .side-nav {
    width: 100%;
    margin-bottom: 16px;
  }

  .message-list {
    max-height: 360px;
  }
}
</style>

