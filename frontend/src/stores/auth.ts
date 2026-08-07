import { defineStore } from 'pinia'
import { getMe, login, register } from '@/services/api'
import type { UserInfo } from '@/types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: JSON.parse(localStorage.getItem('user') || 'null') as UserInfo | null
  }),
  getters: {
    isLogin: (state) => Boolean(state.token)
  },
  actions: {
    setSession(token: string, user: UserInfo) {
      this.token = token
      this.user = user
      localStorage.setItem('token', token)
      localStorage.setItem('user', JSON.stringify(user))
    },
    async login(username: string, password: string) {
      const res = await login({ username, password })
      if (res.token && res.user) this.setSession(res.token, res.user)
    },
    async register(username: string, password: string, nickname: string) {
      const res = await register({ username, password, nickname })
      if (res.token && res.user) this.setSession(res.token, res.user)
    },
    async fetchMe() {
      if (!this.token) return
      this.user = await getMe()
      localStorage.setItem('user', JSON.stringify(this.user))
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    }
  }
})
