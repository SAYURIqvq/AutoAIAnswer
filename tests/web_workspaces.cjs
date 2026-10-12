const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({headless: true, channel: process.env.BROWSER_CHANNEL || undefined});
  try {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.sent = [];
      window.copied = '';
      document.execCommand = () => {
        window.copied = document.activeElement.value;
        return true;
      };
      window.WebSocket = class {
        static OPEN = 1;
        constructor() { this.readyState = 1; window.ws = this; setTimeout(() => this.onopen(), 0); }
        send(value) { window.sent.push(JSON.parse(value)); }
      };
      window.deliver = (type, request_id, payload) => window.ws.onmessage({data: JSON.stringify({type, request_id, payload})});
    });
    await page.route('http://assistant.test/**', async route => {
      const url = new URL(route.request().url());
      const name = url.pathname.startsWith('/static/') ? path.basename(url.pathname) : 'index.html';
      await route.fulfill({body: fs.readFileSync(path.join(__dirname, '../ai_screenshot_assistant/web/static', name)),
        contentType: name.endsWith('.js') ? 'application/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html'});
    });
    await page.goto('http://assistant.test/?session_id=test');
    await page.waitForFunction(() => window.sent.length > 0);
    await page.evaluate(() => deliver('prompt.current', 'prompt', {text: '当前提示词'}));
    assert.equal(await page.locator('#system-prompt').inputValue(), '当前提示词');
    const longPrompt = '题型规则\n'.repeat(5000);
    await page.locator('#system-prompt').fill(longPrompt);
    await page.locator('#save-prompt').click();
    assert.equal(await page.evaluate(() => sent.find(x => x.type === 'command.save_prompt').payload.text), longPrompt);
    await page.locator('#fullscreen-button').click();
    const first = await page.evaluate(() => sent.at(-1).payload.client_request_id);
    await page.locator('#fullscreen-button').click();
    const second = await page.evaluate(() => sent.at(-1).payload.client_request_id);
    assert.notEqual(first, second);
    await page.locator('#question-input').fill('对话问题');
    await page.locator('#ask-button').click();
    const chat = await page.evaluate(() => sent.at(-1).payload.client_request_id);
    await page.evaluate(({first, second, chat}) => {
      deliver('answer.started', chat, {chat: true});
      deliver('answer.delta', chat, {delta: '对话答案'});
      deliver('answer.started', second, {});
      deliver('answer.delta', first, {delta: '过期答案'});
      deliver('answer.delta', second, {delta: '搜题答案'});
      deliver('answer.completed', chat, {result: {text: '对话答案\n```python\nprint(1)\n```'}});
    }, {first, second, chat});
    assert.equal(await page.locator('#output').innerText(), '搜题答案');
    await page.locator('#copy-direct').click();
    assert.equal(await page.evaluate(() => copied), '搜题答案');
    await page.locator('.copy-answer').click();
    assert.equal(await page.evaluate(() => copied), '对话答案\n```python\nprint(1)\n```');
    await page.locator('#clear-direct').click();
    assert.match(await page.locator('#chat-list').innerText(), /对话答案/);
    await page.evaluate(second => deliver('answer.completed', second, {result: {text: '旧答案回流'}}), second);
    assert.doesNotMatch(await page.locator('#output').innerText(), /旧答案/);
    assert.deepEqual(errors, []);
    console.log('Browser checks passed: replacement, isolation, clear, copy, long prompt');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
