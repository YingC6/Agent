import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import Home from './views/Home.vue'
import Result from './views/Result.vue'
import Login from './views/Login.vue'
import Register from './views/Register.vue'
import Trips from './views/Trips.vue'
import Knowledge from './views/Knowledge.vue'
import Discover from './views/Discover.vue'
import PlaceDetail from './views/PlaceDetail.vue'
import Community from './views/Community.vue'
import CommunityAdmin from './views/CommunityAdmin.vue'
import { useAuthStore } from './stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'Home', component: Home, meta: { requiresAuth: true } },
    { path: '/result', name: 'Result', component: Result, meta: { requiresAuth: true } },
    { path: '/trips', name: 'Trips', component: Trips, meta: { requiresAuth: true } },
    { path: '/discover', name: 'Discover', component: Discover, meta: { requiresAuth: true } },
    { path: '/places/:poiId', name: 'PlaceDetail', component: PlaceDetail, meta: { requiresAuth: true } },
    { path: '/community', name: 'Community', component: Community },
    { path: '/community/admin', name: 'CommunityAdmin', component: CommunityAdmin, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/knowledge', name: 'Knowledge', component: Knowledge, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/login', name: 'Login', component: Login },
    { path: '/register', name: 'Register', component: Register }
  ]
})

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(Antd)
router.beforeEach((to) => { const auth = useAuthStore(); if (to.meta.requiresAuth && !auth.isLogin) return { name: 'Login' }; if (to.meta.requiresAdmin && auth.user?.role !== 'admin') return { name: 'Home' }; if ((to.name === 'Login' || to.name === 'Register') && auth.isLogin) return { name: 'Home' } })
app.mount('#app')
