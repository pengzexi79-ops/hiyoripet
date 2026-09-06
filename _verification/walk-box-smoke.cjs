const { createRequire } = require('module');
const req = createRequire(process.cwd() + '\\x.cjs');
const { chromium } = req('C:\\Users\\Windows\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules\\playwright');
const fs = require('fs');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9224');
  const p = b.contexts()[0].pages()[0];
  const out = {};
  const winPos = async () => p.evaluate(() => ({ x: screenLeft, y: screenTop, w: innerWidth, h: innerHeight }));
  const p0 = await winPos();
  for (let i = 0; i < 12; i++) {
    await p.evaluate(() => window.petApi?.dispatch({ type: 'wander' }));
    await sleep(160);
    if (i === 4) await p.screenshot({ path: '_verification/walk-a.png', omitBackground: true });
    if (i === 6) await p.screenshot({ path: '_verification/walk-b.png', omitBackground: true });
  }
  const p1 = await winPos();
  out.walkMoved = Math.round(Math.hypot(p1.x - p0.x, p1.y - p0.y));
  const size = await winPos();
  await p.mouse.click(Math.round(size.w / 2), Math.round(size.h * 0.45));
  await sleep(120);
  await p.mouse.click(Math.round(size.w / 2), Math.round(size.h * 0.45));
  let reacted = false;
  for (let i = 0; i < 8 && !reacted; i++) { reacted = await p.evaluate(() => !!document.querySelector('.reaction')); if (!reacted) await sleep(100); }
  out.doubleReaction = reacted;
  await p.evaluate(() => window.petApi?.dispatch({ type: 'box-add', path: 'C:\\Windows\\notepad.exe' }));
  await sleep(800);
  const bx2 = p.locator('.chat-bubble .bubble-head button');
  if (await bx2.count()) await bx2.click();
  await sleep(900);
  const size2 = await winPos();
  await p.mouse.move(Math.min(180, Math.round(size2.w / 2)), Math.round(size2.h * 0.45));
  await p.mouse.down(); await sleep(900); await p.mouse.up();
  await sleep(500);
  out.boxOpen = await p.locator('.box-panel').count();
  const row = p.locator('.box-row', { hasText: 'notepad.exe' });
  const cat = row.locator('.category-input');
  out.catBefore = await cat.inputValue().catch(() => '');
  await cat.fill('学习资料');
  await cat.press('Enter');
  await sleep(600);
  out.groupTitles = await p.locator('.box-panel .catalog-title').allTextContents();
  await row.getByRole('button', { name: '导出' }).click();
  await sleep(1500);
  out.bubbleAfterExport = await p.locator('.bubble-text').textContent().catch(() => '');
  const desktopLnk = 'C:\\Users\\Windows\\Desktop\\notepad.exe.lnk';
  out.lnkExists = fs.existsSync(desktopLnk);
  if (out.lnkExists) fs.unlinkSync(desktopLnk);
  const bx = p.locator('.chat-bubble .bubble-head button'); if (await bx.count()) await bx.click(); await sleep(900);
  const zs = await winPos();
  for (let i = 0; i < 14; i++) { await p.mouse.move(Math.round(zs.w / 2), Math.round(zs.h / 2)); await p.mouse.wheel(0, -120); await sleep(60); }
  await sleep(600);
  let ms = await winPos();
  if (ms.w === zs.w) {
    for (let i = 0; i < 10; i++) { await p.evaluate(() => document.querySelector('canvas').dispatchEvent(new WheelEvent('wheel', { deltaY: -120, bubbles: true, cancelable: true }))); await sleep(80); }
    await sleep(600);
    ms = await winPos();
    out.zoomVia = 'synthetic-fallback';
  } else { out.zoomVia = 'native'; }
  out.maxSize = ms;
  await p.screenshot({ path: '_verification/zoom-max2.png', omitBackground: true });
  await b.close();
  console.log(JSON.stringify(out, null, 2));
})().catch((e) => { console.error(e); process.exit(1); });
