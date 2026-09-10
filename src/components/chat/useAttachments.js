import { computed, onBeforeUnmount, ref } from 'vue'
import { attachmentError, uploadAttachment } from '../../api/modules/attachments'

export function useAttachments() {
  const attachments = ref([])
  const uploadError = ref('')
  const blocked = computed(() => attachments.value.some((item) => item.status !== 'ready'))
  function remove(item) {
    attachments.value = attachments.value.filter((entry) => entry !== item)
    if (item.preview) URL.revokeObjectURL(item.preview)
  }
  function clear() {
    attachments.value.forEach((item) => { if (item.preview) URL.revokeObjectURL(item.preview) })
    attachments.value = []
    uploadError.value = ''
  }
  async function add(files) {
    uploadError.value = ''
    for (const file of Array.from(files)) {
      if (attachments.value.length >= 4) { uploadError.value = '每条消息最多添加 4 张图片'; break }
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { uploadError.value = '图片格式不支持'; continue }
      if (file.size > 10 * 1024 * 1024) { uploadError.value = '图片太大（>10MB）'; continue }
      const preview = URL.createObjectURL(file)
      attachments.value.push({ original_name: file.name, url: preview, preview, status: 'uploading' })
      const item = attachments.value.at(-1)
      // Reserve all slots synchronously; removed uploads never reappear.
      void uploadAttachment(file).then((result) => {
        if (!attachments.value.includes(item)) return
        Object.assign(item, result, { status: 'ready' })
      }).catch((error) => {
        if (!attachments.value.includes(item)) return
        item.status = 'failed'
        item.error = attachmentError(error)
      })
    }
  }
  onBeforeUnmount(clear)
  return { attachments, uploadError, blocked, add, remove, clear }
}
