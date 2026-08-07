import axios from 'axios'
import type { AuthResponse, Conversation, ConversationReply, CommunityPoi, CommunityPost, CommunityStats, KnowledgeItem, ModerationComment, ModerationPost, PageResult, PoiActionResponse, PoiDetail, PoiInteractionSummary, TripFormData, TripPlan, TripPlanResponse, TripRating, TripRecord, UserInfo } from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({ baseURL: API_BASE_URL, timeout: 180000, headers: { 'Content-Type': 'application/json' } })
apiClient.interceptors.request.use((config) => { const token = localStorage.getItem('token'); if (token) config.headers.Authorization = `Bearer ${token}`; return config })
apiClient.interceptors.response.use((response) => response, (error) => { if (error.response?.status === 401) { localStorage.removeItem('token'); localStorage.removeItem('user') }; return Promise.reject(error) })

export async function register(data: { username: string; password: string; nickname: string }): Promise<AuthResponse> { return (await apiClient.post<AuthResponse>('/api/auth/register', data)).data }
export async function login(data: { username: string; password: string; nickname?: string }): Promise<AuthResponse> { return (await apiClient.post<AuthResponse>('/api/auth/login', data)).data }
export async function getMe(): Promise<UserInfo> { return (await apiClient.get<UserInfo>('/api/auth/me')).data }
export async function parseTripText(text: string): Promise<TripFormData> { return (await apiClient.post<{ success: boolean; data: TripFormData }>('/api/trip/parse', { text })).data.data }
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> { return (await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)).data }
export function createTripStreamUrl(formData: TripFormData): string { const params = new URLSearchParams({ city: formData.city, start_date: formData.start_date, end_date: formData.end_date, travel_days: String(formData.travel_days), transportation: formData.transportation, accommodation: formData.accommodation, preferences: formData.preferences.join(','), free_text_input: formData.free_text_input || '' }); const token = localStorage.getItem('token'); if (token) params.set('token', token); return `${API_BASE_URL}/api/trip/plan/stream?${params.toString()}` }
export async function optimizeTrip(plan: TripPlan, instruction: string): Promise<TripPlan> { return (await apiClient.post<{ success: boolean; data: { plan: TripPlan } }>('/api/trip/optimize', { plan, instruction })).data.data.plan }
export async function listTrips(params: { keyword?: string; page?: number; page_size?: number }): Promise<PageResult<TripRecord>> { return (await apiClient.get<{ success: boolean; data: PageResult<TripRecord> }>('/api/trips', { params })).data.data }
export async function getTrip(id: number): Promise<TripRecord> { return (await apiClient.get<{ success: boolean; data: TripRecord }>(`/api/trips/${id}`)).data.data }
export async function rateTrip(id: number, data: { rating: number; comment: string }): Promise<TripRating> { return (await apiClient.post<{ success: boolean; data: TripRating }>(`/api/trips/${id}/rating`, data)).data.data }
export async function deleteTrip(id: number): Promise<void> { await apiClient.delete(`/api/trips/${id}`) }
export async function createConversation(tripId: number, title = '旅行计划对话'): Promise<Conversation> { return (await apiClient.post<{ success: boolean; data: Conversation }>('/api/conversations', { trip_id: tripId, title })).data.data }
export async function getConversation(id: number): Promise<Conversation> { return (await apiClient.get<{ success: boolean; data: Conversation }>(`/api/conversations/${id}`)).data.data }
export async function sendConversationMessage(id: number, content: string): Promise<ConversationReply> { return (await apiClient.post<{ success: boolean; data: ConversationReply }>(`/api/conversations/${id}/messages`, { content })).data.data }
export async function listKnowledge(params: { city?: string; source?: string } = {}): Promise<KnowledgeItem[]> { return (await apiClient.get<{ success: boolean; data: KnowledgeItem[] }>('/api/knowledge', { params })).data.data }
export async function importMarkdownKnowledge(markdown: string): Promise<KnowledgeItem> { return (await apiClient.post<{ success: boolean; data: KnowledgeItem }>('/api/knowledge/import-markdown', { markdown })).data.data }
export async function deleteKnowledge(id: number): Promise<void> { await apiClient.delete(`/api/knowledge/${id}`) }
export async function searchCommunityPois(params: { keywords: string; city?: string; citylimit?: boolean }): Promise<CommunityPoi[]> { return (await apiClient.get<{ success: boolean; data: CommunityPoi[] }>('/api/community/pois/search', { params })).data.data }
export async function getPoiPhoto(name: string): Promise<string | null> { return (await apiClient.get<{ success: boolean; data: { photo_url: string | null } }>('/api/poi/photo', { params: { name } })).data.data.photo_url }
export async function getCommunityPoi(poiId: string): Promise<PoiDetail> { return (await apiClient.get<{ success: boolean; data: PoiDetail }>(`/api/community/pois/${encodeURIComponent(poiId)}`)).data.data }
export async function togglePoiFavorite(poiId: string): Promise<PoiInteractionSummary> { return (await apiClient.post<{ success: boolean; data: PoiInteractionSummary }>(`/api/community/pois/${encodeURIComponent(poiId)}/favorite`)).data.data }
export async function checkinPoi(poiId: string, note: string): Promise<PoiInteractionSummary> { return (await apiClient.post<{ success: boolean; data: PoiInteractionSummary }>(`/api/community/pois/${encodeURIComponent(poiId)}/checkin`, { note })).data.data }
export async function reviewPoi(poiId: string, data: { rating: number; content: string }): Promise<PoiActionResponse> { return (await apiClient.post<{ success: boolean; data: PoiActionResponse }>(`/api/community/pois/${encodeURIComponent(poiId)}/reviews`, data)).data.data }
export async function listCommunityPosts(params: { poi_id?: string; page?: number; page_size?: number } = {}): Promise<PageResult<CommunityPost>> { return (await apiClient.get<{ success: boolean; data: PageResult<CommunityPost> }>('/api/community/posts', { params })).data.data }
export async function getCommunityPost(id: number): Promise<CommunityPost> { return (await apiClient.get<{ success: boolean; data: CommunityPost }>(`/api/community/posts/${id}`)).data.data }
export async function createCommunityPost(data: { content: string; poi_id?: string }): Promise<{ id: number; status: string }> { return (await apiClient.post<{ success: boolean; data: { id: number; status: string } }>('/api/community/posts', data)).data.data }
export async function togglePostLike(id: number): Promise<void> { await apiClient.post(`/api/community/posts/${id}/likes`) }
export async function createPostComment(id: number, content: string): Promise<{ id: number; status: string }> { return (await apiClient.post<{ success: boolean; data: { id: number; status: string } }>(`/api/community/posts/${id}/comments`, { content })).data.data }
export async function getCommunityStats(): Promise<CommunityStats> { return (await apiClient.get<{ success: boolean; data: CommunityStats }>('/api/community/admin/stats')).data.data }
export async function listPendingPosts(params: { page?: number; page_size?: number } = {}): Promise<PageResult<ModerationPost>> { return (await apiClient.get<{ success: boolean; data: PageResult<ModerationPost> }>('/api/community/admin/moderation/posts', { params })).data.data }
export async function listPendingComments(params: { page?: number; page_size?: number } = {}): Promise<PageResult<ModerationComment>> { return (await apiClient.get<{ success: boolean; data: PageResult<ModerationComment> }>('/api/community/admin/moderation/comments', { params })).data.data }
export async function moderatePost(id: number, status: 'approved' | 'rejected'): Promise<void> { await apiClient.patch(`/api/community/admin/moderation/posts/${id}`, { status }) }
export async function moderateComment(id: number, status: 'approved' | 'rejected'): Promise<void> { await apiClient.patch(`/api/community/admin/moderation/comments/${id}`, { status }) }
export async function healthCheck(): Promise<unknown> { return (await apiClient.get('/health')).data }
export default apiClient
