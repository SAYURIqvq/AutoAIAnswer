const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Exercise the shipped script through its DOM/WebSocket API without paid AI calls.
class Element {
  constructor() {
    this.children = []; this.listeners = {}; this.value = ''; this.className = '';
    this.dataset = {}; this.style = {}; this.options = []; this.classList = {toggle() {}};
    this._text = '';
  }
  set textContent(value) { this._text = value; this.children = []; }
  get textContent() { return this._text + this.children.map(e => e.textContent).join(''); }
  appendChild(child) { child.parent = this; this.children.push(child); return child; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(e => e !== this); }
  setAttribute() {}
  addEventListener(name, fn) { this.listeners[name] = fn; }
  querySelectorAll(selector) {
    const cls = selector.slice(1);
    return this.children.flatMap(e => [e, ...e.querySelectorAll(selector)]).filter(e => e.className.split(' ').includes(cls));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
function phone() {
  const elements = new Map(); const sockets = []; const spoken = []; const cancelled = [];
  const document = {getElementById(id) { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); }, createElement() {return new Element();}};
  class Socket {
    static OPEN = 1;
    constructor() { this.readyState = 1; this.sent = []; sockets.push(this); }
    send(raw) { this.sent.push(JSON.parse(raw)); }
  }
  class Utterance { constructor(text) {this.text = text;} }
  const window = {SESSION_ID: 'test', SpeechSynthesisUtterance: Utterance, speechSynthesis: {
    cancel() {cancelled.push(true);}, getVoices() {return [{lang: 'zh-CN'}];}, speak(u) {spoken.push(u);}
  }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../ai_screenshot_assistant/web/static/app.js'), 'utf8'), {
    window, document, WebSocket: Socket, SpeechSynthesisUtterance: Utterance,
    location: {protocol: 'http:', host: 'test', search: ''}, navigator: {}, URLSearchParams,
    localStorage: {getItem() {return null;}, setItem() {}},
    setTimeout() {}, requestAnimationFrame(fn) {fn();}, console,
  });
  const socket = sockets[0]; socket.onopen();
  return {get: id => document.getElementById(id), spoken, cancelled, socket,
    event(type, payload = {}, request_id = 'r1') {socket.onmessage({data: JSON.stringify({type, payload, request_id})});},
    click(id) {document.getElementById(id).listeners.click();}
  };
}

test('mobile voice is opt-in, cancels the previous answer, and ignores duplicate completions', () => {
  const p = phone();
  p.event('answer.completed', {result: {text: 'silent'}});
  assert.equal(p.spoken.length, 0);
  p.event('voice.mode', {enabled: true});
  assert.equal(p.get('auto-read').checked, true);
  p.event('answer.completed', {result: {text: 'A'.repeat(250)}}, 'r2');
  assert.equal(p.spoken.length, 1);
  const oldUtterance = p.spoken[0];
  p.event('answer.started', {}, 'r3');
  oldUtterance.onend();
  assert.equal(p.spoken.length, 1, 'cancelled chunks must not resume');
  p.event('answer.completed', {result: {text: 'new answer'}}, 'r3');
  assert.equal(p.spoken.at(-1).text, 'new answer');
  p.event('answer.completed', {result: {text: 'new answer'}}, 'r3');
  assert.equal(p.spoken.length, 2);
  p.event('voice.mode', {enabled: false});
  assert.equal(p.get('auto-read').checked, false);
});

test('two phones render the same answer and chat command only once', () => {
  const a = phone(), b = phone();
  a.get('question-input').value = 'question'; a.click('ask-button');
  const command = a.socket.sent.at(-1); const id = command.payload.client_request_id;
  for (const p of [a,b]) {
    p.event('mobile.action', {command: 'command.submit_screenshots', text: 'question'}, id);
    p.event('answer.started', {chat: true}, id);
    p.event('answer.delta', {delta: 'hello'}, id);
    p.event('answer.snapshot', {chat: true, text: 'hello world'}, id);
    assert.equal(p.get('chat-list').querySelectorAll('.assistant').length, 1);
    p.event('answer.completed', {result: {text: 'hello world'}}, id);
    assert.equal(p.get('chat-list').querySelectorAll('.user').length, 1);
  }
  assert.equal(a.get('chat-list').textContent, b.get('chat-list').textContent);
});

test('reconnected screenshot buffer replaces existing attachments', () => {
  const p = phone();
  const image = {image: 'data:image/png;base64,abc', size: 3, add_to_buffer: true};
  p.event('screenshot.captured', image);
  p.event('screenshot.buffer', {screenshots: [image]});
  assert.equal(p.get('preview-list').children.length, 1);
  p.event('screenshot.buffer', {screenshots: []});
  assert.equal(p.get('preview-list').children.length, 0);
});

test('model changes are shared without automatically switching providers', () => {
  const p = phone();
  p.event('model.changed', {route: 'qwen-397b', available_routes: []});
  assert.equal(p.get('model-route').value, 'qwen-397b');
  assert.equal(p.socket.sent.length, 0);
});
