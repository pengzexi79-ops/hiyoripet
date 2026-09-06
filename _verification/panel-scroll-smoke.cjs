const { createRequire } = require('module');
const req = createRequire(process.cwd() + '\\x.cjs');
const { chromium } = req('C:\\Users\\Windows\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules\\playwright');
(async () => {
  const models = ['alpha', 'beta', 'gamma'].map((name, i) => ({
    id: `panel-${name}`, name: `panel-${name}`, protocol: 'openai-compatible',
    base_url: 'https://example.invalid/v1', api_key: 'sk-panel-test', enabled: i === 0,
    role: i === 0 ? 'primary' : 'worker', capabilities: ['text'], tasks: ['chat', 'scene'],
  }));
  const res = await fetch('http://127.0.0.1:8000/api/models', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ models }) });
  const saved = await res.json();
  const b = await chromium.connectOverCDP('http://127.0.0.1:9224');
  const p = b.contexts()[0].pages()[0];
  await p.locator('canvas.stage').dispatchEvent('contextmenu', { button: 2, buttons: 2, clientX: 180, clientY: 300 });
  await p.waitForTimeout(500);
  const metrics = await p.evaluate(() => {
    const panel = document.querySelector('.api-panel');
    const catalog = document.querySelector('.model-catalog');
    const row = document.querySelector('.model-row');
    const info = document.querySelector('.model-row .model-info');
    return {
      panel: panel && { sh: panel.scrollHeight, ch: panel.clientHeight, sw: panel.scrollWidth, cw: panel.clientWidth },
      catalog: catalog && { sh: catalog.scrollHeight, ch: catalog.clientHeight },
      row: row && { w: Math.round(row.getBoundingClientRect().width), h: Math.round(row.getBoundingClientRect().height) },
      info: info && { w: Math.round(info.getBoundingClientRect().width) },
      viewport: { w: innerWidth, h: innerHeight },
    };
  });
  await p.screenshot({ path: '_verification/panel-scroll.png', omitBackground: true });
  console.log(JSON.stringify({ savedCount: saved.models?.length, metrics }, null, 2));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
