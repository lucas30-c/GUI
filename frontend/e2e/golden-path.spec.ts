import { test, expect } from '@playwright/test';
import type { Locator, Page } from '@playwright/test';

/**
 * M4-04 Golden Path E2E（Spec 010 AC-39 / docs/PRODUCT.md §9 步骤 1 ~ 5）。
 *
 * 一条 spec 覆盖普通用户的完整验收链路：
 * 一句话生成初稿 → 点击选中控件 → 文案精修 → 颜色精修 → 尺寸精修 → 非目标节点零变更。
 *
 * 前后端由 playwright.config.ts 的 webServer 数组统一启动（干净进程）：
 * 确定性轨道 —— FastAPI 经 tests/e2e_app.py 注入测试替身（仅测试范围）与
 * Vite dev server（5173 → 8000）。因此本 spec 是**确定性**的收口证据
 * （无网络、无凭证、无随机）。真实模型路径的证据由 opt-in 的
 * backend/tests/llm/test_real_*.py 与真实浏览器验收 complex-generation.spec.ts 承担。
 */

/** 咖啡店初稿模板（backend/tests/doubles/templates.py） */
const DRAFT_TITLE = '晨光咖啡工坊';
const DRAFT_SUBTITLE = '清晨现烘的豆子，配一杯慢下来的时间';
const DRAFT_MENU_TITLE = '本店饮品';
const DRAFT_CONTACT_HOURS = '每日 08:00 - 20:00，工作日可提前预留吧台位';
const DRAFT_CTA = '预订座位';

/** 初稿中的初始计算样式 */
const DRAFT_TITLE_COLOR = 'rgb(59, 35, 20)'; // #3b2314
const DRAFT_TITLE_FONT_SIZE = '44px';
const DRAFT_SUBTITLE_COLOR = 'rgb(107, 74, 50)'; // #6b4a32
const DRAFT_SUBTITLE_FONT_SIZE = '18px';
const DRAFT_MENU_TITLE_COLOR = 'rgb(59, 35, 20)'; // #3b2314
const DRAFT_CTA_FONT_SIZE = '16px';

const TITLE_NEW_TEXT = '欢迎光临';
const CTA_NEW_TEXT = '立即预订座位';

async function expectComputed(
  locator: Locator,
  property: string,
  value: string,
): Promise<void> {
  await expect
    .poll(() =>
      locator.evaluate(
        (el, prop) => window.getComputedStyle(el).getPropertyValue(prop),
        property,
      ),
    )
    .toBe(value);
}

/** 提交一轮精修，要求成功（无错误面板）并给出完整性证明 */
async function refineOk(page: Page, instruction: string): Promise<void> {
  await page.getByTestId('refine-instruction').fill(instruction);
  await page.getByTestId('refine-submit').click();
  await expect(page.getByTestId('refine-loading')).toHaveCount(0);
  await expect(page.getByTestId('refine-error')).toHaveCount(0);
  await expect(page.getByTestId('refine-integrity-flag')).toHaveText(
    'nonTargetNodesUnchanged: true',
  );
}

test('Golden Path：生成 → 选中 → 文案 → 颜色 → 尺寸，全链路非目标零变更', async ({ page }) => {
  // === 步骤 1：输入一句话需求 → 页面渲染出初稿 ===
  await page.goto('/');
  await page.getByTestId('generate-prompt').fill('我要一个咖啡店的落地页');
  await page.getByTestId('generate-submit').click();
  await expect(page.getByTestId('generate-loading')).toHaveCount(0);
  await expect(page.getByTestId('generate-error')).toHaveCount(0);

  const title = page.locator('[data-node-id="hero.title"]');
  const cta = page.locator('[data-node-id="hero.cta"]');
  const subtitle = page.locator('[data-node-id="hero.subtitle"]');
  const menuTitle = page.locator('[data-node-id="menu.title"]');
  const contactHours = page.locator('[data-node-id="contact.hours"]');

  await expect(title).toHaveText(DRAFT_TITLE);
  await expect(subtitle).toHaveText(DRAFT_SUBTITLE);
  await expect(menuTitle).toHaveText(DRAFT_MENU_TITLE);
  await expect(contactHours).toHaveText(DRAFT_CONTACT_HOURS);
  await expect(cta).toHaveText(DRAFT_CTA);
  await expectComputed(title, 'color', DRAFT_TITLE_COLOR);
  await expectComputed(title, 'font-size', DRAFT_TITLE_FONT_SIZE);

  /** 三个见证节点：文案与计算样式在整条链路中必须逐字不变（步骤 6） */
  async function expectWitnessesUnchanged(): Promise<void> {
    await expect(subtitle).toHaveText(DRAFT_SUBTITLE);
    await expect(menuTitle).toHaveText(DRAFT_MENU_TITLE);
    await expect(contactHours).toHaveText(DRAFT_CONTACT_HOURS);
    await expectComputed(subtitle, 'color', DRAFT_SUBTITLE_COLOR);
    await expectComputed(subtitle, 'font-size', DRAFT_SUBTITLE_FONT_SIZE);
    await expectComputed(menuTitle, 'color', DRAFT_MENU_TITLE_COLOR);
    await expectComputed(menuTitle, 'text-align', 'center');
  }

  await expectWitnessesUnchanged();

  // === 步骤 2：点击 Heading 节点 → 选中态出现 ===
  await title.click();
  await expect(page.getByTestId('panel-node-id')).toHaveText('hero.title');
  await expect(page.getByTestId('panel-node-type')).toHaveText('Heading');
  await expect(title).toHaveAttribute('data-selected', 'true');
  await expect(title).toHaveAttribute('aria-current', 'true');
  await expect(page.locator('[data-selected]')).toHaveCount(1);

  // === 步骤 3：文案精修 ===
  await refineOk(page, `set_text:${TITLE_NEW_TEXT}`);
  await expect(title).toHaveText(TITLE_NEW_TEXT);
  await expect(page.getByTestId('refine-patch-op')).toHaveText('update_props');
  await expect(page.getByTestId('refine-patch-target')).toHaveText('hero.title');
  // 文案轮不改样式
  await expectComputed(title, 'color', DRAFT_TITLE_COLOR);
  await expectComputed(title, 'font-size', DRAFT_TITLE_FONT_SIZE);
  await expectWitnessesUnchanged();

  // === 步骤 4：颜色精修 ===
  await refineOk(page, 'set_style:color=#e74c3c');
  await expectComputed(title, 'color', 'rgb(231, 76, 60)');
  await expect(page.getByTestId('refine-patch-op')).toHaveText('update_style');
  await expect(page.getByTestId('refine-patch-style')).toContainText('#e74c3c');
  // 颜色轮不改文案，也不改未提及的字号
  await expect(title).toHaveText(TITLE_NEW_TEXT);
  await expectComputed(title, 'font-size', DRAFT_TITLE_FONT_SIZE);
  await expectWitnessesUnchanged();

  // === 步骤 5：尺寸精修 ===
  await refineOk(page, 'set_style:fontSize=24px');
  await expectComputed(title, 'font-size', '24px');
  await expect(page.getByTestId('refine-patch-style')).toContainText('24px');
  // 步骤 3 的文案与步骤 4 的颜色同时保留 —— 三轮修改累积成立
  await expect(title).toHaveText(TITLE_NEW_TEXT);
  await expectComputed(title, 'color', 'rgb(231, 76, 60)');
  await expectWitnessesUnchanged();

  // === 步骤 6：完整性证明与已确认轮次可见 ===
  await expect(page.getByTestId('refine-integrity-node')).toContainText('hero.title');
  await expect(page.getByTestId('refine-last-success')).toContainText('hero.title');
  await expect(page.getByTestId('refine-history-item')).toHaveCount(3);
  await expect(page.getByTestId('refine-history-count')).toContainText('3 / 20');

  // === 步骤 7：同一链路换到「主按钮」再走一遍文案 → 颜色 → 尺寸（PRODUCT §9 步骤 3 措辞）===
  await cta.click();
  await expect(page.getByTestId('panel-node-id')).toHaveText('hero.cta');
  await expect(page.getByTestId('panel-node-type')).toHaveText('Button');
  await expectComputed(cta, 'font-size', DRAFT_CTA_FONT_SIZE);

  await refineOk(page, `set_text:${CTA_NEW_TEXT}`);
  await expect(cta).toHaveText(CTA_NEW_TEXT);

  await refineOk(page, 'set_style:backgroundColor=#1d4ed8');
  await expectComputed(cta, 'background-color', 'rgb(29, 78, 216)');

  await refineOk(page, 'set_style:fontSize=20px');
  await expectComputed(cta, 'font-size', '20px');
  await expect(cta).toHaveText(CTA_NEW_TEXT);
  await expectComputed(cta, 'background-color', 'rgb(29, 78, 216)');

  // 主按钮三轮之后：Heading 的三轮结果与三个见证节点全部未受影响
  await expect(title).toHaveText(TITLE_NEW_TEXT);
  await expectComputed(title, 'color', 'rgb(231, 76, 60)');
  await expectComputed(title, 'font-size', '24px');
  await expectWitnessesUnchanged();
  await expect(page.getByTestId('refine-history-item')).toHaveCount(6);
});
