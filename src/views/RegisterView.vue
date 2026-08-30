<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import BrandIdentity from '../components/BrandIdentity.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const username = ref('')
const password = ref('')
const errorMessage = ref('')

function validate() {
  if (!email.value.trim()) return '请输入邮箱'
  if (!/^\S+@\S+\.\S+$/.test(email.value.trim())) return '请输入有效的邮箱地址'
  if (!username.value.trim()) return '请输入用户名'
  if (username.value.trim().length < 3) return '用户名至少需要 3 个字符'
  if (!password.value) return '请输入密码'
  if (password.value.length < 8) return '密码至少需要 8 个字符'
  return ''
}

async function handleSubmit() {
  errorMessage.value = validate()
  if (errorMessage.value) return

  try {
    await authStore.register({
      email: email.value.trim(),
      username: username.value.trim(),
      password: password.value,
    })
    router.replace('/chat')
  } catch (error) {
    errorMessage.value = error?.message || '注册失败，请稍后重试'
  }
}
</script>

<template>
  <div class="register-page">
    <div class="register-theme-control">
      <ThemeToggle />
    </div>
    <form
      class="register-card"
      @submit.prevent="handleSubmit"
    >
      <div class="brand">
        <BrandIdentity />
      </div>
      <h1 class="title">
        创建账号
      </h1>
      <p class="subtitle">
        欢迎加入 Omnixa
      </p>

      <div class="field">
        <label
          class="label"
          for="email"
        >邮箱</label>
        <input
          id="email"
          v-model="email"
          type="email"
          name="email"
          autocomplete="email"
          placeholder="请输入邮箱地址"
        >
      </div>

      <div class="field">
        <label
          class="label"
          for="username"
        >用户名</label>
        <input
          id="username"
          v-model="username"
          type="text"
          name="username"
          minlength="3"
          autocomplete="username"
          placeholder="请输入至少 3 个字符的用户名"
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
          minlength="8"
          autocomplete="new-password"
          placeholder="请输入至少 8 个字符的密码"
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
        {{ authStore.loading ? '注册中…' : '注册' }}
      </button>

      <p class="auth-switch">
        已有账号？
        <RouterLink to="/login">
          登录
        </RouterLink>
      </p>
    </form>
  </div>
</template>

<style scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--color-bg);
  color: var(--color-text-primary);
}

.register-card {
  width: min(400px, 100%);
  padding: 32px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-2xl);
  background: var(--color-surface-elevated);
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

.register-theme-control {
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
  box-sizing: border-box;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font-family: inherit;
  font-size: var(--text-base);
  transition: border-color var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard);
}

input::placeholder {
  color: var(--color-text-tertiary);
}

input:focus-visible {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-accent) 20%, transparent);
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
  font-family: inherit;
  font-size: var(--text-md);
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
