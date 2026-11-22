const fs = require('fs');
const src = fs.readFileSync('mc_launcher/ui_web/web/app.js', 'utf8');
const noop = () => {};
const el = new Proxy({}, {
  get(t, k) {
    if (k === 'style' || k === 'dataset' || k === 'classList') return {};
    if (k === 'children' || k === 'childNodes') return [];
    if (k === 'innerHTML' || k === 'textContent' || k === 'value') return '';
    return noop;
  },
  set() { return true; },
});
global.document = {
  addEventListener: noop, removeEventListener: noop,
  querySelector: () => null, querySelectorAll: () => [],
  getElementById: () => null, createElement: () => el, createTextNode: () => el,
  body: el, documentElement: el, head: el, createDocumentFragment: () => el,
  createTreeWalker: () => ({ nextNode: () => null, currentNode: null }),
  createRange: () => ({ selectNodeContents: noop, setStart: noop, setEnd: noop }),
  createEvent: () => ({ initEvent: noop }),
};
global.window = {
  addEventListener: noop, removeEventListener: noop, devicePixelRatio: 1,
  location: { hash: '', href: 'http://localhost/' }, localStorage: { getItem: () => null, setItem: noop },
  matchMedia: () => ({ matches: false, addEventListener: noop }),
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
};
global.navigator = { userAgent: 'node', language: 'zh-CN', clipboard: { writeText: noop } };
global.localStorage = { getItem: () => null, setItem: noop, removeItem: noop };
global.requestAnimationFrame = () => 0;
global.cancelAnimationFrame = noop;
global.performance = { now: () => 0 };
global.fetch = () => Promise.reject(new Error('no net'));
global.Image = function () { return { set src(v) {}, addEventListener: noop }; };
global.NodeFilter = { SHOW_ALL: 0xFFFFFFFF, SHOW_ELEMENT: 1, FILTER_ACCEPT: 1, FILTER_REJECT: 2 };
global.XMLHttpRequest = function () { return { open: noop, send: noop, addEventListener: noop }; };
global.URL = { createObjectURL: () => '', revokeObjectURL: noop };
global.MutationObserver = function () { return { observe: noop, disconnect: noop }; };
global.IntersectionObserver = function () { return { observe: noop, disconnect: noop }; };
global.ResizeObserver = function () { return { observe: noop, disconnect: noop }; };
global.customElements = { define: noop, get: () => null };
global.HTMLElement = function () {};
global.prompt = () => null;
global.confirm = () => false;
global.alert = noop;
global.atob = (s) => Buffer.from(s, 'base64').toString('binary');
global.btoa = (s) => Buffer.from(s, 'binary').toString('base64');
// 只验证「脚本能解析并执行到结尾」：顶层缺函数、变量名写错都会在这里炸，
// 正好覆盖之前 renderBackups 被删导致整页白屏那类问题。执行到结尾就直接退出，
// 不去跑依赖后端的启动流程。
try {
  new Function(src)();
  console.log('LOAD OK');
  process.exit(0);
} catch (err) {
  console.log('LOAD ERROR:', err && err.message);
  process.exit(1);
}
