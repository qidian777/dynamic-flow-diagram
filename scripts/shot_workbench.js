#!/usr/bin/env node
/**
 * shot_workbench.js — 流程工作台交付前自查（五个视图 + 跨流程跳转）
 *
 * 用法：
 *   npm i playwright --no-save
 *   node shot_workbench.js <工作台.html> <输出目录>
 *
 * 产出 7 张图 + 自检报告：
 *   01_home.png        首页总览
 *   02_index.png       流程索引
 *   03_filtered.png    索引筛选后
 *   04_flow_main.png   主流程画布
 *   05_subjump.png     子流程跳转 + 面包屑
 *   06_role.png        岗位视角
 *   07_issues.png      一致性检查
 *
 * 断言：控制台报错、各视图元素数量、跨流程跳转是否落到正确流程、
 *       岗位统计是否与数据吻合、筛选是否真的收窄了结果。
 */
const path = require('path');
const fs = require('fs');

const human = p => path.isAbsolute(p) ? p : path.resolve(p);

(async () => {
  const target = process.argv[2];
  if (!target) { console.error('用法: node shot_workbench.js <html> <outDir>'); process.exit(1); }
  const outDir = process.argv[3] || path.join(path.dirname(human(target)), 'shots');
  fs.mkdirSync(outDir, { recursive: true });

  const { chromium } = require('playwright');
  const url = 'file:///' + human(target).replace(/\\/g, '/');
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5 });
  const errors = [];
  pg.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  pg.on('pageerror', e => errors.push(String(e)));

  const R = [];
  const snap = async (name) => pg.screenshot({ path: path.join(outDir, name) });

  await pg.goto(url);
  await pg.waitForTimeout(1200);

  // ---------- 01 首页 ----------
  await snap('01_home.png');
  const home = await pg.evaluate(() => ({
    title: document.querySelector('.page')?.textContent?.trim(),
    kpis: [...document.querySelectorAll('.kpi b')].map(e => e.textContent),
    vnodes: document.querySelectorAll('.vnode').length,
    subnodes: document.querySelectorAll('.vnode.is-sub').length,
    roles: document.querySelectorAll('.rolecard').length,
  }));
  R.push(`首页：${home.vnodes} 个节点卡（其中 ${home.subnodes} 个可进子流程）· ${home.roles} 个角色卡 · KPI ${home.kpis.join('/')}`);
  if (home.vnodes === 0) R.push('⚠ 首页没有渲染出主流程节点');

  // ---------- 02 索引 ----------
  await pg.click('#nav button[data-k="flows"]');
  await pg.waitForTimeout(600);
  await snap('02_index.png');
  const idx = await pg.evaluate(() => ({ cards: document.querySelectorAll('.fcard').length }));
  R.push(`索引：${idx.cards} 张流程卡`);

  // ---------- 03 筛选 ----------
  await pg.click('.sel[data-sel="role"] > button');
  await pg.waitForTimeout(250);
  await pg.check('.sel[data-sel="role"] .pop input[value="keeper"]');
  await pg.waitForTimeout(500);
  await pg.mouse.click(700, 60);           // 关下拉
  await pg.waitForTimeout(300);
  await snap('03_filtered.png');
  const filt = await pg.evaluate(() => ({
    cards: document.querySelectorAll('.fcard').length,
    names: [...document.querySelectorAll('.fcard h3')].map(e => e.textContent.trim()),
  }));
  R.push(`筛选「设备管理员」后：${filt.cards} 张（应少于 ${idx.cards}）· ${filt.names.join('、')}`);
  if (filt.cards >= idx.cards) R.push('⚠ 筛选没有收窄结果');

  // ---------- 04 主流程画布 ----------
  await pg.evaluate(() => { location.hash = '#/flow/life_main'; });
  await pg.waitForTimeout(1100);
  await snap('04_flow_main.png');
  const flow = await pg.evaluate(() => ({
    nodes: document.querySelectorAll('.node').length,
    wires: document.querySelectorAll('#wires path').length,
    labels: document.querySelectorAll('.elabel').length,
    lanes: document.querySelectorAll('#laneBar i').length,
    over: (() => {                       // 节点重叠检测
      const rs = [...document.querySelectorAll('.node')].map(e => e.getBoundingClientRect());
      let n = 0;
      for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) {
        const a = rs[i], c = rs[j];
        if (a.left < c.right - 6 && a.right > c.left + 6 && a.top < c.bottom - 6 && a.bottom > c.top + 6) n++;
      }
      return n;
    })(),
  }));
  R.push(`主流程：${flow.nodes} 个节点 · ${flow.wires} 条连线 · ${flow.labels} 个分支标签 · ${flow.lanes} 条泳道`);
  R.push(flow.over ? `⚠ 有 ${flow.over} 对节点重叠` : '✓ 节点无重叠');
  if (!flow.nodes) R.push('⚠ 画布没有渲染节点');

  // ---------- 05 子流程跳转 ----------
  const subId = await pg.evaluate(() => {
    const el = document.querySelector('.node.t-sub');
    return el ? el.querySelector('.idx')?.textContent : null;
  });
  if (subId) {
    await pg.click('.node.t-sub');
    await pg.waitForTimeout(500);
    // 抽屉打开 → 点"进入子流程"
    const hasBtn = await pg.$('#goSub');
    if (hasBtn) { await hasBtn.click(); }
    else { await pg.click('.node.t-sub'); }
    await pg.waitForTimeout(1100);
    await snap('05_subjump.png');
    const jump = await pg.evaluate(() => ({
      hash: location.hash,
      crumb: document.querySelector('#crumb')?.textContent?.replace(/\s+/g, ' ').trim(),
      back: getComputedStyle(document.querySelector('#btnBack')).display !== 'none',
      sel: document.querySelectorAll('.node.sel').length,
    }));
    R.push(`子流程跳转：hash=${jump.hash} · 面包屑「${jump.crumb}」· 返回按钮${jump.back ? '可见' : '隐藏'}`);
    if (!jump.hash.includes('/flow/') || jump.hash.includes('life_main')) R.push('⚠ 没有跳到子流程');
    if (!jump.back) R.push('⚠ 返回上级按钮未出现');
  } else {
    R.push('⚠ 主流程里没有找到子流程节点');
  }

  // 返回上级
  await pg.click('#btnBack');
  await pg.waitForTimeout(900);
  const back = await pg.evaluate(() => location.hash);
  R.push(`点返回后：${back}${back.includes('life_main') ? ' ✓' : ' ⚠ 未回到主流程'}`);

  // ---------- 06 岗位视角 ----------
  await pg.evaluate(() => { location.hash = '#/role/keeper'; });
  await pg.waitForTimeout(900);
  await snap('06_role.png');
  const role = await pg.evaluate(() => ({
    steps: document.querySelectorAll('.step').length,
    groups: document.querySelectorAll('.groupbox').length,
    head: document.querySelector('#v-role .lede')?.textContent?.replace(/\s+/g, ' ').trim(),
  }));
  R.push(`岗位视角：${role.groups} 张流程 / ${role.steps} 个动作 —— ${role.head}`);
  if (!role.steps) R.push('⚠ 岗位动作清单为空');

  // ---------- 07 一致性检查 ----------
  await pg.evaluate(() => { location.hash = '#/issues'; });
  await pg.waitForTimeout(700);
  await snap('07_issues.png');
  const iss = await pg.evaluate(() => ({
    total: document.querySelectorAll('.issue').length,
    err: document.querySelectorAll('.issue.error').length,
    warn: document.querySelectorAll('.issue.warning').length,
    codes: [...new Set([...document.querySelectorAll('.issue .code')].map(e => e.textContent))],
  }));
  R.push(`一致性检查：${iss.total} 条（错误 ${iss.err} / 警告 ${iss.warn}）· 类型 ${iss.codes.join(',')}`);
  if (!iss.err) R.push('⚠ 没有检测到断链错误（示例数据里应该有一处）');

  // ---------- 收尾 ----------
  R.push(errors.length ? `⚠ 控制台报错 ${errors.length} 条:\n   ${errors.slice(0, 4).join('\n   ')}` : '✓ 控制台无报错');
  console.log('\n=== 工作台自检 ===');
  console.log(R.join('\n'));
  console.log(`\n截图: ${outDir}`);
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
