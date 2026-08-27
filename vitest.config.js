import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [
    vue({
      template: {
        transformAssetUrls: {
          includeAbsolute: false,
        },
      },
    }),
  ],
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['src/**/*.test.js'],
  },
})