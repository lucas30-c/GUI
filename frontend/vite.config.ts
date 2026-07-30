/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  server: {
    // 显式绑定 IPv4 回环：默认 localhost 在本机只监听 ::1，
    // 会导致 Playwright baseURL http://127.0.0.1:5173 连接失败
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    // e2e/ 由 Playwright 运行，排除在 Vitest 之外
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
