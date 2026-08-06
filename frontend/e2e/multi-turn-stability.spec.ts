import { test, expect } from '@playwright/test';

/**
 * M4-03 多轮上下文稳定性 E2E（Spec 009「E2E 场景：浏览器内 3 连轮」）。
 *
 * 前后端由 playwright.config.ts 的 webServer 数组统一启动：
 * FastAPI（MockProvider / MockGenerationProvider 为默认 Provider）与 Vite dev server。
 *
 * 断言的是「多轮之后仍然只改该改的」这一稳定性性质：
 * 目标节点逐轮更新、两个见证节点文案零变更、已确认轮次计数 1 → 2 → 3、
 * 生成新初稿后计数回到 0。
 */

const GOLD_TITLE = 'Brew & Bean';
const GOLD_SUBTITLE = '每一杯都是匠心之作，从产地到杯中的精品咖啡体验';
const GOLD_CARD_NAME = '经典拿铁';

const ROUND_1_TEXT = 'E2E 多轮第一版标题';
const ROUND_2_TEXT = 'E2E 多轮第二版标题';
const ROUND_3_TEXT = 'E2E 多轮第三版标题';

/** 咖啡店初稿模板文案（backend/src/genui_api/generation/templates.py） */
const DRAFT_TITLE = '晨光咖啡工坊';

test('同节点 3 连轮：文案逐轮更新、见证节点零变更、轮次计数 1→2→3，生成后清空', async ({
  page,
}) => {
  await page.goto('/');
  const title = page.locator('[data-node-id="hero.title"]');
  const subtitle = page.locator('[data-node-id="hero.subtitle"]');
  const cardName = page.locator('[data-node-id="menu.card-1.name"]');
  const historyCount = page.getByTestId('refine-history-count');
  const historyItems = page.getByTestId('refine-history-item');

  await expect(title).toHaveText(GOLD_TITLE);
  await expect(subtitle).toHaveText(GOLD_SUBTITLE);
  await expect(cardName).toHaveText(GOLD_CARD_NAME);

  // 初始为空态：无已确认轮次
  await expect(page.getByTestId('refine-history-empty')).toHaveCount(1);
  await expect(historyItems).toHaveCount(0);
  await expect(historyCount).toContainText('0 / 20');

  await title.click();
  await expect(page.getByTestId('panel-node-id')).toHaveText('hero.title');
  await expect(page.getByTestId('panel-node-type')).toHaveText('Heading');

  // --- 轮 1 ---
  await page.getByTestId('refine-instruction').fill(`set_text:${ROUND_1_TEXT}`);
  await page.getByTestId('refine-submit').click();
  await expect(page.getByTestId('refine-loading')).toHaveCount(0);
  await expect(page.getByTestId('refine-error')).toHaveCount(0);

  await expect(title).toHaveText(ROUND_1_TEXT);
  await expect(historyItems).toHaveCount(1);
  await expect(historyCount).toContainText('1 / 20');
  await expect(historyItems.first()).toContainText('hero.title');
  await expect(subtitle).toHaveText(GOLD_SUBTITLE);
  await expect(cardName).toHaveText(GOLD_CARD_NAME);

  // --- 轮 2（携带 1 条已确认历史）---
  await page.getByTestId('refine-instruction').fill(`set_text:${ROUND_2_TEXT}`);
  await page.getByTestId('refine-submit').click();
  await expect(page.getByTestId('refine-loading')).toHaveCount(0);
  await expect(page.getByTestId('refine-error')).toHaveCount(0);

  await expect(title).toHaveText(ROUND_2_TEXT);
  await expect(historyItems).toHaveCount(2);
  await expect(historyCount).toContainText('2 / 20');
  await expect(subtitle).toHaveText(GOLD_SUBTITLE);
  await expect(cardName).toHaveText(GOLD_CARD_NAME);

  // --- 轮 3（携带 2 条已确认历史）---
  await page.getByTestId('refine-instruction').fill(`set_text:${ROUND_3_TEXT}`);
  await page.getByTestId('refine-submit').click();
  await expect(page.getByTestId('refine-loading')).toHaveCount(0);
  await expect(page.getByTestId('refine-error')).toHaveCount(0);

  await expect(title).toHaveText(ROUND_3_TEXT);
  await expect(historyItems).toHaveCount(3);
  await expect(historyCount).toContainText('3 / 20');

  // 3 轮之后：完整性证明仍为 true，两个见证节点仍是初始文案
  await expect(page.getByTestId('refine-integrity-flag')).toHaveText(
    'nonTargetNodesUnchanged: true',
  );
  await expect(page.getByTestId('refine-integrity-node')).toContainText('hero.title');
  await expect(subtitle).toHaveText(GOLD_SUBTITLE);
  await expect(cardName).toHaveText(GOLD_CARD_NAME);

  // --- 生成新初稿 → 已确认轮次清空（DD-6）---
  await page.getByTestId('generate-prompt').fill('我要一个咖啡店的落地页');
  await page.getByTestId('generate-submit').click();
  await expect(page.getByTestId('generate-loading')).toHaveCount(0);
  await expect(page.getByTestId('generate-error')).toHaveCount(0);

  await expect(page.locator('[data-node-id="hero.title"]')).toHaveText(DRAFT_TITLE);
  await expect(historyItems).toHaveCount(0);
  await expect(page.getByTestId('refine-history-empty')).toHaveCount(1);
  await expect(historyCount).toContainText('0 / 20');
});
