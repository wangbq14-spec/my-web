<script setup>
import { computed, onMounted, ref } from 'vue'
import { getBalance, listUsage } from '../api/modules/usage'

const balance = ref(null)
const usage = ref([])
const loading = ref(true)
const errorMessage = ref('')
const tierNames = { auto: '自动', fast: '快速', balanced: '均衡', deep: '深度思考' }

const totalSpent = computed(() => usage.value.reduce((sum, item) => sum + Number(item.credits_charged || 0), 0))
const tierLabel = (item) => tierNames[item.model_tier] || item.model || '未知模型'
const number = (value) => Number(value || 0).toLocaleString('zh-CN')
const date = (value) => {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '时间未知' : parsed.toLocaleString('zh-CN')
}

async function loadUsage() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [balanceResult, usageResult] = await Promise.all([getBalance(), listUsage()])
    balance.value = balanceResult?.balance ?? 0
    usage.value = Array.isArray(usageResult) ? usageResult : []
  } catch {
    errorMessage.value = '用量加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(loadUsage)
</script>

<template>
  <main class="usage-page">
    <header class="usage-header"><h1>用量 / Usage</h1><p>查看 Credits 余额与模型使用记录。</p></header>
    <p v-if="errorMessage" class="error-banner" role="alert">{{ errorMessage }} <button type="button" @click="loadUsage">重试</button></p>
    <p v-if="loading" class="state-message">正在加载用量…</p>
    <template v-else>
      <section class="usage-summary" aria-label="用量概览">
        <article class="usage-card"><span>当前 Credits 余额</span><strong>{{ number(balance) }}</strong><p>Beta 注册赠送体验积分</p></article>
        <article class="usage-card"><span>累计消耗</span><strong>{{ number(totalSpent) }}</strong><p>基于当前显示的使用记录</p></article>
      </section>
      <section class="history-section" aria-labelledby="usage-history-title">
        <h2 id="usage-history-title">Usage 历史</h2>
        <p v-if="usage.length === 0" class="empty-state">暂无使用记录</p>
        <div v-else class="usage-table-wrap"><table><thead><tr><th>时间</th><th>模型</th><th>Provider</th><th>Tokens（输入 / 输出 / 总计）</th><th>Credits</th></tr></thead><tbody><tr v-for="item in usage" :key="`${item.created_at}-${item.model}-${item.total_tokens}`"><td>{{ date(item.created_at) }}</td><td><strong>{{ tierLabel(item) }}</strong><small v-if="item.model_tier && tierNames[item.model_tier]">{{ item.model }}</small></td><td>{{ item.provider }}</td><td>{{ number(item.prompt_tokens) }} / {{ number(item.completion_tokens) }} / {{ number(item.total_tokens) }}</td><td>{{ number(item.credits_charged) }}</td></tr></tbody></table></div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.usage-page { min-height: 100%; color: var(--color-text-primary); }
.usage-header h1, .usage-header p, h2, .usage-card p { margin: 0; }.usage-header p, .usage-card p { margin-top: var(--space-2); color: var(--color-text-secondary); }.usage-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4); margin: var(--space-6) 0; }.usage-card { border: 1px solid var(--color-border); border-radius: var(--radius-2xl); padding: var(--space-6); background: var(--color-surface); }.usage-card span { color: var(--color-text-secondary); }.usage-card strong { display: block; margin-top: var(--space-3); font-size: 2rem; }.history-section { border: 1px solid var(--color-border); border-radius: var(--radius-2xl); padding: var(--space-5); background: var(--color-surface); }.usage-table-wrap { overflow-x: auto; margin-top: var(--space-4); }table { width: 100%; border-collapse: collapse; white-space: nowrap; }th, td { padding: var(--space-3); border-bottom: 1px solid var(--color-border-subtle); text-align: left; }th { color: var(--color-text-secondary); font-size: var(--text-xs); }td small { display: block; margin-top: 2px; color: var(--color-text-secondary); }.empty-state, .state-message { padding: var(--space-8); color: var(--color-text-secondary); text-align: center; }.error-banner { color: var(--color-danger); }.error-banner button { border: 1px solid currentColor; border-radius: var(--radius-md); background: transparent; color: inherit; cursor: pointer; }@media (max-width: 640px) { .usage-summary { grid-template-columns: 1fr; } }
</style>
