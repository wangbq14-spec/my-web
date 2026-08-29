import axios from 'axios'
import { describe, expect, it } from 'vitest'

describe('axios multipart request contract', () => {
  it('keeps FormData intact with a multipart Content-Type', async () => {
    let capturedConfig
    const client = axios.create({
      adapter: async (config) => {
        capturedConfig = config
        return {
          data: null,
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
        }
      },
    })
    const formData = new FormData()
    formData.append('file', new File(['content'], 'document.txt', { type: 'text/plain' }))

    await client.post('/documents', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })

    expect(capturedConfig.data).toBeInstanceOf(FormData)
    const contentType = capturedConfig.headers.getContentType()
    expect(contentType).toContain('multipart/form-data')
    expect(contentType).not.toContain('application/json')
    expect(contentType).not.toContain('application/x-www-form-urlencoded')
  })
})
