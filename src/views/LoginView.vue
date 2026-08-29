<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const errorMessage = ref('')

async function handleSubmit() {
  errorMessage.value = ''

  if (!username.value.trim() || !password.value) {
    errorMessage.value = '请输入用户名和密码'
    return
  }

  try {
    await authStore.login({
      username: username.value.trim(),
      password: password.value,
    })
    router.replace('/chat')
  } catch (error) {
    errorMessage.value = error?.message || '登录失败，请稍后重试'
  }
}
</script>

<template>
  <div class="login-page">
    <form
      class="login-card"
      @submit.prevent="handleSubmit"
    >
      <h1 class="title">
        登录
      </h1>
      <p class="subtitle">
        欢迎回到智行 AI
      </p>

      <div class="field">
        <label
          class="label"
          for="username"
        >用户名 / 邮箱</label>
        <input
          id="username"
          v-model="username"
          type="text"
          name="username"
          autocomplete="username"
          placeholder="请输入用户名或邮箱"
        >
      </div>

      <div class="field">
        <label
          class="label"
          for="password"
        >密码</label>
        <input
          id="password"
          v-model="password"
          type="password"
          name="password"
          autocomplete="current-password"
          placeholder="请输入密码"
        >
      </div>

      <p
        v-if="errorMessage"
        class="error"
        role="alert"
      >
        {{ errorMessage }}
      </p>

      <button
        type="submit"
        class="submit"
        :disabled="authStore.loading"
      >
        {{ authStore.loading ? '登录中…' : '登录' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background:
    radial-gradient(60rem 30rem at 70% -10%, rgba(124, 58, 237, 0.12), transparent 60%),
    radial-gradient(50rem 28rem at 15% 0%, rgba(79, 70, 229, 0.12), transparent 60%),
    #ffffff;
  color: #1a1a2e;
}

.login-card {
  width: min(400px, 100%);
  padding: 32px;
  border-radius: 20px;
  background: #fff;
  border: 1px solid #eef0f4;
  box-shadow: 0 24px 60px -24px rgba(30, 30, 60, 0.25);
}

.title {
  margin: 0 0 4px;
  font-size: 28px;
  letter-spacing: -0.5px;
}

.subtitle {
  margin: 0 0 24px;
  color: #6b7280;
  font-size: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.label {
  font-size: 14px;
  color: #374151;
}

input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  font-size: 15px;
  font-family: inherit;
  box-sizing: border-box;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

input:focus {
  outline: none;
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15);
}

.error {
  margin: 0 0 16px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 14px;
}

.submit {
  width: 100%;
  padding: 13px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  color: #fff;
  font-size: 16px;
  font-family: inherit;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
}

.submit:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 16px 32px -8px rgba(79, 70, 229, 0.6);
}

.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
