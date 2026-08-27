import { defineStore } from 'pinia'
import * as authApi from '../api/modules/auth'
import {
  clearAccessToken,
  getAccessToken,
  setAccessToken,
} from '../utils/token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getAccessToken(),
    user: null,
    loading: false,
    initialized: false,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.token),
  },

  actions: {
    async login(credentials) {
      this.loading = true
      try {
        const data = await authApi.login(credentials)
        const token = data?.access_token ?? data?.token

        if (!token) {
          throw new Error('登录失败：响应中缺少 access_token')
        }

        setAccessToken(token)
        this.token = token
        await this.fetchCurrentUser()

        return data
      } finally {
        this.loading = false
      }
    },

    async fetchCurrentUser() {
      try {
        const user = await authApi.getCurrentUser()
        this.user = user
        this.initialized = true
        return user
      } catch (error) {
        this.resetAuth()
        throw error
      }
    },

    logout() {
      this.resetAuth()
    },

    resetAuth() {
      clearAccessToken()
      this.token = null
      this.user = null
      this.initialized = true
    },
  },
})
