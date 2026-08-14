import { test, expect } from '@playwright/test';

/**
 * 真实模型浏览器验收 E2E（Owner §6.4）。
 *
 * 轨道 B：前端 5174 → 代理 → 生产后端 8002（.env 真实凭证，Real Provider，
 * 结构化输出 + 无损规范化 + 至多一次精准 repair）。前后端均由
 * playwright.config.ts 从干净进程启动（reuseExistingServer=false）。
 *
 * 覆盖：
 * 1. 真实完成两次连续生成（输入 → 点击 → 等待 Real Provider）；
 * 2. 检查限定在生成画布区域（.workbench-canvas），不检查整个 body；
 * 3. 验证存在有意义的内容节点（节点数与文案下限）；
 * 4. 验证没有 DSL 内部错误暴露（Value error / schema_error / 路径原文）；
 * 5. 验证布局无明显横向溢出、无破图；
 * 6. 收集 Console 错误与失败请求（Network），断言为空；
 * 7. 模拟服务端失败（route 拦截）：验证用户可读错误 + 当前有效页面被保留。
 */

test.use({ baseURL: 'http://127.0.0.1:5174' });

const PROMPT_FIRST = '为独立摄影师创建一个深色作品集主页，包含项目分类、客户评价和联系入口';
const PROMPT_SECOND = '生成一个企业服务落地页，包含 Hero 介绍、核心服务、客户案例和咨询表单';

/** 内部校验原文指纹：画布或错误面板出现任何一项即判定为泄漏 */
const INTERNAL_ERROR_FINGERPRINTS = [
  'Value error',
  'Extra inputs are not permitted',
  'schema_error',
  'Traceback',
  'pydantic',
];

interface Observability {
  consoleErrors: string[];
  failedRequests: string[];
}

function attachObservability(page: import('@playwright/test').Page): Observability {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('requestfailed', (request) => {
    failedRequests.push(`${request.method()} ${request.url()} (network)`);
  });
  page.on('response', (response) => {
    if (response.status() >= 500) {
      failedRequests.push(`${response.status()} ${response.url()}`);
    }
  });
  return { consoleErrors, failedRequests };
}

async function generateAndWait(page: import('@playwright/test').Page, prompt: string) {
  await page.getByTestId('generate-prompt').fill(prompt);
  await page.getByTestId('generate-submit').click();
  // Real Provider：复杂页面首次生成 + 可能的一次 repair，给足超时
  await expect(page.getByTestId('generate-loading')).toHaveCount(0, { timeout: 280_000 });
}

async function assertCanvasHealthy(page: import('@playwright/test').Page) {
  // 检查范围限定在生成画布区域（不是整个 body）
  const canvas = page.locator('.workbench-canvas');
  await expect(canvas).toBeVisible();

  const nodes = canvas.locator('[data-node-id]');
  const nodeCount = await nodes.count();
  expect(nodeCount, '画布内应存在有意义的节点数量').toBeGreaterThanOrEqual(8);

  // 有意义的内容节点：至少 5 段非空文案
  const texts = await canvas.locator('h1, h2, h3, p, button').allTextContents();
  const nonEmpty = texts.filter((text) => text.trim().length > 0);
  expect(nonEmpty.length, '应存在有意义的内容文案').toBeGreaterThanOrEqual(5);

  // 无 DSL 内部错误暴露
  const canvasText = await canvas.innerText();
  for (const fingerprint of INTERNAL_ERROR_FINGERPRINTS) {
    expect(canvasText, `画布不得出现内部错误原文: ${fingerprint}`).not.toContain(fingerprint);
  }

  // 无明显横向溢出
  const overflows = await canvas.evaluate(
    (element) => element.scrollWidth > element.clientWidth + 2,
  );
  expect(overflows, '画布不得出现横向溢出').toBe(false);

  // 等待远程占位图完成加载（placehold.co 单张约 2-3s），再判定破图
  await expect
    .poll(
      async () =>
        canvas
          .locator('img')
          .evaluateAll((images) => images.filter((img) => !img.complete).length),
      { timeout: 30_000 },
    )
    .toBe(0);

  // 无破图（若模型生成了 Image 节点）
  const brokenImages = await canvas
    .locator('img')
    .evaluateAll(
      (images) =>
        images.filter((img) => !img.complete || img.naturalWidth === 0).length,
    );
  expect(brokenImages, '不得出现破图').toBe(0);
}

test.describe('Real Provider 真实浏览器验收', () => {
  test.setTimeout(600_000);

  test('连续两次真实生成：内容完整、无内部错误暴露、无溢出破图、Console/Network 干净', async ({
    page,
  }) => {
    const { consoleErrors, failedRequests } = attachObservability(page);

    await page.goto('/');
    // 初始 Gold Case 渲染正常
    await expect(page.locator('[data-node-id]')).not.toHaveCount(0);
    await expect(page.getByTestId('generate-error')).toHaveCount(0);

    // —— 第一次生成 ——
    await generateAndWait(page, PROMPT_FIRST);
    await expect(page.getByTestId('generate-error')).toHaveCount(0);
    await assertCanvasHealthy(page);

    // —— 连续第二次生成 ——
    await generateAndWait(page, PROMPT_SECOND);
    await expect(page.getByTestId('generate-error')).toHaveCount(0);
    await assertCanvasHealthy(page);

    // Console / Network：无未处理异常、无失败请求
    expect(consoleErrors, `Console 错误: ${consoleErrors.join(' | ')}`).toEqual([]);
    expect(failedRequests, `失败请求: ${failedRequests.join(' | ')}`).toEqual([]);
  });

  test('生成失败时：用户可读错误 + 当前有效页面保留 + 内部细节默认不直显', async ({
    page,
  }) => {
    const { consoleErrors, failedRequests } = attachObservability(page);

    await page.goto('/');
    const beforeNodes = await page.locator('[data-node-id]').count();
    expect(beforeNodes).toBeGreaterThan(0);

    // 模拟服务端失败（网络层拦截，不触碰真实后端）
    await page.route('**/api/v1/dsl/generate', (route) =>
      route.fulfill({
        status: 502,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          requestId: 'e2e-simulated-failure',
          error: {
            code: 'invalid_generated_document',
            message: 'AI 生成的页面未通过系统校验，请重试，或尝试简化页面描述。',
            issues: [
              {
                path: 'root.children.4.style.margin',
                code: 'schema_error',
                message: 'internal-detail-marker',
              },
            ],
          },
        }),
      }),
    );

    await page.getByTestId('generate-prompt').fill(PROMPT_FIRST);
    await page.getByTestId('generate-submit').click();
    await expect(page.getByTestId('generate-loading')).toHaveCount(0, { timeout: 30_000 });

    // 用户可读错误面板出现：可读文案 + 请求编号
    const errorPanel = page.getByTestId('generate-error');
    await expect(errorPanel).toHaveCount(1);
    await expect(page.getByTestId('generate-error-message')).toContainText(
      'AI 生成的页面未通过系统校验',
    );
    await expect(page.getByTestId('generate-error-request-id')).toContainText(
      'e2e-simulated-failure',
    );

    // 错误面板默认可见文本中不含内部诊断原文（折叠在技术细节内）
    const visibleErrorText = await errorPanel.innerText();
    expect(visibleErrorText).not.toContain('internal-detail-marker');
    expect(visibleErrorText).not.toContain('root.children.4');

    // 当前有效页面被完整保留（节点数不变，画布健康）
    const afterNodes = await page.locator('[data-node-id]').count();
    expect(afterNodes).toBe(beforeNodes);
    await assertCanvasHealthy(page);

    // 浏览器会把被拦截的 502 记为「Failed to load resource」console 错误——
    // 这是本测试主动注入的预期失败，须从断言中排除；其余 console 错误仍须为空。
    const unexpectedConsoleErrors = consoleErrors.filter(
      (message) => !message.includes('Failed to load resource'),
    );
    expect(unexpectedConsoleErrors).toEqual([]);
    // route 拦截返回 502 属于预期内失败，仅断言无其他网络层失败
    const unexpected = failedRequests.filter((entry) => !entry.includes('/api/v1/dsl/generate'));
    expect(unexpected).toEqual([]);
  });
});
