<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import BrandIdentity from '../components/BrandIdentity.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
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
    <div class="login-theme-control">
      <ThemeToggle />
    </div>
    <form
      class="login-card"
      @submit.prevent="handleSubmit"
    >
      <div class="brand">
        <BrandIdentity />
      </div>
      <h1 class="title">
        登录
      </h1>
      <p class="subtitle">
        欢迎回到 Omnixa
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

      <p class="auth-switch">
        没有账号？
        <RouterLink to="/register">
          注册
        </RouterLink>
      </p>
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
  background: var(--color-bg);
  color: var(--color-text-primary);
}

.login-card {
  width: min(400px, 100%);
  padding: 32px;
  border-radius: var(--radius-2xl);
  background: var(--color-surface-elevated);
  border: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-float);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
  color: var(--color-text-primary);
  font-size: var(--text-md);
  font-weight: 600;
}

.login-theme-control {
  position: fixed;
  top: var(--space-5);
  right: var(--space-5);
}


.title {
  margin: 0 0 4px;
  font-size: var(--text-page-title);
  letter-spacing: -0.5px;
}

.subtitle {
  margin: 0 0 24px;
  color: var(--color-text-secondary);
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
  color: var(--color-text-primary);
}

input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-family: inherit;
  box-sizing: border-box;
  transition: border-color var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard);
}

input::placeholder {
  color: var(--color-text-tertiary);
}

.error {
  margin: 0 0 16px;
  padding: 10px 12px;
  border-radius: var(--radius-lg);
  background: var(--color-danger-soft);
  color: var(--color-danger);
  font-size: 14px;
}

.submit {
  width: 100%;
  padding: 13px;
  border: none;
  border-radius: var(--radius-lg);
  background: var(--color-action);
  color: var(--color-action-text);
  font-size: var(--text-md);
  font-family: inherit;
  cursor: pointer;
  transition: transform var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard), opacity var(--duration-fast) var(--ease-standard);
}

.submit:hover:not(:disabled) {
  transform: translateY(-2px);
  background: var(--color-action-hover);
}

.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auth-switch {
  margin: 20px 0 0;
  color: var(--color-text-secondary);
  font-size: 14px;
  text-align: center;
}

.auth-switch a {
  color: var(--color-accent);
  font-weight: 600;
}

.auth-switch a:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}
</style>
