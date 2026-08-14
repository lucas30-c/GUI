import { test, expect } from '@playwright/test';

/**
 * M3-02 局部精修闭环 E2E（Spec 006「E2E 场景：连续两轮精修」12 步）。
 *
 * 步骤 1 / 2 由 playwright.config.ts 的 webServer 数组完成（干净进程）：
 * 确定性轨道 —— FastAPI 经 tests/e2e_app.py 注入测试替身（仅测试范围）与
 * Vite dev server（5173 → 8000）。
 */

const GOLD_SUBTITLE = '每一杯都是匠心之作，从产地到杯中的精品咖啡体验';
const GOLD_CARD_NAME = '经典拿铁';

const ROUND_1_TEXT = 'E2E 第一轮标题';
const ROUND_2_TEXT = 'E2E 第二轮按钮';

test('连续两轮局部精修：修改累计生效且非目标区域零变更', async ({ page }) => {
  // 步骤 3：打开页面，Gold Case 渲染完成
  await page.goto('/');
  const title = page.locator('[data-node-id="hero.title"]');
  const button = page.locator('[data-node-id="hero.primary-button"]');
  const subtitle = page.locator('[data-node-id="hero.subtitle"]');
  const cardName = page.locator('[data-node-id="menu.card-1.name"]');

  await expect(title).toHaveText('Brew & Bean');
  await expect(button).toHaveText('查看菜单');
  await expect(subtitle).toHaveText(GOLD_SUBTITLE);
  await expect(cardName).toHaveText(GOLD_CARD_NAME);

  // 步骤 4：选中第一轮目标节点 hero.title（AC-77）
  await title.click();
  await expect(page.getByTestId('panel-node-id')).toHaveText('hero.title');
  await expect(page.getByTestId('panel-node-type')).toHaveText('Heading');

  // 步骤 5：输入指令并提交，等待第一轮完成
  await page.getByTestId('refine-instruction').fill(`set_text:${ROUND_1_TEXT}`);
  await page.getByTestId('refine-submit').click();
  await expect(page.getByTestId('refine-loading')).toHaveCount(0);

  // 步骤 6：目标节点文案已更新（AC-78）
  await expect(title).toHaveText(ROUND_1_TEXT);

  // 步骤 7：非目标节点文案保持初始值（AC-79）
  await expect(subtitle).toHaveText(GOLD_SUBTITLE);
  await expect(cardName).toHaveText(GOLD_CARD_NAME);

  // 步骤 8：结果面板可见 Patch 操作与 nonTargetNodesUnchanged: true（AC-80）
  await expect(page.getByTestId('refine-patch-op')).toHaveText('update_props');
  await expect(page.getByTestId('refine-patch-target')).toHaveText('hero.title');
  await expect(page.getByTestId('refine-integrity-flag')).toHaveText(
    'nonTargetNodesUnchanged: true',
  );
  await expect(page.getByTestId('refine-error')).toHaveCount(0);
  // 成功后 instruction 已清空
  await expect(page.getByTestId('refine-instruction')).toHaveValue('');

  // 步骤 9：选中第二轮目标节点并提交（AC-81）
  await button.click();
  await expect(page.getByTestId('panel-node-id')).toHaveText('hero.primary-button');
  await page.getByTestId('refine-instruction').fill(`set_text:${ROUND_2_TEXT}`);
  await page.getByTestId('refine-submit').click();
  await expect(page.getByTestId('refine-loading')).toHaveCount(0);
  await expect(page.getByTestId('refine-error')).toHaveCount(0);
  await expect(page.getByTestId('refine-patch-target')).toHaveText('hero.primary-button');
  await expect(page.getByTestId('refine-integrity-flag')).toHaveText(
    'nonTargetNodesUnchanged: true',
  );

  // 步骤 10：第二轮基于第一轮返回的最新 document —— hero.title 未回退
  await expect(title).toHaveText(ROUND_1_TEXT);
  await expect(title).not.toHaveText('Brew & Bean');

  // 步骤 11：两轮修改累计存在（AC-82）
  await expect(title).toHaveText(ROUND_1_TEXT);
  await expect(button).toHaveText(ROUND_2_TEXT);

  // 步骤 12：第二轮后非目标节点仍未变（AC-83）
  await expect(subtitle).toHaveText(GOLD_SUBTITLE);
  await expect(cardName).toHaveText(GOLD_CARD_NAME);
});
