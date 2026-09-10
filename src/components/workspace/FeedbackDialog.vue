<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { submitFeedback } from '../../api/modules/feedback'

const route = useRoute()
const open = defineModel({ type: Boolean, default: false })
const type = ref('suggestion')
const message = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const submitted = ref(false)
const dialogEl = ref(null)

watch(open, async (value) => {
  if (value) {
    await new Promise((resolve) => requestAnimationFrame(resolve))
    dialogEl.value?.showModal?.()
  }
})

function close() {
  if (submitting.value) return
  dialogEl.value?.close?.()
  open.value = false
}

async function handleSubmit() {
  errorMessage.value = ''
  if (!message.value.trim()) {
    errorMessage.value = '请填写反馈内容'
    return
  }
  submitting.value = true
  try {
    await submitFeedback({
      type: type.value,
      path: route.path || '/',
      message: message.value.trim(),
    })
    submitted.value = true
    message.value = ''
  } catch (error) {
    errorMessage.value = error?.message || '反馈提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

function resetAndClose() {
  submitted.value = false
  open.value = false
}
</script>

<template>
  <dialog
    v-if="open"
    ref="dialogEl"
    class="feedback-dialog"
    aria-label="意见反馈"
    @cancel.prevent="close"
    @click.self="close"
  >
    <div class="feedback-dialog-inner">
      <template v-if="!submitted">
        <h2 class="feedback-title">意见反馈</h2>
        <p class="feedback-subtitle">你的反馈会用于改进 Beta 版本</p>
        <div class="field">
          <label class="label" for="feedback-type">反馈类型</label>
          <select id="feedback-type" v-model="type" name="feedback_type">
            <option value="bug">问题反馈（Bug）</option>
            <option value="suggestion">改进建议</option>
            <option value="other">其他</option>
          </select>
        </div>
        <div class="field">
          <label class="label" for="feedback-message">内容</label>
          <textarea
            id="feedback-message"
            v-model="message"
            name="feedback_message"
            rows="5"
            maxlength="2000"
            placeholder="请描述你遇到的问题或建议…"
          />
          <p class="char-count">{{ message.length }}/2000</p>
        </div>
        <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
        <div class="actions">
          <button type="button" class="cancel" @click="close">取消</button>
          <button type="button" class="submit" :disabled="submitting" @click="handleSubmit">
            {{ submitting ? '提交中…' : '提交反馈' }}
          </button>
        </div>
      </template>
      <template v-else>
        <h2 class="feedback-title">感谢反馈</h2>
        <p class="feedback-subtitle">我们已收到你的反馈。</p>
        <div class="actions">
          <button type="button" class="submit" @click="resetAndClose">关闭</button>
        </div>
      </template>
    </div>
  </dialog>
</template>

<style scoped>
.feedback-dialog {
  width: min(440px, 92vw);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-2xl);
  padding: 0;
  background: var(--color-surface);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-overlay);
}
.feedback-dialog::backdrop { background: rgb(0 0 0 / 55%); }
.feedback-dialog-inner { padding: var(--space-6); }
.feedback-title { margin: 0 0 4px; font-size: var(--text-lg); }
.feedback-subtitle { margin: 0 0 var(--space-5); color: var(--color-text-secondary); font-size: var(--text-sm); }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: var(--space-4); }
.label { font-size: var(--text-sm); color: var(--color-text-primary); }
select, textarea {
  box-sizing: border-box;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font: inherit;
  font-size: var(--text-sm);
}
select:focus-visible, textarea:focus-visible {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-accent) 20%, transparent);
}
.char-count { margin: 4px 0 0; font-size: var(--text-xs); color: var(--color-text-tertiary); text-align: right; }
.error {
  margin: 0 0 var(--space-4);
  padding: 10px 12px;
  border-radius: var(--radius-lg);
  background: var(--color-danger-soft);
  color: var(--color-danger);
  font-size: var(--text-sm);
}
.actions { display: flex; justify-content: flex-end; gap: var(--space-3); }
.cancel, .submit {
  padding: 10px 16px;
  border-radius: var(--radius-lg);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
}
.cancel { border: 1px solid var(--color-border); background: var(--color-surface); color: inherit; }
.cancel:hover { background: var(--color-surface-hover); }
.submit { border: 0; background: var(--color-action); color: var(--color-action-text); }
.submit:hover:not(:disabled) { background: var(--color-action-hover); }
.submit:disabled { opacity: .6; cursor: not-allowed; }
</style>
