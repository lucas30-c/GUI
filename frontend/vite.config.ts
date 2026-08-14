/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Node 运行时全局量（vite/vitest 在 Node 中执行本文件）。本地声明类型，
// 避免为单个标识符引入 @types/node 依赖（新增依赖需 Owner 审批）。
declare const process: { env: Record<string, string | undefined> }

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
        // E2E 双轨：默认 8000（确定性替身回归）；GENUI_E2E_API_PORT 可切到
        // 真实模型后端端口（Playwright 真实验收专用前端实例使用）。
        target: `http://127.0.0.1:${process.env.GENUI_E2E_API_PORT || '8000'}`,
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
