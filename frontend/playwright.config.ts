import { defineConfig } from '@playwright/test';

/**
 * E2E 双轨装配（Real-Provider-only 架构）：
 *
 * 轨道 A — 确定性回归（默认 baseURL 5173 → 后端 8000）：
 *   后端注入测试替身（tests/e2e_app.py，测试范围内），UI 交互链路的
 *   零模型回归门禁，逐字节确定性。
 *
 * 轨道 B — 真实模型浏览器验收（5174 → 后端 8002）：
 *   生产 app（genui_api.main:app）+ .env 真实凭证；仅由
 *   e2e/complex-generation.spec.ts 使用（该 spec 内 test.use 覆盖 baseURL）。
 *
 * reuseExistingServer 恒为 false：禁止复用未知旧服务，端口冲突直接失败，
 * 保证每次运行都从干净进程启动。运行前请确保 8000/8002/5173/5174 空闲。
 */

const BACKEND_DIR = '../backend';

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://127.0.0.1:5173' },
  webServer: [
    {
      // 轨道 A 后端：确定性替身应用（测试范围内，无需凭证）
      name: 'backend-deterministic',
      command:
        'PYTHONPATH=src:. .venv/bin/python -m uvicorn tests.e2e_app:app --host 127.0.0.1 --port 8000',
      cwd: BACKEND_DIR,
      url: 'http://127.0.0.1:8000/health',
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      // 轨道 B 后端：生产 app + .env 真实凭证（加载责任在启动命令内完成）
      name: 'backend-real',
      command:
        "bash -c 'set -a; [ -f ../.env ] && . ../.env; set +a; exec env PYTHONPATH=src .venv/bin/python -m uvicorn genui_api.main:app --host 127.0.0.1 --port 8002'",
      cwd: BACKEND_DIR,
      url: 'http://127.0.0.1:8002/health',
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      // 轨道 A 前端：代理 → 8000（确定性）
      name: 'frontend-deterministic',
      command: 'npm run dev -- --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      // 轨道 B 前端：代理 → 8002（真实模型），独立端口与实例
      name: 'frontend-real',
      command:
        "bash -c 'GENUI_E2E_API_PORT=8002 npm run dev -- --port 5174 --strictPort'",
      url: 'http://127.0.0.1:5174',
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
