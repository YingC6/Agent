export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  photos?: string[]
  poi_id?: string
  image_url?: string
  ticket_price?: number
}

export interface Meal { type: 'breakfast' | 'lunch' | 'dinner' | 'snack' | string; name: string; address?: string; location?: Location; description?: string; estimated_cost?: number }
export interface Hotel { name: string; address: string; location?: Location; price_range: string; rating: string; distance: string; type: string; estimated_cost?: number }
export interface Budget { total_attractions: number; total_hotels: number; total_meals: number; total_transportation: number; total: number }
export interface RouteSegment {
  origin: string
  destination: string
  route_type: string
  distance_km: number
  duration_minutes: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
  route_segments?: RouteSegment[]
  estimated_transit_minutes?: number
  comfort_level?: string
  plan_b?: string
}
export interface WeatherInfo { date: string; day_weather: string; night_weather: string; day_temp: number; night_temp: number; wind_direction: string; wind_power: string }
export interface TripPlan { city: string; start_date: string; end_date: string; days: DayPlan[]; weather_info: WeatherInfo[]; overall_suggestions: string; budget?: Budget; source?: string; is_fallback?: boolean; warnings?: string[] }
export interface TripFormData { city: string; start_date: string; end_date: string; travel_days: number; transportation: string; accommodation: string; preferences: string[]; free_text_input: string }
export interface TripPlanResponse { success: boolean; message: string; run_id?: string; data?: TripPlan }
export interface TripRating { id: number; trip_id: number; rating: number; comment: string }
export interface KnowledgeItem { id: number; title: string; city: string; days?: number; themes: string[]; keywords: string[]; source: string; source_ref_id?: number; content: string; rating: number; usage_count: number; created_at: string }
export interface UserInfo { id: number; username: string; nickname: string; role: string }
export interface AuthResponse { success: boolean; message: string; token?: string; user?: UserInfo }
export interface AgentStep { run_id?: string; name: string; status: 'running' | 'success' | 'failed' | string; summary: string; duration_ms: number; timestamp_ms?: number }
export interface TripVersion { id: number; version_number: number; source: string; plan: TripPlan; created_at: string }
export interface TripRecord { id: number; title: string; city: string; start_date: string; end_date: string; travel_days: number; source: string; plan: TripPlan; versions?: TripVersion[]; rating?: TripRating; created_at: string }
export interface ConversationMessage { id: number; role: 'user' | 'assistant' | string; content: string; version_id?: number; task_status: 'running' | 'completed' | 'failed' | string; task_steps: AgentStep[]; error_message?: string; duration_ms: number; created_at: string }
export type ConversationIntentName = 'confirm' | 'cancel' | 'modify' | 'weather' | 'restaurant_search' | 'transport_search' | 'poi_search' | 'answer'
export interface ConversationIntent { name: ConversationIntentName; query: string; origin: string; destination: string; route_type: 'walking' | 'driving' | 'transit' }
export interface ConversationQueryResult { type: 'weather' | 'restaurant' | 'transport' | 'poi'; title: string; data: any }
export interface Conversation { id: number; trip_id?: number; current_version_id?: number; title: string; summary: string; summarized_message_count: number; versions?: TripVersion[]; messages: ConversationMessage[]; created_at: string; updated_at: string }
export interface PendingPlanChange { plan: TripPlan; diff: { summary: string; [key: string]: unknown } }
export interface ConversationReply { conversation: Conversation; message: ConversationMessage; trip: TripRecord; pending_change?: PendingPlanChange | null; intent: ConversationIntent; query_results: ConversationQueryResult[] }
export interface ConversationStreamHandlers { onMeta?: (meta: { intent: ConversationIntent; query_results: ConversationQueryResult[] }) => void; onDelta: (content: string) => void }
export interface PageResult<T> { items: T[]; total: number }

export interface CommunityPoi {
  poi_id: string
  name: string
  type: string
  address: string
  city: string
  location: Location
  tel: string
  photos: unknown[]
  photo_url?: string | null
}
export interface PoiInteractionSummary { rating: number; review_count: number; favorite_count: number; checkin_count: number; is_favorited: boolean; is_checked_in: boolean }
export interface PlaceReview { id: number; rating: number; content: string; author: string; created_at: string }
export interface PoiDetail extends CommunityPoi, PoiInteractionSummary { reviews: PlaceReview[] }
export interface PoiActionResponse { summary: PoiInteractionSummary; review?: PlaceReview }
export interface PostComment { id: number; content: string; author: string; created_at: string }
export interface CommunityPost { id: number; poi_id: string | null; content: string; status: string; author: string; created_at: string; updated_at: string; like_count: number; comment_count: number; is_liked: boolean; comments?: PostComment[] }
export interface ModerationPost extends CommunityPost {}
export interface ModerationComment extends PostComment { post_id: number }
export interface CommunityStats { posts: Record<'total' | 'pending' | 'approved' | 'rejected', number>; comments: Record<'total' | 'pending' | 'approved' | 'rejected', number>; poi_interactions: { favorites: number; checkins: number; reviews: number; likes: number } }

export type PreferenceType = 'preference' | 'avoidance' | 'budget'
export interface UserPreference {
  id: number
  memory_type: PreferenceType
  content: string
  importance: number
  created_at: string
  updated_at: string
}

export type ChecklistCategory = '证件' | '衣物' | '电子' | '药品' | '其他'
export interface ChecklistItem {
  id: number
  trip_id: number
  category: ChecklistCategory | string
  content: string
  is_checked: boolean
  sort_order: number
  created_at: string
  updated_at: string
}
export interface ChecklistResult {
  items: ChecklistItem[]
  grouped: Record<string, ChecklistItem[]>
  total: number
  checked_count: number
}

export interface AttractionChange {
  name: string
  field: string
  old_value: string | number
  new_value: string | number
}
export interface DayDiff {
  day_index: number
  added_attractions: string[]
  removed_attractions: string[]
  modified_attractions: AttractionChange[]
  added_meals: string[]
  removed_meals: string[]
  moved_from: string[]
  moved_to: string[]
}
export interface PlanDiff {
  summary: string
  days: DayDiff[]
  budget_change: { old: number; new: number; delta: number } | null
  stats: { added: number; removed: number; modified: number; moved: number }
}
export interface OptimizeResult {
  plan: TripPlan
  diff: PlanDiff
  trip?: TripRecord | null
}
