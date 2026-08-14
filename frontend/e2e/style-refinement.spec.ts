import { test, expect } from '@playwright/test';
import type { Locator, Page } from '@playwright/test';

/**
 * M4-04 受控样式精修 E2E（Spec 010 AC-31 / AC-17）。
 *
 * 前后端由 playwright.config.ts 的 webServer 数组统一启动（干净进程）：
 * 确定性轨道 —— FastAPI 经 tests/e2e_app.py 注入测试替身（仅测试范围）与
 * Vite dev server（5173 → 8000）。
 * 测试替身的 `set_style:` / `set_text_style:` 前缀（AP-7）提供**确定性** style 证据链，
 * 因此本 spec 是 CI 每次收口都必跑的 deterministic evidence，与 opt-in 真实模型 smoke 互补。
 *
 * 断言的性质：style 修改逐轮累积生效、未提及的 style 键保持不变、
 * 两个见证节点的**文案与计算样式**零变更、非法 style 轮次安全失败且文档不变。
 */

const GOLD_TITLE = 'Brew & Bean';
const GOLD_BUTTON = '查看菜单';
const GOLD_SUBTITLE = '每一杯都是匠心之作，从产地到杯中的精品咖啡体验';
const GOLD_MENU_TITLE = '精选饮品';

/** Gold Case 中见证节点的初始计算样式（examples/dsl/coffee-shop-landing.json） */
const SUBTITLE_COLOR = 'rgb(92, 64, 51)'; // #5c4033
const SUBTITLE_FONT_SIZE = '18px';
const MENU_TITLE_COLOR = 'rgb(44, 24, 16)'; // #2c1810

/** hero.title 的初始计算样式 */
const TITLE_INITIAL_COLOR = 'rgb(44, 24, 16)'; // #2c1810
const TITLE_INITIAL_FONT_SIZE = '48px';

const MIXED_BUTTON_TEXT = '立即预订';
const MIXED_TITLE_TEXT = '新标题';

/** 读取节点的计算样式；轮询以避免 React 提交与样式生效之间的竞态 */
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

/** 提交一轮精修并等待其结束（不判定成功/失败，由调用方断言） */
async function submitRound(page: Page, instruction: string): Promise<void> {
  await page.getByTestId('refine-instruction').fill(instruction);
  await page.getByTestId('refine-submit').click();
  await expect(page.getByTestId('refine-loading')).toHaveCount(0);
}

test('受控样式精修：逐轮累积生效、见证节点文案与样式零变更、非法 style 安全失败', async ({
  page,
}) => {
  await page.goto('/');

  const title = page.locator('[data-node-id="hero.title"]');
  const button = page.locator('[data-node-id="hero.primary-button"]');
  const subtitle = page.locator('[data-node-id="hero.subtitle"]');
  const menuTitle = page.locator('[data-node-id="menu.title"]');

  // 见证节点初始状态（文案 + 计算样式）作为后续每轮的比较基准
  await expect(title).toHaveText(GOLD_TITLE);
  await expect(button).toHaveText(GOLD_BUTTON);
  await expect(subtitle).toHaveText(GOLD_SUBTITLE);
  await expect(menuTitle).toHaveText(GOLD_MENU_TITLE);
  await expectComputed(title, 'color', TITLE_INITIAL_COLOR);
  await expectComputed(title, 'font-size', TITLE_INITIAL_FONT_SIZE);
  await expectComputed(subtitle, 'color', SUBTITLE_COLOR);
  await expectComputed(subtitle, 'font-size', SUBTITLE_FONT_SIZE);
  await expectComputed(menuTitle, 'color', MENU_TITLE_COLOR);

  /** 每轮共用的见证断言：两个非目标节点的文案与计算样式必须逐字不变 */
  async function expectWitnessesUnchanged(): Promise<void> {
    await expect(subtitle).toHaveText(GOLD_SUBTITLE);
    await expect(menuTitle).toHaveText(GOLD_MENU_TITLE);
    await expectComputed(subtitle, 'color', SUBTITLE_COLOR);
    await expectComputed(subtitle, 'font-size', SUBTITLE_FONT_SIZE);
    await expectComputed(menuTitle, 'color', MENU_TITLE_COLOR);
  }

  // 2rem 的期望像素值由根字号推导，不写死 —— 断言的是「相对单位被正确应用」
  const rootFontSize = await page.evaluate(
    () => parseFloat(window.getComputedStyle(document.documentElement).fontSize),
  );

  // --- 选中 hero.title ---
  await title.click();
  await expect(page.getByTestId('panel-node-id')).toHaveText('hero.title');
  await expect(page.getByTestId('panel-node-type')).toHaveText('Heading');

  // --- 轮 1：只改颜色 → 未提及的 fontSize 必须保持 48px（浅合并语义）---
  await submitRound(page, 'set_style:color=#e74c3c');
  await expect(page.getByTestId('refine-error')).toHaveCount(0);
  await expectComputed(title, 'color', 'rgb(231, 76, 60)');
  await expectComputed(title, 'font-size', TITLE_INITIAL_FONT_SIZE);
  await expect(page.getByTestId('refine-patch-op')).toHaveText('update_style');
  await expect(page.getByTestId('refine-patch-target')).toHaveText('hero.title');
  await expect(page.getByTestId('refine-patch-style')).toContainText('#e74c3c');
  await expect(page.getByTestId('refine-integrity-flag')).toHaveText(
    'nonTargetNodesUnchanged: true',
  );
  // 文案未被 style 轮次触碰
  await expect(title).toHaveText(GOLD_TITLE);
  await expectWitnessesUnchanged();

  // --- 轮 2：只改尺寸 → 轮 1 的颜色必须仍在（跨轮累积）---
  await submitRound(page, 'set_style:fontSize=24px');
  await expect(page.getByTestId('refine-error')).toHaveCount(0);
  await expectComputed(title, 'font-size', '24px');
  await expectComputed(title, 'color', 'rgb(231, 76, 60)');
  await expect(page.getByTestId('refine-patch-style')).toContainText('24px');
  await expect(page.getByTestId('refine-integrity-flag')).toHaveText(
    'nonTargetNodesUnchanged: true',
  );
  await expectWitnessesUnchanged();

  // --- 轮 3：一次改两个键，含相对单位（AC-31 指定指令）---
  await submitRound(page, 'set_style:color=#c0392b,fontSize=2rem');
  await expect(page.getByTestId('refine-error')).toHaveCount(0);
  await expectComputed(title, 'color', 'rgb(192, 57, 43)');
  await expectComputed(title, 'font-size', `${rootFontSize * 2}px`);
  await expect(page.getByTestId('refine-patch-op')).toHaveText('update_style');
  await expectWitnessesUnchanged();

  // --- 轮 4：混合轮（props + style）落在 Button 上（AC-31 指定指令）---
  await button.click();
  await expect(page.getByTestId('panel-node-id')).toHaveText('hero.primary-button');
  await submitRound(page, `set_text_style:${MIXED_BUTTON_TEXT}|fontWeight=bold`);
  await expect(page.getByTestId('refine-error')).toHaveCount(0);
  // 面板同时展示两条操作，顺序与 Patch operations 数组一致
  await expect(page.getByTestId('refine-patch-op')).toHaveText([
    'update_props',
    'update_style',
  ]);
  await expect(page.getByTestId('refine-patch-target')).toHaveText([
    'hero.primary-button',
    'hero.primary-button',
  ]);
  // 两种效果同时生效：文案改了，字重也改了；未提及的 fontSize 保持 16px
  await expect(button).toHaveText(MIXED_BUTTON_TEXT);
  await expectComputed(button, 'font-weight', '700');
  await expectComputed(button, 'font-size', '16px');
  await expect(page.getByTestId('refine-integrity-flag')).toHaveText(
    'nonTargetNodesUnchanged: true',
  );
  // hero.title 的三轮累积结果未被本轮回退
  await expectComputed(title, 'color', 'rgb(192, 57, 43)');
  await expectComputed(title, 'font-size', `${rootFontSize * 2}px`);
  await expectWitnessesUnchanged();

  // --- 轮 5：混合轮落在 Heading 上 —— 文案与颜色同时变更 ---
  await title.click();
  await expect(page.getByTestId('panel-node-id')).toHaveText('hero.title');
  await submitRound(page, `set_text_style:${MIXED_TITLE_TEXT}|color=#333333`);
  await expect(page.getByTestId('refine-error')).toHaveCount(0);
  await expect(title).toHaveText(MIXED_TITLE_TEXT);
  await expectComputed(title, 'color', 'rgb(51, 51, 51)');
  // 轮 3 写入的 fontSize 未被混合轮丢弃
  await expectComputed(title, 'font-size', `${rootFontSize * 2}px`);
  await expect(page.getByTestId('refine-patch-op')).toHaveText([
    'update_props',
    'update_style',
  ]);
  await expectWitnessesUnchanged();

  // --- 轮 6：白名单外的 style 键 → 安全失败且文档零变更 ---
  await submitRound(page, 'set_style:boxShadow=1px');
  await expect(page.getByTestId('refine-error')).toHaveCount(1);
  await expect(page.getByTestId('refine-error-kind')).toHaveText('服务端错误');
  await expect(page.getByTestId('refine-error-code')).toHaveText(
    'invalid_candidate_structure',
  );
  // 失败轮不触碰文档：目标节点与见证节点全部停在轮 5 之后的状态
  await expect(title).toHaveText(MIXED_TITLE_TEXT);
  await expectComputed(title, 'color', 'rgb(51, 51, 51)');
  await expectComputed(title, 'font-size', `${rootFontSize * 2}px`);
  await expect(button).toHaveText(MIXED_BUTTON_TEXT);
  await expectComputed(button, 'font-weight', '700');
  await expectWitnessesUnchanged();
  // 失败轮不入队：已确认轮次仍为前 5 轮
  await expect(page.getByTestId('refine-history-item')).toHaveCount(5);
  await expect(page.getByTestId('refine-history-count')).toContainText('5 / 20');
});
