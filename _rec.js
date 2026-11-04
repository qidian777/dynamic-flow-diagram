const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const dir = './_rec';
  fs.rmSync(dir, { recursive: true, force: true });
  const b = await chromium.launch();
  const ctx = await b.newContext({
    viewport: { width: 1380, height: 800 },
    deviceScaleFactor: 1,
    recordVideo: { dir, size: { width: 1380, height: 800 } }
  });
  const pg = await ctx.newPage();
  const url = 'file:///' + process.cwd().replace(/\\/g, '/') + '/assets/template.html';
  await pg.goto(url);
  await pg.waitForTimeout(1800);          // 全景停留

  // 悬停判断节点 → 气泡
  await pg.hover('.node:has-text("材料是否齐全")');
  await pg.waitForTimeout(2000);
  await pg.mouse.move(30, 700);
  await pg.waitForTimeout(600);

  // 演示播放
  await pg.click('#play');
  await pg.waitForTimeout(11500);
  await pg.mouse.move(30, 700);
  await pg.waitForTimeout(400);

  const p = await pg.video().path();
  await ctx.close();
  await b.close();
  console.log('video:', p, (fs.statSync(p).size / 1024 / 1024).toFixed(2), 'MB');
})();
