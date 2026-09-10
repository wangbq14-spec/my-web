<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import http from '../../api/http'
import { attachmentUrl } from '../../api/modules/attachments'

const props = defineProps({ attachments: { type: Array, default: () => [] } })
const dialog = ref(null)
const selected = ref(null)
const failed = ref(new Set())
const srcs = ref(new Map())
const inFlight = new Set()
let trigger = null

// Key by the local blob preview first so a composer item keeps a stable
// identity across the upload transition (preview -> server id/url). This
// prevents the watcher from revoking the preview blob early.
function keyOf(item) {
  return item.preview ?? item.id ?? item.url
}

function isLocal(raw) {
  return /^blob:/.test(raw || '')
}

async function resolve(item) {
  const key = keyOf(item)
  const raw = item.preview ?? item.url
  if (srcs.value.has(key) || failed.value.has(key) || inFlight.has(key)) return
  // Local composer previews need no fetch; server URLs need the auth header,
  // which a plain <img> tag cannot send — load via the axios instance.
  if (isLocal(raw)) {
    srcs.value.set(key, raw)
    srcs.value = new Map(srcs.value)
    return
  }
  inFlight.add(key)
  try {
    // Server URLs arrive as API paths like `/api/chat/attachments/{id}`. The
    // axios instance already prefixes `VITE_API_BASE_URL` (which ends in
    // `/api`), so resolve to an absolute URL first — axios then uses it
    // verbatim instead of double-prefixing `/api/api/...`.
    const absUrl = attachmentUrl(raw)
    if (!absUrl) {
      failed.value.add(key)
    } else {
      const blob = await http.get(absUrl, { responseType: 'blob' })
      srcs.value.set(key, URL.createObjectURL(blob))
    }
  } catch {
    failed.value.add(key)
  } finally {
    inFlight.delete(key)
  }
  srcs.value = new Map(srcs.value)
  failed.value = new Set(failed.value)
}

function displaySrc(item) {
  const key = keyOf(item)
  if (srcs.value.has(key)) return srcs.value.get(key)
  // Never hand a raw server URL to a plain <img> (it cannot send the JWT and
  // would 401 -> prematurely flip to "lost"). Show a loading state instead.
  const local = item.preview ?? item.url
  return isLocal(local) ? local : ''
}

watch(() => props.attachments, (items) => {
  const keys = new Set((items || []).map(keyOf))
  // Revoke object URLs for attachments that left the list.
  for (const [key, url] of srcs.value) {
    if (!keys.has(key) && /^blob:/.test(url)) URL.revokeObjectURL(url)
  }
  const next = new Map()
  for (const [key, url] of srcs.value) if (keys.has(key)) next.set(key, url)
  srcs.value = next
  for (const item of items || []) void resolve(item)
}, { immediate: true, deep: true })

onBeforeUnmount(() => {
  for (const url of srcs.value.values()) {
    if (/^blob:/.test(url)) URL.revokeObjectURL(url)
  }
})

function open(item, event) {
  trigger = event.currentTarget
  selected.value = item
  dialog.value.showModal()
}
function close() {
  dialog.value?.close()
  selected.value = null
  trigger?.focus()
}
function markFailed(item) {
  failed.value.add(keyOf(item))
  failed.value = new Set(failed.value)
}
function isFailed(item) {
  return failed.value.has(keyOf(item))
}
</script>

<template>
  <div v-if="attachments.length" class="attachment-gallery">
    <template v-for="(item, index) in attachments" :key="item.id ?? index">
      <button v-if="isFailed(item)" type="button" class="attachment-thumbnail attachment-lost" :aria-label="`图片已失效：${item.original_name || '图片'}`" disabled>
        <span class="attachment-lost-label">图片已失效</span>
      </button>
      <button v-else type="button" class="attachment-thumbnail" :aria-label="`查看图片：${item.original_name || '图片'}`" @click="open(item, $event)">
        <img v-if="displaySrc(item)" :src="displaySrc(item)" :alt="item.original_name || '图片附件'" @error="markFailed(item)">
        <span v-else class="attachment-loading" aria-hidden="true">…</span>
      </button>
    </template>
    <dialog ref="dialog" class="attachment-lightbox" aria-label="图片预览" @cancel.prevent="close" @click.self="close">
      <button type="button" class="preview-close" aria-label="关闭图片预览" autofocus @click="close">关闭</button>
      <img v-if="selected" :src="displaySrc(selected)" :alt="selected.original_name || '图片附件'">
    </dialog>
  </div>
</template>

<style scoped>
.attachment-gallery { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.attachment-thumbnail { padding: 0; width: 80px; height: 80px; overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface-sunken); cursor: zoom-in; }
.attachment-thumbnail:hover { border-color: var(--color-text-secondary); }
.attachment-thumbnail:active { opacity: .8; }
.attachment-thumbnail img { width: 100%; height: 100%; object-fit: cover; }
.attachment-loading { display: grid; place-items: center; width: 100%; height: 100%; color: var(--color-text-tertiary); font-size: var(--text-lg); }
.attachment-lost { cursor: default; display: grid; place-items: center; }
.attachment-lost-label { font-size: var(--text-xs); color: var(--color-text-tertiary); padding: var(--space-2); text-align: center; }
.attachment-lightbox { max-width: 92vw; max-height: 90vh; padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-2xl); background: var(--color-surface); color: var(--color-text-primary); box-shadow: var(--shadow-overlay); }
.attachment-lightbox::backdrop { background: rgb(0 0 0 / 65%); }
.attachment-lightbox > img { display: block; max-width: 82vw; max-height: 75vh; object-fit: contain; }
.preview-close { display: block; margin: 0 0 var(--space-3) auto; padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-pill); background: var(--color-surface); color: inherit; cursor: pointer; }
.preview-close:hover { background: var(--color-surface-hover); }
</style>
