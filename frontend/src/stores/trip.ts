import { defineStore } from 'pinia'
import type { AgentStep, Conversation, TripPlan } from '@/types'

export const useTripStore = defineStore('trip', {
  state: () => ({
    currentPlan: JSON.parse(sessionStorage.getItem('tripPlan') || 'null') as TripPlan | null,
    steps: [] as AgentStep[],
    generating: false,
    conversation: JSON.parse(sessionStorage.getItem('conversation') || 'null') as Conversation | null
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
      sessionStorage.removeItem('tripPlan')
      sessionStorage.removeItem('conversation')
    }
  }
})
