#!/usr/bin/env node
/**
 * shot.js — 交付前截图自查
 *
 * 用法：
 *   npm i playwright --no-save
 *   node shot.js <html文件路径> [输出目录]
 *
 * 产出 5 张图 + 一份自检报告（控制台）：
 *   01_init.png    初始全图
 *   02_phase.png   单阶段筛选后
 *   03_hover.png   悬停气泡（并检测是否压住其他节点）
 *   04_drawer.png  详情抽屉
 *   05_play.png    演示播放中
 *
 * 检测项：气泡与节点相交、横向溢出、控制台报错、页面体积。
 */
const path = require('path');
const fs = require('fs');

(async () => {
  const target = process.argv[2];
  if (!target) { console.error('用法: node shot.js <html> [outDir]'); process.exit(1); }
  const outDir = process.argv[3] || path.dirname(humanPath(target));
  const { chromium } = require('playwright');

  const url = 'file:///' + humanPath(target).replace(/\\/g, '/');
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  pg.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  pg.on('pageerror', e => errors.push(String(e)));

  await pg.goto(url);
  await pg.waitForTimeout(1600);
  await pg.screenshot({ path: path.join(outDir, '01_init.png') });

  const report = [];
  report.push(`文件体积: ${(fs.statSync(humanPath(target)).size / 1024).toFixed(1)} KB`);

  // 单阶段
  const tab = await pg.$('#tabs button:nth-child(2)');
  if (tab) { await tab.click(); await pg.waitForTimeout(900); }
  await pg.screenshot({ path: path.join(outDir, '02_phase.png') });
  const back = await pg.$('#tabs button:first-child');
  if (back) { await back.click(); await pg.waitForTimeout(900); }

  // 悬停 + 遮罩检测
  const nodes = await pg.$$('.node:not(.ghost)');
  if (nodes.length) {
    const pick = nodes[Math.floor(nodes.length / 2)];
    await pick.hover();
    await pg.waitForTimeout(450);
    await pg.screenshot({ path: path.join(outDir, '03_hover.png') });

    const res = await pg.evaluate(() => {
      const tip = document.querySelector('#tip.on');
      if (!tip) return { shown: false };
      const t = tip.getBoundingClientRect();
      const others = [...document.querySelectorAll('.node:not(.ghost)')]
        .map(e => ({ el: e, r: e.getBoundingClientRect() }))
        .filter(({ r }) => !(r.right < t.left - 4 || r.left > t.right + 4
                          || r.bottom < t.top - 4 || r.top > t.bottom + 4));
      return {
        shown: true,
        overlapped: others.map(o => (o.el.querySelector('.t') || {}).textContent || '?'),
        clipped: t.left < 0 || t.top < 0 || t.right > innerWidth || t.bottom > innerHeight,
      };
    });
    if (!res.shown) report.push('⚠ 悬停气泡未出现');
    else {
      report.push(res.overlapped.length ? `⚠ 气泡压住节点: ${res.overlapped.join('、')}` : '✓ 气泡未遮挡任何节点');
      report.push(res.clipped ? '⚠ 气泡被窗口裁切' : '✓ 气泡在视口内');
    }
    await pg.mouse.move(5, 5);
  }

  // 抽屉
  if (nodes.length) {
    const n2 = nodes[Math.min(2, nodes.length - 1)];
    await n2.click();
    await pg.waitForTimeout(700);
    await pg.screenshot({ path: path.join(outDir, '04_drawer.png') });
    await pg.keyboard.press('Escape');
    await pg.waitForTimeout(400);
  }

  // 演示
  const play = await pg.$('#play');
  if (play) {
    await play.click();
    await pg.waitForTimeout(2600);
    await pg.screenshot({ path: path.join(outDir, '05_play.png') });
    await play.click();
  }

  report.push(errors.length ? `⚠ 控制台报错 ${errors.length} 条:\n   ${errors.slice(0, 3).join('\n   ')}` : '✓ 控制台无报错');
  console.log('\n=== 自检报告 ===');
  console.log(report.join('\n'));
  console.log(`\n截图已输出到: ${outDir}`);
  console.log('请逐张看图确认：有无元素互相遮盖、文字溢出、该对齐却未对齐。');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });

function humanPath(p) { return path.isAbsolute(p) ? p : path.resolve(p); }
