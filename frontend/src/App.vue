<template>
  <a-layout class="app-layout">
    <a-layout-header class="app-header">
      <div class="brand" @click="router.push('/')">TripMind 智能旅行规划平台</div>
      <a-menu mode="horizontal" theme="dark" class="nav" :selected-keys="[route.name as string]">
        <template v-if="auth.isLogin">
          <a-menu-item key="Home" @click="router.push('/')">创建行程</a-menu-item>
          <a-menu-item key="Trips" @click="router.push('/trips')">我的行程</a-menu-item>
          <a-menu-item key="Discover" @click="router.push('/discover')">发现地点</a-menu-item>
          <a-menu-item key="Preferences" @click="router.push('/preferences')">我的偏好</a-menu-item>
        </template>
        <a-menu-item key="Community" @click="router.push('/community')">旅行社区</a-menu-item>
        <a-menu-item v-if="auth.user?.role === 'admin'" key="CommunityAdmin" @click="router.push('/community/admin')">社区管理</a-menu-item>
        <a-menu-item v-if="auth.user?.role === 'admin'" key="Knowledge" @click="router.push('/knowledge')">知识库</a-menu-item>
      </a-menu>
      <div class="user-actions"><template v-if="auth.isLogin"><span class="nickname">{{ auth.user?.nickname }}</span><a-button size="small" @click="logout">退出</a-button></template><template v-else><a-button type="link" @click="router.push('/login')">登录</a-button></template></div>
    </a-layout-header>
    <a-layout-content class="app-content"><router-view /></a-layout-content>
  </a-layout>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
const router = useRouter(); const route = useRoute(); const auth = useAuthStore()
const logout = () => { auth.logout(); router.push('/login') }
</script>

<style>
body { margin: 0; background: #f5f7fb; } #app { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif; }.app-layout { min-height: 100vh; }.app-header { display: flex; align-items: center; gap: 24px; padding: 0 32px; }.brand { color: #fff; font-size: 20px; font-weight: 700; cursor: pointer; white-space: nowrap; }.nav { flex: 1; min-width: 0; }.user-actions { display: flex; align-items: center; gap: 12px; color: #fff; }.nickname { color: rgba(255, 255, 255, .9); }.app-content { padding: 24px; }
</style>
