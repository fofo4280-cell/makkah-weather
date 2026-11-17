const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1200, height: 900 } });
  const reqs = [];
  p.on('request', r => reqs.push(r.method() + ' ' + r.resourceType() + ' ' + r.url()));
  p.on('response', async r => {
    const u = r.url();
    if (/json|api|radar|frame|list|time/i.test(u) && !/\.(png|jpg|webp)/i.test(u)) {
      try { const t = await r.text(); fs.appendFileSync('out/bodies.txt', '\n=== ' + r.status() + ' ' + u + '\n' + JSON.stringify(r.headers()) + '\n' + t.slice(0, 4000)); } catch (e) {}
    }
    if (/\.(png|jpg|webp)/i.test(u)) fs.appendFileSync('out/imghdr.txt', r.status() + ' ' + u + ' ' + JSON.stringify(r.headers()) + '\n');
  });
  await p.goto('https://www.yanbuweather.com/pages/RainRadar/', { waitUntil: 'networkidle', timeout: 90000 }).catch(e => console.log(e.message));
  await p.waitForTimeout(15000);
  fs.writeFileSync('out/page.html', await p.content());
  fs.writeFileSync('out/reqs.txt', reqs.join('\n'));
  await p.screenshot({ path: 'out/shot.png' });
  await b.close();
})();
