const { createRequire } = require('module');
const req = createRequire(process.cwd() + '\\x.cjs');
const { chromium } = req('C:\\Users\\Windows\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules\\playwright');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9224');
  const p = b.contexts()[0].pages()[0];
  const out = {};
  out.before = await p.evaluate(() => ({ w: innerWidth, h: innerHeight, vis: document.visibilityState }));
  await p.evaluate(() => { window.__frames = 0; const tick = () => { window.__frames += 1; requestAnimationFrame(tick); }; requestAnimationFrame(tick); });
  const t0 = Date.now();
  for (let i = 0; i < 24; i++) { await p.mouse.move(180, 300); await p.mouse.wheel(0, -120); await sleep(60); }
  const zoomMs = Date.now() - t0;
  const frames = await p.evaluate(() => window.__frames);
  out.zoomFps = Math.round((frames / zoomMs) * 1000);
  out.zoomed = await p.evaluate(() => ({ w: innerWidth, h: innerHeight }));
  await p.evaluate(() => { window.__frames = 0; });
  const t1 = Date.now();
  for (let i = 0; i < 24; i++) { await p.mouse.wheel(0, 120); await sleep(60); }
  const frames2 = await p.evaluate(() => window.__frames);
  out.restoreFps = Math.round((frames2 / (Date.now() - t1)) * 1000);
  out.restored = await p.evaluate(() => ({ w: innerWidth, h: innerHeight }));
  await sleep(600);
  out.clicks = 0;
  for (let i = 0; i < 60; i++) { await p.mouse.click(180, 260, { delay: 5 }); out.clicks += 1; await sleep(25); }
  await sleep(500);
  out.after = await p.evaluate(() => ({ w: innerWidth, h: innerHeight, vis: document.visibilityState, reaction: !!document.querySelector('.reaction'), canvas: document.querySelector('canvas')?.getBoundingClientRect().toJSON() }));
  await p.screenshot({ path: '_verification/zoom-click-after.png', omitBackground: true });
  await b.close();
  console.log(JSON.stringify(out, null, 2));
})().catch((e) => { console.error(e); process.exit(1); });
