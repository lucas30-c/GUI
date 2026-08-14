import { test, expect } from '@playwright/test';

/**
 * M4-01 一句话生成初稿 → 选择节点 → 局部精修 全链路 E2E（Spec 007 AC-68 ~ AC-72）。
 *
 * 前后端由 playwright.config.ts 的 webServer 数组统一启动（干净进程）：
 * 确定性轨道 —— FastAPI 经 tests/e2e_app.py 注入测试替身（MockGenerationProvider
 * + MockProvider，仅测试范围）与 Vite dev server（5173 → 8000）。
 * 真实模型浏览器验收由 e2e/complex-generation.spec.ts（轨道 B，5174 → 8002）承担。
 */

const GOLD_TITLE = 'Brew & Bean';

/** 咖啡店初稿模板文案（backend/tests/doubles/templates.py） */
const DRAFT_TITLE = '晨光咖啡工坊';
const DRAFT_SUBTITLE = '清晨现烘的豆子，配一杯慢下来的时间';
const DRAFT_CTA = '预订座位';

const REFINED_TITLE = 'E2E 初稿精修后的标题';

test('一句话生成初稿后可继续局部精修：文案更新且见证节点不变', async ({ page }) => {
  // 步骤 1：打开页面，初始渲染的是 Gold Case
  await page.goto('/');
  const title = page.locator('[data-node-id="hero.title"]');
  const subtitle = page.locator('[data-node-id="hero.subtitle"]');
  const cta = page.locator('[data-node-id="hero.cta"]');

  await expect(title).toHaveText(GOLD_TITLE);

  // 步骤 2：输入含「咖啡」的一句话需求并提交生成
  await page.getByTestId('generate-prompt').fill('我要一个咖啡店的落地页');
  await page.getByTestId('generate-submit').click();
  await expect(page.getByTestId('generate-loading')).toHaveCount(0);
  await expect(page.getByTestId('generate-error')).toHaveCount(0);

  // 步骤 3：页面出现咖啡店模板文案，且与 Gold Case 文案不同（AC-69）
  await expect(title).toHaveText(DRAFT_TITLE);
  await expect(title).not.toHaveText(GOLD_TITLE);
  await expect(subtitle).toHaveText(DRAFT_SUBTITLE);
  await expect(cta).toHaveText(DRAFT_CTA);
  // 旧文档节点已不存在（整文档替换）
  await expect(page.locator('[data-node-id="hero.primary-button"]')).toHaveCount(0);

  // 步骤 4：生成成功后无选中态、精修面板回到未选中、结果面板为空、prompt 已清空
  await expect(page.locator('[data-selected]')).toHaveCount(0);
  await expect(page.getByTestId('panel-node-id')).toHaveCount(0);
  await expect(page.getByTestId('refine-patch')).toHaveCount(0);
  await expect(page.getByTestId('refine-result-empty')).toHaveCount(1);
  await expect(page.getByTestId('generate-prompt')).toHaveValue('');

  // 步骤 5：点击新文档的 hero.title，精修面板显示其 ID 与 Type（AC-70）
  await title.click();
  await expect(page.getByTestId('panel-node-id')).toHaveText('hero.title');
  await expect(page.getByTestId('panel-node-type')).toHaveText('Heading');

  // 步骤 6：提交 set_text: 精修指令（AC-71）
  await page.getByTestId('refine-instruction').fill(`set_text:${REFINED_TITLE}`);
  await page.getByTestId('refine-submit').click();
  await expect(page.getByTestId('refine-loading')).toHaveCount(0);
  await expect(page.getByTestId('refine-error')).toHaveCount(0);

  await expect(title).toHaveText(REFINED_TITLE);

  // 步骤 7：见证节点保持模板原值不变（AC-72）
  await expect(subtitle).toHaveText(DRAFT_SUBTITLE);
  await expect(cta).toHaveText(DRAFT_CTA);

  // 步骤 8：结果面板给出 Patch 与完整性证明
  await expect(page.getByTestId('refine-patch-op')).toHaveText('update_props');
  await expect(page.getByTestId('refine-patch-target')).toHaveText('hero.title');
  await expect(page.getByTestId('refine-integrity-flag')).toHaveText(
    'nonTargetNodesUnchanged: true',
  );
});

test('「意图无法识别」分支已移除：任意需求都得到合法初稿（确定性替身回退模板）', async ({
  page,
}) => {
  await page.goto('/');

  await page.getByTestId('generate-prompt').fill('随便来点什么');
  await page.getByTestId('generate-submit').click();
  await expect(page.getByTestId('generate-loading')).toHaveCount(0);

  // Real-Provider-only：产品不存在 unrecognized_intent 安全失败分支；
  // 确定性替身对无关键词 prompt 回退到默认模板，仍是合法可渲染文档。
  await expect(page.getByTestId('generate-error')).toHaveCount(0);
  const canvasNodes = page.locator('.workbench-canvas [data-node-id]');
  await expect(canvasNodes.first()).toBeVisible();
  expect(await canvasNodes.count()).toBeGreaterThanOrEqual(5);
  // 回退模板（产品介绍）的首屏标题出现
  await expect(page.locator('[data-node-id="hero.title"]')).toHaveText('Latchwork 协作台');
});
