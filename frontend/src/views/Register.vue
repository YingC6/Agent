<template>
  <div class="auth-page">
    <a-card class="auth-card" title="注册 TripMind">
      <a-form layout="vertical" :model="form" @finish="submit">
        <a-form-item name="username" label="用户名" :rules="[{ required: true, message: '请输入用户名' }]">
          <a-input v-model:value="form.username" size="large" />
        </a-form-item>
        <a-form-item name="nickname" label="昵称">
          <a-input v-model:value="form.nickname" size="large" />
        </a-form-item>
        <a-form-item name="password" label="密码" :rules="[{ required: true, message: '请输入密码' }, { min: 6, message: '至少6位密码' }]">
          <a-input-password v-model:value="form.password" size="large" />
        </a-form-item>
        <a-button type="primary" html-type="submit" block size="large" :loading="loading">注册并登录</a-button>
      </a-form>
      <div class="switch">已有账号？<a @click="router.push('/login')">去登录</a></div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', nickname: '', password: '' })

const submit = async () => {
  loading.value = true
  try {
    await auth.register(form.username, form.password, form.nickname || form.username)
    message.success('注册成功')
    router.push('/')
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: calc(100vh - 112px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.auth-card {
  width: 420px;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.12);
}

.switch {
  margin-top: 18px;
  text-align: center;
}
</style>
