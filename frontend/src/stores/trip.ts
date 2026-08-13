import { defineStore } from 'pinia'
import type { AgentStep, CommunityPoi, Conversation, TripPlan } from '@/types'

export const useTripStore = defineStore('trip', {
  state: () => ({
    currentPlan: JSON.parse(sessionStorage.getItem('tripPlan') || 'null') as TripPlan | null,
    steps: [] as AgentStep[],
    generating: false,
    conversation: JSON.parse(sessionStorage.getItem('conversation') || 'null') as Conversation | null,
    pendingPois: JSON.parse(sessionStorage.getItem('pendingPois') || '[]') as CommunityPoi[]
  }),
  actions: {
    setPlan(plan: TripPlan) {
      this.currentPlan = plan
      sessionStorage.setItem('tripPlan', JSON.stringify(plan))
    },
    setConversation(conversation: Conversation | null) {
      this.conversation = conversation
      if (conversation) sessionStorage.setItem('conversation', JSON.stringify(conversation))
      else sessionStorage.removeItem('conversation')
    },
    addPendingPoi(poi: CommunityPoi) {
      if (!this.pendingPois.some(item => item.poi_id === poi.poi_id)) {
        this.pendingPois.push(poi)
        sessionStorage.setItem('pendingPois', JSON.stringify(this.pendingPois))
      }
    },
    removePendingPoi(poiId: string) {
      this.pendingPois = this.pendingPois.filter(item => item.poi_id !== poiId)
      sessionStorage.setItem('pendingPois', JSON.stringify(this.pendingPois))
    },
    setSteps(steps: AgentStep[]) {
      this.steps = steps
    },
    addStep(step: AgentStep) {
      this.steps.push(step)
    },
    clear() {
      this.currentPlan = null
      this.steps = []
      this.conversation = null
      this.pendingPois = []
      sessionStorage.removeItem('tripPlan')
      sessionStorage.removeItem('conversation')
      sessionStorage.removeItem('pendingPois')
    }
  }
})
