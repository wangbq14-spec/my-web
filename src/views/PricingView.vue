<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  cancelRechargeRequest,
  getPaymentInfo,
  getRechargeQuote,
  listRechargeRequests,
  submitCustomRecharge,
  submitRecharge,
} from '../api/modules/recharge'

const packages = ref([])
const qrImageUrl = ref(null)
const requests = ref([])
const loading = ref(true)
const errorMessage = ref('')
const selectedPackage = ref('')
const note = ref('')
const submitting = ref(false)
const submitSuccess = ref('')
const submitError = ref('')
const cancelingId = ref(null)
const submitFormRef = ref(null)

const customRecharge = ref(null)
const customAmount = ref('')
const customQuote = ref(null)
const customQuoting = ref(false)
const customAmountError = ref('')
const customQuoteError = ref('')
const customSubmitting = ref(false)
const customDebounceTimer = ref(null)

const statusNames = { pending: '待审核', approved: '已到账', rejected: '已拒绝', cancelled: '已取消' }

const statusLabel = (item) => statusNames[item.status] || item.status || '未知状态'
const number = (value) => Number(value || 0).toLocaleString('zh-CN')
const date = (value) => {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '时间未知' : parsed.toLocaleString('zh-CN')
}

async function loadData() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [paymentResult, requestResult] = await Promise.all([getPaymentInfo(), listRechargeRequests()])
    packages.value = Array.isArray(paymentResult?.packages) ? paymentResult.packages : []
    qrImageUrl.value = paymentResult?.qr_image_url || null
    customRecharge.value = paymentResult?.custom_recharge || null
    requests.value = Array.isArray(requestResult) ? requestResult : []
    if (!selectedPackage.value && packages.value.length) {
      selectedPackage.value = packages.value[0].code
    }
  } catch {
    errorMessage.value = '充值信息加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function selectPackage(code) {
  selectedPackage.value = code
  submitFormRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}

async function refreshRequests() {
  const result = await listRechargeRequests()
  requests.value = Array.isArray(result) ? result : []
}

async function handleSubmit() {
  if (!selectedPackage.value || submitting.value) return
  const pkg = packages.value.find((item) => item.code === selectedPackage.value)
  if (!pkg) return
  submitSuccess.value = ''
  submitError.value = ''
  submitting.value = true
  try {
    await submitRecharge({
      package_code: pkg.code,
      credits_requested: pkg.credits,
      ...(note.value.trim() ? { note: note.value.trim() } : {}),
    })
    submitSuccess.value = '充值申请已提交，等待人工审核到账'
    note.value = ''
    await refreshRequests()
  } catch (error) {
    submitError.value = error?.message || '充值申请提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

function parseCustomAmount(raw) {
  const config = customRecharge.value || {}
  const text = String(raw || '').trim()
  if (!text) return { value: null, error: '' }
  if (!/^\d+(\.\d+)?$/.test(text)) return { value: null, error: '请输入有效的金额' }
  const value = Number(text)
  if (!Number.isFinite(value) || Number.isNaN(value)) return { value: null, error: '请输入有效的金额' }
  const min = Number(config.min_cny || 1)
  const max = Number(config.max_cny || 500)
  const step = Number(config.step_cny || 1)
  if (value <= 0) return { value: null, error: '金额必须大于 0' }
  if (value < min) return { value: null, error: `金额不能低于 ${min} 元` }
  if (value > max) return { value: null, error: `金额不能超过 ${max} 元` }
  if (step > 0 && (value - min) % step !== 0) return { value: null, error: `金额需为 ${step} 元的整数倍` }
  return { value: String(value), error: '' }
}

function scheduleCustomQuote() {
  if (customDebounceTimer.value) clearTimeout(customDebounceTimer.value)
  customDebounceTimer.value = setTimeout(updateCustomQuote, 400)
}

async function updateCustomQuote() {
  const { value, error } = parseCustomAmount(customAmount.value)
  customAmountError.value = error
  customQuoteError.value = ''
  customQuote.value = null
  if (!value) return
  customQuoting.value = true
  try {
    customQuote.value = await getRechargeQuote(value)
  } catch (err) {
    customQuoteError.value = err?.message || '暂无法获取预计积分，请稍后再试'
  } finally {
    customQuoting.value = false
  }
}

async function handleCustomSubmit() {
  if (customSubmitting.value) return
  const { value, error } = parseCustomAmount(customAmount.value)
  customAmountError.value = error
  if (!value) return
  submitSuccess.value = ''
  submitError.value = ''
  customSubmitting.value = true
  try {
    await submitCustomRecharge(value)
    submitSuccess.value = '充值申请已提交，等待人工审核到账'
    customAmount.value = ''
    customQuote.value = null
    customAmountError.value = ''
    await refreshRequests()
  } catch (err) {
    submitError.value = err?.message || '充值申请提交失败，请稍后重试'
  } finally {
    customSubmitting.value = false
  }
}

async function cancelRequest(id) {
  if (cancelingId.value !== null) return
  cancelingId.value = id
  submitError.value = ''
  try {
    await cancelRechargeRequest(id)
    await refreshRequests()
  } catch (error) {
    submitError.value = error?.message || '取消申请失败，请稍后重试'
  } finally {
    cancelingId.value = null
  }
}

onMounted(loadData)
onBeforeUnmount(() => {
  if (customDebounceTimer.value) clearTimeout(customDebounceTimer.value)
})
</script>

<template>
  <main class="pricing-page">
    <header class="pricing-header">
      <h1>人工充值</h1>
      <p>本产品为人工充值，付款后请联系客服确认，人工到账。</p>
    </header>

    <p v-if="errorMessage" class="error-banner" role="alert">{{ errorMessage }} <button type="button" @click="loadData">重试</button></p>
    <p v-if="loading" class="state-message">正在加载充值信息…</p>

    <template v-else>
      <section class="packages-section" aria-labelledby="packages-title">
        <h2 id="packages-title">充值套餐</h2>
        <p v-if="packages.length === 0" class="empty-state">暂无可用套餐</p>
        <div v-else class="packages-grid">
          <article v-for="pkg in packages" :key="pkg.code" class="package-card">
            <strong class="package-amount">{{ pkg.amount_display }}</strong>
            <p class="package-credits">{{ number(pkg.credits) }} 积分</p>
            <button type="button" class="package-submit" @click="selectPackage(pkg.code)">提交充值申请</button>
          </article>
        </div>
      </section>

      <section v-if="customRecharge?.enabled" class="custom-section" aria-labelledby="custom-title">
        <h2 id="custom-title">自定义金额</h2>
        <p class="custom-desc">
          不选套餐时，可输入任意金额充值（{{ customRecharge.min_cny }}–{{ customRecharge.max_cny }} 元），预计积分由系统按
          {{ number(customRecharge.credit_per_cny) }} 积分/元实时计算。
        </p>
        <div class="custom-row">
          <span class="custom-yen" aria-hidden="true">¥</span>
          <input
            id="custom-amount"
            v-model="customAmount"
            type="text"
            inputmode="decimal"
            autocomplete="off"
            placeholder="输入金额，例如 12"
            aria-label="自定义充值金额"
            @input="scheduleCustomQuote"
          >
          <button
            type="button"
            class="custom-submit"
            :disabled="customSubmitting || customQuoting || !customQuote || !!customAmountError"
            @click="handleCustomSubmit"
          >
            {{ customSubmitting ? '正在提交…' : '提交充值申请' }}
          </button>
        </div>
        <p v-if="customAmountError" class="form-error" role="alert">{{ customAmountError }}</p>
        <p v-else-if="customQuoting" class="custom-quote">正在计算预计积分…</p>
        <p v-else-if="customQuote" class="custom-quote" role="status">
          预计获得：{{ number(customQuote.credits) }} Credits
          <span class="custom-quote-sub">（报价版本 {{ customQuote.pricing_version }}，15 分钟内有效）</span>
        </p>
        <p v-else-if="customQuoteError" class="form-error" role="alert">{{ customQuoteError }}</p>
      </section>

      <section class="qr-section" aria-labelledby="qr-title">
        <h2 id="qr-title">收款码</h2>
        <div class="qr-area">
          <img v-if="qrImageUrl" :src="qrImageUrl" alt="收款码" class="qr-image">
          <p v-else class="qr-placeholder">当前暂未开放扫码充值（可提交充值申请，由管理员人工审核后到账）</p>
        </div>
        <p v-if="qrImageUrl" class="qr-manual-note" role="status">付款后由管理员人工确认到账，不会自动到账。</p>
      </section>

      <aside class="beta-notice" aria-label="Beta 说明">
        <p>
          <strong>Classroom Beta 说明：</strong>
          本页面为 Beta 人工充值流程，不会自动到账，请勿向任何声称"自动到账"的二维码付款。
          使用帮助见《Omnixa Classroom Beta 使用说明》（docs/classroom-beta.md）。
        </p>
      </aside>

      <section ref="submitFormRef" class="submit-section" aria-labelledby="submit-title">
        <h2 id="submit-title">提交充值申请</h2>
        <p v-if="submitSuccess" class="success-banner" role="status">{{ submitSuccess }}</p>
        <p v-if="submitError" class="form-error" role="alert">{{ submitError }}</p>
        <form class="submit-form" @submit.prevent="handleSubmit">
          <label for="package-select">套餐</label>
          <select id="package-select" v-model="selectedPackage">
            <option v-for="pkg in packages" :key="pkg.code" :value="pkg.code">
              {{ pkg.amount_display }} · {{ number(pkg.credits) }} 积分
            </option>
          </select>
          <label for="recharge-note">备注（选填）</label>
          <textarea id="recharge-note" v-model="note" rows="3" placeholder="例如：已付款，请查收" />
          <button type="submit" class="submit-btn" :disabled="submitting || !selectedPackage">
            {{ submitting ? '正在提交…' : '提交充值申请' }}
          </button>
        </form>
      </section>

      <section class="requests-section" aria-labelledby="requests-title">
        <h2 id="requests-title">充值申请记录</h2>
        <p v-if="requests.length === 0" class="empty-state">暂无充值申请</p>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr><th>时间</th><th>套餐</th><th>积分</th><th>金额</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in requests" :key="item.id">
                <td>{{ date(item.created_at) }}</td>
                <td>{{ item.package_code }}</td>
                <td>{{ number(item.credits_requested) }}</td>
                <td>{{ item.amount_display }}</td>
                <td>{{ statusLabel(item) }}</td>
                <td>
                  <button
                    v-if="item.status === 'pending'"
                    type="button"
                    class="cancel-btn"
                    :disabled="cancelingId !== null"
                    @click="cancelRequest(item.id)"
                  >
                    取消
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.pricing-page { min-height: 100%; color: var(--color-text-primary); }
.pricing-header h1, .pricing-header p, h2, .package-card p, .submit-form label { margin: 0; }
.pricing-header p { margin-top: var(--space-2); color: var(--color-text-secondary); }
.packages-section, .custom-section, .qr-section, .submit-section, .requests-section { border: 1px solid var(--color-border); border-radius: var(--radius-2xl); padding: var(--space-5); background: var(--color-surface); margin-top: var(--space-6); }
.packages-section h2, .custom-section h2, .qr-section h2, .submit-section h2, .requests-section h2 { margin-bottom: var(--space-4); }
.packages-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-4); }
.package-card { border: 1px solid var(--color-border); border-radius: var(--radius-xl); padding: var(--space-5); background: var(--color-surface); }
.package-amount { display: block; font-size: 2rem; }
.package-credits { margin-top: var(--space-2); color: var(--color-text-secondary); }
.package-submit { margin-top: var(--space-4); min-height: var(--space-11); width: 100%; border: 1px solid var(--color-accent); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-3); background: transparent; color: var(--color-accent); font: inherit; font-size: var(--text-sm); cursor: pointer; }
.package-submit:hover, .package-submit:focus-visible { background: var(--color-accent-soft); }
.qr-area { display: flex; min-height: 220px; align-items: center; justify-content: center; border: 1px dashed var(--color-border); border-radius: var(--radius-xl); padding: var(--space-5); background: var(--color-surface-sunken); }
.qr-image { width: 220px; height: 220px; object-fit: contain; }
.qr-placeholder { margin: 0; color: var(--color-text-secondary); }
.qr-manual-note { margin: var(--space-3) 0 0; color: var(--color-accent); }
.beta-notice { margin-top: var(--space-6); padding: var(--space-4) var(--space-5); border: 1px dashed var(--color-border); border-radius: var(--radius-2xl); background: var(--color-surface-sunken); color: var(--color-text-secondary); font-size: var(--text-sm); }
.beta-notice p { margin: 0; }
.submit-form { display: grid; gap: var(--space-2); }
.submit-form label { color: var(--color-text-secondary); font-size: var(--text-xs); }
.submit-form select, .submit-form textarea { width: 100%; min-width: 0; box-sizing: border-box; border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-3); background: var(--color-surface); color: var(--color-text-primary); font: inherit; font-size: var(--text-sm); }
.submit-form textarea { resize: vertical; }
.submit-btn { justify-self: start; min-height: var(--space-11); border: 1px solid var(--color-accent); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-4); background: var(--color-accent); color: var(--color-surface); font: inherit; font-size: var(--text-sm); cursor: pointer; }
.submit-btn:hover:not(:disabled), .submit-btn:focus-visible:not(:disabled) { filter: brightness(1.05); }
.submit-btn:disabled { opacity: .55; cursor: not-allowed; }
.custom-desc { margin: 0 0 var(--space-3); color: var(--color-text-secondary); font-size: var(--text-sm); }
.custom-row { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.custom-yen { color: var(--color-text-secondary); font-size: var(--text-lg); }
#custom-amount { flex: 1 1 200px; min-width: 0; box-sizing: border-box; border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-3); background: var(--color-surface); color: var(--color-text-primary); font: inherit; font-size: var(--text-sm); }
.custom-submit { min-height: var(--space-11); border: 1px solid var(--color-accent); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-4); background: var(--color-accent); color: var(--color-surface); font: inherit; font-size: var(--text-sm); cursor: pointer; }
.custom-submit:hover:not(:disabled), .custom-submit:focus-visible:not(:disabled) { filter: brightness(1.05); }
.custom-submit:disabled { opacity: .55; cursor: not-allowed; }
.custom-quote { margin: var(--space-3) 0 0; color: var(--color-accent); }
.custom-quote-sub { color: var(--color-text-secondary); font-size: var(--text-xs); }
.success-banner { color: var(--color-accent); }
.form-error { color: var(--color-danger); }
.table-wrap { overflow-x: auto; margin-top: var(--space-4); }
table { width: 100%; border-collapse: collapse; white-space: nowrap; }
th, td { padding: var(--space-3); border-bottom: 1px solid var(--color-border-subtle); text-align: left; }
th { color: var(--color-text-secondary); font-size: var(--text-xs); }
.cancel-btn { min-height: var(--space-11); border: 1px solid var(--color-danger); border-radius: var(--radius-lg); padding: var(--space-1) var(--space-3); background: transparent; color: var(--color-danger); font: inherit; font-size: var(--text-xs); cursor: pointer; }
.cancel-btn:hover:not(:disabled), .cancel-btn:focus-visible:not(:disabled) { background: var(--color-danger-soft); }
.cancel-btn:disabled { opacity: .55; cursor: not-allowed; }
.empty-state, .state-message { padding: var(--space-8); color: var(--color-text-secondary); text-align: center; }
.error-banner { color: var(--color-danger); }
.error-banner button { border: 1px solid currentColor; border-radius: var(--radius-md); background: transparent; color: inherit; cursor: pointer; }
@media (max-width: 640px) { .packages-grid { grid-template-columns: 1fr; } }
</style>
