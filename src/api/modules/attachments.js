import http from '../http'

export function uploadAttachment(file) {
  const body = new FormData()
  body.append('file', file)
  return http.post('/chat/attachments', body, { headers: { 'Content-Type': 'multipart/form-data' } })
}

export function attachmentError(error, fallback = '图片上传失败，请重试') {
  const text = JSON.stringify([error?.code, error?.message, error?.data]).toLowerCase()
  if (error?.status === 402 || /insufficient|积分不足/.test(text)) return '积分不足，无法继续生成'
  if (error?.status === 413 || /too.large|size.limit|图片太大|超过.*10/.test(text)) return '图片太大（>10MB）'
  if (/vision.*unavailable|provider.*unavailable|provider.*不可用/.test(text)) return 'Vision provider 不可用'
  if (/vision.*not.supported|unsupported.*vision|model.*not.support|模型.*不支持/.test(text)) return '当前模型不支持图片'
  if (error?.status === 415 || /unsupported.*(format|type)|格式不支持|不支持.*格式/.test(text)) return '图片格式不支持'
  return fallback
}

export function attachmentUrl(value) {
  if (!value) return ''
  try {
    const base = new URL(import.meta.env.VITE_API_BASE_URL || '/', window.location.origin)
    const url = new URL(value, `${base.href.replace(/\/$/, '')}/`)
    // Only same-origin http(s) URLs are safe to fetch: the axios interceptor
    // attaches the bearer token, so never hand it to an arbitrary host.
    const safe = ['http:', 'https:'].includes(url.protocol) && url.origin === base.origin
    return safe ? url.href : ''
  } catch { return '' }
}
