const { createRequire } = require('module');
const req = createRequire(process.cwd() + '\\x.cjs');
const { chromium } = req('C:\\Users\\Windows\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules\\playwright');
const fs = require('fs');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9224');
  const p = b.contexts()[0].pages()[0];
  const out = {};
  const desk = 'D:\\Users\\Windows\\Desktop\\zz-pet-test.lnk';
  const { execSync } = require('child_process');
  execSync(`powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('${desk}'); $s.TargetPath='C:\\Windows\\notepad.exe'; $s.Save()"`);
  out.lnkBefore = fs.existsSync(desk);
  await p.evaluate((path) => window.petApi?.dispatch({ type: 'box-add', path }), desk);
  await sleep(1200);
  out.lnkAfterEat = fs.existsSync(desk);
  const items = await (await fetch('http://127.0.0.1:8000/api/box')).json();
  const testItem = items.items.find((i) => i.path === desk);
  out.itemId = testItem?.id;
  out.iconStatus = testItem ? (await fetch(`http://127.0.0.1:8000/api/box/icon/${testItem.id}`)).status : -1;
  const bx = p.locator('.chat-bubble .bubble-head button');
  if (await bx.count()) await bx.click();
  await sleep(900);
  const size = await p.evaluate(() => ({ w: innerWidth, h: innerHeight }));
  await p.mouse.move(Math.min(180, Math.round(size.w / 2)), Math.round(size.h * 0.45));
  await p.mouse.down(); await sleep(900); await p.mouse.up();
  await sleep(700);
  out.layout = await p.evaluate(() => {
    const box = document.querySelector('.box-panel');
    const br = box?.getBoundingClientRect();
    return { w: innerWidth, box: br && { x: Math.round(br.x), right: Math.round(br.right), y: Math.round(br.y) }, cards: document.querySelectorAll('.box-card').length, icons: document.querySelectorAll('.box-card .box-icon').length };
  });
  await p.screenshot({ path: '_verification/box-cards.png', omitBackground: true });
  const closeBoxBtn = p.locator('button[aria-label="关闭收纳箱"]');
  if (await closeBoxBtn.count()) await closeBoxBtn.click();
  await sleep(900);
  await p.evaluate(() => window.petApi?.dispatch({ type: 'say', text: '气泡位置验证' }));
  await sleep(700);
  out.bubble = await p.evaluate(() => {
    const el = document.querySelector('.chat-bubble');
    const r = el?.getBoundingClientRect();
    return r && { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), innerW: innerWidth };
  });
  await p.screenshot({ path: '_verification/bubble-column.png', omitBackground: true });
  const bx2 = p.locator('.chat-bubble .bubble-head button');
  if (await bx2.count()) await bx2.click();
  await sleep(900);
  const s2 = await p.evaluate(() => ({ w: innerWidth, h: innerHeight }));
  const headY = Math.round(s2.h * 0.2);
  for (let i = 0; i < 3; i++) { await p.mouse.click(Math.round(s2.w / 2), headY); await sleep(250); }
  await sleep(400);
  out.headPatSpeech = await p.locator('.bubble-text').textContent().catch(() => '');
  if (testItem) {
    await fetch('http://127.0.0.1:8000/api/box/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: testItem.id }) });
    await sleep(800);
    out.lnkAfterExport = fs.existsSync(desk);
    if (fs.existsSync(desk)) fs.unlinkSync(desk);
    await fetch(`http://127.0.0.1:8000/api/box/${testItem.id}`, { method: 'DELETE' });
  }
  await b.close();
  console.log(JSON.stringify(out, null, 2));
})().catch((e) => { console.error(e); process.exit(1); });
