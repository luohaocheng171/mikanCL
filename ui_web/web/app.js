/* MikanCL 美化版前端：单页应用，所有后端调用走 window.pywebview.api。
   页面按需渲染，长任务由后端线程执行、前端轮询进度。 */
'use strict';

const S = {
  data: null,
  page: 'home',
  tasks: [],
  taskStates: {},
  selectedVersion: '',
  manifest: null,
  manifestAt: 0,
  manifestSource: '',
  manifestFilter: 'release',
  manifestQuery: '',
  dlTab: 'game',
  loader: { kind: 'fabric', mc: '', versions: [], mcVersions: [], loading: false },
  javaTab: { dist: 'temurin', major: 21, pkg: 'jdk', mode: 'zip', versions: [], loading: false, scanned: null },
  bedrock: { channel: 'release', store: null, entries: [], installed: null },
  content: { source: 'modrinth', kind: 'mod', q: '', gv: '', loader: '', category: '', projects: [], offset: 0, loading: false, searched: false },
  settings: { tab: 'general', java: null, view: 'common' },
  worldTool: { scanned: null, source: '', era: 'auto', target: '', output: '', workers: 0, extra: [], jobId: '', running: false, logs: [], progress: 0, result: null },
  timer: null,
};

const NAV = [
  ['home', '主页', 'home'],
  ['download', '下载中心', 'download'],
  ['content', '内容中心', 'content'],
  ['instances', '实例管理', 'instances'],
  ['control', '版本设置', 'control'],
  ['account', '账号与皮肤', 'account'],
  ['servers', '联机', 'servers'],
  ['wiki', '教程中心', 'wiki'],
  ['browser', '浏览器', 'browser'],
  ['tools', '工具箱', 'tools'],
  ['creator', '创世神面板', 'creator'],
  ['settings', '设置', 'settings'],
];

const TYPE_CN = {
  release: '正式版', snapshot: '快照', old_beta: '旧测试版', old_alpha: '旧预览版',
  custom: '自定义', broken: '损坏', pending: '待安装',
};
const LOADER_CN = { fabric: 'Fabric', forge: 'Forge', neoforge: 'NeoForge', quilt: 'Quilt', liteloader: 'LiteLoader', forbric: 'Forbric' };
const CHANNEL_CN = { release: '正式版', preview: '预览版', beta: 'Beta', alpha: 'Alpha' };

/* 界面语言词典：目前覆盖导航、设置标签与新增的下载文件夹文案，
   未收录的文本回退中文原文，后续可以继续补充。 */
const I18N = {
  en_US: {
    '主页': 'Home', '下载中心': 'Downloads', '内容中心': 'Content', '实例管理': 'Instances',
    '版本设置': 'Version settings', '账号与皮肤': 'Account & skins', '联机': 'Multiplayer',
    '教程中心': 'Guides', '浏览器': 'Browser', '工具箱': 'Toolbox', '设置': 'Settings',
    '创世神面板': 'Save Creator',
    '常规': 'General', '外观': 'Appearance', '下载': 'Download', '扩展': 'Extensions',
    '高级': 'Advanced', '关于': 'About',
    '打开下载文件夹': 'Open downloads folder', '下载文件夹': 'Downloads folder',
    '手动下载 / 另存为的文件保存到这里': 'Manual downloads and “Save as” files go here',
    '更改': 'Change', '打开': 'Open', '恢复默认': 'Reset',
    '只影响「另存为 / 只下载不安装」的文件；游戏、Mod 与整合包仍写入对应版本目录。': 'Only affects “Save as” and download-only files; games, mods and modpacks still go to their version folder.',
  },
  ru_RU: {
    '主页': 'Главная', '下载中心': 'Загрузки', '内容中心': 'Контент', '实例管理': 'Экземпляры',
    '版本设置': 'Настройки версии', '账号与皮肤': 'Аккаунт и скины', '联机': 'Сеть',
    '教程中心': 'Руководства', '浏览器': 'Браузер', '工具箱': 'Инструменты', '设置': 'Настройки',
    '创世神面板': 'Редактор сохранений',
    '常规': 'Общие', '外观': 'Оформление', '下载': 'Загрузка', '扩展': 'Расширения',
    '高级': 'Дополнительно', '关于': 'О программе',
    '打开下载文件夹': 'Открыть папку загрузок', '下载文件夹': 'Папка загрузок',
    '手动下载 / 另存为的文件保存到这里': 'Сюда сохраняются ручные загрузки и файлы «Сохранить как»',
    '更改': 'Изменить', '打开': 'Открыть', '恢复默认': 'Сбросить',
    '只影响「另存为 / 只下载不安装」的文件；游戏、Mod 与整合包仍写入对应版本目录。': 'Касается только файлов «Сохранить как» и загрузок без установки; игры, моды и сборки по-прежнему пишутся в папку версии.',
  },
  fr_FR: {
    '主页': 'Accueil', '下载中心': 'Téléchargements', '内容中心': 'Contenu', '实例管理': 'Instances',
    '版本设置': 'Réglages de version', '账号与皮肤': 'Compte et skins', '联机': 'Multijoueur',
    '教程中心': 'Guides', '浏览器': 'Navigateur', '工具箱': 'Outils', '设置': 'Réglages',
    '创世神面板': 'Éditeur de sauvegarde',
    '常规': 'Général', '外观': 'Apparence', '下载': 'Téléchargement', '扩展': 'Extensions',
    '高级': 'Avancé', '关于': 'À propos',
    '打开下载文件夹': 'Ouvrir le dossier de téléchargements', '下载文件夹': 'Dossier de téléchargements',
    '手动下载 / 另存为的文件保存到这里': 'Les téléchargements manuels et les fichiers « Enregistrer sous » vont ici',
    '更改': 'Changer', '打开': 'Ouvrir', '恢复默认': 'Réinitialiser',
    '只影响「另存为 / 只下载不安装」的文件；游戏、Mod 与整合包仍写入对应版本目录。': 'Concerne uniquement les fichiers « Enregistrer sous » et les téléchargements sans installation ; jeux, mods et modpacks restent dans le dossier de la version.',
  },
  ja_JP: {
    '主页': 'ホーム', '下载中心': 'ダウンロード', '内容中心': 'コンテンツ', '实例管理': 'インスタンス',
    '版本设置': 'バージョン設定', '账号与皮肤': 'アカウントとスキン', '联机': 'マルチプレイ',
    '教程中心': 'ガイド', '浏览器': 'ブラウザ', '工具箱': 'ツール', '设置': '設定',
    '创世神面板': 'セーブエディター',
    '常规': '一般', '外观': '外観', '下载': 'ダウンロード', '扩展': '拡張',
    '高级': '詳細', '关于': 'このアプリについて',
    '打开下载文件夹': 'ダウンロードフォルダーを開く', '下载文件夹': 'ダウンロードフォルダー',
    '手动下载 / 另存为的文件保存到这里': '手動ダウンロードと「名前を付けて保存」したファイルの保存先',
    '更改': '変更', '打开': '開く', '恢复默认': '既定に戻す',
    '只影响「另存为 / 只下载不安装」的文件；游戏、Mod 与整合包仍写入对应版本目录。': '「名前を付けて保存」とダウンロードのみのファイルに適用されます。ゲーム・Mod・整合パックは各バージョンのフォルダーに保存されます。',
  },
};
function T(text) {
  const lang = (S.data && S.data.language) || 'zh_CN';
  const dict = I18N[lang];
  return (dict && dict[text]) || text;
}

function h(id) { return document.getElementById(id); }
function api() { return (window.pywebview && window.pywebview.api) || null; }
async function call(name, ...args) {
  const a = api();
  if (!a || typeof a[name] !== 'function') throw new Error('美化版后端尚未就绪');
  return a[name](...args);
}
function esc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}
function A(value) { return encodeURIComponent(typeof value === 'string' ? value : JSON.stringify(value)); }
function G(raw) {
  if (!raw) return '';
  const text = decodeURIComponent(raw);
  if ((text.startsWith('{') && text.endsWith('}')) || (text.startsWith('[') && text.endsWith(']'))) {
    try { return JSON.parse(text); } catch (_) { /* 普通字符串 */ }
  }
  return text;
}
function fmtSize(value) {
  const size = Number(value || 0);
  if (!size) return '未知';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0, n = size;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return n.toFixed(1) + ' ' + units[i];
}
function fmtTime(ts) {
  const d = new Date((ts || 0) * 1000);
  if (!ts) return '';
  const pad = (x) => String(x).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}
function toast(message, kind) {
  const node = document.createElement('div');
  node.className = 'toast ' + (kind === 'error' ? 'error' : kind === 'ok' ? 'ok' : '');
  node.textContent = String(message || '');
  h('toasts').appendChild(node);
  setTimeout(() => { node.style.opacity = '0'; node.style.transform = 'translateY(6px)'; }, 2600);
  setTimeout(() => node.remove(), 3100);
}
function setStatus(text, right) { h('statusLeft').textContent = text || '就绪'; if (right != null) h('statusRight').textContent = right; }

const ICONS = {
  home: '<path d="M4 11 12 4l8 7"/><path d="M6 10v10h12V10"/>',
  download: '<path d="M12 4v10"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/>',
  content: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/>',
  instances: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="M4 7.5 12 12l8-4.5"/>',
  control: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2.2"/><circle cx="8" cy="17" r="2.2"/>',
  account: '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c1-4 3.6-6 7-6s6 2 7 6"/>',
  servers: '<circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c2.5 2.4 3.8 5 3.8 8s-1.3 5.6-3.8 8c-2.5-2.4-3.8-5-3.8-8S9.5 6.4 12 4Z"/>',
  tools: '<path d="M14.5 6.5a4 4 0 1 0 5 5L21 21H3l9-9"/><path d="m9 9 6 6"/>',
  wiki: '<path d="M5 4h9a3 3 0 0 1 3 3v13H8a3 3 0 0 0-3 3V4Z"/><path d="M8 20a2 2 0 0 1 0-4h9"/><path d="M9 8h5M9 11h5"/>',
  browser: '<circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c2.5 2.4 3.8 5 3.8 8s-1.3 5.6-3.8 8c-2.5-2.4-3.8-5-3.8-8S9.5 6.4 12 4Z"/>',
  settings: '<circle cx="12" cy="12" r="3.2"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
  creator: '<path d="M12 3v5M9.5 5.5h5"/><circle cx="12" cy="10" r="2.2"/><path d="M6 21v-3a6 6 0 0 1 12 0v3"/><path d="M4 13h2M18 13h2"/>',
};
function icon(name) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || '') + '</svg>'; }

/* ---------- 通用动作分发 ---------- */
const ACT = {};
ACT.nav = async (page) => {
  // 「整合包」在美化版里是内容中心的一个分类，不是独立页面
  if (page === 'modpack') {
    S.content = Object.assign(S.content || {}, { kind: 'modpack', offset: 0 });
    setPage('content');
    return;
  }
  setPage(page);
};
document.addEventListener('click', (event) => {
  const node = event.target.closest('[data-act]');
  if (!node) return;
  const fn = ACT[node.dataset.act];
  if (!fn) return;
  event.preventDefault();
  Promise.resolve(fn(G(node.dataset.arg || ''), node)).catch((err) => toast(err && err.message ? err.message : err, 'error'));
});
document.addEventListener('change', (event) => {
  const node = event.target.closest('[data-set]');
  if (!node) return;
  let value = node.type === 'checkbox' ? node.checked : node.value;
  if (node.dataset.number === '1') value = Number(value || 0);
  saveSetting(node.dataset.set, value).catch((err) => toast(err.message || err, 'error'));
});
document.addEventListener('input', (event) => {
  const node = event.target.closest('[data-live]');
  if (!node) return;
  const target = h(node.dataset.live);
  if (target) target.textContent = node.dataset.suffix ? node.value + node.dataset.suffix : node.value;
  if (node.dataset.glassPreview === '1') applyGlassStrength(node.value);
  else if (node.dataset.glassBlurPreview === '1') {
    if (S.data) S.data.glass_blur = Number(node.value);
    applyGlassBlur(node.value);
    applyGlassStrength((S.data && S.data.glass_strength != null) ? S.data.glass_strength : 62);
  } else if (node.dataset.uiPreview) {
    const draft = Object.assign({}, (S.data || {}));
    draft[node.dataset.uiPreview] = Number(node.value);
    applyUiDetail(draft);
  }
});

async function saveSetting(key, value) {
  const res = await call('settings_set', { [key]: value });
  if (!res.ok) { toast(res.message || '保存失败', 'error'); return; }
  if (res.palette) applyPalette(res.palette);
  if (S.data) {
    if (key === 'theme_name') S.data.theme = value;
    if (key === 'player_name') { S.data.player = value; S.data.account.name = value; h('railAvatarText').textContent = value.slice(0, 1).toUpperCase(); }
    if (key === 'ui_animations') document.body.classList.toggle('no-anim', !value);
    if (key === 'glass_effect') document.body.classList.toggle('no-glass', !value);
    if (key === 'glass_see_through') setGlassMode(!!value, S.data.glass_strength);
    if (key === 'glass_strength') { S.data.glass_strength = value; applyGlassStrength(value); }
    if (key === 'glass_blur') { S.data.glass_blur = value; applyGlassBlur(value); applyGlassStrength(S.data.glass_strength == null ? 62 : S.data.glass_strength); }
    if (key === 'ui_brightness' || key === 'ui_radius' || key === 'ui_scale') { S.data[key] = value; applyUiDetail(S.data); }
    if (key === 'accent_color') { S.data.accent_color = value; }
    if (key === 'text_color') { S.data.text_color = value; }
    if (key === 'isolation_mode') S.data.isolation_mode = value;
    if (key === 'language') {
      S.data.language = value;
      navHtml();
      renderPage(S.page);
    }
  }
  if (S.settingsData && key in S.settingsData) S.settingsData[key] = value;
  toast('设置已保存', 'ok');
}

function applyPalette(p) {
  if (!p) return;
  const root = document.documentElement.style;
  if (p.background) root.setProperty('--bg', p.background);
  if (p.card) root.setProperty('--theme-card', p.card);
  if (p.text) root.setProperty('--text', p.text);
  if (p.muted) root.setProperty('--muted', p.muted);
  if (p.muted_dim) root.setProperty('--dim', p.muted_dim);
  if (p.accent) root.setProperty('--accent', p.accent);
  if (p.accent_text) root.setProperty('--accent-text', p.accent_text);
  if (typeof p.light === 'boolean') applyColorMode(p.light);
}

/* 明亮 / 黑暗模式：整体配色由主题调色板决定，这里只切换 body 标记与标题栏图标 */
function applyColorMode(light) {
  document.body.classList.toggle('light-mode', !!light);
  const btn = h('modeBtn');
  if (btn) {
    btn.textContent = light ? '☾' : '☀';
    btn.title = light ? '切换到黑暗模式' : '切换到明亮模式';
  }
}

function navHtml() {
  const features = (S.data && S.data.features) || {};
  const NAV_FEATURE = {
    home: 'home',
    download: 'download',
    content: 'content',
    instances: 'control',
    control: 'control',
    account: 'account',
    servers: 'multiplayer',
    wiki: 'wiki',
    browser: 'browser',
    creator: 'creator',
  };
  const items = NAV.filter(([id]) => {
    const key = NAV_FEATURE[id];
    return !key || features[key] !== false;
  });
  const extensions = (S.extensions || []).filter((item) => item.type === 'web' && item.enabled && !item.error);
  h('railNav').innerHTML = items.map(([id, label, ico]) => {
    const text = T(label);
    return '<button data-page="' + id + '" data-label="' + esc(text) + '" title="' + esc(text) + '">' + icon(ico) +
      '<span class="tile-label">' + esc(text) + '</span></button>';
  }).join('') + extensions.map((item) =>
    '<button class="ext-nav" data-page="ext:' + esc(item.id) + '" data-label="' + esc(item.name) + '" title="' + esc(item.name) + '">' +
    '<span class="ext-nav-icon">' + esc(item.icon || '✚') + '</span>' +
    '<span class="tile-label">' + esc(item.name) + '</span></button>'
  ).join('');
  h('railNav').querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', () => setPage(btn.dataset.page));
    bindNavTip(btn);
  });
}

function bindNavTip(btn) {
  let tip = document.getElementById('navTip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'navTip';
    tip.className = 'nav-tip';
    document.body.appendChild(tip);
  }
  const show = () => {
    const label = btn.dataset.label || '';
    if (!label) return;
    const rect = btn.getBoundingClientRect();
    tip.textContent = label;
    tip.style.top = Math.round(rect.top + rect.height / 2) + 'px';
    tip.classList.add('show');
  };
  const hide = () => tip.classList.remove('show');
  btn.addEventListener('mouseenter', show);
  btn.addEventListener('mouseleave', hide);
  btn.addEventListener('click', hide);
}

function setPage(page) {
  S.page = page;
  h('view').innerHTML = '';
  h('railNav').querySelectorAll('button').forEach((btn) => btn.classList.toggle('active', btn.dataset.page === page));
  let label = '';
  if (page.indexOf('ext:') === 0) {
    const ext = (S.extensions || []).find((item) => 'ext:' + item.id === page);
    label = ext ? ext.name : '扩展';
  } else {
    const meta = NAV.find((item) => item[0] === page);
    label = meta ? meta[1] : '';
  }
  h('pageTitle').textContent = label;
  if (page !== 'home' && page.indexOf('ext:') !== 0 && label) noteRecent(page, label);
  renderPage(page);
}
/* ---------- 最近使用 ---------- */
function recentList() {
  try {
    const raw = JSON.parse(localStorage.getItem('mikan.recent') || '[]');
    return Array.isArray(raw) ? raw.filter((item) => item && item.page) : [];
  } catch (_) { return []; }
}
function noteRecent(page, label) {
  try {
    const list = recentList().filter((item) => item.page !== page);
    list.unshift({ page: page, label: label });
    localStorage.setItem('mikan.recent', JSON.stringify(list.slice(0, 5)));
  } catch (_) { /* 隐私模式 / 存储禁用时忽略 */ }
}
function recentChipsHtml() {
  const list = recentList();
  if (!list.length) return '';
  return '<div class="recent-row"><span class="hint">最近使用</span>' +
    list.map((item) => '<button class="chip" data-act="recent-open" data-arg="' + esc(item.page) + '">' +
      esc(item.label) + '</button>').join('') + '</div>';
}
ACT['recent-open'] = (page) => { if (page) setPage(page); };
function renderPage(page) {
  if (page === 'home') renderHome();
  else if (page === 'download') renderDownload();
  else if (page === 'content') renderContent();
  else if (page === 'instances') renderInstances();
  else if (page === 'control') renderControl();
  else if (page === 'account') renderAccount();
  else if (page === 'skin') renderSkinStudio();
  else if (page === 'servers') renderServers();
  else if (page === 'wiki') renderWiki();
  else if (page === 'browser') renderBrowser();
  else if (page === 'tools') renderTools();
  else if (page === 'creator') renderCreator();
  else if (page === 'settings') renderSettings();
  else if (page.indexOf('ext:') === 0) renderExtensionPage(page.slice(4));
}
function refreshPage() { renderPage(S.page); }

/* ---------- 扩展 ---------- */
async function loadExtensions() {
  try {
    const res = await call('extensions_list');
    S.extensions = (res && res.items) || [];
  } catch (_) { S.extensions = []; }
  navHtml();
  if (S.page === 'settings' && (S.settings.tab || 'general') === 'extensions') {
    fillSettingsBody(S.settingsData || {});
  }
}

async function renderExtensionPage(extId) {
  const view = h('view');
  if (!view) return;
  view.innerHTML = '<div class="page"><div class="card" style="flex:1"><div class="card-body" style="padding:0;display:flex;flex-direction:column;min-height:0">' +
    '<div class="loading"><span class="spinner"></span>正在载入扩展…</div></div></div></div>';
  let res;
  try { res = await call('extension_page', extId); } catch (err) {
    view.innerHTML = '<div class="page"><div class="empty">扩展载入失败：' + esc(err.message || err) + '</div></div>';
    return;
  }
  if (!res || !res.ok) {
    view.innerHTML = '<div class="page"><div class="empty">' + esc((res && res.message) || '扩展不存在') + '</div></div>';
    return;
  }
  view.innerHTML = '<div class="page"><iframe class="extension-frame" sandbox="allow-scripts" title="' + esc(res.name) + '"></iframe></div>';
  const frame = view.querySelector('iframe');
  if (frame) frame.srcdoc = res.html || '';
}

/* ---------- 启动 ---------- */
function boot() {
  if (!api()) { h('view').innerHTML = '<div class="loading"><span class="spinner"></span>等待内核初始化…</div>'; setTimeout(boot, 400); return; }
  call('bootstrap').then((data) => {
    S.data = data;
    S.tasks = data.tasks || [];
    S.selectedVersion = data.selected_version || (data.versions[0] && data.versions[0].id) || '';
    navHtml();
    applyPalette(data.palette);
    document.body.classList.toggle('no-anim', data.ui_animations === false);
    document.body.classList.toggle('no-glass', data.glass_effect === false);
    h('runtimeLabel').textContent = data.runtime || '';
    h('railAvatarText').textContent = (data.account.name || 'M').slice(0, 1).toUpperCase();
    h('statusRight').textContent = 'v' + data.app + ' · 美化版';
    if (data.agreement && data.agreement.needs) showAgreement(data.agreement.texts);
    setPage('home');
    startTaskPolling();
    hydrateAvatar();
    setGlassMode(data.glass_see_through, data.glass_strength);
    applyUiDetail(data);
    call('window_rect').then((rect) => { if (rect && rect.ok) syncMaximized(rect.maximized); }).catch(() => {});
    applyBackground(data.background_image);
    applyDynamicWallpaper(data.dynamic_wallpaper);
    setTimeout(loadExtensions, 500);
    setTimeout(warmJava, 600);
  }).catch((err) => {
    h('view').innerHTML = '<div class="empty">初始化失败：' + esc(err.message || err) + '</div>';
  });
}

function warmJava() {
  if (!S.data) return;
  if (((S.data.java || {}).list || []).length) return;
  call('java_scan', false).then((r) => {
    if (!r || !r.ok || !r.java) return;
    S.data.java = r.java;
    if (S.page === 'settings') renderSettings();
    else if (S.page === 'download') renderPage();
  }).catch(() => {});
}

function hydrateAvatar() {
  const account = S.data && S.data.account;
  if (!account || !account.skin_path) return;
  call('preview', account.skin_path).then((src) => {
    if (!src) return;
    const head = h('railAvatarHead');
    applyHead(head, src);
    h('railAvatarText').style.display = 'none';
  }).catch(() => {});
}

/* 把整张 64×64 皮肤裁剪成头部：面部 (8,8) + 帽子层 (40,8)，不再显示整张皮肤 */
function applyHead(el, src) {
  if (!el || !src) return el;
  el.style.backgroundImage = 'url("' + src + '"), url("' + src + '")';
  el.classList.add('has-head');
  return el;
}

function showAgreement(texts) {
  h('agreementTitle').textContent = texts.title || '用户协议';
  h('agreementBody').innerHTML =
    '<p>' + esc(texts.intro || '') + '</p>' +
    (texts.sections || []).map(([title, body]) => '<h4>' + esc(title) + '</h4><div>' + esc(body) + '</div>').join('') +
    '<p class="hint">' + esc((texts.version || '').replace('{0}', texts.version_value || '')) + '</p>';
  h('agreeLabel').textContent = texts.checkbox || '我已阅读并同意以上全部条款';
  h('acceptBtn').textContent = texts.accept || '同意并继续';
  h('declineBtn').textContent = texts.decline || '不同意，退出';
  h('agreementOverlay').hidden = false;
}
h('agreeCheck').addEventListener('change', (event) => { h('acceptBtn').disabled = !event.target.checked; });
h('acceptBtn').addEventListener('click', async () => {
  try {
    await call('accept_agreement');
    h('agreementOverlay').hidden = true;
    toast('协议已接受', 'ok');
  } catch (err) { toast(err.message || err, 'error'); }
});
h('declineBtn').addEventListener('click', async () => {
  try { await call('decline_agreement'); } catch (_) { /* 退出流程 */ }
});

/* ---------- 任务轮询 ---------- */
function startTaskPolling() {
  if (S.timer) clearInterval(S.timer);
  S.timer = setInterval(pollTasks, 1200);
}
async function pollTasks() {
  if (!api()) return;
  let tasks;
  try { tasks = await call('tasks'); } catch (_) { return; }
  const before = S.taskStates;
  S.taskStates = {};
  tasks.forEach((task) => { S.taskStates[task.id] = task.state; });
  const finished = tasks.find((task) => task.state === 'ok' && before[task.id] && before[task.id] !== 'ok' && (task.kind === 'version' || task.kind === 'modpack' || task.kind === 'forbric' || task.kind === 'bedrock'));
  S.tasks = tasks;
  const running = tasks.filter((task) => task.state === 'running' || task.state === 'paused');
  const pill = h('taskPill');
  if (running.length) {
    const active = running[0];
    pill.hidden = false;
    pill.textContent = '任务 ' + active.percent.toFixed(0) + '% · ' + active.stage;
    pill.onclick = () => { S.dlTab = 'tasks'; setPage('download'); };
  } else {
    pill.hidden = true;
  }
  if (S.page === 'download' && S.dlTab === 'tasks') renderTaskList();
  if (S.page === 'home') updateHeroTask();
  if (finished) {
    toast('安装完成：' + finished.title, 'ok');
    reloadVersions(true);
    // Forbric / 整合包装完会自动注册实例，重新拉一次 bootstrap 让实例页立即看到
    if (finished.kind === 'forbric' || finished.kind === 'modpack') refreshBootstrap().catch(() => {});
  }
}

/* ---------- 主页 ---------- */
function versionOptions() {
  const versions = (S.data && S.data.versions) || [];
  if (!versions.length) return '<option value="">暂无版本</option>';
  return versions.map((v) =>
    '<option value="' + esc(v.id) + '"' + (v.id === S.selectedVersion ? ' selected' : '') + '>' +
    esc(v.id) + (v.loader ? ' · ' + esc(v.loader) : '') + '</option>'
  ).join('');
}
function findVersion(id) {
  return ((S.data && S.data.versions) || []).find((v) => v.id === id) || null;
}
function selectedInstance() {
  const list = (S.data && S.data.instances) || [];
  return list.find((item) => item.id === S.data.selected_instance) || null;
}
function renderHome() {
  if (!S.data) return;
  const versions = S.data.versions || [];
  if (!versions.some((v) => v.id === S.selectedVersion)) S.selectedVersion = (versions[0] && versions[0].id) || '';
  const current = findVersion(S.selectedVersion);
  const skins = S.data.skins || [];
  const dirs = S.data.game_dirs || [];
  const instance = selectedInstance();
  h('view').innerHTML =
    '<div class="page home">' +
      '<div class="hero">' +
        '<div class="hero-glow"></div>' +
        '<div class="avatar-lg" id="heroAvatar"><i id="heroAvatarHead" class="skin-head"></i><span id="heroAvatarText">' + esc((S.data.account.name || 'S').slice(0, 1).toUpperCase()) + '</span></div>' +
        '<h1 class="hero-name">' + esc(S.data.account.name || S.data.player) + '</h1>' +
        '<div class="hero-sub">' +
          '<select class="ver-select" id="heroInstance" title="切换实例">' +
            (S.data.instances || []).map((item) => '<option value="' + esc(item.id) + '"' + (item.id === S.data.selected_instance ? ' selected' : '') + '>' + esc(item.name) + '</option>').join('') +
          '</select>' +
          '<select class="ver-select" data-change="hero-version" id="heroVersion">' + versionOptions() + '</select>' +
          (dirs.length > 1 ? '<select class="ver-select" id="heroDir" title="数据目录">' +
            dirs.map((d) => '<option value="' + esc(d.id) + '"' + (d.id === S.data.active_game_dir ? ' selected' : '') + '>' + esc(d.name) + '</option>').join('') +
          '</select>' : '') +
          (current && current.loader ? '<span class="tag accent">' + esc(LOADER_CN[current.loader] || current.loader) + '</span>' : '') +
          (current ? '<span class="tag">' + esc(TYPE_CN[current.type] || current.type) + '</span>' : '') +
          '<span class="tag">' + esc(S.data.account.type_label || '离线') + '</span>' +
          (instance ? '<span class="tag">' + esc(instance.name) + '</span>' : '') +
        '</div>' +
        '<button class="launch" id="launchBtn"' + (versions.length && current && !current.error ? '' : ' disabled') + '>启动游戏</button>' +
        '<div class="hero-actions">' +
          '<button class="btn small ghost" data-act="go-download">下载中心</button>' +
          '<button class="btn small ghost" data-act="go-content">内容中心</button>' +
          '<button class="btn small ghost" data-act="go-download" data-arg="bedrock">基岩版</button>' +
          '<button class="btn small ghost" data-act="open-path" data-arg="instance">打开实例目录</button>' +
          '<button class="btn small primary" data-act="home-ui-pack" title="为当前选中版本生成并替换半透明毛玻璃 UI 材质包">UI 材质包一键替换</button>' +
        '</div>' +
        '<div class="hero-hint" id="heroHint">' + heroHint(current) + '</div>' +
        recentChipsHtml() +
      '</div>' +
      '<div class="home-cards">' +
        '<div class="card">' +
          '<div class="card-head"><h2>已安装版本</h2><div class="head-actions">' +
            '<button class="btn small ghost" data-act="refresh-versions">刷新</button>' +
            '<button class="btn small ghost" data-act="go-download">安装</button>' +
          '</div></div>' +
          '<div class="card-body scroll">' +
            (versions.length >= 6 ? '<input class="search" id="verSearch" placeholder="搜索版本…" />' : '') +
            '<div class="version-list">' + versionListHtml(versions) + '</div></div>' +
        '</div>' +
        '<div class="card">' +
          '<div class="card-head"><h2>最近皮肤</h2><div class="head-actions"><button class="btn small ghost" data-act="go-account">管理</button></div></div>' +
          '<div class="card-body scroll"><div class="skin-grid">' +
            (skins.length ? skins.map((skin) => '<button class="skin" data-act="quick-skin" data-arg="' + A(skin.path) + '" data-model="' + esc(skin.model || '') + '" title="' + esc(skin.name) + '"><i class="skin-head" data-skin-path="' + esc(skin.path) + '"></i></button>').join('') : '<div class="empty">还没有导入皮肤。<br>到「账号与皮肤」导入一张 PNG 皮肤。</div>') +
          '</div></div>' +
        '</div>' +
      '</div>' +
    '</div>';
  h('heroVersion').addEventListener('change', (event) => {
    S.selectedVersion = event.target.value; renderHome();
  });
  if (h('heroInstance')) h('heroInstance').addEventListener('change', async (event) => {
    const res = await call('select_instance', event.target.value);
    if (!res.ok) {
      event.target.value = S.data.selected_instance || '';
      toast(res.message || '切换实例失败', 'error');
      return;
    }
    S.data.instances = res.instances || [];
    S.data.selected_instance = event.target.value;
    S.data.versions = res.versions || [];
    S.selectedVersion = '';
    toast('已切换实例');
    renderHome();
  });
  if (h('heroDir')) h('heroDir').addEventListener('change', async (event) => {
    const res = await call('select_game_dir', event.target.value);
    if (!res.ok) { toast(res.message || '切换数据目录失败'); return; }
    S.data.active_game_dir = event.target.value;
    S.data.versions = res.versions || [];
    S.selectedVersion = '';
    toast('已切换数据目录');
    renderHome();
  });
  h('launchBtn').addEventListener('click', launchGame);
  if (h('verSearch')) h('verSearch').addEventListener('input', (event) => {
    const query = event.target.value.trim().toLowerCase();
    document.querySelectorAll('.version-list .ver').forEach((item) => {
      item.style.display = (!query || (item.dataset.ver || '').toLowerCase().includes(query)) ? '' : 'none';
    });
  });
  bindVersionDrag();
  hydrateSkins();
  hydrateHeroAvatar();
}
function heroHint(current) {
  if (!current) return '还没有安装游戏版本，先去下载中心安装一个。';
  if (current.error) return '版本文件损坏：' + current.error;
  return '版本 ' + current.id + ' · 点击侧栏头像可快速切换皮肤';
}
function versionListHtml(versions) {
  if (!versions.length) return '<div class="empty" style="padding:26px 16px">' +
    '<div style="font-size:14px;font-weight:600;margin-bottom:6px">下一步：先装一个游戏版本</div>' +
    '装好原版后再按需添加 Forge / Fabric 等加载器；也可以把 .jar、mods 文件夹或整合包直接拖进窗口导入。' +
    '<div class="row" style="justify-content:center;gap:8px;margin-top:12px;flex-wrap:wrap">' +
      '<button class="btn small primary" data-act="guide" data-arg="home">下一步：下载游戏版本</button>' +
      '<button class="btn small" data-act="nav" data-arg="modpack">安装整合包</button>' +
      '<button class="btn small ghost" data-act="nav" data-arg="wiki">看安装教程</button>' +
    '</div></div>';
  return versions.map((v) =>
    '<button class="ver' + (v.id === S.selectedVersion ? ' active' : '') + '" draggable="true" data-ver="' + esc(v.id) + '" data-act="pick-version" data-arg="' + A(v.id) + '" title="拖动可调整顺序；右键打开菜单">' +
      '<span>' + esc(v.id) + '</span>' +
      '<small>' + esc(TYPE_CN[v.type] || v.type) + (v.loader ? ' · ' + esc(LOADER_CN[v.loader] || v.loader) : '') + '</small>' +
      '<i class="ver-more" data-act="version-detail" data-arg="' + A(v.id) + '" title="版本详情">›</i>' +
    '</button>'
  ).join('');
}
function bindVersionDrag() {
  const list = document.querySelector('.version-list');
  if (!list) return;
  let dragId = '';
  list.querySelectorAll('.ver').forEach((btn) => {
    btn.addEventListener('dragstart', (event) => {
      dragId = btn.dataset.ver || '';
      if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
      btn.classList.add('dragging');
    });
    btn.addEventListener('dragend', () => { dragId = ''; btn.classList.remove('dragging'); });
    btn.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      const id = btn.dataset.ver || '';
      showContextMenu(event.clientX, event.clientY, [
        { label: '版本详情 / 安装加载器', run: () => openVersionDetail(id) },
        { label: '启动该版本', run: () => { S.selectedVersion = id; launchGame(); } },
        { label: '打开游戏目录', run: () => call('open_path', 'version:' + id).catch(() => {}) },
        { label: '打开版本目录', run: () => call('open_path', 'versiondir:' + id).catch(() => {}) },
        { label: '打开 Mods 目录', run: () => call('open_path', 'versionmods:' + id).catch(() => {}) },
        { label: '版本设置', run: () => openVersionSettings(id) },
        { label: '复制版本名', run: () => copyText(id) },
        { label: '删除版本', run: async () => {
          if (!(await ask('删除版本', '将删除 ' + id + ' 的版本文件（不删除存档与 mods）。确定继续？'))) return;
          const res = await call('delete_version', id);
          if (!res.ok) return toast(res.message, 'error');
          await refreshBootstrap();
          toast('已删除版本 ' + id, 'ok');
        } },
      ]);
    });
  });
  list.addEventListener('dragover', (event) => event.preventDefault());
  list.addEventListener('drop', async (event) => {
    event.preventDefault();
    const target = event.target.closest('.ver');
    if (!dragId || !target) return;
    const targetId = target.dataset.ver || '';
    if (targetId === dragId) return;
    const ids = Array.from(list.querySelectorAll('.ver')).map((item) => item.dataset.ver);
    ids.splice(ids.indexOf(dragId), 1);
    ids.splice(ids.indexOf(targetId), 0, dragId);
    const res = await call('version_order_save', ids);
    if (!res.ok) { toast(res.message || '保存顺序失败', 'error'); return; }
    const byId = {};
    (S.data.versions || []).forEach((item) => { byId[item.id] = item; });
    S.data.versions = ids.map((id) => byId[id]).filter(Boolean);
    renderHome();
  });
}
function hydrateSkins() {
  document.querySelectorAll('[data-skin-path]').forEach((el) => {
    const path = el.dataset.skinPath;
    if (!path) return;
    call('preview', path).then((src) => applyHead(el, src)).catch(() => {});
  });
}
function hydrateHeroAvatar() {
  const path = S.data.account && S.data.account.skin_path;
  if (!path) return;
  call('preview', path).then((src) => {
    if (!src) return;
    applyHead(h('heroAvatarHead'), src);
    const text = h('heroAvatarText');
    if (text) text.style.display = 'none';
  }).catch(() => {});
}
function updateHeroTask() {
  const running = S.tasks.filter((t) => t.state === 'running' || t.state === 'paused');
  const hint = h('heroHint');
  if (!hint) return;
  if (running.length) hint.textContent = '任务：' + running[0].stage + ' ' + running[0].percent.toFixed(0) + '%';
}
async function launchGame() {
  if (!S.selectedVersion) return toast('请先选择版本', 'error');
  const instance = selectedInstance();
  const version = S.selectedVersion;
  const instId = instance ? instance.id : '';
  let force = false;
  let check = { blocked: [], warnings: [] };
  try { check = await call('launch_check', version, instId); } catch (_) {}
  if (check.blocked && check.blocked.length) {
    const ok = await ask('启动前检查未通过', check.blocked.join('\n\n') + '\n\n仍要强制启动吗？');
    if (!ok) return;
    force = true;
  }
  const res = await call('launch', version, instId, force);
  if (!res.ok) {
    const detail = (res.blocked && res.blocked[0]) || res.message || '启动失败';
    return toast(detail, 'error');
  }
  toast('正在准备启动…', 'ok');
  const job = await watchJob(res.job);
  if (!job || job.state !== 'ok') {
    const err = (job && (job.error || job.stage)) || '启动超时';
    return toast(err, 'error');
  }
  const result = job.result || {};
  toast(result.message || '游戏已启动', 'ok');
  if (result.params) setTimeout(() => toast(result.params, 'ok'), 1200);
  const warnings = (result.warnings || []).concat(check.warnings || []);
  if (warnings.length) setTimeout(() => toast(warnings[0], 'error'), 1500);
  if (result.support_prompt) showSupportPrompt();
  setStatus('已启动', result.version || version);
}

function showSupportPrompt() {
  openSheet('支持正版！',
    '<div class="empty" style="padding:4px 0 8px">如果你喜欢 Minecraft，请购买正版支持作者。启动器只提供便捷管理，不会绕过正版验证。</div>',
    '<button class="btn ghost" id="supportLater">下次一定</button><button class="btn primary" id="supportBuy">这就去买</button>');
  h('supportLater').onclick = closeSheet;
  h('supportBuy').onclick = () => {
    closeSheet();
    call('open_url', 'https://www.minecraft.net/zh-hans/store/minecraft-java-bedrock-edition-pc').catch(() => {});
  };
}
async function reloadVersions(silent) {
  try {
    const versions = await call('scan_versions', false);
    S.data.versions = versions;
    if (!versions.some((v) => v.id === S.selectedVersion)) S.selectedVersion = (versions[0] && versions[0].id) || '';
    if (S.page === 'home') renderHome();
    if (!silent) toast('版本列表已刷新', 'ok');
  } catch (err) { if (!silent) toast(err.message || err, 'error'); }
}

/* ---------- 下载中心 ---------- */
function renderDownload() {
  const features = (S.data && S.data.features) || {};
  const allTabs = [['game', '游戏版本', 'download'], ['loader', '加载器', 'loaders'], ['java', 'Java', 'java'], ['bedrock', '基岩版', 'bedrock'], ['accel', '下载加速', 'download_accel'], ['tasks', '任务列表', 'downloads']];
  const tabs = allTabs.filter((t) => features[t[2]] !== false);
  if (tabs.length && !tabs.some((t) => t[0] === S.dlTab)) S.dlTab = tabs[0][0];
  h('view').innerHTML =
    '<div class="page">' +
      '<div class="toolbar">' +
        '<div class="tabs">' + tabs.map(([id, name]) =>
          '<button class="tab' + (S.dlTab === id ? ' active' : '') + '" data-act="dl-tab" data-arg="' + id + '">' + name + '</button>'
        ).join('') + '</div><span class="spacer"></span>' +
        '<button class="btn small ghost" data-act="open-tasks-center">任务中心</button>' +
      '</div>' +
      '<div class="scroll" id="dlBody" style="flex:1;min-height:0;margin-top:12px"></div>' +
    '</div>';
  if (S.dlTab === 'game') renderGameTab();
  else if (S.dlTab === 'loader') renderLoaderTab();
  else if (S.dlTab === 'java') renderJavaTab();
  else if (S.dlTab === 'bedrock') renderBedrockTab();
  else if (S.dlTab === 'accel') renderAccelTab();
  else renderTaskList();
}
ACT['dl-tab'] = (id) => { S.dlTab = id; renderDownload(); };
ACT['open-tasks-center'] = () => { S.dlTab = 'tasks'; renderDownload(); };

function renderAccelTab() {
  const body = h('dlBody');
  if (!body) return;
  const dir = S.accelDir || '';
  body.innerHTML =
    '<div class="card"><div class="card-head"><h2>下载加速</h2><span class="muted">任意直链，多线程分段下载，支持暂停 / 续传</span></div>' +
      '<div class="card-body">' +
        '<textarea id="accelText" rows="6" placeholder="每行一个链接，或直接粘贴一段包含链接的文本（自动提取、去重）" style="width:100%"></textarea>' +
        '<div class="toolbar" style="margin-top:10px">' +
          '<span class="muted">保存到：' + (dir ? esc(dir) : '默认 data/downloads') + '</span>' +
          '<button class="btn small ghost" data-act="accel-pick">选择目录…</button>' +
          '<span class="spacer"></span>' +
          '<span class="muted">线程数</span>' +
          '<input type="number" id="accelThreads" min="1" max="328" step="1" value="16" style="width:84px" />' +
          '<button class="btn primary" data-act="accel-start">开始加速下载</button>' +
        '</div>' +
      '</div>' +
    '</div>';
}
ACT['accel-pick'] = async () => {
  const res = await call('accel_pick_dir');
  if (!res.ok) { if (res.message) toast(res.message, 'error'); return; }
  S.accelDir = res.directory || '';
  renderAccelTab();
};
ACT['accel-start'] = async () => {
  const box = h('accelText');
  const text = box ? box.value : '';
  const field = h('accelThreads');
  const threads = Math.max(1, Math.min(328, parseInt((field && field.value) || '16', 10) || 16));
  const res = await call('accel_start', text, threads, S.accelDir || '');
  if (!res.ok) return toast(res.message, 'error');
  toast('已加入 ' + res.count + ' 个下载任务', 'ok');
  if (box) box.value = '';
  S.dlTab = 'tasks';
  renderDownload();
};

function renderGameTab() {
  const body = h('dlBody');
  if (!body) return;
  const filters = [['release', '正式版'], ['snapshot', '快照'], ['old', '旧版本'], ['all', '全部']];
  body.innerHTML =
    '<div class="toolbar" style="margin-bottom:10px">' +
      '<div class="chips">' + filters.map(([id, name]) =>
        '<button class="chip' + (S.manifestFilter === id ? ' active' : '') + '" data-act="manifest-filter" data-arg="' + id + '">' + name + '</button>'
      ).join('') + '</div><span class="spacer"></span>' +
      '<input type="text" id="manifestSearch" placeholder="输入版本号筛选，例如 1.20" style="width:200px" value="' + esc(S.manifestQuery) + '" />' +
      '<button class="btn small ghost" data-act="manifest-refresh">刷新清单</button>' +
    '</div>' +
    '<div id="manifestNote" class="hint" style="margin-bottom:8px"></div>' +
    '<div class="list" id="manifestList">' + (S.manifest ? '' : '<div class="loading"><span class="spinner"></span>正在获取 Mojang 版本清单…</div>') + '</div>';
  const search = h('manifestSearch');
  search.addEventListener('input', () => {
    S.manifestQuery = search.value.trim();
    renderManifestList();
  });
  // 双击任意版本行 → 版本详情：可顺手选择 Mod 加载器，下载原版时一并安装
  const mlist = h('manifestList');
  mlist.addEventListener('dblclick', (event) => {
    if (event.target.closest('button')) return;
    const row = event.target.closest('[data-mc]');
    if (row) openInstallSheet(row.dataset.mc);
  });
  if (S.manifest) renderManifestList();
  else loadManifest(false);
}
async function loadManifest(force) {
  try {
    const res = await call('manifest', !!force);
    if (!res.ok) { h('manifestNote').textContent = res.message; h('manifestList').innerHTML = '<div class="empty">' + esc(res.message) + '</div>'; return; }
    S.manifest = res.versions;
    S.manifestAt = Date.now();
    S.manifestSource = res.source;
    const note = h('manifestNote');
    if (note) note.textContent = '来源：' + res.source + (res.cached ? ' · 本地缓存' : '') + ' · 共 ' + res.versions.length + ' 个版本';
    renderManifestList();
  } catch (err) { if (h('manifestNote')) h('manifestNote').textContent = err.message || err; }
}
ACT['manifest-refresh'] = () => loadManifest(true);
ACT['manifest-filter'] = (mode) => { S.manifestFilter = mode; renderGameTab(); };

function filteredManifest() {
  if (!S.manifest) return [];
  const query = S.manifestQuery.toLowerCase();
  return S.manifest.filter((item) => {
    if (S.manifestFilter === 'release' && item.type !== 'release') return false;
    if (S.manifestFilter === 'snapshot' && item.type !== 'snapshot') return false;
    if (S.manifestFilter === 'old' && !(item.type === 'old_beta' || item.type === 'old_alpha')) return false;
    if (query && !item.id.toLowerCase().includes(query)) return false;
    return true;
  });
}
function renderManifestList() {
  const list = h('manifestList');
  if (!list) return;
  const rows = filteredManifest();
  const shown = rows.slice(0, 140);
  list.innerHTML = shown.length ? shown.map((item) =>
    '<div class="row" data-mc="' + A(item.id) + '" title="双击查看详情 / 选择加载器" style="cursor:pointer">' +
      '<div class="row-main"><b>' + esc(item.id) + '</b><small>' + esc(TYPE_CN[item.type] || item.type) + ' · ' + esc((item.release || '').slice(0, 10)) + '</small></div>' +
      '<div class="row-meta">' + (findVersion(item.id) ? '<span class="tag accent">已安装</span>' : '') + '</div>' +
      '<div class="row-actions"><button class="btn small ghost" data-act="install-detail" data-arg="' + A(item.id) + '">详情</button>' +
        '<button class="btn small ' + (findVersion(item.id) ? '' : 'primary') + '" data-act="install-vanilla" data-arg="' + A(item.id) + '"' + (findVersion(item.id) ? ' disabled' : '') + '>安装</button>' +
        '<button class="btn small ghost" data-act="vanilla-save" data-arg="' + A(item.id) + '">另存 Jar</button>' +
        (findVersion(item.id) ? '<button class="btn small danger" data-act="delete-vanilla" data-arg="' + A(item.id) + '">删除</button>' : '') + '</div>' +
    '</div>'
  ).join('') + (rows.length > shown.length ? '<div class="hint">仅显示前 140 条，请用搜索框缩小范围（共 ' + rows.length + ' 条）</div>' : '')
    : '<div class="empty">没有匹配的版本。</div>';
}
ACT['install-vanilla'] = async (id) => {
  const res = await call('install_version', id, '', '');
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message, 'ok');
};
ACT['vanilla-save'] = async (id) => {
  const res = await call('save_vanilla_jar', id);
  if (!res.ok) { if (res.message) toast(res.message, 'error'); return; }
  toast(res.message, 'ok');
  S.dlTab = 'tasks';
};
ACT['delete-vanilla'] = async (id) => {
  if (!(await ask('删除版本', '将删除 ' + id + ' 的版本文件（不删除存档与 mods）。确定继续？'))) return;
  const res = await call('delete_version', id);
  if (!res.ok) return toast(res.message, 'error');
  await refreshBootstrap();
  if (S.page === 'download' && S.dlTab === 'game') renderGameTab();
  toast('已删除版本 ' + id, 'ok');
};

function renderLoaderTab() {
  const body = h('dlBody');
  if (!body) return;
  const kinds = ['fabric', 'quilt', 'forge', 'neoforge', 'liteloader', 'forbric'];
  const mcOptions = (S.loader.mcVersions || []).map((v) => '<option value="' + esc(v) + '"' + (v === S.loader.mc ? ' selected' : '') + '>' + esc(v) + '</option>').join('');
  body.innerHTML =
    '<div class="card" style="max-width:720px">' +
      '<div class="card-head"><h2>加载器一键安装</h2><span class="hint">与原版安装共用下载队列</span></div>' +
      '<div class="card-body" style="display:flex;flex-direction:column;gap:12px">' +
        '<div class="field"><label>加载器类型</label><div class="chips">' + kinds.map((kind) =>
          '<button class="chip' + (S.loader.kind === kind ? ' active' : '') + '" data-act="loader-kind" data-arg="' + kind + '">' + (LOADER_CN[kind] || kind) + '</button>'
        ).join('') + '</div></div>' +
        '<div class="grid2">' +
          '<div class="field"><label>Minecraft 版本</label><select id="loaderMc">' + (mcOptions || '<option value="">加载中…</option>') + '</select></div>' +
          '<div class="field"><label>加载器版本</label><select id="loaderVer"><option value="">最新稳定版</option>' + (S.loader.versions || []).map((v) => {
            const value = typeof v === 'string' ? v : v.version || v.id || '';
            return '<option value="' + esc(value) + '"' + (value === S.loader.version ? ' selected' : '') + '>' + esc(value) + '</option>';
          }).join('') + '</select></div>' +
        '</div>' +
        '<div class="hint" id="loaderHint">' + loaderHint() + '</div>' +
        '<div class="toolbar"><button class="btn primary" id="loaderInstall"' + (loaderBlocked() ? ' disabled' : '') + '>安装加载器</button>' +
          '<button class="btn ghost" id="loaderSaveAs">另存安装器…</button>' +
          '<button class="btn ghost" data-act="loader-refresh">刷新版本列表</button>' +
          '<span class="spacer"></span><button class="btn ghost" data-act="open-path" data-arg="game">打开游戏目录</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  h('loaderMc').addEventListener('change', (event) => {
    S.loader.mc = event.target.value;
    S.loader.version = '';
    loadLoaderVersions();
  });
  h('loaderVer').addEventListener('change', (event) => { S.loader.version = event.target.value; });
  h('loaderInstall').addEventListener('click', installLoader);
  h('loaderSaveAs').addEventListener('click', async () => {
    if (!S.loader.mc) return toast('请先选择 Minecraft 版本', 'error');
    if (S.loader.kind === 'forbric') return toast('Forbric 由官方安装器引导，请直接点击安装', 'error');
    const res = await call('save_loader_installer', S.loader.kind, S.loader.mc, S.loader.version || '');
    if (!res.ok) { if (res.message) toast(res.message, 'error'); return; }
    toast(res.message, 'ok');
    S.dlTab = 'tasks';
  });
  if (!S.loader.mcVersions.length) loadLoaderMcVersions();
  else if (!S.loader.versions.length && S.loader.mc) loadLoaderVersions();
}
function loaderBlocked() {
  return S.loader.kind === 'forbric' && (!S.loader.mc || S.loader.mc !== '26.2');
}
function loaderHint() {
  if (S.loader.kind === 'forbric') {
    if (loaderBlocked()) {
      return '当前选择的 Minecraft 版本为 ' + (S.loader.mc || '未选择') + '，Forbric 仅兼容 26.2，安装按钮已禁用。';
    }
    return 'Forbric 是实验性三合一加载器，将引导官方安装器写入 26.2-forbric 版本。';
  }
  return '安装会先确保原版就绪，再写入加载器版本。安装进度在任务列表里实时显示。';
}
async function loadLoaderMcVersions() {
  const hint = h('loaderHint');
  if (hint) hint.textContent = '正在获取游戏版本…';
  try {
    const res = await call('loader_mc_versions', S.loader.kind);
    S.loader.mcVersions = res.versions || [];
    S.loader.mc = S.loader.mcVersions[0] || '';
    if (S.page === 'download' && S.dlTab === 'loader') renderLoaderTab();
    if (S.loader.mc) loadLoaderVersions();
    if (hint) hint.textContent = loaderHint();
  } catch (err) { if (hint) hint.textContent = err.message || err; }
}
async function loadLoaderVersions() {
  if (!S.loader.mc) return;
  // 切换 MC 版本后旧加载器版本号已失效，必须清空，否则会显示错误版本
  S.loader.version = '';
  S.loader.versions = [];
  const hint = h('loaderHint');
  if (hint) hint.textContent = '正在获取加载器版本…';
  try {
    const res = await call('loader_versions', S.loader.kind, S.loader.mc);
    S.loader.versions = res.versions || [];
    if (S.page === 'download' && S.dlTab === 'loader') renderLoaderTab();
    if (hint) hint.textContent = loaderHint();
  } catch (err) { if (hint) hint.textContent = err.message || err; }
}
ACT['loader-kind'] = (kind) => { S.loader.kind = kind; S.loader.versions = []; S.loader.version = ''; S.loader.mcVersions = []; renderLoaderTab(); };
ACT['version-detail'] = (id) => openVersionDetail(id);
ACT['loader-refresh'] = () => { S.loader.mcVersions = []; S.loader.versions = []; renderLoaderTab(); };
async function installLoader() {
  const mc = S.loader.mc;
  const version = S.loader.version || '';
  if (!mc) return toast('请先选择 Minecraft 版本', 'error');
  if (S.loader.kind === 'forbric' && mc !== '26.2') return toast('Forbric 当前仅支持 Minecraft 26.2', 'error');
  const res = await call('install_version', mc, S.loader.kind, version);
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message, 'ok');
}

/* ---------- 下载清单版本详情：双击即可顺手选加载器，一次装好 ---------- */
ACT['install-detail'] = (id) => openInstallSheet(id);
function openInstallSheet(id) {
  S.mcd = { mc: id, kind: '', versions: [], version: '', loading: false, loaded: false };
  openSheet('安装 · ' + id, '<div id="mcdBody"></div>',
    '<button class="btn ghost" id="mcdClose">关闭</button><button class="btn primary" id="mcdInstall">下载安装</button>');
  if (h('mcdClose')) h('mcdClose').onclick = closeSheet;
  if (h('mcdInstall')) h('mcdInstall').onclick = mcdInstall;
  renderInstallSheet();
}
function renderInstallSheet() {
  const body = h('mcdBody');
  const mcd = S.mcd;
  if (!body || !mcd) return;
  const installed = findVersion(mcd.mc);
  const kinds = ['', 'fabric', 'quilt', 'forge', 'neoforge', 'liteloader', 'forbric'];
  const blocked = mcd.kind === 'forbric' && mcd.mc !== '26.2';
  const options = mcd.versions.map((item) => {
    const value = typeof item === 'string' ? item : item.version || item.id || '';
    return '<option value="' + esc(value) + '"' + (value === mcd.version ? ' selected' : '') + '>' + esc(value) + '</option>';
  }).join('');
  body.innerHTML =
    '<div class="card" style="margin-bottom:12px"><div class="card-head"><h2>' + esc(mcd.mc) + '</h2>' +
      '<span class="hint">' + (installed ? '已安装 · ' + esc(TYPE_CN[installed.type] || installed.type) : '未安装') + '</span></div>' +
      '<div class="card-body"><div class="hint">选择原版或加载器后一次装好，不需要再单独进入加载器页面。</div></div></div>' +
    '<div class="card"><div class="card-head"><h2>安装内容</h2><span class="hint">默认只安装原版</span></div>' +
      '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
        '<div class="chips">' + kinds.map((kind) =>
          '<button class="chip' + (mcd.kind === kind ? ' active' : '') + '" data-mcd-kind="' + kind + '">' + (kind ? (LOADER_CN[kind] || kind) : '原版') + '</button>'
        ).join('') + '</div>' +
        (mcd.kind ? '<div class="field"><label>加载器版本</label><select id="mcdVer"><option value="">最新稳定版</option>' + options + '</select></div>' : '') +
        '<div class="hint" id="mcdHint">' + installSheetHint() + '</div>' +
      '</div></div>';
  body.querySelectorAll('[data-mcd-kind]').forEach((btn) => {
    btn.onclick = () => {
      mcd.kind = btn.dataset.mcdKind;
      mcd.versions = []; mcd.version = ''; mcd.loading = false; mcd.loaded = false;
      renderInstallSheet();
    };
  });
  if (h('mcdVer')) h('mcdVer').onchange = (event) => { mcd.version = event.target.value; };
  const install = h('mcdInstall');
  if (install) install.disabled = blocked;
  if (mcd.kind && !mcd.versions.length && !mcd.loading && !mcd.loaded) mcdLoadVersions();
}
function installSheetHint() {
  const mcd = S.mcd;
  if (!mcd) return '';
  if (mcd.kind === 'forbric') {
    return mcd.mc === '26.2'
      ? 'Forbric 为实验性三合一加载器，将引导官方安装器写入 26.2-forbric。'
      : 'Forbric 仅兼容 Minecraft 26.2，当前版本不可用。';
  }
  if (mcd.loading) return '正在获取加载器版本…';
  if (mcd.kind && mcd.loaded && !mcd.versions.length) {
    return '该 Minecraft 版本没有可用的 ' + (LOADER_CN[mcd.kind] || mcd.kind) + ' 版本，可直接安装原版。';
  }
  return mcd.kind
    ? '会先补全原版客户端，再写入所选加载器；进度显示在下载任务列表。'
    : '只安装原版客户端，不包含任何 Mod 加载器。';
}
async function mcdLoadVersions() {
  const mcd = S.mcd;
  if (!mcd || !mcd.kind) return;
  mcd.loading = true;
  const hint = h('mcdHint');
  if (hint) hint.textContent = '正在获取加载器版本…';
  try {
    const res = await call('loader_versions', mcd.kind, mcd.mc);
    mcd.versions = res.versions || [];
  } catch (_) { mcd.versions = []; }
  mcd.loading = false;
  mcd.loaded = true;
  if (S.mcd === mcd) renderInstallSheet();
}
async function mcdInstall() {
  const mcd = S.mcd;
  if (!mcd) return;
  if (mcd.kind === 'forbric' && mcd.mc !== '26.2') return toast('Forbric 当前仅支持 Minecraft 26.2', 'error');
  const install = h('mcdInstall');
  if (install) install.disabled = true;
  const res = await call('install_version', mcd.mc, mcd.kind, mcd.version || '');
  if (!res.ok) { if (install) install.disabled = false; return toast(res.message, 'error'); }
  toast(res.message || '已加入下载队列', 'ok');
  closeSheet();
  S.dlTab = 'tasks';
  if (S.page === 'download') renderDownload();
}

/* ---------- 版本设置：独立页面，完整照搬经典版 ControlPage ---------- */
async function openVersionSettings(id) {
  if (h('overlay') && !h('overlay').hidden) closeSheet();
  const st = ctrlState();
  st.versionId = id || st.versionId || '';
  const inst = ctrlCurrentInstance();
  if (inst) st.instanceId = inst.id;
  S.selectedVersion = st.versionId || S.selectedVersion;
  setPage('control');
}

/* ---------- 版本详情（二级菜单）：加载器安装 / Mod 管理 / 右键菜单 ---------- */
function mcVersionOf(id) {
  const match = /^(\d+\.\d+(?:\.\d+)?)/.exec(id || '');
  return match ? match[1] : '';
}
async function openVersionDetail(id) {
  const version = (S.data.versions || []).find((item) => item.id === id) || { id: id };
  S.vd = {
    id: id,
    kind: version.loader || 'fabric',
    mc: mcVersionOf(id),
    versions: [],
    version: '',
    loading: false,
    loaded: false,
    mods: null,
    scan: null,
  };
  openSheet('版本详情 · ' + id, '<div id="vdBody"><div class="empty">加载中…</div></div>',
    '<button class="btn ghost" id="sheetCancel">关闭</button>');
  await vdRefresh();
}
async function vdRefresh() {
  const vd = S.vd;
  if (!vd) return;
  try { vd.mods = await call('mods_list', vd.id); } catch (_) { vd.mods = null; }
  try { vd.scan = await call('mod_scan', vd.id); } catch (_) { vd.scan = null; }
  renderVd();
}
function renderVd() {
  const body = h('vdBody');
  const vd = S.vd;
  if (!body || !vd) return;
  const version = (S.data.versions || []).find((item) => item.id === vd.id) || {};
  const conflicts = (vd.scan && vd.scan.conflicts) || [];
  const mods = (vd.mods && vd.mods.items) || [];
  const kinds = ['fabric', 'quilt', 'forge', 'neoforge', 'liteloader', 'forbric'];
  const options = vd.versions.map((item) => {
    const value = typeof item === 'string' ? item : item.version || item.id || '';
    return '<option value="' + esc(value) + '"' + (value === vd.version ? ' selected' : '') + '>' + esc(value) + '</option>';
  }).join('');
  body.innerHTML =
    '<div class="card" style="margin-bottom:12px"><div class="card-head"><h2>' + esc(vd.id) + '</h2>' +
      '<span class="hint">' + esc(TYPE_CN[version.type] || version.type || '版本') + (version.loader ? ' · ' + esc(LOADER_CN[version.loader] || version.loader) : '') + '</span></div>' +
      '<div class="card-body"><div class="toolbar">' +
        '<button class="btn primary" id="vdLaunch">启动</button>' +
        '<button class="btn ghost" id="vdOpenGame">打开游戏目录</button>' +
        '<button class="btn ghost" id="vdOpenVer">打开版本目录</button>' +
        '<button class="btn ghost" id="vdOpenMods">打开 Mods</button>' +
        '<button class="btn ghost" id="vdSettings">版本设置</button>' +
        '<span class="spacer"></span><button class="btn danger small" id="vdDelete">删除版本</button>' +
      '</div><div class="hint" style="margin-top:6px">全部隔离模式下，Mod、存档、配置都在该版本自己的目录中。</div></div></div>' +
    '<div class="card" style="margin-bottom:12px"><div class="card-head"><h2>安装 / 更换加载器</h2><span class="hint">先确保原版就绪，再写入加载器</span></div>' +
      '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
        '<div class="chips">' + kinds.map((kind) =>
          '<button class="chip' + (vd.kind === kind ? ' active' : '') + '" data-vd-kind="' + kind + '">' + (LOADER_CN[kind] || kind) + '</button>'
        ).join('') + '</div>' +
        '<div class="grid2"><div class="field"><label>Minecraft 版本</label><input id="vdMc" value="' + esc(vd.mc) + '" readonly /></div>' +
        '<div class="field"><label>加载器版本</label><select id="vdVer"><option value="">最新稳定版</option>' + options + '</select></div></div>' +
        '<div class="hint" id="vdHint">' + (vd.loading ? '正在获取加载器版本…' : (vd.kind === 'forbric' && vd.mc !== '26.2' ? 'Forbric 仅兼容 Minecraft 26.2，当前版本不可用。' : '安装进度会显示在下载任务列表。')) + '</div>' +
        '<div class="toolbar"><button class="btn primary" id="vdInstall"' + (vd.kind === 'forbric' && vd.mc !== '26.2' ? ' disabled' : '') + '>安装加载器</button>' +
          '<button class="btn ghost" id="vdSaveAs">另存安装器…</button>' +
          '<button class="btn ghost" id="vdRefreshVer">刷新版本列表</button></div>' +
      '</div></div>' +
    '<div class="card"><div class="card-head"><h2>Mod 管理</h2><span class="hint">' + esc((vd.mods && vd.mods.dir) || '') + '</span></div>' +
      '<div class="card-body scroll" style="max-height:280px">' +
        (conflicts.length ? '<div class="hint" style="color:var(--warn);margin-bottom:8px">检测到 ' + conflicts.length + ' 项冲突：' +
          conflicts.map((item) => esc((item.modid || item.type) + ' ' + (item.detail || ''))).join('；') + '</div>' : '') +
        (mods.length ? '<div class="list">' + mods.map((item) =>
          '<div class="row"><div style="min-width:0"><b style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(item.name) + '</b>' +
          '<span class="hint">' + (item.enabled ? '已启用' : '已禁用') + ' · ' + fmtSize(item.size) + '</span></div><span class="spacer"></span>' +
          '<button class="btn small ghost" data-vd-toggle="' + A(item.path) + '">' + (item.enabled ? '禁用' : '启用') + '</button>' +
          '<button class="btn small danger" data-vd-delmod="' + A(item.path) + '">删除</button></div>'
        ).join('') + '</div>' : '<div class="empty">该版本还没有 Mod。<br>去「内容中心」搜索安装，或直接把 .jar 放进 mods 目录。</div>') +
      '</div></div>';
  if (h('vdLaunch')) h('vdLaunch').onclick = async () => {
    S.selectedVersion = vd.id;
    closeSheet();
    await launchGame();
  };
  if (h('vdOpenGame')) h('vdOpenGame').onclick = () => call('open_path', 'version:' + vd.id).catch(() => {});
  if (h('vdOpenVer')) h('vdOpenVer').onclick = () => call('open_path', 'versiondir:' + vd.id).catch(() => {});
  if (h('vdOpenMods')) h('vdOpenMods').onclick = () => call('open_path', 'versionmods:' + vd.id).catch(() => {});
  if (h('vdSettings')) h('vdSettings').onclick = () => openVersionSettings(vd.id);
  if (h('vdDelete')) h('vdDelete').onclick = async () => {
    if (!(await ask('删除版本', '将删除 ' + vd.id + ' 的版本文件（不删除存档与 mods）。确定继续？'))) return;
    const res = await call('delete_version', vd.id);
    if (!res.ok) return toast(res.message, 'error');
    closeSheet();
    await refreshBootstrap();
    toast('已删除版本 ' + vd.id, 'ok');
  };
  if (h('vdVer')) h('vdVer').onchange = (event) => { vd.version = event.target.value; };
  if (h('vdRefreshVer')) h('vdRefreshVer').onclick = () => { vd.versions = []; vd.loaded = false; vd.version = ''; renderVd(); };
  const install = h('vdInstall');
  if (install) install.onclick = async () => {
    if (vd.kind === 'forbric' && vd.mc !== '26.2') return toast('Forbric 当前仅支持 Minecraft 26.2', 'error');
    // 加载器要装在原版版本上：已安装版本 ID 可能带加载器后缀（1.21.1-forge-52.x），
    // 必须传基础 MC 版本号，否则后端找不到原版清单。
    const res = await call('install_version', vd.mc || vd.id, vd.kind, vd.version || '');
    if (!res.ok) return toast(res.message, 'error');
    toast(res.message || '已开始安装加载器', 'ok');
  };
  if (h('vdSaveAs')) h('vdSaveAs').onclick = async () => {
    const res = await call('save_loader_installer', vd.kind, vd.mc, vd.version || '');
    toast(res.message, res.ok ? 'ok' : 'error');
  };
  body.querySelectorAll('[data-vd-kind]').forEach((btn) => {
    btn.onclick = () => { vd.kind = btn.dataset.vdKind; vd.versions = []; vd.loaded = false; vd.version = ''; renderVd(); };
  });
  body.querySelectorAll('[data-vd-toggle]').forEach((btn) => {
    btn.onclick = async () => { await call('mod_toggle', btn.dataset.vdToggle); vdRefresh(); };
  });
  body.querySelectorAll('[data-vd-delmod]').forEach((btn) => {
    btn.onclick = async () => {
      if (!(await ask('删除 Mod', '确定删除该 Mod 文件？'))) return;
      await call('mod_delete', btn.dataset.vdDelmod);
      vdRefresh();
    };
  });
  if (!vd.versions.length && !vd.loading && !vd.loaded) vdLoadVersions();
}
async function vdLoadVersions() {
  const vd = S.vd;
  if (!vd || !vd.mc) { if (vd) vd.loaded = true; return; }
  vd.loading = true;
  vd.loaded = false;
  try {
    const res = await call('loader_versions', vd.kind, vd.mc);
    vd.versions = res.versions || [];
  } catch (_) { vd.versions = []; }
  vd.loading = false;
  vd.loaded = true;
  if (S.vd === vd) renderVd();
}

/* ---------- 右键菜单 ---------- */
function showContextMenu(x, y, items) {
  hideContextMenu();
  const menu = document.createElement('div');
  menu.id = 'ctxMenu';
  menu.className = 'ctx-menu';
  menu.innerHTML = items.map((item, index) => '<button data-idx="' + index + '">' + esc(item.label) + '</button>').join('');
  document.body.appendChild(menu);
  const width = menu.offsetWidth;
  const height = menu.offsetHeight;
  menu.style.left = Math.min(x, window.innerWidth - width - 6) + 'px';
  menu.style.top = Math.min(y, window.innerHeight - height - 6) + 'px';
  menu.querySelectorAll('button').forEach((btn, index) => {
    btn.onclick = () => { hideContextMenu(); const item = items[index]; if (item && item.run) item.run(); };
  });
  // 菜单内部的按下事件不能冒泡到 document，否则菜单会在 click 派发前被移除，表现为“点了没反应”
  menu.addEventListener('pointerdown', (event) => event.stopPropagation());
  menu.addEventListener('contextmenu', (event) => event.preventDefault());
  setTimeout(() => document.addEventListener('pointerdown', hideContextMenu, { once: true }), 0);
}
function hideContextMenu() {
  const menu = document.getElementById('ctxMenu');
  if (menu) menu.remove();
}
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') hideContextMenu(); });

function renderJavaTab() {
  const body = h('dlBody');
  if (!body) return;
  const dists = S.javaTab.dists || null;
  if (!dists) { loadJavaDists(); }
  const dist = (dists || []).find((d) => d.id === S.javaTab.dist) || (dists || [])[0] || null;
  const majors = (dist && dist.majors) || [8, 17, 21];
  const inst = S.javaTab.scanned || (S.data.java || {});
  const installerOk = !!(dist && dist.installer_supported);
  if (!installerOk && S.javaTab.mode !== 'zip') S.javaTab.mode = 'zip';
  const modeLabel = S.javaTab.mode === 'zip' ? 'ZIP 安装' : (S.javaTab.mode === 'msi' ? 'MSI 安装' : 'EXE 安装');
  body.innerHTML =
    '<div class="split">' +
      '<div class="panel card">' +
        '<div class="card-head"><h2>下载并安装 Java</h2><span class="hint">ZIP 自动解压到 data/runtime 并写入 PATH</span></div>' +
        '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
          '<div class="chips">' +
            '<button class="chip' + (S.javaTab.mode === 'zip' ? ' active' : '') + '" data-act="java-mode" data-arg="zip">ZIP 便携版</button>' +
            '<button class="chip' + (S.javaTab.mode === 'msi' ? ' active' : '') + (installerOk ? '' : ' disabled') + '" data-act="java-mode" data-arg="msi">MSI 安装程序</button>' +
            '<button class="chip' + (S.javaTab.mode === 'exe' ? ' active' : '') + (installerOk ? '' : ' disabled') + '" data-act="java-mode" data-arg="exe">EXE 安装程序</button>' +
          '</div>' +
          '<div class="grid3">' +
            '<div class="field"><label>发行版</label><select id="javaDist">' + (dists || []).map((d) =>
              '<option value="' + esc(d.id) + '"' + (d.id === S.javaTab.dist ? ' selected' : '') + '>' + esc(d.name) + '</option>'
            ).join('') + '</select></div>' +
            '<div class="field"><label>主版本</label><select id="javaMajor">' + majors.map((m) =>
              '<option value="' + m + '"' + (m === S.javaTab.major ? ' selected' : '') + '>' + m + '</option>'
            ).join('') + '</select></div>' +
            '<div class="field"><label>类型</label><select id="javaPkg">' +
              '<option value="jdk"' + (S.javaTab.pkg === 'jdk' ? ' selected' : '') + '>JDK</option>' +
              '<option value="jre"' + (S.javaTab.pkg === 'jre' ? ' selected' : '') + '>JRE</option>' +
            '</select></div>' +
          '</div>' +
          '<div class="toolbar"><button class="btn primary" data-act="java-fetch">获取版本列表</button>' +
            '<button class="btn ghost" data-act="java-rescan">重新扫描已装 Java</button></div>' +
          '<div class="hint">' + esc((dist && dist.description) || '选择发行版与主版本后点击获取版本列表。') +
            (installerOk ? '' : ' 当前发行版没有官方 EXE/MSI 安装包，请使用 ZIP 便携版。') + '</div>' +
          '<div class="list" id="javaVersionList">' + (S.javaTab.loading ? '<div class="loading"><span class="spinner"></span>正在查询版本…</div>' :
            (S.javaTab.versions.length ? S.javaTab.versions.map((row) =>
              '<div class="row"><div class="row-main"><b>' + esc(row.version || row.name || '') + '</b><small>' +
              esc(row.package || '') + ' · ' + esc(row.kind ? row.kind.toUpperCase() + ' · ' : '') + esc(fmtSize(row.size)) + (row.latest ? ' · 最新' : '') + (row.note ? ' · ' + esc(row.note) : '') + '</small></div>' +
              '<div class="row-actions">' +
                '<button class="btn small primary" data-act="java-install" data-arg="' + A(Object.assign({ major: S.javaTab.major, package: S.javaTab.pkg, mode: S.javaTab.mode }, row)) + '">' + modeLabel + '</button>' +
              '</div></div>'
            ).join('') : '<div class="empty">' + (S.javaTab.mode === 'exe'
              ? '没有可用的 EXE：Temurin / Azul / Corretto 在 Windows 只提供 MSI；EXE 会回退到 Oracle 官方直链，仅部分版本（如 25/27）可用，可改用 MSI 或 ZIP。'
              : '点击「获取版本列表」查询可用安装包。') + '</div>')) + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="panel card">' +
        '<div class="card-head"><h2>已检测的 Java</h2><span class="hint">' + (inst.count || 0) + ' 个</span></div>' +
        '<div class="card-body scroll"><div class="list">' +
          (((inst.list) || []).length ? inst.list.map((j) =>
            '<button class="row" data-act="java-pick" data-arg="' + A(j.path) + '" style="cursor:pointer">' +
              '<div class="row-main"><b>Java ' + esc(j.major) + ' · ' + esc(j.vendor || '') + '</b><small class="mono">' + esc(j.path) + '</small></div>' +
              (inst.path === j.path ? '<span class="tag accent">当前</span>' : '') +
            '</button>'
          ).join('') : '<div class="empty">没有检测到 Java，可下载 ZIP 版自动安装。</div>') +
        '</div>' +
        '<div class="hint" style="margin-top:8px">点击条目设为启动器默认 Java；启动时会按版本自动匹配更合适的运行时。</div></div>' +
      '</div>' +
    '</div>';
  h('javaDist').addEventListener('change', (event) => {
    S.javaTab.dist = event.target.value; S.javaTab.versions = [];
    const d = (S.javaTab.dists || []).find((x) => x.id === S.javaTab.dist);
    if (d && d.majors.includes(S.javaTab.major) === false) S.javaTab.major = d.majors[0];
    if (d && !d.installer_supported) S.javaTab.mode = 'zip';
    S.javaTab.versions = [];
    renderJavaTab();
  });
  h('javaMajor').addEventListener('change', (event) => { S.javaTab.major = Number(event.target.value); S.javaTab.versions = []; });
  h('javaPkg').addEventListener('change', (event) => { S.javaTab.pkg = event.target.value; S.javaTab.versions = []; });
}
async function loadJavaDists() {
  try {
    S.javaTab.dists = await call('java_distributions', );
    if (S.page === 'download' && S.dlTab === 'java') renderJavaTab();
  } catch (err) { toast(err.message || err, 'error'); }
}
ACT['java-mode'] = async (mode) => {
  if (mode !== 'zip') {
    const dist = (S.javaTab.dists || []).find((d) => d.id === S.javaTab.dist);
    if (!dist || !dist.installer_supported) { toast('该发行版没有官方安装程序，请使用 ZIP 便携版', 'error'); return; }
  }
  S.javaTab.mode = mode;
  S.javaTab.versions = [];
  renderJavaTab();
};
ACT['java-fetch'] = async () => {
  S.javaTab.loading = true; renderJavaTab();
  try {
    const res = await call('java_versions', S.javaTab.dist, S.javaTab.major, S.javaTab.pkg, S.javaTab.mode);
    S.javaTab.loading = false;
    S.javaTab.versions = res.versions || [];
    if (!res.ok) toast(res.message, 'error');
    renderJavaTab();
  } catch (err) { S.javaTab.loading = false; renderJavaTab(); toast(err.message || err, 'error'); }
};
ACT['java-rescan'] = async () => {
  try {
    const res = await call('java_scan', true);
    S.javaTab.scanned = res.java;
    S.data.java = res.java;
    renderJavaTab();
    toast('已重新扫描 Java', 'ok');
  } catch (err) { toast(err.message || err, 'error'); }
};
ACT['java-install'] = async (asset) => {
  const mode = asset.mode === 'zip' ? 'zip' : (asset.mode === 'msi' || asset.mode === 'exe' ? asset.mode : 'installer');
  const res = await call('java_install', asset, mode);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (!res.ok) return;
  const job = await watchJob(res.job);
  if (job && job.state === 'ok') {
    toast('Java 安装完成，正在刷新列表', 'ok');
    await ACT['java-rescan']();
  } else {
    toast((job && (job.error || job.stage)) || 'Java 安装未完成', 'error');
  }
};
ACT['java-pick'] = async (path) => {
  const res = await call('java_select', path);
  if (res.ok) { S.javaTab.scanned = res.java; S.data.java = res.java; renderJavaTab(); toast('已设为默认 Java', 'ok'); }
};

function renderBedrockTab() {
  const body = h('dlBody');
  if (!body) return;
  const catalog = S.bedrock.catalog;
  if (!catalog) { loadBedrockCatalog(); body.innerHTML = '<div class="loading"><span class="spinner"></span>读取基岩版目录…</div>'; return; }
  const channels = [['release', '历史版本'], ['store', '商店正式版'], ['store-preview', '商店预览版']];
  const releases = (catalog.releases || []).filter((row) =>
    S.bedrock.channel === 'release' ? row.channel === 'release' : S.bedrock.channel === 'store' ? row.channel === 'release' : row.channel === 'preview'
  );
  const installed = catalog.installed;
  body.innerHTML =
    '<div class="split">' +
      '<div class="panel card">' +
        '<div class="card-head"><h2>基岩版目录</h2><button class="btn small ghost" data-act="bedrock-local">本地 Appx 安装</button></div>' +
        '<div class="card-body" style="display:flex;flex-direction:column;gap:10px;min-height:0">' +
          '<div class="chips">' + channels.map(([id, name]) =>
            '<button class="chip' + (S.bedrock.channel === id ? ' active' : '') + '" data-act="bedrock-channel" data-arg="' + id + '">' + name + '</button>'
          ).join('') + '</div>' +
          '<div class="bedrock-note">mcappx 的历史版本页面对程序化访问有 Cloudflare 拦截，这里提供「打开官方页面下载 + 本地 Appx 安装」的兜底；商店直链可能失效。</div>' +
          (S.bedrock.channel === 'release' ?
            '<div class="list scroll" style="max-height:calc(100vh - 330px)">' + (releases.length ? releases.map((row) =>
              '<div class="row"><div class="row-main"><b>' + esc(row.version) + '</b><small>' + esc(row.major || '') + ' · ' + esc(row.date || '') + ' · ' + esc((row.archs || []).join('/')) + '</small></div>' +
              '<div class="row-actions"><button class="btn small ghost" data-act="bedrock-page" data-arg="' + A(row.url || '') + '">打开页面</button></div></div>'
            ).join('') : '<div class="empty">目录里没有该通道版本。</div>') + '</div>'
            :
            '<div class="toolbar"><button class="btn primary" data-act="bedrock-store-fetch">获取商店直链</button><span class="hint">' + (S.bedrock.entries.length ? '共 ' + S.bedrock.entries.length + ' 个包' : '未获取') + '</span></div>' +
            '<div class="list scroll" style="max-height:calc(100vh - 360px)">' + (S.bedrock.entries.length ? S.bedrock.entries.map((entry, index) =>
              '<div class="row"><div class="row-main"><b>' + esc(entry.version || entry.name || '') + '</b><small>' + esc((entry.arch || 'x64')) + ' · ' + esc(fmtSize(entry.size)) + '</small></div>' +
              '<div class="row-actions"><button class="btn small primary" data-act="bedrock-store-install" data-arg="' + A(index) + '">下载并安装</button></div></div>'
            ).join('') : '<div class="empty">' + (S.bedrock.storeError || '点击获取商店直链。') + '</div>') + '</div>') +
        '</div>' +
      '</div>' +
      '<div class="panel card">' +
        '<div class="card-head"><h2>已安装基岩版</h2></div>' +
        '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
          (installed ? '<div class="row"><div class="row-main"><b>' + esc(installed.name || installed.package_id || 'Minecraft') + '</b><small>版本 ' + esc(installed.version || '') + '</small></div>' + (catalog.running ? '<span class="tag accent">运行中</span>' : '') + '</div>' : '<div class="empty">尚未安装基岩版。</div>') +
          '<div class="toolbar"><button class="btn primary" data-act="bedrock-launch"' + (installed ? '' : ' disabled') + '>启动基岩版</button>' +
          '<button class="btn ghost" data-act="bedrock-uninstall"' + (installed ? '' : ' disabled') + '>卸载</button></div>' +
          '<div class="hint">基岩版与 Java 版共用下载中心与启动入口，条目带专属标注。</div>' +
          '<div class="card-head" style="padding:6px 0"><h2>版本总览</h2></div>' +
          '<div class="list scroll" style="max-height:180px">' + (catalog.majors || []).slice(0, 12).map((major) =>
            '<div class="row"><div class="row-main"><b>' + esc(major.name || major.id) + '</b><small>' + esc(major.id) + '</small></div>' +
            '<button class="btn small ghost" data-act="bedrock-page" data-arg="' + A(major.url || '') + '">页面</button></div>'
          ).join('') + '</div>' +
        '</div>' +
      '</div>' +
    '</div>';
}
async function loadBedrockCatalog() {
  try {
    const data = await call('bedrock_catalog');
    S.bedrock.catalog = data;
    if (S.page === 'download' && S.dlTab === 'bedrock') renderBedrockTab();
  } catch (err) { toast(err.message || err, 'error'); }
}
ACT['bedrock-channel'] = (id) => { S.bedrock.channel = id; renderBedrockTab(); };
ACT['bedrock-local'] = async () => {
  const res = await call('bedrock_install_local');
  toast(res.message || (res.ok ? '开始安装' : '已取消'), res.ok ? 'ok' : 'error');
};
ACT['bedrock-page'] = async (url) => { if (url) await call('bedrock_open_page', url); };
ACT['bedrock-store-fetch'] = async () => {
  const ring = S.bedrock.channel === 'store-preview' ? 'Preview' : 'Retail';
  S.bedrock.storeError = '正在获取商店目录…';
  renderBedrockTab();
  const res = await call('bedrock_fetch_store', ring);
  S.bedrock.entries = res.entries || [];
  S.bedrock.storeError = res.ok ? '' : res.message;
  renderBedrockTab();
};
ACT['bedrock-store-install'] = async (index) => {
  const entry = (S.bedrock.entries || [])[index];
  if (!entry) return;
  const res = await call('bedrock_install_store', entry);
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['bedrock-launch'] = async () => { const res = await call('bedrock_launch'); toast(res.message, res.ok ? 'ok' : 'error'); };
ACT['bedrock-uninstall'] = async () => {
  if (!(await ask('卸载基岩版', '将从系统移除已安装的 Minecraft 基岩版包，确定继续？'))) return;
  const res = await call('bedrock_uninstall'); toast(res.message, res.ok ? 'ok' : 'error'); loadBedrockCatalog();
};

/* ---------- 任务列表 ---------- */
function taskHtml(task) {
  const state = task.state;
  const stateText = { running: '进行中', paused: '已暂停', ok: '完成', failed: '失败', cancelled: '已取消' }[state] || state;
  const cls = state === 'failed' ? ' failed' : state === 'paused' ? ' paused' : '';
  return '<div class="task-item" data-task="' + esc(task.id) + '">' +
    '<div class="task-head"><b>' + esc(task.title) + '</b><span class="tag ' + (state === 'failed' ? 'danger' : state === 'paused' ? 'warn' : state === 'ok' ? 'accent' : '') + '">' + stateText + '</span></div>' +
    '<div class="hint">' + esc(task.stage) + (task.detail ? ' · ' + esc(task.detail) : '') + '</div>' +
    '<div class="progress' + cls + '"><i style="width:' + Math.min(100, Math.max(0, task.percent)) + '%"></i></div>' +
    '<div class="toolbar" style="margin-top:4px">' +
      '<span class="hint">' + task.percent.toFixed(0) + '% · ' + esc(fmtTime(task.created)) + '</span><span class="spacer"></span>' +
      (state === 'running' ? '<button class="btn small ghost" data-act="task-pause" data-arg="' + A(task.id) + '">暂停</button>' : '') +
      (state === 'paused' ? '<button class="btn small ghost" data-act="task-resume" data-arg="' + A(task.id) + '">继续</button>' : '') +
      ((state === 'running' || state === 'paused') ? '<button class="btn small danger" data-act="task-cancel" data-arg="' + A(task.id) + '">取消</button>' : '') +
      ((state === 'failed' || state === 'cancelled') ? '<button class="btn small" data-act="task-retry" data-arg="' + A(task.id) + '">重试</button>' : '') +
      (task.error ? '<button class="btn small ghost" data-act="task-log" data-arg="' + A(task.id) + '">错误详情</button>' : '') +
      '<button class="btn small ghost" data-act="task-delete" data-arg="' + A(task.id) + '">删除任务</button>' +
    '</div>' +
  '</div>';
}
function renderTaskList() {
  const body = h('dlBody');
  if (!body) return;
  const tasks = S.tasks || [];
  body.innerHTML =
    '<div class="toolbar" style="margin-bottom:10px"><span class="hint">下载与安装全部多线程执行，可暂停/继续/取消；未完成任务保留 .part 断点。</span><span class="spacer"></span>' +
    '<button class="btn small ghost" data-act="open-path" data-arg="downloads">' + esc(T('打开下载文件夹')) + '</button>' +
    '<button class="btn small ghost" data-act="task-clear">清理已完成</button></div>' +
    '<div class="list">' + (tasks.length ? tasks.map(taskHtml).join('') : '<div class="empty" style="padding:26px 16px">' +
      '<div style="font-size:14px;font-weight:600;margin-bottom:6px">下一步：下载一个游戏版本</div>' +
      '安装原版 / 加载器 / Java / 基岩版，或把整合包拖进窗口，任务会实时显示在这里，可暂停与断点续传。' +
      '<div class="row" style="justify-content:center;gap:8px;margin-top:12px;flex-wrap:wrap">' +
        '<button class="btn small primary" data-act="guide" data-arg="download">下一步：下载游戏版本</button>' +
        '<button class="btn small" data-act="nav" data-arg="modpack">安装整合包</button>' +
        '<button class="btn small ghost" data-act="nav" data-arg="wiki">看安装教程</button>' +
      '</div></div>') + '</div>';
}
ACT['task-pause'] = async (id) => { await call('task_pause', id); await pollTasks(); };
ACT['task-resume'] = async (id) => { await call('task_resume', id); await pollTasks(); };
ACT['task-cancel'] = async (id) => { await call('task_cancel', id); await pollTasks(); toast('已请求取消', 'ok'); };
ACT['task-retry'] = async (id) => {
  const res = await call('task_retry', id);
  toast(res.message || (res.ok ? '已重新开始任务' : '任务不存在'), res.ok ? 'ok' : 'error');
  await pollTasks();
};
ACT['task-clear'] = async () => { await call('task_clear'); await pollTasks(); renderTaskList(); };
ACT['task-delete'] = async (id) => {
  const task = (S.tasks || []).find((t) => t.id === id);
  if (task && (task.state === 'running' || task.state === 'paused')) {
    if (!(await ask('删除任务', '该任务仍在进行，删除会先取消它。确定继续？'))) return;
  }
  const res = await call('task_delete', id);
  if (!res.ok) toast(res.message || '删除失败', 'error');
  await pollTasks();
  renderTaskList();
};
ACT['task-log'] = (id) => {
  const task = (S.tasks || []).find((t) => t.id === id);
  if (!task) return;
  openSheet('任务日志 · ' + task.title, '<div class="log-box">' + esc((task.logs || []).join('\n') || '没有日志') + '</div>');
};

/* ---------- 内容中心 ---------- */
const CONTENT_KINDS = [['mod', 'Mod'], ['modpack', '整合包'], ['resourcepack', '资源包'], ['texturepack', '材质包'], ['shader', '光影包']];
const SOURCES = [['modrinth', 'Modrinth'], ['curseforge', 'CurseForge']];
const CONTENT_LOADERS = [['', '全部加载器'], ['fabric', 'Fabric'], ['forge', 'Forge'], ['neoforge', 'NeoForge'], ['quilt', 'Quilt']];
let contentCats = null;

function loadContentCats() {
  if (contentCats) return Promise.resolve(contentCats);
  return call('content_categories').then((res) => {
    contentCats = (res && res.ok && res.categories) || [];
    return contentCats;
  }).catch(() => { contentCats = []; return contentCats; });
}

function renderContent() {
  const c = S.content;
  const needsLoader = c.kind === 'mod' || c.kind === 'modpack';
  const cats = contentCats || [];
  h('view').innerHTML =
    '<div class="page">' +
      '<div class="card" style="flex:none;margin-bottom:10px"><div class="card-body" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">' +
        '<b style="font-size:14px">半透明毛玻璃 UI 材质包</b>' +
        '<span class="hint">按钮 / 面板 / 快捷栏统一磨砂 · 自动识别版本 · 重复执行自动替换旧包</span>' +
        '<span class="spacer"></span>' +
        '<select id="contentUiVersion" style="width:150px"><option value="">选择已安装版本…</option></select>' +
        '<button class="btn small primary" data-act="content-ui-pack">一键安装并替换</button>' +
        '<button class="btn small ghost" data-act="content-ui-pack-all">全部版本一键替换</button>' +
      '</div></div>' +
      '<div class="toolbar">' +
        '<div class="tabs">' + CONTENT_KINDS.map(([id, name]) =>
          '<button class="tab' + (c.kind === id ? ' active' : '') + '" data-act="content-kind" data-arg="' + id + '">' + name + '</button>'
        ).join('') + '</div>' +
        '<span class="spacer"></span>' +
        '<select id="contentSource" style="width:120px">' + SOURCES.map(([id, name]) =>
          '<option value="' + id + '"' + (c.source === id ? ' selected' : '') + '>' + name + '</option>'
        ).join('') + '</select>' +
        (needsLoader ? '<select id="contentLoader" style="width:130px">' + CONTENT_LOADERS.map(([id, name]) =>
          '<option value="' + id + '"' + (c.loader === id ? ' selected' : '') + '>' + name + '</option>'
        ).join('') + '</select>' : '') +
        '<input type="text" id="contentGv" placeholder="游戏版本（可选）" style="width:130px" value="' + esc(c.gv) + '" />' +
        '<input type="text" id="contentQ" placeholder="搜索名称 / 关键词" style="width:220px" value="' + esc(c.q) + '" />' +
        '<button class="btn primary" data-act="content-search">搜索</button>' +
      '</div>' +
      '<div class="chips" style="padding:2px 0 6px;overflow-x:auto;flex-wrap:nowrap">' +
        '<button class="chip' + (c.category === '' ? ' active' : '') + '" data-act="content-cat" data-arg="">全部</button>' +
        cats.map((item) => '<button class="chip' + (c.category === item.key ? ' active' : '') + '" data-act="content-cat" data-arg="' + A(item.key) + '">' + esc(item.label) + '</button>').join('') +
      '</div>' +
      '<div class="hint" style="margin:2px 0 8px">安装目标：' + esc(contentTarget()) + ' · 会自动安装必需的前置 Mod · 资源包 / 材质包 / 光影包互不混用</div>' +
      '<div class="scroll" id="contentBody" style="flex:1;min-height:0">' +
        (c.loading ? '<div class="loading"><span class="spinner"></span>正在搜索…</div>' :
          (c.projects.length ? '<div class="projects">' + c.projects.map(projectCard).join('') + '</div>' +
            (c.projects.length >= 20 ? '<div class="toolbar" style="justify-content:center;margin-top:12px"><button class="btn ghost" data-act="content-more">加载更多</button></div>' : '')
          : '<div class="empty" style="padding:26px 16px">' +
              (c.searched
                ? '<div style="font-size:14px;font-weight:600;margin-bottom:6px">没有找到结果，下一步可以这样试</div>' +
                  '换个关键词或切换来源；放宽 Minecraft 版本 / 加载器筛选；或者直接去整合包中心挑一个现成整合包。' +
                  '<div class="row" style="justify-content:center;gap:8px;margin-top:12px;flex-wrap:wrap">' +
                    '<button class="btn small" data-act="guide" data-arg="content">下一步：怎么搜</button>' +
                    '<button class="btn small" data-act="nav" data-arg="modpack">去整合包中心</button>' +
                    '<button class="btn small ghost" data-act="nav" data-arg="wiki">看下载教程</button>' +
                  '</div>'
                : '<div style="font-size:14px;font-weight:600;margin-bottom:6px">下一步：搜索或直接拖入文件</div>' +
                  '在上方输入关键词搜索 Mod、整合包、资源包、材质包、光影包；也可以把 .jar 或 mods 文件夹拖进窗口，按版本导入。' +
                  '<div class="row" style="justify-content:center;gap:8px;margin-top:12px;flex-wrap:wrap">' +
                    '<button class="btn small primary" data-act="guide" data-arg="content">下一步：搜索或拖入</button>' +
                    '<button class="btn small" data-act="nav" data-arg="modpack">浏览整合包</button>' +
                    '<button class="btn small ghost" data-act="nav" data-arg="wiki">看内容下载教程</button>' +
                  '</div>') +
            '</div>')) +
      '</div>' +
    '</div>';
  h('contentQ').addEventListener('keydown', (event) => { if (event.key === 'Enter') { S.content.q = event.target.value.trim(); doContentSearch(false); } });
  h('contentGv').addEventListener('change', (event) => { S.content.gv = event.target.value.trim(); });
  h('contentSource').addEventListener('change', (event) => { S.content.source = event.target.value; });
  if (h('contentLoader')) h('contentLoader').addEventListener('change', (event) => {
    S.content.loader = event.target.value;
    doContentSearch(false);
  });
  if (contentCats === null) loadContentCats().then(() => { if (S.page === 'content') renderContent(); });
  fillContentUiVersions();
  if (!c.searched && !c.loading) doContentSearch(false);
}

async function fillContentUiVersions() {
  const select = h('contentUiVersion');
  if (!select) return;
  try {
    const res = await call('ui_pack_versions');
    if (!res || !res.ok) return;
    const list = res.versions || [];
    select.innerHTML = '<option value="">选择已安装版本…</option>' +
      list.map((version) => '<option value="' + esc(version) + '">' + esc(version) + '</option>').join('');
    const preferred = list.includes(S.selectedVersion) ? S.selectedVersion : (list[0] || '');
    if (preferred) select.value = preferred;
  } catch (_) { /* 版本列表失败不影响内容搜索 */ }
}
function contentTarget() {
  const instance = selectedInstance();
  return instance ? '实例「' + instance.name + '」' : '当前游戏目录';
}
function projectCard(project) {
  return '<div class="project" data-act="project-open" data-arg="' + A(project) + '">' +
    (project.icon ? '<img src="' + esc(project.icon) + '" alt="" loading="lazy" />' : '<img alt="" />') +
    '<div class="p-main"><b>' + esc(project.title) + '</b><small>' + esc(project.description || '') + '</small>' +
    '<div class="p-tags"><span class="tag">' + esc(project.type_label || '') + '</span>' +
    '<span class="tag">' + esc(project.downloads ? project.downloads.toLocaleString() : '') + '</span>' +
    (project.author ? '<span class="tag">' + esc(project.author) + '</span>' : '') + '</div>' +
    '</div></div>';
}
ACT['content-kind'] = (kind) => {
  S.content.kind = kind;
  S.content.offset = 0;
  // 用途分类只对 Mod / 整合包有意义，切到其它类型时复位，避免出现空结果
  if (kind !== 'mod' && kind !== 'modpack') { S.content.category = ''; S.content.loader = ''; }
  doContentSearch(false);
};
ACT['content-cat'] = (key) => {
  S.content.category = key || '';
  S.content.offset = 0;
  doContentSearch(false);
};
ACT['content-search'] = () => {
  const q = h('contentQ');
  S.content.q = q ? q.value.trim() : '';
  S.content.gv = h('contentGv') ? h('contentGv').value.trim() : '';
  if (h('contentLoader')) S.content.loader = h('contentLoader').value;
  doContentSearch(false);
};
ACT['content-more'] = () => doContentSearch(true);
async function doContentSearch(append) {
  const c = S.content;
  c.loading = true;
  c.searched = true;
  c.offset = append ? c.projects.length : 0;
  renderContent();
  try {
    const res = await call('search_content', c.source, c.kind, c.q, c.gv, c.loader, c.offset, c.category);
    c.loading = false;
    if (!res.ok) { toast(res.message, 'error'); c.projects = append ? c.projects : []; }
    else {
      c.projects = append ? c.projects.concat(res.projects) : res.projects;
    }
  } catch (err) { c.loading = false; toast(err.message || err, 'error'); }
  if (S.page === 'content') renderContent();
}
ACT['project-open'] = (project) => openProject(project);

let projCtx = null;

function projHero(extra) {
  const p = projCtx.project;
  return '<div class="detail-hero">' +
    (p.icon ? '<img src="' + esc(p.icon) + '" alt="" />' : '') +
    '<div class="d-main"><b>' + esc(p.title) + '</b><small>' + esc(p.type_label || '') +
    (p.author ? ' · ' + esc(p.author) : '') +
    (p.downloads ? ' · ' + esc(p.downloads.toLocaleString()) + ' 次下载' : '') + '</small>' +
    '<div class="p-tags">' + (p.categories || []).map((cat) => '<span class="tag">' + esc(cat) + '</span>').join('') + '</div></div>' +
    '</div>' +
    '<div class="detail-desc">' + esc(p.description || '') + '</div>' + (extra || '');
}

function projChannelTag(channel) {
  const key = String(channel || '').toLowerCase();
  if (key === 'release' || key === '1' || key === '') return '<span class="tag accent">稳定版</span>';
  if (key === 'beta' || key === '2') return '<span class="tag warn">测试版</span>';
  if (key === 'alpha' || key === '3') return '<span class="tag warn">Alpha 测试</span>';
  return '<span class="tag">' + esc(channel) + '</span>';
}

function projChannelRank(version) {
  const key = String(version.channel || '').toLowerCase();
  return (key === 'release' || key === '1' || key === '') ? 0 : 1;
}

function setProjFoot(html) {
  h('sheetFoot').innerHTML = html || '<button class="btn ghost" id="projPage">打开项目主页</button>';
  const pageBtn = h('projPage');
  if (pageBtn) pageBtn.onclick = () => projCtx && projCtx.project.page && call('open_url', projCtx.project.page);
}

async function openProject(project) {
  projCtx = { project, mcVersions: [], versions: [], selected: 0, mc: '' };
  openSheet(project.title, '<div class="loading"><span class="spinner"></span>正在读取支持的 Minecraft 版本…</div>');
  setProjFoot();
  let res;
  try { res = await call('content_project_versions', project.source, project.id); }
  catch (err) { res = { ok: false, message: err.message, versions: [] }; }
  if (!projCtx || projCtx.project !== project) return;
  const values = (res && res.ok && res.versions) || [];
  projCtx.mcVersions = values;
  if (values.length) renderProjChooser();
  else await loadProjFiles('', res && res.message);
}

function renderProjChooser() {
  const ctx = projCtx;
  if (!ctx) return;
  h('sheetBody').innerHTML = projHero() +
    '<div class="hint" style="margin-top:12px">该 Mod 支持 <b>' + ctx.mcVersions.length + '</b> 个 Minecraft 版本。先选择游戏版本，再加载该版本可用的 Jar 文件。</div>' +
    '<div class="chips" style="flex-wrap:wrap;margin-top:10px">' +
    ctx.mcVersions.map((mc) => '<button class="chip" data-act="proj-mc" data-arg="' + A(mc) + '">' + esc(mc) + '</button>').join('') +
    '</div>';
  setProjFoot();
}

async function loadProjFiles(mcVersion, errorMessage) {
  const ctx = projCtx;
  if (!ctx) return;
  ctx.mc = mcVersion || '';
  ctx.versions = [];
  h('sheetBody').innerHTML = projHero() +
    '<div class="hint" style="margin-top:10px">游戏版本：<b>' + esc(mcVersion || '全部（未筛选）') + '</b></div>' +
    '<div class="loading"><span class="spinner"></span>正在加载可用文件…</div>';
  setProjFoot('<button class="btn ghost" id="projPage">打开项目主页</button>' +
    (ctx.mcVersions.length ? '<button class="btn ghost" id="projBack">← 重选游戏版本</button>' : ''));
  if (h('projBack')) h('projBack').onclick = () => renderProjChooser();
  let res;
  try { res = await call('content_versions', ctx.project.source, ctx.project.id, mcVersion || '', S.content.loader || ''); }
  catch (err) { res = { ok: false, message: err.message, versions: [] }; }
  if (!projCtx || projCtx !== ctx) return;
  if (!res.ok || !(res.versions || []).length) {
    h('sheetBody').innerHTML = projHero() +
      '<div class="empty">' + esc(errorMessage || (res && res.message) || '没有该游戏版本可用的文件，请重选版本。') + '</div>';
    if (h('projBack')) h('projBack').onclick = () => renderProjChooser();
    return;
  }
  ctx.versions = res.versions.slice().sort((a, b) => projChannelRank(a) - projChannelRank(b) ||
    String(b.date || '').localeCompare(String(a.date || '')));
  ctx.selected = 0;
  renderProjFiles();
}

function renderProjFiles() {
  const ctx = projCtx;
  if (!ctx) return;
  const versions = ctx.versions;
  const stable = versions.filter((v) => projChannelRank(v) === 0);
  const testing = versions.filter((v) => projChannelRank(v) > 0);
  const rowHtml = (version, index) =>
    '<div class="row" data-act="proj-pick" data-arg="' + index + '" style="align-items:flex-start">' +
      '<div class="row-main"><b class="mono">' + esc(version.filename || version.name) + '</b>' +
      '<small>' + esc(version.name || '') + ' · ' + esc((version.date || '').slice(0, 10)) + ' · ' + esc(fmtSize(version.size || 0)) + '</small></div>' +
      '<div class="p-tags">' + projChannelTag(version.channel) +
      (version.loaders || []).slice(0, 2).map((name) => '<span class="tag">' + esc(LOADER_CN[name] || name) + '</span>').join('') +
      (index === ctx.selected ? '<span class="tag accent">已选中</span>' : '') + '</div>' +
      '<div class="row-actions">' +
      '<button class="btn small ghost" data-act="proj-save" data-arg="' + index + '">另存为</button>' +
      '<button class="btn small primary" data-act="proj-install" data-arg="' + index + '">安装</button></div></div>';
  h('sheetBody').innerHTML = projHero() +
    '<div class="toolbar" style="margin-top:8px"><span class="hint">游戏版本：<b>' + esc(ctx.mc || '全部') + '</b> · 共 ' + versions.length + ' 个文件</span><span class="spacer"></span>' +
    (ctx.mcVersions.length ? '<button class="btn small ghost" data-act="proj-back-mc">重选游戏版本</button>' : '') + '</div>' +
    (stable.length ? '<div class="hint" style="margin:8px 0 4px">稳定版</div>' + stable.map((v) => rowHtml(v, versions.indexOf(v))).join('') : '') +
    (testing.length ? '<div class="hint" style="margin:12px 0 4px">测试版 / Alpha</div>' + testing.map((v) => rowHtml(v, versions.indexOf(v))).join('') : '') +
    '<div id="projDeps" style="margin-top:14px"></div>' +
    '<div class="hint" style="margin-top:10px">安装到：' + esc(contentTarget()) + ' · 安装时会自动补齐必需前置。</div>';
  setProjFoot('<button class="btn ghost" id="projPage">打开项目主页</button>' +
    (ctx.mcVersions.length ? '<button class="btn ghost" id="projBack">← 重选游戏版本</button>' : ''));
  if (h('projBack')) h('projBack').onclick = () => renderProjChooser();
  loadProjDeps(ctx.selected);
}

async function loadProjDeps(index) {
  const ctx = projCtx;
  const version = ctx && ctx.versions[index];
  const box = h('projDeps');
  if (!version || !box) return;
  const required = (version.required || []).filter((dep) => dep.project_id);
  const optional = (version.optional || []).filter((dep) => dep.project_id);
  if (!required.length && !optional.length) {
    box.innerHTML = '<b style="font-size:12px">前置依赖检查</b><div class="hint" style="margin-top:4px">该文件没有必需前置，可直接安装。</div>';
    return;
  }
  box.innerHTML = '<b style="font-size:12px">前置依赖检查</b><div class="loading" style="margin-top:4px"><span class="spinner"></span>正在检查前置…</div>';
  let res;
  try { res = await call('content_dependencies', ctx.project.source, required.map((dep) => dep.project_id)); }
  catch (err) { res = { ok: false, message: err.message, projects: [] }; }
  if (!projCtx || projCtx !== ctx) return;
  const names = {};
  (res.projects || []).forEach((project) => { names[project.id] = project; });
  const rows = required.map((dep) => {
    const project = names[dep.project_id];
    return '<div class="dep" data-act="open-dep" data-arg="' + A({ source: ctx.project.source, id: dep.project_id }) + '">' +
      '<span class="tag warn">必需</span><b>' + esc(project ? project.title : dep.project_id) + '</b>' +
      '<span class="hint">' + (project ? esc(project.type_label || '点击查看') : '点击查看 / 安装') + '</span></div>';
  }).join('');
  box.innerHTML = '<b style="font-size:12px">前置依赖检查</b>' +
    '<div class="hint" style="margin:4px 0">需要 ' + required.length + ' 个必需前置，安装时会自动补齐。' +
    (res.ok ? '' : '（部分名称解析失败：' + esc(res.message) + '）') + '</div>' +
    '<div class="dep-list">' + rows + '</div>' +
    (optional.length ? '<div class="hint">另有 ' + optional.length + ' 个可选前置</div>' : '');
}

ACT['proj-mc'] = (mc) => loadProjFiles(mc);
ACT['proj-back-mc'] = () => renderProjChooser();
ACT['proj-pick'] = (index) => {
  if (!projCtx) return;
  projCtx.selected = Number(index) || 0;
  renderProjFiles();
};
ACT['proj-save'] = async (index) => {
  const ctx = projCtx;
  const version = ctx && ctx.versions[Number(index)];
  if (!version) return;
  const result = await call('save_content_as', ctx.project.source, ctx.project.id, version.id, ctx.project.type, version.filename || '');
  if (!result.ok) { if (result.message) toast(result.message, 'error'); return; }
  toast(result.message, 'ok');
  S.dlTab = 'tasks';
};
ACT['proj-install'] = async (index, node) => {
  const ctx = projCtx;
  const version = ctx && ctx.versions[Number(index)];
  if (!version) return;
  if (node) node.disabled = true;
  if (ctx.project.type === 'modpack') {
    await openModpackInstallSheet(ctx, version);
    if (node) node.disabled = false;
    return;
  }
  const instance = selectedInstance();
  const result = await call('install_content', ctx.project.source, ctx.project.id, version.id, ctx.project.type, instance ? instance.id : '');
  if (!result.ok) { if (node) node.disabled = false; return toast(result.message, 'error'); }
  toast(result.message, 'ok');
  closeSheet();
  S.dlTab = 'tasks';
};

async function openModpackInstallSheet(ctx, version) {
  let versions = [];
  try {
    const res = await call('ui_pack_versions');
    if (res && res.ok) versions = res.installed || [];
  } catch (_) { versions = []; }
  const canAttach = versions.length > 0;
  openSheet('安装整合包 · ' + ctx.project.title,
    '<div class="detail-desc">' + esc(ctx.project.description || '') + '</div>' +
    '<div class="section" style="padding:10px 12px;border-radius:10px;margin-top:10px;background:rgba(255,255,255,.05)">' +
      '<h3 style="margin:0 0 6px">安装方式</h3>' +
      '<label class="hint" style="display:flex;align-items:flex-start;gap:8px;margin-bottom:6px">' +
        '<input type="radio" name="mpMode" value="new" checked /> <span><b>下载全新版本安装</b><br/>自动下载整合包要求的原版与加载器，创建独立实例，和现有整合包互不影响。</span></label>' +
      '<label class="hint" style="display:flex;align-items:flex-start;gap:8px">' +
        '<input type="radio" name="mpMode" value="attach"' + (canAttach ? '' : ' disabled') + ' /> <span><b>附加到已有版本</b><br/>' +
        (canAttach ? '把整合包内容直接写进下面选中的版本，适合补装或覆盖。' : '当前还没有已安装的游戏版本，无法附加。') + '</span></label>' +
    '</div>' +
    '<div class="field-row" style="margin-top:10px"><span class="hint" style="flex:none">已有版本</span>' +
      '<select id="mpTarget" style="flex:1" disabled><option value="">' +
        (canAttach ? '请选择版本…' : '没有已安装版本') + '</option>' +
        versions.map((id) => '<option value="' + esc(id) + '">' + esc(id) + '</option>').join('') +
      '</select></div>' +
    '<div class="hint" style="margin-top:8px">文件：' + esc(version.filename || version.name || '') +
      (version.size ? ' · ' + esc(fmtSize(version.size)) : '') + '</div>',
    '<button class="btn ghost" id="sheetCancel">取消</button>' +
    '<button class="btn primary" id="mpGo">开始安装</button>');
  const modes = h('sheetBody').querySelectorAll('input[name="mpMode"]');
  const syncMode = () => {
    const select = h('mpTarget');
    const mode = Array.from(modes).find((item) => item.checked);
    if (select) select.disabled = !(mode && mode.value === 'attach');
  };
  modes.forEach((item) => item.addEventListener('change', syncMode));
  h('mpGo').onclick = async () => {
    const modeNode = Array.from(modes).find((item) => item.checked);
    const mode = modeNode ? modeNode.value : 'new';
    const target = h('mpTarget') ? h('mpTarget').value : '';
    if (mode === 'attach' && !target) return toast('请选择要附加的已有版本', 'error');
    closeSheet();
    const result = await call('install_content', ctx.project.source, ctx.project.id, version.id,
      'modpack', '', mode, target);
    if (!result.ok) return toast(result.message, 'error');
    toast(result.message || '已加入安装队列', 'ok');
    S.dlTab = 'tasks';
    watchJob(result.job).then(async (job) => {
      if (job && job.state === 'ok') toast('整合包安装完成', 'ok');
      else if (job && job.state === 'failed') toast(job.error || '整合包安装失败', 'error');
      await refreshBootstrap();
      pollTasks();
    });
  };
}
ACT['open-dep'] = async (payload) => {
  try {
    const res = await call('search_by_ids', payload.source, [payload.id]);
    if (res.ok && res.projects.length) openProject(res.projects[0]);
    else toast(res.message || '找不到这个前置项目', 'error');
  } catch (err) { toast(err.message || err, 'error'); }
};

/* ---------- 实例管理 ---------- */
function renderInstances() {
  if (!S.data) return;
  const instances = S.data.instances || [];
  const dirs = S.data.game_dirs || [];
  const versions = S.data.versions || [];
  const instance = selectedInstance();
  h('view').innerHTML =
    '<div class="page flow" style="gap:12px">' +
      '<div class="grid2" style="flex:none">' +
        '<div class="card"><div class="card-head"><h2>当前实例</h2><span class="hint">' + esc(S.data.active_game_dir || 'default') + '</span></div>' +
          '<div class="card-body">' +
            (instance ? '<div class="row"><div class="row-main"><b>' + esc(instance.name) + '</b><small class="mono">' + esc(instance.game_dir) + ' · ' + esc(instance.version_id || '未指定版本') + '</small></div></div>' : '<div class="empty">当前使用默认目录，未选择实例。</div>') +
            '<div class="toolbar" style="margin-top:10px"><button class="btn small ghost" data-act="open-path" data-arg="instance">打开目录</button>' +
            '<button class="btn small ghost" data-act="open-path" data-arg="saves">打开存档</button>' +
            '<button class="btn small ghost" data-act="open-path" data-arg="mods">打开 Mods</button>' +
            '<button class="btn small ghost" data-act="export-script">导出启动脚本</button>' +
            '<button class="btn small ghost" data-act="export-modpack">导出整合包</button>' +
            '<button class="btn small ghost" data-act="instance-repair">修复实例</button>' +
            '<button class="btn small ghost" data-act="batch-launch">多选启动</button></div>' +
          '</div></div>' +
        '<div class="card"><div class="card-head"><h2>全局隔离模式</h2></div>' +
          '<div class="card-body"><div class="chips">' + Object.entries(S.data.isolation_options || {}).map(([key, label]) =>
            '<button class="chip' + (key === S.data.isolation_mode ? ' active' : '') + '" data-act="set-isolation" data-arg="' + key + '">' + esc(label) + '</button>'
          ).join('') + '</div><div class="hint" style="margin-top:8px">Mod 隔离 / 存档隔离 / 全部隔离与经典版一致，切换后立即生效。</div></div></div>' +
      '</div>' +
      '<div class="card" style="flex:none"><div class="card-head"><h2>实例列表</h2><div class="head-actions">' +
        '<button class="btn small ghost" data-act="new-instance">新建实例</button>' +
        '<button class="btn small ghost" data-act="open-path" data-arg="game">游戏目录</button></div></div>' +
        '<div class="card-body scroll" style="max-height:320px"><div class="list">' +
          (instances.length ? instances.map((item) =>
            '<div class="row"><div class="row-main"><b>' + esc(item.name) + (item.selected ? ' <span class="tag accent">当前</span>' : '') + '</b>' +
            '<small class="mono">' + esc(item.game_dir) + '</small>' +
            '<small>' + esc(item.version_id || '') + (item.loader ? ' · ' + esc(item.loader) : '') + '</small></div>' +
            '<div class="row-actions">' +
              '<button class="btn small ' + (item.selected ? '' : 'primary') + '" data-act="instance-select" data-arg="' + A(item.id) + '">选中</button>' +
              '<button class="btn small ghost" data-act="instance-open" data-arg="' + A(item.game_dir) + '">目录</button>' +
              (item.id === 'default' ? '' : '<button class="btn small ghost" data-act="instance-move" data-arg="' + A(item.id + '|-1') + '" title="上移">▲</button>' +
              '<button class="btn small ghost" data-act="instance-move" data-arg="' + A(item.id + '|1') + '" title="下移">▼</button>') +
              (item.id === 'default' ? '' : '<button class="btn small danger" data-act="instance-remove" data-arg="' + A(item.id) + '">移除</button>') +
            '</div></div>'
          ).join('') : '<div class="empty">还没有实例。新建实例可把不同版本、整合包和存档彻底分开。</div>') +
        '</div></div></div>' +
      '<div class="card" style="flex:none"><div class="card-head"><h2>数据目录分区</h2><div class="head-actions"><button class="btn small ghost" data-act="dir-add">添加目录</button></div></div>' +
        '<div class="card-body"><div class="list">' + dirs.map((dir) =>
          '<div class="row"><div class="row-main"><b>' + esc(dir.name) + (dir.id === S.data.active_game_dir ? ' <span class="tag accent">使用中</span>' : '') + '</b><small class="mono">' + esc(dir.path) + '</small></div>' +
          '<div class="row-actions"><button class="btn small ghost" data-act="dir-select" data-arg="' + A(dir.id) + '">切换</button>' +
          (dir.id === 'default' ? '' : '<button class="btn small danger" data-act="dir-remove" data-arg="' + A(dir.id) + '">删除</button>') + '</div></div>'
        ).join('') + '</div></div></div>' +
      '<div class="card" style="flex:none"><div class="card-head"><h2>版本设置</h2><div class="head-actions">' +
        '<select id="vsVersion" style="max-width:190px">' +
          (versions.length ? versions.map((v) => '<option value="' + esc(v.id) + '"' +
            ((instance && instance.version_id === v.id) || (!instance && versions[0] && versions[0].id === v.id) ? ' selected' : '') + '>' +
            esc(v.id) + (v.loader ? ' · ' + esc(v.loader) : '') + '</option>').join('') : '<option value="">无版本</option>') +
        '</select><button class="btn small ghost" data-act="open-path" data-arg="mods">打开 Mods</button></div></div>' +
        '<div class="card-body" id="vsBody"><div class="hint">加载中…</div></div></div>' +
      '<div class="card" style="flex:none"><div class="card-head"><h2>内容文件管理</h2><div class="head-actions">' +
        '<button class="chip' + ((S.packTab || 'mods') === 'mods' ? ' active' : '') + '" data-act="pack-tab" data-arg="mods">Mods</button>' +
        '<button class="chip' + (S.packTab === 'resourcepacks' ? ' active' : '') + '" data-act="pack-tab" data-arg="resourcepacks">资源包</button>' +
        '<button class="chip' + (S.packTab === 'shaderpacks' ? ' active' : '') + '" data-act="pack-tab" data-arg="shaderpacks">光影包</button>' +
        '<button class="btn small ghost" data-act="pack-open" data-arg="' + (S.packTab || 'mods') + '">打开目录</button></div></div>' +
        '<div class="card-body" id="modsBody"><div class="hint">加载中…</div></div></div>' +
    '</div>';
  if (versions.length === 0) toast('还没有安装游戏版本，新建实例后请先到下载中心安装', 'error');
  const versionSelect = h('vsVersion');
  if (versionSelect) versionSelect.addEventListener('change', () => loadVersionSettings(versionSelect.value));
  loadVersionSettings();
  loadMods();
}
ACT['export-modpack'] = async () => {
  const res = await call('export_modpack', '');
  if (!res.ok) return toast(res.message || '导出失败', 'error');
  toast(res.message || '正在导出整合包…', 'ok');
};
ACT['instance-move'] = async (payload) => {
  const text = String(payload || '');
  const [id, deltaText] = text.split('|');
  if (!id) return;
  const res = await call('instance_move', id, parseInt(deltaText, 10) || 0);
  if (!res.ok) return toast(res.message || '移动失败', 'error');
  S.data.instances = res.instances;
  renderInstances();
};
ACT['export-script'] = async () => {
  const version = S.selectedVersion;
  if (!version) return toast('请先选择版本', 'error');
  const instance = selectedInstance();
  const res = await call('export_script', version, instance ? instance.id : '');
  if (!res.ok) { if (res.message !== '已取消') toast(res.message || '导出失败', 'error'); return; }
  toast(res.message, 'ok');
};
ACT['instance-repair'] = async () => {
  const instance = selectedInstance();
  if (!instance) return toast('当前没有可修复的实例', 'error');
  const res = await call('repair_instance', instance.id);
  toast(res.message || (res.ok ? '开始修复实例' : '修复失败'), res.ok ? 'ok' : 'error');
  if (res.ok) S.dlTab = 'tasks';
};
ACT['batch-launch'] = async () => {
  const versions = S.data.versions || [];
  if (!versions.length) return toast('没有可启动的版本', 'error');
  openSheet('多选启动',
    '<div class="hint" style="margin-bottom:8px">按顺序启动：上一个游戏退出后自动启动下一个，任一个失败会跳过并继续。</div>' +
    '<div class="list" style="max-height:320px;overflow:auto">' +
      versions.map((v, index) =>
        '<label class="row" style="gap:10px"><input type="checkbox" class="batch-ver" value="' + esc(v.id) + '"' + (index === 0 ? ' checked' : '') + ' /><span>' + esc(v.id) + (v.loader ? ' · ' + esc(v.loader) : '') + '</span></label>'
      ).join('') +
    '</div>',
    '<button class="btn ghost" id="batchCancel">取消</button><button class="btn primary" id="batchRun">开始启动</button>');
  h('batchCancel').onclick = closeSheet;
  h('batchRun').onclick = async () => {
    const ids = Array.from(document.querySelectorAll('.batch-ver:checked')).map((el) => el.value);
    if (!ids.length) return toast('请至少选择一个版本', 'error');
    closeSheet();
    const instance = selectedInstance();
    const res = await call('launch_batch', ids, instance ? instance.id : '');
    if (!res.ok) return toast(res.message, 'error');
    toast('已加入批量启动队列', 'ok');
    S.dlTab = 'tasks';
    setPage('download');
  };
};
ACT['new-instance'] = async () => {
  const versions = S.data.versions || [];
  if (!versions.length) return toast('请先安装至少一个游戏版本', 'error');
  openSheet('新建实例',
    '<div class="field"><label>实例名称</label><input type="text" id="instName" placeholder="例如：生存服 / 整合包测试" /></div>' +
    '<div class="field" style="margin-top:10px"><label>对应版本</label><select id="instVersion">' +
      versions.map((v) => '<option value="' + esc(v.id) + '">' + esc(v.id) + (v.loader ? ' · ' + esc(v.loader) : '') + '</option>').join('') +
    '</select></div>' +
    '<div class="field" style="margin-top:10px"><label>实例目录（留空则自动创建）</label><div class="field-row"><input type="text" id="instDir" placeholder="自动：data/instances/名称" style="flex:1" /><button class="btn small ghost" id="instPick">选择</button></div></div>',
    '<button class="btn ghost" id="instCancel">取消</button><button class="btn primary" id="instCreate">创建</button>');
  h('instPick').onclick = async () => {
    const res = await call('pick_folder', 'instance');
    if (res.ok) h('instDir').value = res.path;
  };
  h('instCancel').onclick = closeSheet;
  h('instCreate').onclick = async () => {
    const name = h('instName').value.trim();
    if (!name) return toast('请输入实例名称', 'error');
    const res = await call('add_instance', name, h('instVersion').value, h('instDir').value.trim());
    if (!res.ok) return toast(res.message, 'error');
    closeSheet();
    await refreshBootstrap();
  };
};
ACT['instance-select'] = async (id) => {
  const res = await call('select_instance', id);
  if (res.ok) { S.data.instances = res.instances; await reloadVersions(true); renderInstances(); toast('已切换实例', 'ok'); }
};
ACT['instance-open'] = async (path) => {
  if (!path) return;
  const res = await call('open_path', 'game');
  if (!res.ok) toast(res.message, 'error');
};
ACT['instance-remove'] = async (id) => {
  if (!(await ask('移除实例', '只从启动器列表移除，不会删除磁盘文件。确定继续？'))) return;
  const res = await call('remove_instance', id);
  if (res.ok) { S.data.instances = res.instances; renderInstances(); toast('已移除', 'ok'); }
};
const PRIORITIES = { high: '高', above_normal: '高于正常', normal: '正常', below_normal: '低于正常', low: '低' };
async function loadVersionSettings(versionId) {
  const body = h('vsBody');
  if (!body) return;
  const instance = selectedInstance();
  const id = versionId || (h('vsVersion') && h('vsVersion').value) ||
    (instance && instance.version_id) || ((S.data.versions || [])[0] || {}).id || '';
  if (!id) { body.innerHTML = '<div class="empty">还没有安装任何版本，无法编辑版本设置。</div>'; return; }
  // 切换版本时前一次请求可能后返回，用请求标记丢弃过期结果，避免显示错版本
  S.vsLoading = id;
  const res = await call('version_settings', id);
  if (S.vsLoading !== id) return;
  if (!res.ok) { body.innerHTML = '<div class="empty">' + esc(res.message) + '</div>'; return; }
  const st = res.setting || {};
  body.innerHTML =
    '<div class="form-grid">' +
      '<div class="field"><label>最大内存（MB，0 跟随全局 ' + esc(String(res.global_memory || '')) + '）</label>' +
        '<input type="number" id="vsMemory" min="0" step="256" value="' + esc(String(st.memory_mb || 0)) + '" /></div>' +
      '<div class="field"><label>版本隔离</label><select id="vsIsolation"><option value="">跟随全局</option>' +
        Object.entries(res.isolation_options || {}).map(([key, label]) =>
          '<option value="' + esc(key) + '"' + (key === st.isolation ? ' selected' : '') + '>' + esc(label) + '</option>').join('') +
      '</select></div>' +
      '<div class="field"><label>进程优先级</label><select id="vsPriority"><option value="">跟随全局</option>' +
        Object.entries(PRIORITIES).map(([key, label]) =>
          '<option value="' + key + '"' + (key === st.priority ? ' selected' : '') + '>' + label + '</option>').join('') +
      '</select></div>' +
      '<div class="field"><label>游戏窗口标题</label><input type="text" id="vsTitle" placeholder="留空跟随全局" value="' + esc(st.window_title || '') + '" /></div>' +
      '<div class="field"><label>额外 JVM 参数</label><input type="text" id="vsJvm" placeholder="-XX:+UseG1GC 等" value="' + esc(st.extra_jvm_args || '') + '" /></div>' +
      '<div class="field"><label>额外游戏参数</label><input type="text" id="vsArgs" placeholder="--width 1280 等" value="' + esc(st.extra_game_args || '') + '" /></div>' +
      '<div class="field"><label>自动连接服务器</label><div class="field-row">' +
        '<input type="text" id="vsServer" placeholder="主机或 IP" value="' + esc(st.server || '') + '" style="flex:1" />' +
        '<input type="number" id="vsPort" min="1" max="65535" value="' + esc(String(st.port || 25565)) + '" style="width:96px" />' +
      '</div></div>' +
      '<div class="field"><label>启动后自动进服</label><div class="chips">' +
        '<button class="chip' + (st.auto_connect ? ' active' : '') + '" data-act="vs-auto" data-arg="1">开启</button>' +
        '<button class="chip' + (st.auto_connect ? '' : ' active') + '" data-act="vs-auto" data-arg="0">关闭</button>' +
      '</div></div>' +
    '</div>' +
    '<div class="toolbar" style="margin-top:10px"><button class="btn primary" data-act="vs-save">保存版本设置</button>' +
    '<span class="hint">这些设置只作用于当前选择的版本；0 / 留空表示跟随全局。</span></div>';
  S.vsAuto = !!st.auto_connect;
}
ACT['vs-auto'] = (value) => {
  S.vsAuto = value === '1' || value === 1;
  document.querySelectorAll('[data-act="vs-auto"]').forEach((chip) => {
    chip.classList.toggle('active', String(S.vsAuto) === (chip.dataset.arg === '1' ? 'true' : 'false'));
  });
};
ACT['vs-save'] = async () => {
  const versionId = (h('vsVersion') && h('vsVersion').value) || '';
  if (!versionId) return toast('请先选择版本', 'error');
  const payload = {
    memory_mb: Number((h('vsMemory') && h('vsMemory').value) || 0),
    isolation: (h('vsIsolation') && h('vsIsolation').value) || '',
    priority: (h('vsPriority') && h('vsPriority').value) || '',
    window_title: (h('vsTitle') && h('vsTitle').value.trim()) || '',
    extra_jvm_args: (h('vsJvm') && h('vsJvm').value.trim()) || '',
    extra_game_args: (h('vsArgs') && h('vsArgs').value.trim()) || '',
    server: (h('vsServer') && h('vsServer').value.trim()) || '',
    port: Number((h('vsPort') && h('vsPort').value) || 25565),
    auto_connect: !!S.vsAuto,
  };
  const res = await call('version_settings_save', versionId, payload);
  toast(res.message || (res.ok ? '已保存' : '保存失败'), res.ok ? 'ok' : 'error');
};
async function loadMods() {
  const body = h('modsBody');
  if (!body) return;
  const kind = S.packTab || 'mods';
  const res = kind === 'mods' ? await call('mods_list') : await call('packs_list', kind);
  const items = res.items || [];
  const label = kind === 'mods' ? 'Mod' : (kind === 'resourcepacks' ? '资源包' : '光影包');
  body.innerHTML =
    '<div class="hint mono" style="margin-bottom:6px">' + esc(res.dir || '') + '</div>' +
    (items.length
      ? '<div class="list scroll" style="max-height:240px">' + items.map((item) =>
        '<div class="row"><div class="row-main"><b>' + esc(item.name) + '</b><small>' + fmtSize(item.size) + ' · ' +
        (item.enabled ? '<span class="tag ok">启用</span>' : '<span class="tag">禁用</span>') + '</small></div>' +
        '<div class="row-actions"><button class="btn small ghost" data-act="' + (kind === 'mods' ? 'mod-toggle' : 'pack-toggle') + '" data-arg="' + A(item.path) + '">' +
        (item.enabled ? '禁用' : '启用') + '</button>' +
        '<button class="btn small danger" data-act="' + (kind === 'mods' ? 'mod-delete' : 'pack-delete') + '" data-arg="' + A(item.path) + '">删除</button></div></div>'
      ).join('') + '</div>'
      : '<div class="empty">' + esc(res.dir || '') + ' 还没有' + label + '。可在内容中心安装，或直接把文件放进该目录。</div>');
}
ACT['pack-tab'] = (kind) => { S.packTab = kind; renderInstances(); };
ACT['pack-toggle'] = async (path) => {
  const res = await call('pack_toggle', path);
  toast(res.ok ? (res.enabled ? '已启用' : '已禁用') : res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadMods();
};
ACT['pack-delete'] = async (path) => {
  if (!(await ask('删除文件', '将直接从磁盘删除，确定继续？'))) return;
  const res = await call('pack_delete', path);
  toast(res.ok ? '已删除' : res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadMods();
};
ACT['pack-open'] = async (kind) => {
  const res = await call('pack_open', kind || 'mods');
  if (!res.ok) toast(res.message || '打开失败', 'error');
};
ACT['mod-toggle'] = async (path) => {
  const res = await call('mod_toggle', path);
  toast(res.ok ? (res.enabled ? '已启用' : '已禁用') : res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadMods();
};
ACT['mod-delete'] = async (path) => {
  if (!(await ask('删除 Mod', '将直接从磁盘删除该 Mod 文件，确定继续？'))) return;
  const res = await call('mod_delete', path);
  toast(res.ok ? '已删除' : res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadMods();
};

ACT['dir-add'] = async () => {
  const res = await call('add_game_dir', '', '');
  if (!res.ok) return toast(res.message, 'error');
  await refreshBootstrap();
  if (S.page === 'settings') refreshPage();
  const count = (res.versions || []).length;
  toast(count ? '已切换目录，检测到 ' + count + ' 个已安装版本' : (res.message || '已添加数据目录'), 'ok');
};
ACT['dir-select'] = async (id) => {
  const res = await call('select_game_dir', id);
  if (!res.ok) return toast(res.message, 'error');
  S.data.active_game_dir = id;
  await refreshBootstrap();
  toast('已切换数据目录', 'ok');
};
ACT['dir-remove'] = async (id) => {
  const res = await call('remove_game_dir', id);
  if (!res.ok) return toast(res.message, 'error');
  await refreshBootstrap();
};
ACT['set-isolation'] = async (mode) => {
  await saveSetting('isolation_mode', mode);
  await refreshBootstrap();
  if (S.settingsData) S.settingsData.isolation_mode = mode;
  if (S.page === 'settings' && S.settingsData) fillSettingsBody(S.settingsData);
};
async function refreshBootstrap() {
  const data = await call('bootstrap');
  S.data = data;
  applyPalette(data.palette);
  if (S.page === 'instances') renderInstances();
  else if (S.page === 'home') renderHome();
  else if (S.page === 'account') renderAccount();
}

/* ---------- 版本设置（完整照搬经典版 ControlPage） ---------- */
const CTRL_TABS = [
  ['overview', '概览'],
  ['game', '游戏设置'],
  ['mods', '模组管理'],
  ['resourcepacks', '资源包管理'],
  ['shaderpacks', '光影包管理'],
  ['modpack', '整合包'],
  ['manage', '版本管理'],
];
function ctrlState() {
  if (!S.control) S.control = { tab: 'overview', instanceId: '', versionId: '' };
  return S.control;
}
function ctrlInstances() { return (S.data && S.data.instances) || []; }
function ctrlCurrentInstance() {
  const st = ctrlState();
  const list = ctrlInstances();
  return list.find((item) => item.id === st.instanceId) || list.find((item) => item.selected) || list[0] || null;
}
function ctrlCurrentVersion() {
  const st = ctrlState();
  const inst = ctrlCurrentInstance();
  return st.versionId || (inst && inst.version_id) || S.selectedVersion || (((S.data && S.data.versions) || [])[0] || {}).id || '';
}
function ctrlGameDir() {
  const inst = ctrlCurrentInstance();
  return (inst && inst.game_dir) || (S.data && S.data.active_game_dir) || '';
}
function ctrlInfo(label, value) {
  return '<div class="field"><label>' + label + '</label><div class="hint mono" style="word-break:break-all">' + (value ? esc(String(value)) : '—') + '</div></div>';
}
function ctrlField(label, control) {
  return '<div class="field"><label>' + label + '</label>' + control + '</div>';
}
function ctrlOptions(items, selected) {
  return (items || []).map(([value, label]) =>
    '<option value="' + A(String(value)) + '"' + (String(selected) === String(value) ? ' selected' : '') + '>' + esc(label) + '</option>'
  ).join('');
}
function ctrlHealthTag(health) {
  const level = (health && health.level) || 'yellow';
  const color = level === 'green' ? '#3ddc97' : level === 'yellow' ? '#ffc857' : '#ff6b6b';
  return '<span class="tag" style="color:' + color + ';border-color:' + color + '">' + esc((health && health.label) || '未知') + '</span>';
}
function renderControl() {
  if (!S.data) return;
  const st = ctrlState();
  const current = ctrlCurrentInstance();
  if (current) st.instanceId = st.instanceId || current.id;
  const instances = ctrlInstances();
  const versions = (S.data && S.data.versions) || [];
  const versionId = ctrlCurrentVersion();
  if (!st.versionId) st.versionId = versionId;
  const instanceOptions = instances.map((item) =>
    '<option value="' + A(item.id) + '"' + (item.id === st.instanceId ? ' selected' : '') + '>' + esc(item.name || item.id) + (item.version_id ? ' · ' + esc(item.version_id) : '') + '</option>'
  ).join('');
  const versionOptions = versions.map((item) =>
    '<option value="' + A(item.id) + '"' + (item.id === versionId ? ' selected' : '') + '>' + esc(item.id) + (item.type ? ' · ' + esc(item.type) : '') + '</option>'
  ).join('');
  const tabs = CTRL_TABS.map(([id, label]) =>
    '<button class="chip' + (st.tab === id ? ' active' : '') + '" data-act="ctrl-tab" data-arg="' + id + '">' + label + '</button>'
  ).join('');
  h('view').innerHTML =
    '<div class="page flow">' +
      '<div class="card"><div class="card-head"><h2>版本设置</h2><span class="hint">与经典版「版本设置」一一对应：7 个页面 + 快捷工具</span></div>' +
        '<div class="card-body"><div class="form-grid">' +
          ctrlField('实例', '<select id="ctrlInstance">' + (instanceOptions || '<option value="default">默认实例</option>') + '</select>') +
          ctrlField('版本', '<select id="ctrlVersion">' + (versionOptions || '<option value="">暂无已安装版本</option>') + '</select>') +
          ctrlInfo('实例目录', ctrlGameDir()) +
        '</div>' +
        '<div class="chips" style="margin-top:10px">' + tabs + '</div>' +
        '<div class="toolbar" style="margin-top:8px">' +
          '<button class="btn small ghost" data-act="ctrl-open-dir">打开游戏目录</button>' +
          '<button class="btn small ghost" data-act="ctrl-refresh">刷新</button>' +
          '<span class="hint">切换实例会同步切换启动器当前实例，内容中心安装也会落到该实例。</span>' +
        '</div></div></div>' +
      '<div id="ctrlBody"><div class="loading"><span class="spinner"></span>正在读取版本设置…</div></div>' +
    '</div>';
  if (h('ctrlInstance')) {
    h('ctrlInstance').onchange = async (event) => {
      st.instanceId = G(event.target.value);
      const inst = instances.find((item) => item.id === st.instanceId);
      st.versionId = (inst && inst.version_id) || st.versionId;
      try {
        const res = await call('select_instance', st.instanceId);
        if (res && res.ok) {
          S.data.instances = res.instances || S.data.instances;
          S.data.versions = res.versions || S.data.versions;
          S.data.selected_instance = st.instanceId;
          S.selectedVersion = st.versionId;
        }
      } catch (err) { toast(err.message || err, 'error'); }
      renderControl();
    };
  }
  if (h('ctrlVersion')) {
    h('ctrlVersion').onchange = (event) => {
      st.versionId = G(event.target.value);
      S.selectedVersion = st.versionId;
      ctrlLoad();
    };
  }
  ctrlLoad();
}
async function ctrlLoad() {
  const box = h('ctrlBody');
  if (!box) return;
  const st = ctrlState();
  const versionId = ctrlCurrentVersion();
  const instanceId = st.instanceId || ((ctrlCurrentInstance() || {}).id || '');
  box.innerHTML = '<div class="loading"><span class="spinner"></span>正在读取…</div>';
  try {
    if (st.tab === 'overview') await ctrlRenderOverview(box, versionId);
    else if (st.tab === 'game') await ctrlRenderGame(box, versionId);
    else if (st.tab === 'mods') await ctrlRenderMods(box, versionId);
    else if (st.tab === 'resourcepacks') await ctrlRenderPacks(box, versionId, 'resourcepacks');
    else if (st.tab === 'shaderpacks') await ctrlRenderPacks(box, versionId, 'shaderpacks');
    else if (st.tab === 'modpack') ctrlRenderModpack(box, instanceId, versionId);
    else await ctrlRenderManage(box, instanceId, versionId);
  } catch (err) {
    box.innerHTML = '<div class="card"><div class="card-body"><div class="empty">读取失败：' + esc(err.message || err) + '</div></div></div>';
  }
}
async function ctrlRenderOverview(box, versionId) {
  if (!versionId) { box.innerHTML = '<div class="card"><div class="card-body"><div class="empty">还没有已安装版本，请先在「下载安装」安装一个版本。</div></div></div>'; return; }
  const info = await call('version_info', versionId, ctrlState().instanceId || '');
  if (!info.ok) { box.innerHTML = '<div class="card"><div class="card-body"><div class="empty">' + esc(info.message || '读取失败') + '</div></div></div>'; return; }
  const health = info.health || {};
  const issues = (health.issues || []).map((item) => '<li>' + esc(item) + '</li>').join('');
  box.innerHTML =
    '<div class="grid2">' +
      '<div class="card"><div class="card-head"><h2>版本信息</h2>' + ctrlHealthTag(health) + '</div><div class="card-body">' +
        '<div class="form-grid">' +
          ctrlInfo('版本 ID', info.version) +
          ctrlInfo('版本类型', info.type) +
          ctrlInfo('加载器', info.loader || '原版 / 未识别') +
          ctrlInfo('继承版本', info.inherits || '—') +
          ctrlInfo('所需 Java', 'Java ' + (info.java_major || '?')) +
          ctrlInfo('已匹配 Java', info.java && info.java.version ? ('Java ' + info.java.version + (info.java.path ? ' · ' + info.java.path : '')) : '自动选择') +
          ctrlInfo('版本目录', info.path) +
          ctrlInfo('客户端 Jar', info.jar || '继承自父版本 / 不存在') +
          ctrlInfo('最后修改', info.modified ? fmtTime(info.modified) : '—') +
        '</div>' +
        '<div class="toolbar" style="margin-top:12px">' +
          '<button class="btn primary" data-act="ctrl-launch">启动游戏</button>' +
          '<button class="btn ghost" data-act="ctrl-open-versiondir">打开版本文件夹</button>' +
          '<button class="btn danger" data-act="ctrl-delete-version">删除此版本</button>' +
        '</div>' +
        '<div class="hint" style="margin-top:8px">删除会同时移除绑定该版本的实例记录；存档、截图等实例目录内容不会被删除。</div>' +
      '</div></div>' +
      '<div class="card"><div class="card-head"><h2>健康检查</h2></div><div class="card-body">' +
        (issues ? '<ul class="hint" style="margin:0 0 10px 18px">' + issues + '</ul>' : '<div class="hint">未发现缺失文件。</div>') +
        '<div class="toolbar"><button class="btn small ghost" data-act="ctrl-repair">修复版本</button>' +
        '<button class="btn small ghost" data-act="ctrl-deps">依赖补全</button></div>' +
      '</div></div>' +
    '</div>' +
    ctrlToolsCard();
}
async function ctrlRenderGame(box, versionId) {
  if (!versionId) { box.innerHTML = '<div class="card"><div class="card-body"><div class="empty">请先选择版本。</div></div></div>'; return; }
  let vs = { setting: {}, isolation_options: {}, global_memory: 4096 };
  let g = {};
  try { vs = await call('version_settings', versionId); } catch (err) { vs = { setting: {} }; }
  try { g = await call('settings_get'); } catch (err) { g = {}; }
  let javas = [];
  try {
    const scanned = await call('java_scan', false);
    javas = (scanned && scanned.java && scanned.java.list) || (scanned && scanned.list) || [];
  } catch (err) { javas = (S.data && S.data.java && S.data.java.list) || []; }
  if (!javas.length && S.data && S.data.java) javas = S.data.java.list || [];
  const setting = vs.setting || {};
  const javaOptions = '<option value="">自动选择（推荐）</option>' + javas.map((item) =>
    '<option value="' + A(item.path) + '"' + (g.java_path === item.path ? ' selected' : '') + '>Java ' + esc(item.major || item.version || '?') + ' · ' + esc(item.version || '') + (item.vendor ? ' · ' + esc(item.vendor) : '') + '</option>'
  ).join('');
  const isolationOptions = '<option value="">跟随全局</option>' + Object.entries(vs.isolation_options || {}).map(([key, label]) =>
    '<option value="' + A(key) + '"' + (String(setting.isolation || '') === String(key) ? ' selected' : '') + '>' + esc(label) + '</option>'
  ).join('');
  const priorities = [['', '跟随全局'], ['high', '高'], ['above_normal', '高于普通'], ['below_normal', '低于普通'], ['low', '低']];
  const priorityOptions = priorities.map(([value, label]) =>
    '<option value="' + value + '"' + (String(setting.priority || '') === value ? ' selected' : '') + '>' + label + '</option>'
  ).join('');
  const afterOptions = Object.entries(g.after_options || {}).map(([key, label]) =>
    '<option value="' + A(key) + '"' + (String(g.after_launch_action || '') === String(key) ? ' selected' : '') + '>' + esc(label) + '</option>'
  ).join('');
  box.innerHTML =
    '<div class="card"><div class="card-head"><h2>游戏设置（全局）</h2><span class="hint">对应经典版「游戏设置」页</span></div><div class="card-body">' +
      '<div class="form-grid">' +
        ctrlField('Java 运行时', '<select id="cgJava">' + javaOptions + '</select>') +
        ctrlField('最大内存（MB）', '<input id="cgMemory" type="number" min="512" max="65536" step="512" value="' + Number(g.memory_mb || 4096) + '" />') +
        ctrlField('窗口宽度', '<input id="cgWidth" type="number" min="640" max="7680" value="' + Number(g.width || 1280) + '" />') +
        ctrlField('窗口高度', '<input id="cgHeight" type="number" min="480" max="4320" value="' + Number(g.height || 720) + '" />') +
      '</div>' +
      ctrlField('额外 JVM 参数（空格分隔）', '<input id="cgJvm" value="' + esc(g.extra_jvm_args || '') + '" placeholder="-XX:+UseG1GC" />') +
      ctrlField('额外游戏参数（空格分隔）', '<input id="cgGame" value="' + esc(g.extra_game_args || '') + '" placeholder="--width 1280 --height 720" />') +
      '<div class="toolbar" style="margin-top:10px">' +
        '<label class="hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="cgAuto"' + (g.auto_connect_enabled ? ' checked' : '') + ' /> 自动连接服务器</label>' +
        '<input id="cgServer" value="' + esc(g.auto_connect_server || '') + '" placeholder="服务器地址" style="max-width:240px" />' +
        '<input id="cgPort" type="number" min="1" max="65535" value="' + Number(g.auto_connect_port || 25565) + '" style="max-width:120px" />' +
        '<label class="hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="cgHide"' + (g.after_launch_action === 'hide' ? ' checked' : '') + ' /> 启动游戏后隐藏启动器</label>' +
      '</div>' +
      '<div class="toolbar" style="margin-top:12px"><button class="btn primary" data-act="ctrl-game-save">保存设置</button>' +
        '<span class="hint">当前最大内存 ' + Number(g.memory_mb || 4096) + ' MB；修改后对下一次启动生效。</span></div>' +
    '</div></div>' +
    '<div class="card" style="margin-top:12px"><div class="card-head"><h2>当前版本设置</h2><span class="hint">仅作用于 ' + esc(versionId) + '</span></div><div class="card-body">' +
      '<div class="form-grid">' +
        ctrlField('隔离策略', '<select id="cvIsolation">' + (isolationOptions || '<option value="">跟随全局</option>') + '</select>') +
        ctrlField('版本内存（MB，0 = 跟随全局）', '<input id="cvMemory" type="number" min="0" max="65536" step="512" value="' + Number(setting.memory_mb || 0) + '" />') +
        ctrlField('启动优先级', '<select id="cvPriority">' + priorityOptions + '</select>') +
        ctrlField('窗口标题', '<input id="cvTitle" value="' + esc(setting.window_title || '') + '" placeholder="留空使用默认标题" />') +
      '</div>' +
      '<div class="form-grid" style="margin-top:10px">' +
        ctrlField('额外 JVM 参数', '<input id="cvJvm" value="' + esc(setting.extra_jvm_args || '') + '" placeholder="留空跟随全局" />') +
        ctrlField('额外游戏参数', '<input id="cvGame" value="' + esc(setting.extra_game_args || '') + '" placeholder="留空跟随全局" />') +
      '</div>' +
      '<div class="toolbar" style="margin-top:10px">' +
        '<label class="hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="cvAuto"' + (setting.auto_connect ? ' checked' : '') + ' /> 自动连接服务器</label>' +
        '<input id="cvServer" value="' + esc(setting.server || '') + '" placeholder="服务器地址" style="max-width:240px" />' +
        '<input id="cvPort" type="number" min="1" max="65535" value="' + Number(setting.port || 25565) + '" style="max-width:120px" />' +
      '</div>' +
      '<div class="toolbar" style="margin-top:12px"><button class="btn primary" data-act="ctrl-vsetting-save">保存当前版本设置</button>' +
        '<span class="hint">版本内存与隔离策略会覆盖全局设置；留空/0 表示跟随全局。</span></div>' +
    '</div></div>';
}
async function ctrlRenderMods(box, versionId) {
  if (!versionId) { box.innerHTML = '<div class="card"><div class="card-body"><div class="empty">请先选择版本。</div></div></div>'; return; }
  const res = await call('mods_list', versionId, ctrlState().instanceId || '');
  let scan = { conflicts: [], missing: [] };
  try { scan = await call('mod_scan', versionId, ctrlState().instanceId || ''); } catch (err) { scan = { conflicts: [], missing: [] }; }
  const updates = ((S.control.updates || {}).items) || [];
  const updateMap = {};
  updates.forEach((item) => { updateMap[item.path] = item; });
  const items = res.items || [];
  const conflicts = (scan.conflicts || []).map((item) =>
    '<div class="hint" style="color:#ff9f6b">' + esc((item.type ? '[' + item.type + '] ' : '') + (item.modid || '') + (item.files && item.files.length ? ' · ' + item.files.join(', ') : '') + (item.detail ? ' · ' + item.detail : '')) + '</div>'
  ).join('');
  const rows = items.length ? items.map((item) => {
    const up = updateMap[item.path];
    return '<div class="row"><div class="row-main"><b>' + esc(item.name) + (up ? ' <span class="tag">可更新 → ' + esc(up.latest) + '</span>' : '') + '</b>' +
      '<small>' + fmtSize(item.size) + (item.enabled ? '' : ' · 已禁用') + '</small></div>' +
      '<div class="row-actions"><button class="btn small ghost" data-act="ctrl-mod-toggle" data-arg="' + A(item.path) + '">' + (item.enabled ? '禁用' : '启用') + '</button>' +
      '<button class="btn small danger" data-act="ctrl-mod-delete" data-arg="' + A(item.path) + '">删除</button></div></div>';
  }).join('') : '<div class="empty">mods 目录为空。可添加本地文件或从内容中心在线安装。</div>';
  box.innerHTML =
    '<div class="card"><div class="card-head"><h2>模组管理</h2><span class="hint">' + esc(versionId) + ' · ' + items.length + ' 个文件</span></div><div class="card-body">' +
      '<div class="hint mono" style="margin-bottom:8px">' + esc(res.dir || '') + '</div>' +
      '<div class="toolbar" style="margin-bottom:8px">' +
        '<button class="btn small" data-act="ctrl-content-add" data-arg="mods">添加文件</button>' +
        '<button class="btn small ghost" data-act="ctrl-pack-open" data-arg="mods">打开文件夹</button>' +
        '<button class="btn small ghost" data-act="ctrl-online" data-arg="mod">在线添加 Mod</button>' +
        '<button class="btn small ghost" data-act="ctrl-mod-check">检查更新</button>' +
        '<button class="btn small ghost" data-act="ctrl-mod-apply"' + (updates.length ? '' : ' disabled') + '>安装更新</button>' +
      '</div>' +
      (conflicts ? '<div class="card" style="margin-bottom:8px"><div class="card-body">' + conflicts + '</div></div>' : '') +
      '<div class="list">' + rows + '</div>' +
    '</div></div>' + ctrlToolsCard();
}
async function ctrlRenderPacks(box, versionId, kind) {
  if (!versionId) { box.innerHTML = '<div class="card"><div class="card-body"><div class="empty">请先选择版本。</div></div></div>'; return; }
  const res = await call('packs_list', kind, versionId, ctrlState().instanceId || '');
  const items = res.items || [];
  const isResource = kind === 'resourcepacks';
  const rows = items.length ? items.map((item, index) => {
    const order = isResource ? '<span class="tag">' + (index + 1) + '</span>' : (item.current ? '<span class="tag">当前</span>' : '');
    return '<div class="row"><div class="row-main"><b>' + order + ' ' + esc(item.name) + '</b><small>' + fmtSize(item.size) + (item.enabled ? '' : ' · 已禁用') + '</small></div>' +
      '<div class="row-actions">' +
        (isResource && item.enabled ? '<button class="btn small ghost" data-act="ctrl-pack-move" data-arg="' + A(item.path + '|-1') + '">上移</button>' +
          '<button class="btn small ghost" data-act="ctrl-pack-move" data-arg="' + A(item.path + '|1') + '">下移</button>' : '') +
        '<button class="btn small ghost" data-act="ctrl-pack-toggle" data-arg="' + A(item.path) + '">' + (item.enabled ? '禁用' : '启用') + '</button>' +
        '<button class="btn small danger" data-act="ctrl-pack-delete" data-arg="' + A(item.path) + '">删除</button>' +
      '</div></div>';
  }).join('') : '<div class="empty">' + (isResource ? 'resourcepacks' : 'shaderpacks') + ' 目录为空。</div>';
  box.innerHTML =
    '<div class="card"><div class="card-head"><h2>' + (isResource ? '资源包管理' : '光影包管理') + '</h2><span class="hint">' + esc(versionId) + ' · ' + items.length + ' 个文件</span></div><div class="card-body">' +
      '<div class="hint mono" style="margin-bottom:8px">' + esc(res.dir || '') + '</div>' +
      '<div class="toolbar" style="margin-bottom:8px">' +
        '<button class="btn small" data-act="ctrl-content-add" data-arg="' + kind + '">添加文件</button>' +
        '<button class="btn small ghost" data-act="ctrl-pack-open" data-arg="' + kind + '">打开文件夹</button>' +
        '<button class="btn small ghost" data-act="ctrl-online" data-arg="' + (isResource ? 'resourcepack' : 'shader') + '">在线添加' + (isResource ? '资源包' : '光影包') + '</button>' +
        '<button class="btn small ghost" data-act="ctrl-refresh">刷新</button>' +
      '</div>' +
      (isResource ? '<div class="hint" style="margin-bottom:8px">排序会写回 options.txt 的 resourcePacks 列表；被禁用的包保留在目录里但不参与加载。</div>' : '') +
      '<div class="list">' + rows + '</div>' +
    '</div></div>' + ctrlToolsCard();
}
function ctrlRenderModpack(box, instanceId, versionId) {
  box.innerHTML =
    '<div class="grid2">' +
      '<div class="card"><div class="card-head"><h2>导出整合包</h2></div><div class="card-body">' +
        '<div class="hint">把当前实例的 mods、config、resourcepacks、shaderpacks、options.txt 等打包为 .mikan，可分享或迁移到别的电脑。</div>' +
        '<div class="toolbar" style="margin-top:10px"><button class="btn primary" data-act="ctrl-modpack-export">导出为 .mikan</button></div>' +
      '</div></div>' +
      '<div class="card"><div class="card-head"><h2>导入整合包到当前版本</h2></div><div class="card-body">' +
        '<div class="hint">支持 .mikan、CurseForge（manifest.json + overrides）与 Modrinth（modrinth.index.json）压缩包。overrides / client-overrides 会自动去掉前缀写入实例目录；同名文件会被覆盖。</div>' +
        '<div class="hint" style="margin-top:6px">清单里的在线 Mod 不会自动下载，导入后可在「模组管理」或内容中心补齐。</div>' +
        '<div class="toolbar" style="margin-top:10px"><button class="btn primary" data-act="ctrl-modpack-import">选择整合包导入</button></div>' +
      '</div></div>' +
    '</div>' +
    '<div class="card" style="margin-top:12px"><div class="card-head"><h2>当前实例</h2></div><div class="card-body"><div class="form-grid">' +
      ctrlInfo('实例', instanceId || 'default') +
      ctrlInfo('绑定版本', versionId || '未绑定') +
      ctrlInfo('实例目录', ctrlGameDir()) +
    '</div><div class="toolbar" style="margin-top:10px">' +
      '<button class="btn small ghost" data-act="ctrl-pack-open" data-arg="mods">打开 mods</button>' +
      '<button class="btn small ghost" data-act="ctrl-open-dir">打开游戏目录</button>' +
    '</div></div></div>';
}
async function ctrlRenderManage(box, instanceId, versionId) {
  const st = ctrlState();
  let saves = { saves: [], backups: [], dir: '', backup_root: '' };
  let g = {};
  try { saves = await call('saves_list', instanceId); } catch (err) { saves = { saves: [], backups: [], dir: '' }; }
  try { g = await call('settings_get'); } catch (err) { g = {}; }
  const inst = ctrlCurrentInstance() || {};
  const saveRows = (saves.saves || []).map((item) =>
    '<div class="row"><div class="row-main"><b>' + esc(item.name) + '</b>' +
      '<small>' + esc(item.folder) + ' · ' + esc(item.mode || '') + ' · ' + esc(item.version || '') + ' · ' + fmtSize(item.size) + ' · ' + fmtTime(item.last_played) + '</small></div>' +
      '<div class="row-actions">' +
        '<button class="btn small ghost" data-act="ctrl-save-edit" data-arg="' + A(item.folder) + '">编辑</button>' +
        '<button class="btn small ghost" data-act="ctrl-nbt" data-arg="' + A(item.folder) + '">NBT</button>' +
        '<button class="btn small ghost" data-act="ctrl-save-export" data-arg="' + A(item.folder) + '">导出</button>' +
        '<button class="btn small ghost" data-act="ctrl-world-quick" data-arg="' + A(item.folder) + '">转换导入</button>' +
        '<button class="btn small ghost" data-act="ctrl-save-backup" data-arg="' + A(item.folder) + '">备份</button>' +
        '<button class="btn small danger" data-act="ctrl-save-delete" data-arg="' + A(item.folder) + '">删除</button>' +
      '</div></div>'
  ).join('');
  const backupRows = (saves.backups || []).map((item) =>
    '<div class="row"><div class="row-main"><b>' + esc(item.world) + (item.auto ? ' <span class="tag">自动</span>' : '') + '</b>' +
      '<small class="mono">' + esc(item.path) + '</small><small>' + fmtSize(item.size) + ' · ' + fmtTime(item.created) + '</small></div>' +
      '<div class="row-actions"><button class="btn small ghost" data-act="ctrl-saves-restore" data-arg="' + A(item.path) + '">恢复</button>' +
      '<button class="btn small ghost" data-act="ctrl-world-quick" data-arg="' + A(item.path) + '">转换导入</button></div></div>'
  ).join('');
  box.innerHTML =
    '<div class="card"><div class="card-head"><h2>实例信息</h2>' + (instanceId === 'default' ? '<span class="tag">默认实例</span>' : '') + '</div><div class="card-body">' +
      '<div class="form-grid">' +
        ctrlInfo('实例名称', inst.name || instanceId) +
        ctrlInfo('实例目录', inst.game_dir || ctrlGameDir()) +
        ctrlInfo('绑定版本', inst.version_id || versionId || '未绑定') +
        ctrlInfo('加载器', inst.loader || '原版 / 未识别') +
        ctrlInfo('整合包', inst.is_modpack ? '是' : '否') +
      '</div>' +
      '<div class="toolbar" style="margin-top:10px">' +
        '<button class="btn small ghost" data-act="ctrl-rename"' + (instanceId === 'default' ? ' disabled' : '') + '>重命名实例</button>' +
        '<button class="btn small ghost" data-act="ctrl-open-dir">打开目录</button>' +
        '<button class="btn small ghost" data-act="ctrl-save-import">导入世界存档</button>' +
        '<button class="btn small ghost" data-act="ctrl-nbt-file">编辑 level.dat</button>' +
        '<button class="btn small ghost" data-act="ctrl-repair">修复版本</button>' +
        '<button class="btn small ghost" data-act="ctrl-clean">清理游戏目录</button>' +
        '<button class="btn small ghost" data-act="ctrl-export-script">导出启动脚本</button>' +
        '<button class="btn small danger" data-act="ctrl-delete-version">删除版本目录</button>' +
        '<button class="btn small danger" data-act="ctrl-remove-instance"' + (instanceId === 'default' ? ' disabled' : '') + '>移除实例记录</button>' +
      '</div>' +
      '<div class="hint" style="margin-top:6px">修复版本会备份并重拉损坏的版本 JSON；清理游戏目录会删除启动器日志、natives、临时文件与 7 天前的崩溃报告。</div>' +
    '</div></div>' +
    '<div class="card" style="margin-top:12px"><div class="card-head"><h2>批量工具</h2><span class="hint">对应经典版版本管理页底部</span></div><div class="card-body">' +
      '<div class="toolbar">' +
        '<button class="btn small ghost" data-act="ctrl-batch-health">批量健康检查</button>' +
        '<button class="btn small ghost" data-act="ctrl-batch-repair">批量补全文件</button>' +
        '<button class="btn small ghost" data-act="ctrl-batch-export">批量导出配置</button>' +
        '<button class="btn small ghost" data-act="ctrl-deps">依赖补全</button>' +
      '</div><div id="ctrlBatchBox" style="margin-top:10px"></div>' +
    '</div></div>' +
    '<div class="card" style="margin-top:12px"><div class="card-head"><h2>存档与备份</h2><span class="hint">' + esc(saves.dir || '') + '</span></div><div class="card-body">' +
      '<div class="toolbar" style="margin-bottom:8px">' +
        '<button class="btn small ghost" data-act="ctrl-refresh">刷新</button>' +
        '<button class="btn small" data-act="ctrl-saves-backup-all">备份全部</button>' +
        '<button class="btn small ghost" data-act="ctrl-open-backups">打开备份目录</button>' +
        '<button class="btn small ghost" data-act="ctrl-backup-dir">选择备份目录</button>' +
        '<label class="hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="ctrlAutoBackup"' + (g.auto_backup_saves ? ' checked' : '') + ' /> 启动前自动备份</label>' +
      '</div>' +
      '<div class="hint mono" style="margin-bottom:8px">备份目录：' + esc(saves.backup_root || g.backup_dir || '') + '</div>' +
      '<div class="list">' + (saveRows || '<div class="empty">当前实例目录下没有存档。</div>') + '</div>' +
      (backupRows ? '<div class="hint" style="margin:12px 0 6px">备份（' + (saves.backups || []).length + '）</div><div class="list" style="max-height:260px;overflow:auto">' + backupRows + '</div>' : '') +
      '<div class="toolbar" style="margin-top:10px">' +
        '<button class="btn small ghost" data-act="ctrl-tool" data-arg="存档转换器">打开存档转换器</button>' +
        '<button class="btn small ghost" data-act="ctrl-save-import">导入存档 zip</button>' +
      '</div>' +
    '</div></div>' + ctrlToolsCard();
  if (h('ctrlAutoBackup')) {
    h('ctrlAutoBackup').onchange = async (event) => {
      const res = await call('settings_set', { auto_backup_saves: event.target.checked });
      toast(res.message || (event.target.checked ? '已开启启动前自动备份' : '已关闭启动前自动备份'), res.ok === false ? 'error' : 'ok');
    };
  }
  st.manageInstance = instanceId;
}
function ctrlToolsCard() {
  return '<div class="card" style="margin-top:12px"><div class="card-head"><h2>快捷工具</h2><span class="hint">对应经典版版本设置页底部</span></div><div class="card-body">' +
    '<div class="toolbar">' +
      '<button class="btn small ghost" data-act="ctrl-tool" data-arg="世界种子">世界种子预览</button>' +
      '<button class="btn small ghost" data-act="ctrl-tool" data-arg="截图图库">截图图库</button>' +
      '<button class="btn small ghost" data-act="ctrl-tool" data-arg="崩溃报告">崩溃报告</button>' +
      '<button class="btn small ghost" data-act="ctrl-tool" data-arg="Mod 关系">Mod 关系图</button>' +
      '<button class="btn small ghost" data-act="ctrl-deps">依赖补全</button>' +
    '</div></div></div>';
}
ACT['ctrl-tab'] = (tab) => { ctrlState().tab = tab; renderControl(); };
ACT['ctrl-refresh'] = () => ctrlLoad();
ACT['ctrl-open-dir'] = async () => {
  await call('select_instance', ctrlState().instanceId || 'default');
  const res = await call('open_path', 'instance');
  if (res && res.ok === false) toast(res.message || '打开失败', 'error');
};
ACT['ctrl-open-versiondir'] = async () => {
  const res = await call('open_path', 'versiondir:' + ctrlCurrentVersion());
  if (res && res.ok === false) toast(res.message || '打开失败', 'error');
};
ACT['ctrl-launch'] = async () => {
  const st = ctrlState();
  await call('select_instance', st.instanceId || 'default');
  S.selectedVersion = ctrlCurrentVersion();
  await launchGame();
};
ACT['ctrl-delete-version'] = async () => {
  const vid = ctrlCurrentVersion();
  if (!vid) return toast('请先选择版本', 'error');
  if (!(await ask('删除版本', '将永久删除版本目录「' + vid + '」，并移除绑定它的实例记录。存档与截图不会被删除，确定继续？'))) return;
  const res = await call('delete_version', vid);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) {
    S.data.versions = res.versions || [];
    S.data.instances = (await call('instances')).instances || [];
    ctrlState().versionId = '';
    renderControl();
  }
};
ACT['ctrl-repair'] = async () => {
  const st = ctrlState();
  const res = await call('repair_instance', st.instanceId || 'default');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-clean'] = async () => {
  if (!(await ask('清理游戏目录', '将删除启动器日志（保留最近 3 个）、versions/*/natives、*.tmp / *.part 与 7 天前的 crash-reports。确定继续？'))) return;
  const res = await call('clean_game');
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['ctrl-export-script'] = async () => {
  const res = await call('export_script', ctrlCurrentVersion());
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['ctrl-deps'] = () => { setPage('tools'); setTimeout(() => ACT['tool-jump']('依赖补全'), 260); };
ACT['ctrl-tool'] = (title) => { setPage('tools'); setTimeout(() => ACT['tool-jump'](title), 260); };
ACT['ctrl-game-save'] = async () => {
  const payload = {
    java_path: h('cgJava') ? G(h('cgJava').value) : '',
    memory_mb: Number(h('cgMemory') ? h('cgMemory').value : 4096),
    width: Number(h('cgWidth') ? h('cgWidth').value : 1280),
    height: Number(h('cgHeight') ? h('cgHeight').value : 720),
    extra_jvm_args: h('cgJvm') ? h('cgJvm').value.trim() : '',
    extra_game_args: h('cgGame') ? h('cgGame').value.trim() : '',
    auto_connect_enabled: !!(h('cgAuto') && h('cgAuto').checked),
    auto_connect_server: h('cgServer') ? h('cgServer').value.trim() : '',
    auto_connect_port: Number(h('cgPort') ? h('cgPort').value : 25565),
    after_launch_action: (h('cgHide') && h('cgHide').checked) ? 'hide' : 'nothing',
  };
  const res = await call('settings_set', payload);
  toast(res.message || '游戏设置已保存', res.ok === false ? 'error' : 'ok');
  ctrlLoad();
};
ACT['ctrl-vsetting-save'] = async () => {
  const vid = ctrlCurrentVersion();
  if (!vid) return toast('请先选择版本', 'error');
  const payload = {
    isolation: h('cvIsolation') ? G(h('cvIsolation').value) : '',
    memory_mb: Number(h('cvMemory') ? h('cvMemory').value : 0),
    priority: h('cvPriority') ? h('cvPriority').value : '',
    window_title: h('cvTitle') ? h('cvTitle').value.trim() : '',
    extra_jvm_args: h('cvJvm') ? h('cvJvm').value.trim() : '',
    extra_game_args: h('cvGame') ? h('cvGame').value.trim() : '',
    auto_connect: !!(h('cvAuto') && h('cvAuto').checked),
    server: h('cvServer') ? h('cvServer').value.trim() : '',
    port: Number(h('cvPort') ? h('cvPort').value : 25565),
  };
  const res = await call('version_settings_save', vid, payload);
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['ctrl-content-add'] = async (kind) => {
  const res = await call('content_add_files', kind, ctrlCurrentVersion(), ctrlState().instanceId || '');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-pack-open'] = async (kind) => {
  const res = await call('pack_open', kind, ctrlCurrentVersion(), ctrlState().instanceId || '');
  if (res && res.ok === false) toast(res.message || '打开失败', 'error');
};
ACT['ctrl-online'] = async (kind) => {
  const inst = ctrlCurrentInstance() || {};
  if (inst.id) {
    await call('select_instance', inst.id);
    if (S.data) S.data.selected_instance = inst.id;
  }
  S.content = S.content || {};
  S.content = Object.assign(S.content || {}, { kind: kind, gv: inst.mc_version || '', loader: inst.loader || '', q: '', offset: 0, projects: [], searched: false });
  setPage('content');
  toast('已打开内容中心，安装目标为当前实例', 'ok');
};
ACT['ctrl-mod-toggle'] = async (path) => {
  const res = await call('mod_toggle', path);
  toast(res.message || (res.enabled ? '已启用' : '已禁用'), res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-mod-delete'] = async (path) => {
  if (!(await ask('删除 Mod', '将直接删除该文件，不可恢复。确定继续？'))) return;
  const res = await call('mod_delete', path);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) { S.control.updates = null; ctrlLoad(); }
};
ACT['ctrl-mod-check'] = async () => {
  const res = await call('mod_updates_check', ctrlCurrentVersion(), ctrlState().instanceId || '');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (!res.ok) return;
  S.control.updates = res;
  ctrlLoad();
};
ACT['ctrl-mod-apply'] = async () => {
  const res = await call('mod_updates_apply', ctrlCurrentVersion(), ctrlState().instanceId || '');
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message, 'ok');
  const job = await watchJob(res.job);
  if (job && job.state === 'ok') {
    S.control.updates = null;
    toast('Mod 更新完成', 'ok');
    ctrlLoad();
  }
};
ACT['ctrl-pack-toggle'] = async (path) => {
  const res = await call('pack_toggle', path);
  toast(res.message || (res.enabled ? '已启用' : '已禁用'), res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-pack-delete'] = async (path) => {
  if (!(await ask('删除文件', '将直接删除该文件，不可恢复。确定继续？'))) return;
  const res = await call('pack_delete', path);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-pack-move'] = async (raw) => {
  const parts = String(raw || '').split('|');
  const res = await call('pack_reorder', parts[0], Number(parts[1] || 0));
  if (!res.ok) toast(res.message, 'error');
  ctrlLoad();
};
ACT['ctrl-save-backup'] = async (folder) => {
  const res = await call('saves_backup', folder, ctrlState().instanceId || '');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-saves-backup-all'] = async () => {
  const res = await call('saves_backup', '', ctrlState().instanceId || '');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-saves-restore'] = async (path) => {
  if (!(await ask('恢复存档', '目标位置已有同名存档时会覆盖，确定继续？'))) return;
  const res = await call('saves_restore', path, ctrlState().instanceId || '');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-save-delete'] = async (folder) => {
  if (!(await ask('删除存档', '将直接从磁盘删除「' + folder + '」，不可恢复。'))) return;
  const res = await call('saves_delete', folder, ctrlState().instanceId || '');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-save-export'] = async (folder) => {
  const res = await call('save_export_world', folder, ctrlState().instanceId || '');
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['ctrl-save-import'] = async () => {
  const res = await call('save_import_world', ctrlState().instanceId || '');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-save-edit'] = async (folder) => {
  await call('select_instance', ctrlState().instanceId || 'default');
  return ACT['save-edit'](folder);
};
ACT['ctrl-nbt'] = (folder) => { S.nbtInstance = ctrlState().instanceId || ''; setPage('tools'); setTimeout(() => ACT['save-nbt'](folder), 300); };
ACT['ctrl-nbt-file'] = () => {
  setPage('tools');
  setTimeout(() => {
    if (S.control && S.control.nbtPick) { S.control.nbtPick(); return; }
    const res = call('nbt_open');
    res.then((data) => {
      if (!data || !data.ok) return;
      S.nbt = data;
      paintNbt();
      toast('已打开 ' + (data.path || 'NBT 文件'), 'ok');
    }).catch((err) => toast(err.message || err, 'error'));
  }, 300);
};
ACT['ctrl-world-quick'] = async (path) => {
  setPage('tools');
  await loadWorldTool();
  setTimeout(() => ACT['world-quick'](path), 80);
};
ACT['ctrl-open-backups'] = async () => {
  const res = await call('open_path', 'backups');
  if (res && res.ok === false) toast(res.message || '打开失败', 'error');
};
ACT['ctrl-backup-dir'] = async () => {
  const res = await call('backup_pick_dir');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) ctrlLoad();
};
ACT['ctrl-rename'] = async () => {
  const st = ctrlState();
  const inst = ctrlCurrentInstance() || {};
  openSheet('重命名实例', 
    '<div class="field"><label>实例名称</label><input id="ctrlRenameInput" value="' + esc(inst.name || '') + '" /></div>' +
    '<div class="hint" style="margin-top:8px">只修改启动器显示名称，不会移动实例目录。</div>',
    '<button class="btn ghost" id="ctrlRenameCancel">取消</button><button class="btn primary" id="ctrlRenameOk">保存</button>');
  h('ctrlRenameCancel').onclick = closeSheet;
  h('ctrlRenameOk').onclick = async () => {
    const name = String((h('ctrlRenameInput') && h('ctrlRenameInput').value) || '').trim();
    if (!name) return toast('实例名称不能为空', 'error');
    const res = await call('rename_instance', st.instanceId, name);
    toast(res.message, res.ok ? 'ok' : 'error');
    if (res.ok) {
      closeSheet();
      S.data.instances = (await call('instances')).instances || S.data.instances;
      renderControl();
    }
  };
};
ACT['ctrl-remove-instance'] = async () => {
  const st = ctrlState();
  if (st.instanceId === 'default') return toast('默认实例不能移除', 'error');
  if (!(await ask('移除实例记录', '只删除启动器中的实例记录，不会删除磁盘上的游戏文件。确定继续？'))) return;
  const res = await call('remove_instance', st.instanceId);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) {
    S.data.instances = (await call('instances')).instances || [];
    st.instanceId = 'default';
    st.versionId = '';
    renderControl();
  }
};
ACT['ctrl-batch-health'] = async () => {
  const res = await call('batch_health');
  const box = h('ctrlBatchBox');
  if (!box) return;
  if (!res.ok) { box.innerHTML = '<div class="empty">' + esc(res.message || '检查失败') + '</div>'; return; }
  const rows = (res.items || []).map((item) =>
    '<div class="row"><div class="row-main"><b>' + ctrlHealthTag(item) + ' ' + esc(item.name) + '</b>' +
      '<small>' + esc(item.version) + (item.issues && item.issues.length ? ' · ' + esc(item.issues.join('；')) : '') + '</small></div></div>'
  ).join('');
  box.innerHTML = '<div class="hint">绿色 ' + Number((res.counts || {}).green || 0) + ' · 黄色 ' + Number((res.counts || {}).yellow || 0) + ' · 红色 ' + Number((res.counts || {}).red || 0) + '</div><div class="list">' + rows + '</div>';
};
ACT['ctrl-batch-repair'] = async () => {
  const res = await call('batch_repair');
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message, 'ok');
  const job = await watchJob(res.job);
  if (job && job.state === 'ok') toast('批量补全完成', 'ok');
};
ACT['ctrl-batch-export'] = async () => {
  const res = await call('batch_export_config');
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['ctrl-modpack-export'] = async () => {
  const res = await call('export_modpack', ctrlState().instanceId || 'default');
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['ctrl-modpack-import'] = async () => {
  const res = await call('modpack_import_current', ctrlState().instanceId || 'default');
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message, 'ok');
  const job = await watchJob(res.job);
  if (job && job.state === 'ok') toast('整合包内容已导入', 'ok');
};

/* ---------- 通用弹层 ---------- */
function openSheet(title, body, foot) {
  h('sheetTitle').textContent = title || '';
  h('sheetBody').innerHTML = body || '';
  h('sheetFoot').innerHTML = foot || '<button class="btn ghost" id="sheetCancel">关闭</button>';
  h('overlay').hidden = false;
  h('sheetClose').onclick = closeSheet;
  if (h('sheetCancel')) h('sheetCancel').onclick = closeSheet;
}
function closeSheet() { h('overlay').hidden = true; h('sheetBody').innerHTML = ''; h('sheetFoot').innerHTML = ''; }
function ask(title, message) {
  return new Promise((resolve) => {
    openSheet(title, '<div class="empty" style="padding:4px 0 8px">' + esc(message) + '</div>',
      '<button class="btn ghost" id="askNo">取消</button><button class="btn primary" id="askYes">确定</button>');
    h('askNo').onclick = () => { closeSheet(); resolve(false); };
    h('askYes').onclick = () => { closeSheet(); resolve(true); };
  });
}
h('overlay').addEventListener('click', (event) => { if (event.target === h('overlay')) closeSheet(); });

function copyText(text) {
  const box = document.createElement('textarea');
  box.value = String(text || '');
  box.style.position = 'fixed'; box.style.opacity = '0';
  document.body.appendChild(box);
  box.select();
  try { document.execCommand('copy'); toast('已复制到剪贴板', 'ok'); }
  catch (_) { toast('复制失败，请手动选择文本', 'error'); }
  box.remove();
}

async function watchJob(jobId, onDone) {
  const started = Date.now();
  while (Date.now() - started < 12 * 60 * 1000) {
    await new Promise((r) => setTimeout(r, 900));
    let list;
    try { list = await call('tasks'); } catch (_) { continue; }
    const job = (list || []).find((item) => item.id === jobId);
    if (!job) continue;
    setStatus(job.stage + ' · ' + job.percent.toFixed(0) + '%', '任务运行中');
    if (job.state === 'ok') { if (onDone) onDone(job); return job; }
    if (job.state === 'failed' || job.state === 'cancelled') return job;
  }
  return null;
}

/* ---------- 通用跳转动作 ---------- */
ACT['go-download'] = (tab) => { if (tab) S.dlTab = tab; setPage('download'); };
ACT['go-content'] = (kind) => { if (kind) S.content = Object.assign(S.content, { kind: kind, offset: 0 }); setPage('content'); };
ACT['go-account'] = () => setPage('account');
ACT['go-settings'] = (tab) => { S.settings.tab = tab || 'general'; setPage('settings'); };
ACT['pick-version'] = (id) => { S.selectedVersion = id; renderHome(); };
ACT['refresh-versions'] = async () => { await reloadVersions(true); toast('版本列表已刷新', 'ok'); };
ACT['open-path'] = async (kind) => { const res = await call('open_path', kind); if (!res.ok) toast(res.message, 'error'); };
ACT['backup-pick-dir'] = async () => {
  const res = await call('backup_pick_dir');
  if (!res.ok) return toast(res.message || '未选择目录', 'error');
  toast('备份目录已更新为 ' + res.backup_dir, 'ok');
  await reloadSettingsAfterApply();
};
ACT['download-pick-dir'] = async () => {
  const res = await call('download_pick_dir');
  if (!res.ok) return toast(res.message || '未选择目录', 'error');
  toast('下载文件夹已更新为 ' + res.download_dir, 'ok');
  await reloadSettingsAfterApply();
};
ACT['download-reset-dir'] = async () => {
  const res = await call('download_reset_dir');
  if (!res.ok) return toast(res.message || '恢复失败', 'error');
  toast('已恢复为系统下载文件夹', 'ok');
  await reloadSettingsAfterApply();
};
ACT['open-url'] = async (url) => { const res = await call('open_url', url); if (!res.ok) toast(res.message, 'error'); };

/* ---------- 账号与皮肤 ---------- */
function renderAccount() {
  const data = S.data; if (!data) return;
  const feats = data.features || {};
  const account = data.account || {};
  const skins = data.skins || [];
  h('view').innerHTML =
    '<div class="page flow" style="gap:12px">' +
      '<div class="grid2" style="flex:none">' +
        '<div class="card"><div class="card-head"><h2>当前账号</h2><span class="hint">' + esc(account.type_label || account.type || '') + '</span></div>' +
          '<div class="card-body">' +
            '<div class="detail-hero" style="margin:0 0 12px">' +
              '<div class="skin-big" style="width:70px;height:70px;border-radius:13px;background:#132018;font-size:19px">' +
                '<i id="skinBig" class="skin-head"></i>' +
                '<span id="skinBigFallback">' + esc((account.name || 'S').slice(0, 1).toUpperCase()) + '</span>' +
              '</div>' +
              '<div class="d-main"><b>' + esc(account.name || 'Steve') + '</b>' +
                '<small class="mono">' + esc(account.uuid || '离线 UUID') + '</small>' +
                '<small>模型：' + esc(account.skin_model === 'slim' ? 'Alex（细手臂）' : 'Steve（宽手臂）') + '</small></div>' +
            '</div>' +
            '<div class="toolbar">' + (feats.offline_skin === false ? '' : '<button class="btn small primary" data-act="skin-import">导入皮肤</button>') +
              '<button class="btn small ghost" data-act="skin-model">切换模型</button>' +
              (feats.skin_factory === false ? '' : '<button class="btn small ghost" data-act="skin-studio">皮肤工坊</button>') +
              (feats.offline_skin === false ? '' : '<button class="btn small ghost" data-act="skin-library">打开皮肤库</button>') +
              '<button class="btn small ghost" data-act="skin-pack-fill" title="检查已下载的游戏版本，缺失皮肤包的自动生成并导入">补齐缺失版本皮肤包</button></div>' +
            '<div class="hint" style="margin-top:8px">皮肤会写入 CustomSkinLoader 的 LocalSkin 目录，进游戏自动生效。</div>' +
          '</div></div>' +
        '<div class="card"><div class="card-head"><h2>快速切换皮肤</h2><span class="hint">最近导入</span></div>' +
          '<div class="card-body"><div class="skin-grid">' +
            (skins.length ? skins.map((item) =>
              '<button class="skin" data-act="quick-skin" data-arg="' + A(item.path) + '" data-model="' + esc(item.model || 'classic') + '" title="' + esc(item.name) + '">' +
              '<i class="skin-head" data-skin="' + esc(A(item.path)) + '"></i></button>'
            ).join('') : '<div class="empty">还没有导入过皮肤。点击左侧「导入皮肤」开始。</div>') +
          '</div></div></div>' +
      '</div>' +
      '<div class="card" style="flex:none"><div class="card-head"><h2>账号列表</h2><div class="head-actions">' +
        (feats.offline_login === false ? '' : '<button class="btn small ghost" data-act="acc-offline-sheet">添加离线</button>') +
        '<button class="btn small primary" data-act="ms-login">微软正版登录</button>' +
        '<button class="btn small ghost" data-act="authlib-sheet">外置登录</button></div></div>' +
        '<div class="card-body scroll" style="max-height:280px"><div class="list" id="accountList"><div class="loading"><span class="spinner"></span>正在读取账号…</div></div></div></div>' +
      (feats.skin_pack === false ? '' : '<div class="card" style="flex:none"><div class="card-head"><h2>半透明毛玻璃 UI 材质包</h2><span class="hint">一键安装并替换旧包 · 自动识别版本</span></div>' +
        '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
          '<div class="field-row"><span class="hint" style="flex:none">适配版本</span>' +
            '<select id="uiPackVersion" style="flex:1"><option value="">选择已安装版本…</option></select>' +
            '<button class="btn small primary" data-act="ui-pack-install">一键安装并替换</button></div>' +
          '<div class="field-row">' +
            '<label class="hint" style="display:flex;align-items:center;gap:6px;flex:1"><input type="checkbox" id="uiPackEnable" checked />安装后自动启用（1.6.1+），重复执行自动替换旧包</label>' +
            '<button class="btn small ghost" data-act="ui-pack-all" title="为全部已安装版本生成">全部版本一键替换</button>' +
            '<button class="btn small ghost" data-act="ui-pack-export">导出 UI 包…</button></div>' +
          '<div class="hint">按钮 / 输入框 / 滑块 / 背包与箱子面板 / 快捷栏都会原位改造成半透明磨砂，菜单背景换成无缝玻璃瓦片；1.0–1.5.2 生成纹理包，需在游戏内「材质包」手动选中。</div>' +
        '</div></div>') +
      (feats.skin_pack === false ? '' : '<div class="card" style="flex:none"><div class="card-head"><h2>皮肤包</h2><span class="hint">分享给其他玩家 · 可指定版本与手臂模型</span></div>' +
        '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
          '<div class="field-row"><input type="text" id="packPlayer" placeholder="目标玩家名（对方游戏内名字）" style="flex:1" />' +
          '<select id="packModel"><option value="classic">Steve（宽手臂）</option><option value="slim">Alex（细手臂）</option></select>' +
          '<select id="packVersion"><option value="">自动 / 不限版本</option></select></div>' +
          '<div class="field-row"><input type="text" id="packSource" placeholder="皮肤 PNG（留空则使用当前账号皮肤）" style="flex:1" readonly />' +
          '<button class="btn small ghost" data-act="skin-pack-pick">选择 PNG</button>' +
          '<button class="btn small primary" data-act="skin-pack-export">导出皮肤包</button>' +
          '<button class="btn small ghost" data-act="skin-pack-install">安装皮肤包</button></div>' +
          '<div class="field-row"><input type="text" id="packCape" placeholder="披风 PNG（可选，64×32）" style="flex:1" readonly />' +
          '<button class="btn small ghost" data-act="skin-pack-pick-cape">选择披风</button></div>' +
          '<div class="field-row"><span class="hint" style="flex:none">导入到指定版本</span>' +
            '<select id="packImportVersion" style="flex:1"><option value="">选择已安装版本…</option></select>' +
            '<button class="btn small ghost" data-act="skin-pack-import-version" title="把皮肤包 / PNG 导入到所选版本的游戏目录">导入皮肤包…</button></div>' +
          '<div class="field-row">' +
            '<label class="hint" style="display:flex;align-items:center;gap:6px;flex:1"><input type="checkbox" id="packEnable" />安装后自动启用皮肤包</label>' +
            '<button class="btn small primary" data-act="skin-pack-overwrite" title="清理所有游戏目录的旧皮肤包并写入当前皮肤">一键覆盖安装</button>' +
          '</div>' +
          '<div class="hint">导出的 zip 可直接被启动器导入，也可以作为资源包放进 resourcepacks/；安装时会写入目标玩家的 LocalSkin 皮肤。</div>' +
        '</div></div>') +
    '</div>';
  hydrateSkins();
  loadAccounts();
  loadSkinPackVersions();
  applyBackground(data.background_image);
}

async function hydrateSkins() {
  const account = S.data && S.data.account;
  const big = h('skinBig');
  if (big && account && account.skin_path) {
    try {
      const src = await call('preview', account.skin_path);
      if (src) { applyHead(big, src); if (h('skinBigFallback')) h('skinBigFallback').style.display = 'none'; }
    } catch (_) { /* 皮肤读取失败时保留首字母 */ }
  }
  // 账号页用 data-skin，主页「最近皮肤」用 data-skin-path，两者都要裁剪出头部
  const thumbs = document.querySelectorAll('[data-skin], [data-skin-path]');
  for (const el of thumbs) {
    const raw = el.dataset.skin || el.dataset.skinPath;
    if (!raw) continue;
    try {
      const src = await call('preview', decodeURIComponent(raw));
      if (src) applyHead(el, src);
    } catch (_) { /* 单张失败不影响其它 */ }
  }
}

async function loadSkinPackVersions() {
  const select = h('packVersion');
  try {
    const res = await call('skin_pack_versions');
    if (select && res.ok) {
      select.innerHTML = '<option value="">自动 / 不限版本</option>' +
        (res.versions || []).map((version) => '<option value="' + esc(version) + '">' + esc(version) + '</option>').join('');
      const target = h('packImportVersion');
      if (target) {
        const installed = (res.installed && res.installed.length) ? res.installed : (res.versions || []);
        target.innerHTML = '<option value="">选择已安装版本…</option>' +
          installed.map((version) => '<option value="' + esc(version) + '">' + esc(version) + '</option>').join('');
      }
    }
  } catch (_) { /* 版本列表失败不影响其它功能 */ }
  try {
    const uiSelect = h('uiPackVersion');
    if (uiSelect) {
      const res = await call('ui_pack_versions');
      if (res.ok) {
        const list = res.versions || [];
        uiSelect.innerHTML = '<option value="">选择已安装版本…</option>' +
          list.map((version) => '<option value="' + esc(version) + '">' + esc(version) + '</option>').join('');
        const preferred = list.includes(S.selectedVersion) ? S.selectedVersion : (list[0] || '');
        if (preferred) uiSelect.value = preferred;
      }
    }
  } catch (_) { /* UI 材质包版本列表失败不影响其它功能 */ }
}

async function loadAccounts() {
  let res;
  try { res = await call('accounts'); } catch (err) { return; }
  const box = h('accountList'); if (!box) return;
  const items = res.list || [];
  box.innerHTML = items.length ? items.map((a) =>
    '<div class="row"><div class="row-main"><b>' + esc(a.name) + (a.id === res.selected ? ' <span class="tag accent">使用中</span>' : '') +
      (a.expired ? ' <span class="tag warn">令牌过期</span>' : '') + '</b>' +
      '<small>' + esc(a.type_label) + (a.server ? ' · ' + esc(a.server) : '') + '</small>' +
      '<small class="mono">' + esc(a.uuid || '') + '</small></div>' +
      '<div class="row-actions">' +
        '<button class="btn small ' + (a.id === res.selected ? 'ghost' : 'primary') + '" data-act="acc-select" data-arg="' + A(a.id) + '">使用</button>' +
        (a.type === 'microsoft' ? '<button class="btn small ghost" data-act="acc-refresh" data-arg="' + A(a.id) + '">刷新</button>' : '') +
        '<button class="btn small danger" data-act="acc-remove" data-arg="' + A(a.id) + '">删除</button>' +
      '</div></div>'
  ).join('') : '<div class="empty">没有账号。</div>';
}
ACT['acc-select'] = async (id) => {
  const res = await call('select_account', id);
  if (!res.ok) return toast(res.message, 'error');
  await refreshBootstrap(); loadAccounts(); toast('已切换账号', 'ok');
};
ACT['acc-refresh'] = async (id) => {
  const res = await call('refresh_account', id);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadAccounts();
};
ACT['acc-remove'] = async (id) => {
  if (!(await ask('删除账号', '仅从启动器移除账号记录，不会影响微软账号本身。确定继续？'))) return;
  const res = await call('remove_account', id);
  if (!res.ok) return toast(res.message, 'error');
  await refreshBootstrap(); loadAccounts();
};
ACT['acc-offline-sheet'] = () => {
  openSheet('添加离线账号', '<div class="field"><label>玩家名（最多 16 个字符）</label><input type="text" id="offName" maxlength="16" placeholder="Steve" /></div>',
    '<button class="btn ghost" id="offCancel">取消</button><button class="btn primary" id="offAdd">添加</button>');
  h('offCancel').onclick = closeSheet;
  h('offAdd').onclick = async () => {
    const name = h('offName').value.trim();
    if (!name) return toast('请输入玩家名', 'error');
    const res = await call('add_offline', name);
    if (!res.ok) return toast(res.message, 'error');
    closeSheet(); await refreshBootstrap(); loadAccounts(); toast('已添加离线账号', 'ok');
  };
};
ACT['ms-login'] = async () => {
  const res = await call('ms_login_start');
  if (!res.ok) return toast(res.message, 'error');
  openSheet('微软正版登录',
    '<div class="field"><label>1. 在浏览器打开下面的地址</label><div class="field-row">' +
      '<input type="text" id="msUrl" readonly value="' + esc(res.url) + '" style="flex:1" /><button class="btn small ghost" id="msOpen">打开</button></div></div>' +
    '<div class="field" style="margin-top:12px"><label>2. 输入设备码</label><input type="text" id="msCode" readonly value="' + esc(res.code) + '" style="font-size:18px;letter-spacing:3px;text-align:center" /></div>' +
    '<div class="hint" style="margin-top:10px">' + esc(res.message || '') + '（有效期约 ' + Math.round((res.expires || 900) / 60) + ' 分钟）</div>',
    '<button class="btn ghost" id="msClose">取消</button><button class="btn primary" id="msDone">我已完成授权</button>');
  h('msClose').onclick = closeSheet;
  h('msOpen').onclick = () => call('open_url', res.url);
  h('msDone').onclick = async () => {
    h('msDone').disabled = true;
    const poll = await call('ms_login_poll');
    if (!poll.ok) { h('msDone').disabled = false; return toast(poll.message, 'error'); }
    toast('正在等待微软授权…', 'ok');
    const job = await watchJob(poll.job);
    h('msDone').disabled = false;
    if (job && job.state === 'ok') {
      closeSheet(); await refreshBootstrap(); loadAccounts(); toast('微软正版登录成功', 'ok');
    } else {
      toast((job && (job.error || job.stage)) || '登录未完成，请重试', 'error');
    }
  };
};
ACT['authlib-sheet'] = () => {
  openSheet('外置登录（authlib-injector）',
    '<div class="field"><label>皮肤站地址（Yggdrasil API）</label><input type="text" id="alServer" placeholder="https://littleskin.cn/api/yggdrasil" /></div>' +
    '<div class="field" style="margin-top:10px"><label>邮箱 / 用户名</label><input type="text" id="alUser" /></div>' +
    '<div class="field" style="margin-top:10px"><label>密码</label><input type="password" id="alPass" /></div>' +
    '<div class="hint" style="margin-top:10px">首次使用会自动下载 authlib-injector。也可在「工具箱 → 依赖补全」提前安装。</div>',
    '<button class="btn ghost" id="alCancel">取消</button><button class="btn primary" id="alGo">登录</button>');
  h('alCancel').onclick = closeSheet;
  h('alGo').onclick = async () => {
    const server = h('alServer').value.trim();
    const user = h('alUser').value.trim();
    const pass = h('alPass').value;
    if (!server || !user) return toast('请填写服务器地址与用户名', 'error');
    h('alGo').disabled = true;
    const res = await call('authlib_login', server, user, pass);
    if (!res.ok) { h('alGo').disabled = false; return toast(res.message, 'error'); }
    const job = await watchJob(res.job);
    h('alGo').disabled = false;
    if (job && job.state === 'ok') {
      closeSheet(); await refreshBootstrap(); loadAccounts(); toast('外置登录成功', 'ok');
    } else {
      toast((job && (job.error || job.stage)) || '外置登录失败', 'error');
    }
  };
};
ACT['skin-import'] = async () => {
  const current = (S.data && S.data.account && S.data.account.skin_model) || 'classic';
  openSheet('导入皮肤',
    '<div style="display:flex;flex-direction:column;gap:12px">' +
      '<div><div class="hint" style="margin-bottom:6px">手臂模型</div>' +
        '<div class="field-row">' +
          '<label class="hint" style="display:flex;align-items:center;gap:6px"><input type="radio" name="skinImportModel" value="classic"' + (current === 'classic' ? ' checked' : '') + ' /> Steve（宽手臂）</label>' +
          '<label class="hint" style="display:flex;align-items:center;gap:6px"><input type="radio" name="skinImportModel" value="slim"' + (current === 'slim' ? ' checked' : '') + ' /> Alex（细手臂）</label>' +
        '</div></div>' +
      '<label class="hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="skinImportOverwrite" checked /> 覆盖所有已安装版本（自动生成对应格式的皮肤包）</label>' +
      '<div class="hint">导入后会自动扫描已安装的游戏版本，为每个版本生成适配资源包；之后新装版本也会自动补做皮肤包。</div>' +
    '</div>',
    '<button class="btn ghost" id="skinImportCancel">取消</button><button class="btn primary" id="skinImportGo">选择 PNG 并导入</button>');
  h('skinImportCancel').onclick = closeSheet;
  h('skinImportGo').onclick = async () => {
    const picked = document.querySelector('input[name="skinImportModel"]:checked');
    const model = picked ? picked.value : current;
    const overwrite = !!h('skinImportOverwrite').checked;
    closeSheet();
    const res = await call('import_skin', model, overwrite);
    if (!res.ok) return toast(res.message, 'error');
    await refreshBootstrap();
    toast(res.message || '皮肤已导入', 'ok');
  };
};
ACT['quick-skin'] = async (path, node) => {
  const model = (node && node.dataset.model) || '';
  const res = await call('apply_skin_path', path, model, true);
  if (!res.ok) return toast(res.message, 'error');
  await refreshBootstrap();
  toast('已切换到该皮肤', 'ok');
};
ACT['skin-model'] = async () => {
  const current = (S.data && S.data.account && S.data.account.skin_model) || 'classic';
  const next = current === 'slim' ? 'classic' : 'slim';
  const res = await call('skin_model', next);
  if (!res.ok) return toast(res.message, 'error');
  await refreshBootstrap();
  toast(next === 'slim' ? '已切换为 Alex（细手臂）' : '已切换为 Steve（宽手臂）', 'ok');
};
ACT['skin-library'] = async () => {
  let res;
  try { res = await call('skin_library'); } catch (err) { return toast(err.message || '读取皮肤库失败', 'error'); }
  const items = res.items || [];
  openSheet('皮肤库',
    (items.length
      ? '<div class="skin-grid">' + items.map((item) =>
        '<button class="skin" data-act="quick-skin" data-arg="' + A(item.path) + '" data-model="' + esc(item.model || 'classic') + '" title="' + esc(item.name) + '">' +
        '<img alt="" src="' + esc(item.preview || '') + '" style="' + (item.preview ? '' : 'display:none') + '" /></button>').join('') + '</div>'
      : '<div class="empty">皮肤库还是空的。导入皮肤后会自动记录在这里。</div>') +
    '<div class="hint" style="margin-top:10px">点击任意皮肤即可切换；「打开目录」可直接管理 PNG 文件。</div>',
    '<button class="btn ghost" data-act="open-path" data-arg="skins">打开目录</button><button class="btn primary" id="skinLibClose">关闭</button>');
  if (h('skinLibClose')) h('skinLibClose').onclick = closeSheet;
};
ACT['skin-pack-pick'] = async () => {
  const res = await call('pick_skin_png');
  if (!res.ok) return;
  if (h('packSource')) h('packSource').value = res.path;
};
ACT['skin-pack-pick-cape'] = async () => {
  const res = await call('pick_skin_png');
  if (!res.ok) return;
  if (h('packCape')) h('packCape').value = res.path;
};
ACT['skin-pack-export'] = async () => {
  const player = (h('packPlayer') && h('packPlayer').value.trim()) || '';
  if (!player) return toast('请先填写目标玩家名', 'error');
  if (h('packSource') && h('packSource').value.trim()) S.skinPackSource = h('packSource').value.trim();
  const res = await call('skin_pack_export', player,
    (h('packModel') && h('packModel').value) || 'classic',
    (h('packVersion') && h('packVersion').value) || '',
    S.skinPackSource || '',
    (h('packCape') && h('packCape').value.trim()) || '');
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['skin-pack-install'] = async () => {
  const res = await call('skin_pack_install', !!(h('packEnable') && h('packEnable').checked), (h('packVersion') && h('packVersion').value) || '');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) await refreshBootstrap();
};
ACT['skin-pack-import-version'] = async () => {
  const version = (h('packImportVersion') && h('packImportVersion').value) || '';
  if (!version) return toast('请先选择要导入的版本', 'error');
  const res = await call('skin_pack_import_version', version, !!(h('packEnable') && h('packEnable').checked));
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) await refreshBootstrap();
};
ACT['skin-pack-overwrite'] = async () => {
  const player = (h('packPlayer') && h('packPlayer').value.trim()) || '';
  if (!player) return toast('请先填写目标玩家名', 'error');
  if (h('packSource') && h('packSource').value.trim()) S.skinPackSource = h('packSource').value.trim();
  const res = await call('skin_pack_overwrite',
    player,
    (h('packModel') && h('packModel').value) || 'classic',
    S.skinPackSource || '',
    (h('packCape') && h('packCape').value.trim()) || '',
    (h('packVersion') && h('packVersion').value) || '',
    !!(h('packEnable') && h('packEnable').checked),
    false);
  toast(res.message, res.ok ? 'ok' : 'error');
};

ACT['skin-pack-fill'] = async () => {
  const player = (h('packPlayer') && h('packPlayer').value.trim()) || '';
  if (h('packSource') && h('packSource').value.trim()) S.skinPackSource = h('packSource').value.trim();
  const res = await call('skin_pack_fill_missing',
    player,
    (h('packModel') && h('packModel').value) || 'classic',
    S.skinPackSource || '',
    (h('packCape') && h('packCape').value.trim()) || '',
    !!(h('packEnable') && h('packEnable').checked),
    false);
  toast(res.message || (res.ok ? '已补齐' : '补齐失败'), res.ok ? 'ok' : 'error');
};

/* ---------- 半透明毛玻璃 UI 材质包 ---------- */
ACT['home-ui-pack'] = async () => {
  const version = S.selectedVersion || '';
  if (!version) return toast('请先选择游戏版本', 'error');
  const res = await call('ui_pack_install', version, true);
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['ui-pack-install'] = async () => {
  const version = (h('uiPackVersion') && h('uiPackVersion').value) || '';
  if (!version) return toast('请先选择游戏版本', 'error');
  const res = await call('ui_pack_install', version, !!(h('uiPackEnable') && h('uiPackEnable').checked));
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['ui-pack-all'] = async () => {
  const res = await call('ui_pack_install_all', !!(h('uiPackEnable') && h('uiPackEnable').checked));
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['ui-pack-export'] = async () => {
  const version = (h('uiPackVersion') && h('uiPackVersion').value) || '';
  if (!version) return toast('请先选择游戏版本', 'error');
  const res = await call('ui_pack_export', version);
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['content-ui-pack'] = async () => {
  const version = (h('contentUiVersion') && h('contentUiVersion').value) || '';
  if (!version) return toast('请先选择游戏版本', 'error');
  const res = await call('ui_pack_install', version, true);
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['content-ui-pack-all'] = async () => {
  const res = await call('ui_pack_install_all', true);
  toast(res.message, res.ok ? 'ok' : 'error');
};

/* ---------- 皮肤工坊（像素画布 + CSS 3D 预览） ---------- */
const SKIN_UV = {
  head: { front: [8, 8, 8, 8], right: [0, 8, 8, 8], left: [16, 8, 8, 8], back: [24, 8, 8, 8], top: [8, 0, 8, 8], bottom: [16, 0, 8, 8] },
  body: { front: [20, 20, 8, 12], right: [16, 20, 4, 12], left: [28, 20, 4, 12], back: [32, 20, 8, 12], top: [20, 16, 8, 4], bottom: [28, 16, 8, 4] },
  armR: { front: [44, 20, 4, 12], right: [40, 20, 4, 12], left: [48, 20, 4, 12], back: [52, 20, 4, 12], top: [44, 16, 4, 4], bottom: [48, 16, 4, 4] },
  armL: { front: [36, 52, 4, 12], right: [32, 52, 4, 12], left: [40, 52, 4, 12], back: [44, 52, 4, 12], top: [36, 48, 4, 4], bottom: [40, 48, 4, 4] },
  legR: { front: [4, 20, 4, 12], right: [0, 20, 4, 12], left: [8, 20, 4, 12], back: [12, 20, 4, 12], top: [4, 16, 4, 4], bottom: [8, 16, 4, 4] },
  legL: { front: [20, 52, 4, 12], right: [16, 52, 4, 12], left: [24, 52, 4, 12], back: [28, 52, 4, 12], top: [20, 48, 4, 4], bottom: [24, 48, 4, 4] },
  armRSlim: { front: [44, 20, 3, 12], right: [40, 20, 4, 12], left: [47, 20, 4, 12], back: [51, 20, 3, 12], top: [44, 16, 3, 4], bottom: [47, 16, 3, 4] },
  armLSlim: { front: [36, 52, 3, 12], right: [32, 52, 4, 12], left: [39, 52, 4, 12], back: [43, 52, 3, 12], top: [36, 48, 3, 4], bottom: [39, 48, 3, 4] },
};
const SKIN_SHADE = { front: 1, right: .93, left: .88, back: .86, top: 1, bottom: .82 };

function studioParts(model) {
  const slim = model === 'slim';
  const armW = slim ? 3 : 4;
  return [
    { uv: SKIN_UV.head, w: 8, h: 8, d: 8, x: 0, y: 10 },
    { uv: SKIN_UV.body, w: 8, h: 12, d: 4, x: 0, y: 0 },
    { uv: slim ? SKIN_UV.armRSlim : SKIN_UV.armR, w: armW, h: 12, d: 4, x: -(4 + armW / 2), y: 0 },
    { uv: slim ? SKIN_UV.armLSlim : SKIN_UV.armL, w: armW, h: 12, d: 4, x: 4 + armW / 2, y: 0 },
    { uv: SKIN_UV.legR, w: 4, h: 12, d: 4, x: -2, y: -12 },
    { uv: SKIN_UV.legL, w: 4, h: 12, d: 4, x: 2, y: -12 },
  ];
}
function studioFace(uv, face, w, h, d, s) {
  const [u, v, fw, fh] = uv[face];
  let transform = '';
  if (face === 'front') transform = 'translateZ(' + (d * s / 2) + 'px)';
  else if (face === 'back') transform = 'rotateY(180deg) translateZ(' + (d * s / 2) + 'px)';
  else if (face === 'right') transform = 'rotateY(90deg) translateZ(' + (w * s / 2) + 'px)';
  else if (face === 'left') transform = 'rotateY(-90deg) translateZ(' + (w * s / 2) + 'px)';
  else if (face === 'top') transform = 'rotateX(90deg) translateZ(' + (h * s / 2) + 'px)';
  else if (face === 'bottom') transform = 'rotateX(-90deg) translateZ(' + (h * s / 2) + 'px)';
  return '<div class="skin-face" style="width:' + (fw * s) + 'px;height:' + (fh * s) + 'px;' +
    'margin-left:' + (-fw * s / 2) + 'px;margin-top:' + (-fh * s / 2) + 'px;' +
    'background-size:' + (64 * s) + 'px ' + (64 * s) + 'px;' +
    'background-position:' + (-u * s) + 'px ' + (-v * s) + 'px;' +
    'filter:brightness(' + SKIN_SHADE[face] + ');transform:' + transform + '" data-face="' + face + '" data-uv="' + [u, v, fw, fh].join(',') + '"></div>';
}
function studioSyncFaceTextures() {
  const world = h('skinWorld');
  const canvas = h('skinCanvas');
  if (!world || !canvas) return;
  const source = canvas.toDataURL();
  world.querySelectorAll('.skin-face').forEach((face) => { face.style.backgroundImage = 'url(' + source + ')'; });
}
function paintStudio3D() {
  const world = h('skinWorld');
  if (!world || !S.studio) return;
  const s = 5;
  const source = h('skinCanvas').toDataURL();
  world.style.backgroundImage = 'none';
  world.innerHTML = studioParts(S.studio.model).map((part) =>
    '<div class="skin-box" style="transform:translate3d(' + (part.x * s) + 'px,' + (-part.y * s) + 'px,0)">' +
      Object.keys(SKIN_UV.head).map((face) => studioFace(part.uv, face, part.w, part.h, part.d, s)).join('') +
    '</div>'
  ).join('');
  world.querySelectorAll('.skin-face').forEach((face) => {
    face.style.backgroundImage = 'url(' + source + ')';
    face.addEventListener('pointerdown', (event) => {
      if (S.studio.mode !== 'brush') return;
      event.preventDefault();
      event.stopPropagation();
      S.studio.undo.push(studioSnapshot());
      if (S.studio.undo.length > 30) S.studio.undo.shift();
      S.studio.redo = [];
      S.studio.faceDrawing = true;
      studioPaintFace(face, event);
    });
    face.addEventListener('pointermove', (event) => {
      if (S.studio.mode !== 'brush' || !S.studio.faceDrawing) return;
      event.preventDefault();
      studioPaintFace(face, event);
    });
  });
  world.style.transform = 'scale(' + S.studio.zoom + ') rotateX(' + S.studio.pitch + 'deg) rotateY(' + S.studio.yaw + 'deg)';
}
function studioPaintFace(face, event) {
  const uv = (face.dataset.uv || '').split(',').map(Number);
  if (uv.length !== 4) return;
  const rect = face.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const x = uv[0] + Math.floor((event.clientX - rect.left) / rect.width * uv[2]);
  const y = uv[1] + Math.floor((event.clientY - rect.top) / rect.height * uv[3]);
  if (x < 0 || y < 0 || x >= 64 || y >= 64) return;
  const erase = event.buttons === 2 || S.studio.tool === 'eraser';
  const ctx = studioActiveLayer().canvas.getContext('2d');
  if (erase) ctx.clearRect(x, y, 1, 1);
  else {
    ctx.fillStyle = S.studio.color;
    ctx.fillRect(x, y, 1, 1);
  }
  studioComposite();
  studioSyncFaceTextures();
}

function refreshStudio() {
  studioComposite();
  paintStudio3D();
  renderStudioLayers();
  const canvas = h('skinCanvas');
  if (canvas) canvas.style.setProperty('--studio-zoom', String(S.studio.canvasZoom || 5));
  const state = h('studioState');
  if (state) state.textContent = '画布 64×64 · ' + (S.studio.canvasZoom || 5) + '× · 模型 ' + (S.studio.model === 'slim' ? 'Alex' : 'Steve') + ' · 图层 ' + (S.studio.layers ? S.studio.layers.length : 0) + '/8';
}

function studioNewLayerCanvas() {
  const canvas = document.createElement('canvas');
  canvas.width = 64;
  canvas.height = 64;
  return canvas;
}
function studioEnsureLayers() {
  if (S.studio.layers && S.studio.layers.length) return;
  const base = studioNewLayerCanvas();
  const visible = h('skinCanvas');
  if (visible) base.getContext('2d').drawImage(visible, 0, 0);
  S.studio.layers = [{ name: '底层', visible: true, canvas: base }];
  S.studio.active = 0;
  S.studio.redo = S.studio.redo || [];
}
function studioActiveLayer() {
  studioEnsureLayers();
  return S.studio.layers[S.studio.active] || S.studio.layers[0];
}
function studioComposite() {
  studioEnsureLayers();
  const visible = h('skinCanvas');
  if (!visible) return;
  const ctx = visible.getContext('2d');
  ctx.clearRect(0, 0, 64, 64);
  S.studio.layers.forEach((layer) => {
    if (layer.visible) ctx.drawImage(layer.canvas, 0, 0);
  });
}
function studioSnapshot() {
  studioEnsureLayers();
  return {
    active: S.studio.active,
    layers: S.studio.layers.map((layer) => ({ name: layer.name, visible: layer.visible, data: layer.canvas.toDataURL() })),
  };
}
function studioApplySnapshot(snap) {
  return Promise.all((snap.layers || []).map((layer) => new Promise((resolve) => {
    const img = new Image();
    const canvas = studioNewLayerCanvas();
    const ctx = canvas.getContext('2d');
    img.onload = () => { ctx.drawImage(img, 0, 0); resolve({ name: layer.name, visible: layer.visible, canvas }); };
    img.onerror = () => resolve({ name: layer.name, visible: layer.visible, canvas });
    img.src = layer.data;
  }))).then((layers) => {
    if (!layers.length) return;
    S.studio.layers = layers;
    S.studio.active = Math.min(snap.active || 0, layers.length - 1);
    studioComposite();
    refreshStudio();
  });
}
function renderStudioLayers() {
  const box = h('studioLayerList');
  if (!box) return;
  studioEnsureLayers();
  box.innerHTML = S.studio.layers.map((layer, index) =>
    '<div class="layer-row' + (index === S.studio.active ? ' active' : '') + '">' +
      '<button class="btn small ghost" data-act="studio-layer-vis" data-arg="' + index + '" title="显示/隐藏">' + (layer.visible ? '◉' : '○') + '</button>' +
      '<button class="btn small ghost" data-act="studio-layer-select" data-arg="' + index + '">' + esc(layer.name) + '</button>' +
    '</div>').join('');
}

function renderSkinStudio() {
  S.studio = S.studio || { tool: 'pencil', color: '#3fa45b', model: (S.data && S.data.account && S.data.account.skin_model) || 'classic', yaw: 18, pitch: -8, zoom: 1, canvasZoom: 5, drawing: false, mode: 'brush', undo: [] };
  h('pageTitle').textContent = '皮肤工坊';
  h('view').innerHTML =
    '<div class="page" style="gap:12px">' +
      '<div class="grid2" style="flex:1;min-height:0">' +
        '<div class="card"><div class="card-head"><h2>像素画布</h2><div class="head-actions">' +
          '<button class="btn small ghost" data-act="studio-undo">撤销</button>' +
          '<button class="btn small ghost" data-act="studio-redo">重做</button></div></div>' +
          '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
            '<div class="toolbar">' +
              '<button class="btn small ghost" data-act="studio-tool" data-arg="' + A('pencil') + '">画笔</button>' +
              '<button class="btn small ghost" data-act="studio-tool" data-arg="' + A('eraser') + '">橡皮</button>' +
              '<button class="btn small ghost" data-act="studio-tool" data-arg="' + A('fill') + '">填充</button>' +
              '<button class="btn small ghost" data-act="studio-tool" data-arg="' + A('pick') + '">吸色</button>' +
              '<button class="btn small ' + (S.studio.mode === 'brush' ? 'primary' : 'ghost') + '" data-act="studio-mode" data-arg="' + A('brush') + '">3D 作画</button>' +
              '<button class="btn small ' + (S.studio.mode === 'mouse' ? 'primary' : 'ghost') + '" data-act="studio-mode" data-arg="' + A('mouse') + '">鼠标旋转</button>' +
            '</div>' +
            '<div class="field-row"><input type="color" id="studioColor" value="' + S.studio.color + '" style="width:52px;height:34px;padding:2px" />' +
              '<span class="hint" id="studioState">画布 64×64</span>' +
              '<button class="btn small ghost" data-act="studio-canvas-zoom" data-arg="-1" title="缩小画布">－</button>' +
              '<button class="btn small ghost" data-act="studio-canvas-zoom" data-arg="1" title="放大画布">＋</button>' +
              '<button class="btn small ghost" data-act="studio-load-account">载入当前皮肤</button>' +
              '<button class="btn small ghost" data-act="studio-import">导入 PNG</button></div>' +
            '<div class="studio-canvas-wrap" id="studioCanvasWrap"><canvas id="skinCanvas" width="64" height="64"></canvas></div>' +
            '<div class="layer-bar"><span class="hint">图层（最多 8 层，导出时自动合并）</span>' +
              '<button class="btn small ghost" data-act="studio-layer-add">新建</button>' +
              '<button class="btn small ghost" data-act="studio-layer-del">删除</button>' +
              '<button class="btn small ghost" data-act="studio-layer-up">上移</button>' +
              '<button class="btn small ghost" data-act="studio-layer-down">下移</button></div>' +
            '<div class="layer-list" id="studioLayerList"></div>' +
            '<div class="hint">左键绘制 / 右键擦除；「填充」按 4 邻域铺满同色区域。画布可滚轮上下滚动，用「＋ / －」缩放，腿脚区域就在下方。画布与游戏内皮肤一一对应。</div>' +
          '</div></div>' +
        '<div class="card"><div class="card-head"><h2>3D 预览</h2><span class="hint">拖拽旋转 · 滚轮缩放</span></div>' +
          '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
            '<div class="skin-stage" id="skinStage"><div class="skin-world" id="skinWorld"></div></div>' +
            '<div class="toolbar"><button class="btn small ghost" data-act="studio-model">' +
              (S.studio.model === 'slim' ? 'Alex（细手臂）' : 'Steve（宽手臂）') + '</button>' +
              '<button class="btn small ghost" data-act="studio-plus">放大</button>' +
              '<button class="btn small ghost" data-act="studio-minus">缩小</button>' +
              '<button class="btn small ghost" data-act="studio-reset">重置视角</button></div>' +
            '<div class="hint">预览显示底层皮肤；第二层（帽子 / 外套）在游戏内仍会正常叠加。</div>' +
          '</div></div>' +
      '</div>' +
      '<div class="card" style="flex:none"><div class="card-body"><div class="toolbar">' +
        '<input type="text" id="studioName" placeholder="皮肤名称（可选）" style="flex:1" />' +
        '<button class="btn small primary" data-act="studio-save">保存并应用</button>' +
        '<button class="btn small ghost" data-act="studio-export">导出 PNG</button>' +
        '<button class="btn small ghost" data-act="studio-library">从皮肤库选择</button>' +
      '</div></div></div>' +
    '</div>';
  studioBindCanvas();
  const color = h('studioColor');
  if (color) color.addEventListener('input', () => { S.studio.color = color.value; });
  const stage = h('skinStage');
  if (stage) {
    let dragging = false, lastX = 0, lastY = 0;
    stage.addEventListener('pointerdown', (event) => {
      dragging = true;
      lastX = event.clientX;
      lastY = event.clientY;
      stage.setPointerCapture(event.pointerId);
    });
    stage.addEventListener('pointermove', (event) => {
      if (!dragging) return;
      S.studio.yaw += (event.clientX - lastX) * .6;
      S.studio.pitch = Math.max(-60, Math.min(60, S.studio.pitch - (event.clientY - lastY) * .5));
      lastX = event.clientX;
      lastY = event.clientY;
      paintStudio3D();
    });
    stage.addEventListener('pointerup', () => { dragging = false; S.studio.faceDrawing = false; });
    stage.addEventListener('pointercancel', () => { dragging = false; S.studio.faceDrawing = false; });
    stage.addEventListener('wheel', (event) => {
      event.preventDefault();
      S.studio.zoom = Math.max(.5, Math.min(2, S.studio.zoom + (event.deltaY < 0 ? .1 : -.1)));
      paintStudio3D();
    }, { passive: false });
    if (h('skinWorld')) h('skinWorld').addEventListener('contextmenu', (event) => event.preventDefault());
  }
  refreshStudio();
  (async () => {
    const layers = S.studio.layers || [];
    const base = layers[0] && layers[0].canvas;
    const empty = !base || !base.getContext('2d').getImageData(0, 0, 64, 64).data.some((value, index) => index % 4 === 3 && value > 0);
    const account = S.data && S.data.account;
    if (empty && account && account.skin_path) {
      const src = await call('preview', account.skin_path);
      if (src) await studioLoadImage(src);
    }
  })();
}
function studioBindCanvas() {
  const canvas = h('skinCanvas');
  if (!canvas) return;
  studioEnsureLayers();
  const px = (event) => {
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.floor((event.clientX - rect.left) / rect.width * 64),
      y: Math.floor((event.clientY - rect.top) / rect.height * 64),
    };
  };
  const paint = (event) => {
    const { x, y } = px(event);
    if (x < 0 || y < 0 || x >= 64 || y >= 64) return;
    if (S.studio.tool === 'pick') {
      studioComposite();
      const data = canvas.getContext('2d').getImageData(x, y, 1, 1).data;
      S.studio.color = '#' + [data[0], data[1], data[2]].map((n) => String(n.toString(16)).padStart(2, '0')).join('');
      if (h('studioColor')) h('studioColor').value = S.studio.color;
      return;
    }
    const erase = event.buttons === 2 || S.studio.tool === 'eraser';
    const ctx = studioActiveLayer().canvas.getContext('2d');
    if (erase) ctx.clearRect(x, y, 1, 1);
    else {
      ctx.fillStyle = S.studio.color;
      ctx.fillRect(x, y, 1, 1);
    }
  };
  canvas.addEventListener('contextmenu', (event) => event.preventDefault());
  canvas.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    S.studio.undo.push(studioSnapshot());
    if (S.studio.undo.length > 30) S.studio.undo.shift();
    S.studio.redo = [];
    canvas.setPointerCapture(event.pointerId);
    S.studio.drawing = true;
    if (S.studio.tool === 'fill' && event.button === 0) { studioFloodFill(px(event)); }
    else paint(event);
    refreshStudio();
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!S.studio.drawing) return;
    paint(event);
    studioComposite();
    studioSyncFaceTextures();
  });
  canvas.addEventListener('pointerup', () => { S.studio.drawing = false; });
  canvas.addEventListener('pointercancel', () => { S.studio.drawing = false; });
}
function studioFloodFill(start) {
  const ctx = studioActiveLayer().canvas.getContext('2d');
  const { x, y } = start;
  if (x < 0 || y < 0 || x >= 64 || y >= 64) return;
  const image = ctx.getImageData(0, 0, 64, 64);
  const data = image.data;
  const index = (x, y) => (y * 64 + x) * 4;
  const target = data.slice(index(x, y), index(x, y) + 4);
  const color = S.studio.color;
  const fill = [parseInt(color.slice(1, 3), 16), parseInt(color.slice(3, 5), 16), parseInt(color.slice(5, 7), 16), 255];
  if (target[0] === fill[0] && target[1] === fill[1] && target[2] === fill[2] && target[3] === fill[3]) return;
  const stack = [[x, y]];
  while (stack.length) {
    const [cx, cy] = stack.pop();
    if (cx < 0 || cy < 0 || cx >= 64 || cy >= 64) continue;
    const at = index(cx, cy);
    if (data[at] !== target[0] || data[at + 1] !== target[1] || data[at + 2] !== target[2] || data[at + 3] !== target[3]) continue;
    data[at] = fill[0]; data[at + 1] = fill[1]; data[at + 2] = fill[2]; data[at + 3] = fill[3];
    stack.push([cx + 1, cy]); stack.push([cx - 1, cy]); stack.push([cx, cy + 1]); stack.push([cx, cy - 1]);
  }
  ctx.putImageData(image, 0, 0);
}
function studioLoadImage(src) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const canvas = h('skinCanvas');
      if (!canvas) return resolve();
      if (img.width !== 64 || img.height !== 64) {
        toast('仅支持 64×64 皮肤（当前 ' + img.width + '×' + img.height + '）', 'error');
        return resolve();
      }
      const base = studioNewLayerCanvas();
      base.getContext('2d').drawImage(img, 0, 0, 64, 64);
      S.studio.layers = [{ name: '底层', visible: true, canvas: base }];
      S.studio.active = 0;
      S.studio.undo = [];
      S.studio.redo = [];
      refreshStudio();
      resolve();
    };
    img.onerror = () => { toast('皮肤图片读取失败', 'error'); resolve(); };
    img.src = src;
  });
}
ACT['skin-studio'] = () => setPage('skin');
ACT['studio-tool'] = (tool) => { S.studio.tool = tool; toast('工具：' + ({ pencil: '画笔', eraser: '橡皮', fill: '填充', pick: '吸色' }[tool] || tool), 'ok'); };
ACT['studio-undo'] = async () => {
  if (!S.studio.undo.length) return toast('没有可撤销的操作', 'error');
  const snap = S.studio.undo.pop();
  S.studio.redo.push(studioSnapshot());
  await studioApplySnapshot(snap);
};
ACT['studio-redo'] = async () => {
  if (!S.studio.redo || !S.studio.redo.length) return toast('没有可重做的操作', 'error');
  const snap = S.studio.redo.pop();
  S.studio.undo.push(studioSnapshot());
  await studioApplySnapshot(snap);
};
ACT['studio-mode'] = (mode) => {
  S.studio.mode = mode === 'mouse' ? 'mouse' : 'brush';
  renderSkinStudio();
};
ACT['studio-canvas-zoom'] = (delta) => {
  const step = Number(delta) || 0;
  S.studio.canvasZoom = Math.max(2, Math.min(12, (S.studio.canvasZoom || 5) + step));
  refreshStudio();
};
ACT['studio-layer-add'] = () => {
  studioEnsureLayers();
  if (S.studio.layers.length >= 8) return toast('最多 8 个图层', 'error');
  S.studio.undo.push(studioSnapshot());
  if (S.studio.undo.length > 30) S.studio.undo.shift();
  S.studio.redo = [];
  S.studio.layers.push({ name: '图层 ' + (S.studio.layers.length + 1), visible: true, canvas: studioNewLayerCanvas() });
  S.studio.active = S.studio.layers.length - 1;
  refreshStudio();
};
ACT['studio-layer-del'] = () => {
  studioEnsureLayers();
  if (S.studio.layers.length <= 1) return toast('至少保留一个图层', 'error');
  S.studio.undo.push(studioSnapshot());
  if (S.studio.undo.length > 30) S.studio.undo.shift();
  S.studio.layers.splice(S.studio.active, 1);
  S.studio.active = Math.min(S.studio.active, S.studio.layers.length - 1);
  refreshStudio();
};
ACT['studio-layer-up'] = () => {
  studioEnsureLayers();
  const index = S.studio.active;
  if (index >= S.studio.layers.length - 1) return;
  const layer = S.studio.layers.splice(index, 1)[0];
  S.studio.layers.splice(index + 1, 0, layer);
  S.studio.active = index + 1;
  refreshStudio();
};
ACT['studio-layer-down'] = () => {
  studioEnsureLayers();
  const index = S.studio.active;
  if (index <= 0) return;
  const layer = S.studio.layers.splice(index, 1)[0];
  S.studio.layers.splice(index - 1, 0, layer);
  S.studio.active = index - 1;
  refreshStudio();
};
ACT['studio-layer-vis'] = (index) => {
  studioEnsureLayers();
  const layer = S.studio.layers[Number(index)];
  if (!layer) return;
  layer.visible = !layer.visible;
  refreshStudio();
};
ACT['studio-layer-select'] = (index) => {
  studioEnsureLayers();
  S.studio.active = Number(index) || 0;
  renderStudioLayers();
};
ACT['studio-model'] = () => { S.studio.model = S.studio.model === 'slim' ? 'classic' : 'slim'; renderSkinStudio(); };
ACT['studio-plus'] = () => { S.studio.zoom = Math.min(2, S.studio.zoom + .15); paintStudio3D(); };
ACT['studio-minus'] = () => { S.studio.zoom = Math.max(.5, S.studio.zoom - .15); paintStudio3D(); };
ACT['studio-reset'] = () => { S.studio.yaw = 18; S.studio.pitch = -8; S.studio.zoom = 1; paintStudio3D(); };
ACT['studio-load-account'] = async () => {
  const account = S.data && S.data.account;
  if (!account || !account.skin_path) return toast('当前账号还没有皮肤文件，请先导入皮肤', 'error');
  const src = await call('preview', account.skin_path);
  await studioLoadImage(src);
  toast('已载入当前账号皮肤', 'ok');
};
ACT['studio-import'] = async () => {
  const res = await call('pick_skin_png');
  if (!res.ok) return;
  const src = await call('preview', res.path);
  await studioLoadImage(src);
};
ACT['studio-library'] = async () => {
  const res = await call('skin_library');
  const items = res.items || [];
  openSheet('从皮肤库选择',
    (items.length
      ? '<div class="skin-grid">' + items.map((item) =>
        '<button class="skin" data-act="studio-use" data-arg="' + A(item.path) + '" title="' + esc(item.name) + '">' +
        '<img alt="" src="' + esc(item.preview || '') + '" style="' + (item.preview ? '' : 'display:none') + '" /></button>').join('') + '</div>'
      : '<div class="empty">皮肤库还是空的。</div>'),
    '<button class="btn primary" id="studioLibClose">关闭</button>');
  if (h('studioLibClose')) h('studioLibClose').onclick = closeSheet;
};
ACT['studio-use'] = async (path) => {
  const src = await call('preview', path);
  await studioLoadImage(src);
  closeSheet();
};
ACT['studio-save'] = async () => {
  const canvas = h('skinCanvas');
  const res = await call('skin_save_editor', canvas.toDataURL(),
    (h('studioName') && h('studioName').value.trim()) || '', S.studio.model, true);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) await refreshBootstrap();
};
ACT['studio-export'] = async () => {
  const canvas = h('skinCanvas');
  const res = await call('skin_export_png', canvas.toDataURL(), (h('studioName') && h('studioName').value.trim()) || '');
  toast(res.message, res.ok ? 'ok' : 'error');
};

/* ---------- 联机 ---------- */
function renderServers() {
  h('view').innerHTML =
    '<div class="page flow" style="gap:12px">' +
      '<div class="card" style="flex:none"><div class="card-head"><h2>服务器列表</h2><div class="head-actions">' +
        '<button class="btn small primary" data-act="server-add">添加服务器</button>' +
        '<button class="btn small ghost" data-act="server-refresh">刷新</button></div></div>' +
        '<div class="card-body scroll" style="max-height:420px"><div class="list" id="serverList"><div class="loading"><span class="spinner"></span>正在读取…</div></div></div></div>' +
      '<div class="card" style="flex:none"><div class="card-head"><h2>陶瓦联机（房间码 P2P）</h2><div class="head-actions">' +
        '<button class="btn small ghost" data-act="terra-refresh">刷新状态</button></div></div>' +
        '<div class="card-body" id="terraBox"><div class="loading"><span class="spinner"></span>检测中…</div></div></div>' +
    '</div>';
  loadServers();
  loadTerra();
}
function serverRows(items) {
  if (!items.length) return '<div class="empty">还没有添加服务器。可手动添加，或在启动页选择版本后自动连接已激活的服务器。</div>';
  return items.map((item) =>
    '<div class="row"><div class="row-main"><b>' + esc(item.name) + (item.active ? ' <span class="tag accent">启动即连接</span>' : '') + '</b>' +
      '<small class="mono">' + esc(item.host) + ':' + esc(item.port) + '</small>' +
      (item.note ? '<small>' + esc(item.note) + '</small>' : '') + '</div>' +
      '<div class="row-actions">' +
        '<button class="btn small primary" data-act="server-ping" data-arg="' + A({ host: item.host, port: item.port, name: item.name }) + '">测试</button>' +
        '<button class="btn small ghost" data-act="server-activate" data-arg="' + A(item.id) + '">' + (item.active ? '取消连接' : '设为启动连接') + '</button>' +
        '<button class="btn small danger" data-act="server-remove" data-arg="' + A(item.id) + '">删除</button>' +
      '</div></div>'
  ).join('');
}
async function loadServers() {
  let items = [];
  try { items = await call('servers'); } catch (_) { /* 后端未就绪 */ }
  const box = h('serverList'); if (!box) return;
  box.innerHTML = serverRows(items || []);
}
ACT['server-refresh'] = () => loadServers();
ACT['server-add'] = () => {
  openSheet('添加服务器',
    '<div class="field"><label>名称</label><input type="text" id="srvName" placeholder="例如：朋友的生存服" /></div>' +
    '<div class="field-row" style="margin-top:10px"><div class="field" style="flex:1"><label>地址</label><input type="text" id="srvHost" placeholder="mc.example.com" /></div>' +
    '<div class="field" style="width:110px"><label>端口</label><input type="number" id="srvPort" value="25565" /></div></div>' +
    '<div class="field" style="margin-top:10px"><label>备注（可选）</label><input type="text" id="srvNote" /></div>',
    '<button class="btn ghost" id="srvCancel">取消</button><button class="btn primary" id="srvSave">保存</button>');
  h('srvCancel').onclick = closeSheet;
  h('srvSave').onclick = async () => {
    const host = h('srvHost').value.trim();
    if (!host) return toast('请输入服务器地址', 'error');
    const res = await call('server_add', h('srvName').value.trim(), host, Number(h('srvPort').value || 25565), h('srvNote').value.trim());
    if (!res.ok) return toast(res.message, 'error');
    closeSheet(); await loadServers(); toast('服务器已添加', 'ok');
  };
};
ACT['server-ping'] = async (arg) => {
  const host = arg && arg.host; const port = (arg && arg.port) || 25565;
  if (!host) return;
  setStatus('正在测试 ' + host + '…');
  const res = await call('server_ping', host, Number(port));
  setStatus('就绪');
  const lines =
    '<div class="detail-hero">' + (res.icon ? '<img src="' + res.icon + '" alt="" />' : '') +
      '<div class="d-main"><b>' + esc((arg && arg.name) || host) + '</b><small class="mono">' + esc(host) + ':' + esc(port) + '</small>' +
      '<small>' + (res.online ? '在线 · ' + esc(String(res.players)) + '/' + esc(String(res.max_players)) + ' 人 · 延迟 ' + esc(String(res.latency)) + ' ms' : '离线 / 无法连接') + '</small></div></div>' +
    (res.version ? '<div class="hint">版本：' + esc(res.version) + '</div>' : '') +
    (res.motd ? '<div class="detail-desc">' + esc(res.motd) + '</div>' : '') +
    (res.online ? '' : '<div class="empty">' + esc(res.message || '服务器没有响应，请检查地址与端口。') + '</div>');
  openSheet('服务器状态', lines, '<button class="btn ghost" id="pingClose">关闭</button>');
  h('pingClose').onclick = closeSheet;
};
ACT['server-activate'] = async (id) => {
  const res = await call('server_activate', id);
  if (!res.ok) return toast(res.message, 'error');
  await loadServers();
  toast('已更新启动连接设置', 'ok');
};
ACT['server-remove'] = async (id) => {
  if (!(await ask('删除服务器', '只删除启动器里的这条记录，不影响服务器本身。'))) return;
  const res = await call('server_remove', id);
  if (!res.ok) return toast(res.message, 'error');
  await loadServers();
};
const TERRA_LABEL = {
  waiting: ['空闲', 'warn'], 'not-installed': ['未安装', 'warn'], starting: ['正在启动', 'warn'],
  'host-scanning': ['等待局域网世界', 'warn'], 'host-starting': ['正在创建房间', 'warn'],
  'host-ok': ['房间已创建', 'accent'], 'guest-connecting': ['正在连接', 'warn'],
  'guest-starting': ['正在建立连接', 'warn'], 'guest-ok': ['已进入房间', 'accent'],
  busy: ['处理中', 'warn'], error: ['出错了', 'warn'], exception: ['联机失败', 'warn'],
};
let terraTimer = null;
let terraDeadline = 0;
let terraPingUrl = '';
let terraPingText = '';
let terraPingOk = null;

async function loadTerra() {
  const box = h('terraBox'); if (!box) return;
  let st;
  try { st = await call('terracotta_state'); } catch (err) { box.innerHTML = '<div class="empty">' + esc(err.message || err) + '</div>'; return; }
  const info = TERRA_LABEL[st.state] || [st.state || '空闲', 'warn'];
  const room = String(st.room || '');
  const player = (S.data && S.data.account && S.data.account.name) || 'Player';
  const busy = ['starting', 'busy', 'host-scanning', 'host-starting', 'guest-connecting', 'guest-starting'].includes(st.state);
  const url = String(st.url || '');
  const showPing = !!url && (st.state === 'host-ok' || st.state === 'guest-ok');
  if (!showPing) { terraPingUrl = ''; terraPingText = ''; terraPingOk = null; }
  box.innerHTML =
    '<div class="toolbar"><span class="tag ' + (st.installed ? 'accent' : '') + '">' + (st.installed ? '已安装' : '未安装') + '</span>' +
      '<span class="tag ' + (st.running ? 'accent' : 'warn') + '">' + (st.running ? '运行中 · 本地端口 ' + esc(String(st.port)) : '未运行') + '</span>' +
      '<span class="tag ' + info[1] + '">' + esc(info[0]) + '</span>' +
      '<span class="spacer"></span>' +
      '<button class="btn small primary" data-act="terra-install">下载安装</button>' +
      '<button class="btn small ghost" data-act="terra-start">启动服务</button>' +
      '<button class="btn small ghost" data-act="terra-stop">停止</button></div>' +
    (st.detail ? '<div class="hint" style="margin-top:8px">' + esc(st.detail) + '</div>' : '') +
    (room ? '<div class="room-code" style="margin-top:10px"><span class="hint">房间码（分享码）</span><div class="toolbar" style="margin-top:4px">' +
      '<b class="mono" style="font-size:15px;letter-spacing:1px">' + esc(room) + '</b>' +
      '<span class="spacer"></span><button class="btn small primary" data-act="terra-copy">复制分享码</button></div></div>' : '') +
    '<div class="field-row" style="margin-top:10px;gap:8px">' +
      '<input type="text" id="terraPlayer" placeholder="玩家名" style="width:140px" value="' + esc(player) + '" />' +
      '<input type="text" id="terraRoom" placeholder="房间码 U/XXXX-XXXX-XXXX-XXXX" style="flex:1;min-width:180px" />' +
      '<button class="btn small primary" data-act="terra-host"' + (busy ? ' disabled' : '') + '>创建房间</button>' +
      '<button class="btn small ghost" data-act="terra-join"' + (busy ? ' disabled' : '') + '>加入房间</button>' +
      '<button class="btn small ghost" data-act="terra-leave">结束联机</button>' +
    '</div>' +
    (showPing ? '<div class="hint" id="terraPing" style="margin-top:8px' + (terraPingOk === null ? '' : (terraPingOk ? ';color:#65d46e' : ';color:#e0b15c')) + '">' +
      '<span id="terraPingText">' + esc(terraPingText || ('正在检测 ' + url + ' 是否可用…')) + '</span> ' +
      '<button class="btn small ghost" data-act="terra-ping">重新检测</button></div>' : '') +
    '<div class="hint" style="margin-top:10px">房主先在游戏里打开存档并选择「对局域网开放」，再点创建房间；把生成的分享码发给好友即可加入。</div>';
  if (showPing && terraPingUrl !== url) {
    terraPingUrl = url;
    terraPingText = '';
    terraPingOk = null;
    call('terracotta_ping', url).then((r) => {
      terraPingOk = !!(r && r.online);
      terraPingText = url + ' · ' + (r && r.online
        ? ('地址可用' + (r.latency >= 0 ? ' · 延迟 ' + r.latency + ' ms' : '') + (r.version ? ' · 版本 ' + r.version : ''))
        : ('暂时无法连接：' + ((r && r.message) || '未知原因') + '（可稍后重试）'));
      const el = h('terraPingText');
      if (el) el.textContent = terraPingText;
      const wrap = h('terraPing');
      if (wrap) wrap.style.color = terraPingOk ? '#65d46e' : '#e0b15c';
    }).catch(() => {});
  }
}
ACT['terra-ping'] = () => {
  terraPingUrl = '';
  terraPingText = '';
  terraPingOk = null;
  loadTerra();
};
function terraPlayer() {
  return (h('terraPlayer') && h('terraPlayer').value.trim()) || 'Player';
}
function terraPoll() {
  if (terraTimer) { clearTimeout(terraTimer); terraTimer = null; }
  terraDeadline = Date.now() + 90 * 1000;
  const tick = async () => {
    terraTimer = null;
    if (S.page !== 'servers' || !h('terraBox')) return;
    await loadTerra();
    let st = null;
    try { st = await call('terracotta_state'); } catch (_) {}
    const state = (st && st.state) || '';
    if (state === 'host-ok' || state === 'guest-ok' || state === 'error' || state === 'exception' || state === 'waiting') return;
    if (Date.now() > terraDeadline) return;
    terraTimer = setTimeout(tick, 2000);
  };
  terraTimer = setTimeout(tick, 1500);
}
ACT['terra-refresh'] = () => loadTerra();
ACT['terra-copy'] = async () => {
  let st = null;
  try { st = await call('terracotta_state'); } catch (_) {}
  const room = (st && st.room) || '';
  if (!room) return toast('当前没有可复制的房间码，请先创建房间', 'error');
  copyText(room);
};
ACT['terra-install'] = async () => {
  const res = await call('terracotta_install');
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message, 'ok');
  const job = await watchJob(res.job);
  if (job && job.state === 'ok') toast('陶瓦联机安装完成', 'ok');
  else toast((job && (job.error || job.stage)) || '安装未完成', 'error');
  loadTerra();
};
ACT['terra-start'] = async () => {
  const res = await call('terracotta_start');
  if (!res.ok) return toast(res.message, 'error');
  const job = await watchJob(res.job);
  if (job && job.state === 'ok') {
    const nodes = (job.result && job.result.nodes) || [];
    openSheet('陶瓦联机已启动',
      '<div class="hint">本地端口：<b class="mono">' + esc(String((job.result && job.result.port) || '')) + '</b></div>' +
      '<div class="empty">' + (nodes.length ? '可用公开节点：' + nodes.map((n) => esc(typeof n === 'string' ? n : (n.name || n.host || ''))).join('、') : '暂未获取到公开节点。') + '</div>',
      '<button class="btn ghost" id="terraOk">好</button>');
    h('terraOk').onclick = closeSheet;
    terraPoll();
  } else {
    toast((job && (job.error || job.stage)) || '启动失败', 'error');
  }
  loadTerra();
};
ACT['terra-host'] = async () => {
  const res = await call('terracotta_host', terraPlayer());
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message || '正在创建房间', 'ok');
  watchJob(res.job).then((job) => {
    if (job && job.state === 'ok') toast('房间已创建，可复制分享码', 'ok');
    else if (job) toast(job.error || job.stage || '创建房间失败', 'error');
    loadTerra();
    terraPoll();
  });
  terraPoll();
};
ACT['terra-join'] = async () => {
  const room = (h('terraRoom') && h('terraRoom').value.trim()) || '';
  if (!room) return toast('请填写房间码', 'error');
  const res = await call('terracotta_join', room, terraPlayer());
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message || '正在连接房间', 'ok');
  watchJob(res.job).then((job) => {
    if (job && job.state === 'ok') toast('已进入房间', 'ok');
    else if (job) toast(job.error || job.stage || '加入房间失败', 'error');
    loadTerra();
    terraPoll();
  });
  terraPoll();
};
ACT['terra-leave'] = async () => {
  if (terraTimer) { clearTimeout(terraTimer); terraTimer = null; }
  const res = await call('terracotta_leave');
  if (!res.ok) return toast(res.message, 'error');
  loadTerra(); toast('已结束联机', 'ok');
};
ACT['terra-stop'] = async () => {
  if (terraTimer) { clearTimeout(terraTimer); terraTimer = null; }
  const res = await call('terracotta_stop');
  if (!res.ok) return toast(res.message, 'error');
  loadTerra(); toast('陶瓦联机已停止', 'ok');
};

/* ---------- 创世神面板 ---------- */
const CR_TABS = [['status', '状态'], ['inventory', '背包'], ['ability', '能力'], ['world', '世界'], ['tools', '工具']];
const CR_ERAS = {
  legacy: '1.13 前（数字 ID）', flattened: '1.13+ 扁平化', components: '1.20.5+ 组件化',
  pre_anvil: '非 Anvil（只读）', unknown: '未知（只读）',
};
const CR_OVER_CAP = '您输入的值已超出原版上限，强制写入可能导致游戏崩溃或读档失败，是否继续？';

function crNum(id, fallback) {
  const node = h(id);
  if (!node) return fallback == null ? 0 : fallback;
  const value = Number(String(node.value).trim());
  return Number.isFinite(value) ? value : (fallback == null ? 0 : fallback);
}
function crText(id, fallback) {
  const node = h(id);
  const text = node ? String(node.value).trim() : '';
  return text || (fallback == null ? '' : fallback);
}
function crChecked(id) { const node = h(id); return !!(node && node.checked); }
function crField(label, input) {
  return '<div style="display:flex;flex-direction:column;gap:4px"><span class="hint">' + esc(label) + '</span>' + input + '</div>';
}
function crParseEnchants(text, cap) {
  const result = [];
  String(text || '').split(',').forEach((chunk) => {
    const part = chunk.trim();
    if (!part) return;
    const index = part.lastIndexOf(':');
    if (index < 0) throw new Error('附魔「' + part + '」缺少等级，应写成 sharpness:5');
    const name = part.slice(0, index).trim();
    const level = Number(part.slice(index + 1));
    if (!name) throw new Error('附魔「' + part + '」缺少名称');
    if (!Number.isInteger(level) || level < 0 || level > cap) throw new Error('附魔等级必须在 0 - ' + cap + ' 之间');
    result.push({ id: name.indexOf(':') >= 0 ? name : 'minecraft:' + name, level: level });
  });
  return result;
}

async function renderCreator() {
  const view = h('view');
  if (!view) return;
  if (!S.creator) {
    S.creator = {
      loaded: false, worlds: [], root: '', world: '', state: null, player: null, playerUuid: 'level',
      tab: 'status', items: [], ender: [], attributes: [], effects: [], catalog: null, catalogTotal: 0,
      editing: null, form: {}, opsDir: '', ops: [], backups: [], region: null, preview: null,
      advConfirm: false, restoreTarget: '', adv: [], advSelected: {}, advAllConfirm: false,
      convert: { source: '', target: '1.21.4', era: 'auto' },
    };
  }
  const sc = S.creator;
  if (!sc.loaded) {
    view.innerHTML = '<div class="page flow"><div class="loading"><span class="spinner"></span>扫描存档中…</div></div>';
    try {
      const res = await call('creator_worlds');
      sc.worlds = (res && res.items) || [];
      sc.root = (res && res.dir) || '';
      sc.loaded = true;
      if (sc.worlds.length) await creatorLoadWorld(sc.worlds[0].path);
    } catch (err) {
      view.innerHTML = '<div class="page flow"><div class="card"><div class="card-body"><div class="empty">' +
        esc(err.message || err) + '</div></div></div></div>';
      return;
    }
  }
  creatorPaint();
}

async function creatorLoadWorld(path) {
  const sc = S.creator;
  const res = await call('creator_open', path);
  if (!res || !res.ok) { toast((res && res.message) || '读取存档失败', 'error'); return; }
  const state = res.state;
  sc.world = path;
  sc.state = state;
  sc.form = {};
  sc.items = [];
  sc.ender = [];
  sc.attributes = [];
  sc.effects = [];
  sc.catalog = null;
  sc.editing = null;
  sc.preview = null;
  sc.region = null;
  sc.backups = [];
  sc.advConfirm = false;
  sc.adv = [];
  sc.advSelected = {};
  sc.advAllConfirm = false;
  sc.convert = { source: path, target: '1.21.4', era: 'auto' };
  sc.playerUuid = (state.players[0] && state.players[0].uuid) || 'level';
  await creatorLoadPlayer(sc.playerUuid);
  await creatorLoadAdvancements();
}

async function creatorLoadAdvancements() {
  const sc = S.creator;
  if (!sc.world) return;
  const res = await call('creator_advancements', sc.world, sc.playerUuid);
  sc.adv = (res && res.ok && res.report && res.report.entries) || [];
}

async function creatorLoadPlayer(uuid) {
  const sc = S.creator;
  if (!sc.state) return;
  const res = await call('creator_read_player', sc.world, uuid);
  if (!res || !res.ok) { toast((res && res.message) || '读取玩家失败', 'error'); return; }
  const player = res.player || {};
  sc.playerUuid = uuid;
  sc.player = player;
  sc.items = (player.inventory || []).map((item) => Object.assign({}, item));
  sc.ender = (player.ender_items || []).map((item) => Object.assign({}, item));
  sc.attributes = (player.attributes || []).map((item) => Object.assign({}, item));
  sc.effects = (player.effects || []).map((item) => Object.assign({}, item));
  sc.editing = null;
  sc.preview = null;
  sc.form = {};
}

function crCollectRows() {
  const sc = S.creator;
  const attrs = [];
  document.querySelectorAll('[data-cr-attr]').forEach((node) => {
    const index = Number(node.dataset.crAttr);
    attrs[index] = attrs[index] || { name: '', base: 0, modifiers: [] };
    if (node.dataset.field === 'name') attrs[index].name = String(node.value).trim();
    else attrs[index].base = Number(node.value || 0);
  });
  document.querySelectorAll('[data-cr-mod]').forEach((node) => {
    const attrIndex = Number(node.dataset.crMod);
    const modIndex = Number(node.dataset.index);
    attrs[attrIndex] = attrs[attrIndex] || { name: '', base: 0, modifiers: [] };
    attrs[attrIndex].modifiers = attrs[attrIndex].modifiers || [];
    attrs[attrIndex].modifiers[modIndex] = attrs[attrIndex].modifiers[modIndex] || {
      name: '', amount: 0, operation: 'add_value',
    };
    const field = node.dataset.field;
    if (field === 'operation') attrs[attrIndex].modifiers[modIndex].operation = String(node.value);
    else attrs[attrIndex].modifiers[modIndex][field] = Number(node.value || 0);
  });
  attrs.forEach((entry) => {
    if (!entry) return;
    entry.modifiers = (entry.modifiers || []).filter(Boolean).map((mod) =>
      Object.assign({ name: entry.name }, mod));
  });
  sc.attributes = attrs.filter((item) => item && item.name);
  const effects = [];
  document.querySelectorAll('[data-cr-effect]').forEach((node) => {
    const index = Number(node.dataset.crEffect);
    effects[index] = effects[index] || { id: 1, amplifier: 0, duration: 200, hide_particles: false };
    const field = node.dataset.field;
    if (field === 'hide') effects[index].hide_particles = !!node.checked;
    else effects[index][field] = Number(node.value || 0);
  });
  sc.effects = effects.filter(Boolean);
}

const CR_RULES = [
  ['keepInventory', '死亡保留物品'],
  ['doDaylightCycle', '昼夜循环'],
  ['doMobSpawning', '自然生成怪物'],
  ['doFireTick', '火焰蔓延'],
  ['doWeatherCycle', '天气循环'],
  ['doMobLoot', '生物掉落物'],
  ['doTileDrops', '方块掉落物'],
  ['mobGriefing', '生物破坏方块'],
  ['naturalRegeneration', '自然回血'],
  ['showCoordinates', '显示坐标'],
  ['announceAdvancements', '广播成就'],
];

function crCollectForm() {
  const sc = S.creator;
  if (!sc || !sc.state) return;
  if (h('crHealth')) {
    Object.assign(sc.form, {
      pos: [crNum('crX'), crNum('crY'), crNum('crZ')],
      health: crNum('crHealth'), food: crNum('crFood'),
      food_level: Math.round(crNum('crFoodLevel')),
      safe_teleport: crChecked('crSafeTp'),
      xp_level: Math.round(crNum('crXp')),
      game_type: Number(crText('crMode', '0')), dimension: crText('crDim', 'minecraft:overworld'),
    });
  }
  if (h('crTime')) {
    const gamerules = { randomTickSpeed: String(Math.round(crNum('crRandomTick', 3))) };
    CR_RULES.forEach(([key]) => { gamerules[key] = crChecked('crRule_' + key) ? 'true' : 'false'; });
    sc.form.level = {
      time: Math.round(crNum('crTime')), day_time: Math.round(crNum('crDayTime')),
      weather: crText('crWeather', 'clear'), border_size: crNum('crBorder'),
      border_center: [crNum('crBorderX'), crNum('crBorderZ')],
      spawn: [Math.round(crNum('crSpawnX')), Math.round(crNum('crSpawnY')), Math.round(crNum('crSpawnZ'))],
      gamerules: gamerules,
    };
  }
  crCollectRows();
}

function creatorPaint() {
  const view = h('view');
  if (!view) return;
  const sc = S.creator;
  const state = sc.state;
  if (!state) {
    view.innerHTML = '<div class="page flow"><div class="card"><div class="card-head"><h2>创世神面板</h2>' +
      '<div class="head-actions"><button class="btn small ghost" data-act="cr-refresh">重新扫描</button>' +
      '<button class="btn small ghost" data-act="cr-pick-world">选择存档目录</button></div></div>' +
      '<div class="card-body"><div class="hint">在 ' + esc(sc.root || '游戏目录/saves') +
      ' 下没有找到带 level.dat 的存档。也可以手动选择其他目录。</div></div></div></div>';
    return;
  }
  const caps = state.vanilla_caps || {};
  const editable = !!state.editable;
  const worldOptions = sc.worlds.map((item) =>
    '<option value="' + esc(item.path) + '"' + (item.path === sc.world ? ' selected' : '') + '>' + esc(item.name) + '</option>'
  ).join('');
  const playerOptions = (state.players || []).map((item) =>
    '<option value="' + esc(item.uuid) + '"' + (item.uuid === sc.playerUuid ? ' selected' : '') + '>' + esc(item.name) + '</option>'
  ).join('');
  const meta = esc(state.name) + ' · DataVersion ' + esc(state.data_version) + ' · ' +
    esc(state.version_name || '未知版本') + ' · ' + esc(CR_ERAS[state.era] || state.era) +
    (editable ? '' : ' · 只读：' + esc(state.reason || ''));
  const pending = (sc.pending || []).length
    ? '<div class="hint" style="color:#e0a33e">检测到未完成事务：' + esc(sc.pending.join(', ')) + '，请先处理世界目录下的 .mikancl-tx。</div>'
    : '';
  const tabs = CR_TABS.map(([id, label]) =>
    '<button class="chip' + (sc.tab === id ? ' active' : '') + '" data-act="cr-tab" data-arg="' + id + '">' + label + '</button>'
  ).join('');
  let body = '';
  if (!editable) body = '<div class="empty">该存档年代无法安全编辑：' + esc(state.reason || '') + '</div>';
  else if (sc.tab === 'status') body = crStatusHtml(sc, caps);
  else if (sc.tab === 'inventory') body = crInventoryHtml(sc, caps);
  else if (sc.tab === 'ability') body = crAbilityHtml(sc, caps);
  else if (sc.tab === 'world') body = crWorldHtml(sc, caps);
  else body = crToolsHtml(sc);
  const preview = sc.preview ? crPreviewHtml(sc) : '';
  view.innerHTML =
    '<div class="page flow"><div style="display:flex;flex-direction:column;gap:12px;padding-right:4px">' +
      '<div class="card"><div class="card-head"><h2>创世神面板</h2><div class="head-actions">' +
        '<button class="btn small ghost" data-act="cr-refresh">重新扫描</button>' +
        '<button class="btn small ghost" data-act="cr-pick-world">选择存档目录</button></div></div>' +
        '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
          '<div class="field-row"><select id="crWorld" data-cr-change="world" style="min-width:200px;flex:1">' + worldOptions + '</select>' +
          '<select id="crPlayer" data-cr-change="player">' + playerOptions + '</select></div>' +
          '<div class="hint">离线深度编辑：请先完全关闭游戏。保存前会强制完整备份，写入失败按事务回滚；数值上限按原版理论值放开。</div>' +
          '<div class="hint">' + meta + '</div>' + pending +
        '</div></div>' +
      '<div class="card"><div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
        '<div class="chips">' + tabs + '</div><div id="crBody">' + body + '</div>' + preview +
        '<div class="toolbar"><span class="hint" style="flex:1">' + (editable ? '修改不会立即写入，先预览再确认。' : '只读模式') + '</span>' +
        '<button class="btn primary" data-act="cr-preview"' + (editable ? '' : ' disabled') + '>预览并保存</button></div>' +
      '</div></div>' +
    '</div></div>';
}

function crStatusHtml(sc, caps) {
  const f = sc.form || {};
  const p = sc.player || {};
  const pos = f.pos || p.pos || [0, 64, 0];
  const mode = f.game_type != null ? f.game_type : (p.game_type || 0);
  return '<div class="grid2">' +
    crField('坐标 X', '<input id="crX" type="number" step="0.001" value="' + Number(pos[0] || 0) + '">') +
    crField('坐标 Y', '<input id="crY" type="number" step="0.001" value="' + Number(pos[1] || 0) + '">') +
    crField('坐标 Z', '<input id="crZ" type="number" step="0.001" value="' + Number(pos[2] || 0) + '">') +
    crField('生命（上限 ' + Number(caps.health || 1024) + '）', '<input id="crHealth" type="number" step="0.01" min="0" max="' + Number(caps.health || 1024) + '" value="' + Number(f.health != null ? f.health : (p.health || 20)) + '">') +
    crField('饥饿值 foodLevel（原版 20）', '<input id="crFoodLevel" type="number" min="0" max="20" value="' + Math.round(f.food_level != null ? f.food_level : (p.food_level != null ? p.food_level : 20)) + '">') +
    crField('饱和度 foodSaturationLevel', '<input id="crFood" type="number" step="0.01" min="0" max="' + Number(caps.saturation || 20) + '" value="' + Number(f.food != null ? f.food : (p.food || 5)) + '">') +
    crField('经验等级（上限 ' + Number(caps.xp_level || 21863) + '）', '<input id="crXp" type="number" min="0" max="' + Number(caps.xp_level || 21863) + '" value="' + Math.round(f.xp_level != null ? f.xp_level : (p.xp_level || 0)) + '">') +
    crField('游戏模式', '<select id="crMode">' +
      [['0', '生存'], ['1', '创造'], ['2', '冒险'], ['3', '旁观']].map(([value, label]) =>
        '<option value="' + value + '"' + (Number(value) === Number(mode) ? ' selected' : '') + '>' + value + ' · ' + label + '</option>').join('') +
      '</select>') +
    crField('维度', '<input id="crDim" type="text" value="' + esc(f.dimension || p.dimension || 'minecraft:overworld') + '">') +
  '</div>' +
  '<label class="chip" style="margin-top:10px"><input id="crSafeTp" type="checkbox"' + (f.safe_teleport ? ' checked' : '') + '> 安全传送（保存时按目标 X/Z 自动寻找最高方块落点）</label>';
}

const CR_OPS = [
  ['add_value', '加算'], ['add_multiplied_base', '乘算（基础）'], ['add_multiplied_total', '乘算（总）'],
];

function crOpOptions(current) {
  const value = typeof current === 'string' ? current : 'add_value';
  return CR_OPS.map(([id, label]) =>
    '<option value="' + id + '"' + (id === value ? ' selected' : '') + '>' + label + '</option>').join('');
}

function crItemRow(item, index, store) {
  const ench = (item.enchantments || []).map((e) =>
    String(e.id).replace('minecraft:', '') + ' ' + e.level).join(', ');
  const attrs = (item.attributes || []).map((a) =>
    String(a.name || '').replace('minecraft:generic.', '') + ' ' + Number(a.amount || 0)).join(', ');
  return '<div class="row"><div class="row-main"><b>' + esc(item.id || '(未设置)') + '</b>' +
    '<span class="hint">槽位 ' + esc(item.slot) + ' · 数量 ' + esc(item.count) +
    (ench ? ' · ' + esc(ench) : '') + (attrs ? ' · ' + esc(attrs) : '') +
    (item.tag_json ? ' · 含 Raw NBT' : '') + '</span></div>' +
    '<button class="btn small ghost" data-act="cr-edit-item" data-arg="' + store + ':' + index + '">编辑</button>' +
    '<button class="btn small danger" data-act="cr-del-item" data-arg="' + store + ':' + index + '">删除</button></div>';
}

function crInventoryHtml(sc, caps) {
  const rows = sc.items.map((item, index) => crItemRow(item, index, 'inventory')).join('');
  const ender = (sc.ender || []).map((item, index) => crItemRow(item, index, 'ender')).join('');
  let editor = '';
  if (sc.editing) {
    const ed = sc.editing;
    const enchants = (ed.enchantments || []).map((e) =>
      String(e.id).replace('minecraft:', '') + ':' + e.level).join(',');
    const raw = ed.tag_json ? JSON.stringify(ed.tag_json, null, 2) : '';
    const attrs = (ed.attributes || []).map((entry, index) => {
      const row = [
        '<input data-cr-itemattr="' + index + '" data-field="name" type="text" placeholder="minecraft:generic.attack_damage" value="' + esc(entry.name || '') + '">',
        '<input data-cr-itemattr="' + index + '" data-field="amount" type="number" step="0.01" value="' + Number(entry.amount || 0) + '">',
        '<select data-cr-itemattr="' + index + '" data-field="operation">' + crOpOptions(entry.operation) + '</select>',
        '<input data-cr-itemattr="' + index + '" data-field="slot" type="text" placeholder="any / mainhand" value="' + esc(entry.slot || 'any') + '">',
        '<button class="btn small danger" data-act="cr-del-itemattr" data-arg="' + index + '">删除</button>',
      ];
      return '<div class="row">' + row.join('') + '</div>';
    }).join('');
    editor = '<div class="card" style="margin-top:10px"><div class="card-head"><h2>' +
      (ed.store === 'ender' ? '末影箱物品编辑' : '物品编辑') + '</h2></div>' +
      '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
      '<div class="grid2">' +
      crField('物品 ID', '<input id="crItemId" type="text" placeholder="minecraft:diamond_sword" value="' + esc(ed.id || '') + '">') +
      crField('槽位（36-39 护甲 / 40 副手 / 末影箱 0-26）', '<input id="crItemSlot" type="number" min="0" max="255" value="' + Number(ed.slot || 0) + '">') +
      crField('数量（上限 ' + Number(caps.max_count || 127) + '）', '<input id="crItemCount" type="number" min="0" max="' + Number(caps.max_count || 127) + '" value="' + Number(ed.count || 1) + '">') +
      crField('损伤值', '<input id="crItemDamage" type="number" min="0" value="' + Number(ed.damage || 0) + '">') +
      crField('附魔（≤' + Number(caps.enchant_level || 255) + ' 级）', '<input id="crItemEnch" type="text" placeholder="sharpness:255,unbreaking:3" value="' + esc(enchants) + '">') +
      '</div>' +
      '<div class="hint">属性修饰符：名字填「攻击伤害 / 护甲 / 移速」等，数值按原版理论上限放开；1.20.5+ 写入组件，旧版写入 tag.AttributeModifiers。</div>' +
      '<div class="chips">' +
        '<button class="btn small ghost" data-act="cr-itemattr-add" data-arg="minecraft:generic.attack_damage">+ 攻击伤害</button>' +
        '<button class="btn small ghost" data-act="cr-itemattr-add" data-arg="minecraft:generic.armor">+ 护甲</button>' +
        '<button class="btn small ghost" data-act="cr-itemattr-add" data-arg="minecraft:generic.movement_speed">+ 移速</button>' +
        '<button class="btn small ghost" data-act="cr-itemattr-add" data-arg="minecraft:generic.attack_speed">+ 攻速</button>' +
        '<button class="btn small ghost" data-act="cr-itemattr-add" data-arg="minecraft:generic.max_health">+ 最大生命</button>' +
      '</div>' +
      '<div class="list">' + (attrs || '<div class="hint">暂无属性修饰符</div>') + '</div>' +
      '<div class="field-row"><input id="crItemQuery" type="text" placeholder="搜索物品 ID 或名称" style="flex:1" value="' + esc(sc.query || '') + '">' +
      '<button class="btn small ghost" data-act="cr-scan">扫描物品 ID</button></div>' +
      (sc.catalog ? '<div class="list" style="max-height:220px;overflow:auto">' +
        sc.catalog.slice(0, 120).map((item) => '<div class="row"><div class="row-main"><b>' + esc(item.id) + '</b>' +
          '<span class="hint">' + esc(item.name || '') + '</span></div>' +
          '<button class="btn small ghost" data-act="cr-pick-catalog" data-arg="' + esc(item.id) + '">选择</button></div>').join('') +
        '</div><div class="hint">共 ' + Number(sc.catalogTotal || sc.catalog.length) + ' 个候选，显示前 ' + Math.min(120, sc.catalog.length) + ' 个</div>' : '') +
      '<span class="hint">原始 NBT（带类型 JSON，可选）</span>' +
      '<textarea id="crItemRaw" rows="8" placeholder=\'{"tag":10,"value":{"display":{"tag":10,"value":{...}}}}\'>' + esc(raw) + '</textarea>' +
      '<div class="toolbar"><button class="btn primary" data-act="cr-item-apply">保存物品</button>' +
      '<button class="btn ghost" data-act="cr-item-cancel">取消</button></div>' +
      '</div></div>';
  }
  return '<div class="card" style="margin-bottom:10px"><div class="card-head"><h2>主背包 / 护甲 / 副手</h2>' +
    '<div class="head-actions"><button class="btn small primary" data-act="cr-new-item" data-arg="inventory">添加物品</button>' +
    '<button class="btn small ghost" data-act="cr-scan">扫描物品 ID</button></div></div>' +
    '<div class="card-body"><div class="list" style="max-height:300px;overflow:auto">' + (rows || '<div class="hint">背包为空</div>') + '</div>' +
    '<div class="hint" style="margin-top:6px">槽位 0-35 主背包（0-8 快捷栏）、36-39 护甲、40 副手；当前 ' + sc.items.length + ' 个物品。</div></div></div>' +
    '<div class="card" style="margin-bottom:10px"><div class="card-head"><h2>末影箱</h2>' +
    '<div class="head-actions"><button class="btn small primary" data-act="cr-new-item" data-arg="ender">添加物品</button></div></div>' +
    '<div class="card-body"><div class="list" style="max-height:220px;overflow:auto">' + (ender || '<div class="hint">末影箱为空</div>') + '</div>' +
    '<div class="hint" style="margin-top:6px">槽位 0-26；当前 ' + (sc.ender || []).length + ' 个物品。</div></div></div>' + editor;
}

function crAbilityHtml(sc, caps) {
  const attrs = sc.attributes.map((entry, index) => {
    const mods = (entry.modifiers || []).map((mod, m) =>
      '<div class="row"><span class="hint" style="min-width:70px">修饰符 ' + (m + 1) + '</span>' +
      '<input data-cr-mod="' + index + '" data-index="' + m + '" data-field="amount" type="number" step="0.01" value="' + Number(mod.amount || 0) + '">' +
      '<select data-cr-mod="' + index + '" data-index="' + m + '" data-field="operation">' + crOpOptions(mod.operation) + '</select>' +
      '<button class="btn small danger" data-act="cr-del-mod" data-arg="' + index + ':' + m + '">删除</button></div>').join('');
    return '<div class="card" style="padding:8px"><div class="row">' +
      '<input data-cr-attr="' + index + '" data-field="name" type="text" placeholder="generic.max_health" value="' + esc(entry.name || '') + '">' +
      '<input data-cr-attr="' + index + '" data-field="base" type="number" step="0.01" value="' + Number(entry.base || 0) + '">' +
      '<button class="btn small ghost" data-act="cr-add-mod" data-arg="' + index + '">添加修饰符</button>' +
      '<button class="btn small danger" data-act="cr-del-attr" data-arg="' + index + '">删除</button></div>' +
      (mods ? '<div class="list" style="margin-top:6px" data-cr-modlist="' + index + '">' + mods + '</div>' : '') + '</div>';
  }).join('');
  const effects = sc.effects.map((entry, index) =>
    '<div class="row"><input data-cr-effect="' + index + '" data-field="id" type="number" value="' + Number(entry.id || 1) + '">' +
    '<input data-cr-effect="' + index + '" data-field="amplifier" type="number" value="' + Number(entry.amplifier || 0) + '">' +
    '<input data-cr-effect="' + index + '" data-field="duration" type="number" value="' + Number(entry.duration || 0) + '">' +
    '<label class="hint"><input data-cr-effect="' + index + '" data-field="hide" type="checkbox"' + (entry.hide_particles ? ' checked' : '') + '> 隐藏粒子</label>' +
    '<button class="btn small danger" data-act="cr-del-effect" data-arg="' + index + '">删除</button></div>'
  ).join('');
  return '<div class="card" style="margin-bottom:10px"><div class="card-head"><h2>Attributes</h2>' +
    '<div class="head-actions"><button class="btn small ghost" data-act="cr-add-attr">添加属性</button></div></div>' +
    '<div class="card-body"><div class="list">' + (attrs || '<div class="hint">暂无属性</div>') + '</div>' +
    '<div class="hint" style="margin-top:6px">属性名如 generic.max_health / generic.movement_speed，基础值上限 ' + Number(caps.attribute || 2048) + '；修饰符可填极大数值（乘算会直接放大）。</div></div></div>' +
    '<div class="card"><div class="card-head"><h2>状态效果</h2>' +
    '<div class="head-actions"><button class="btn small ghost" data-act="cr-add-effect">添加效果</button></div></div>' +
    '<div class="card-body"><div class="list">' + (effects || '<div class="hint">暂无效果</div>') + '</div>' +
    '<div class="hint" style="margin-top:6px">列依次为效果 ID、等级(Amplifier)、持续时间(刻)、是否隐藏粒子；时长上限 ' + Number(caps.effect_duration || 1000000) + '，等级上限 255。</div></div></div>';
}

function crWorldHtml(sc, caps) {
  const f = sc.form.level || {};
  const level = sc.state.level || {};
  const rules = (f.gamerules) || level.gamerules || {};
  const get = (key, fallback) => (f[key] != null ? f[key] : (level[key] != null ? level[key] : fallback));
  const spawn = f.spawn || level.spawn || [0, 64, 0];
  const border = f.border_size != null ? f.border_size : ((level.border && level.border.size) || 59999968);
  const center = f.border_center ||
    [(level.border && level.border.center_x) || 0, (level.border && level.border.center_z) || 0];
  const switches = CR_RULES.map(([key, label]) => {
    const value = rules[key];
    const checked = key === 'randomTickSpeed' ? false : (value !== 'false');
    return '<label class="chip"><input id="crRule_' + key + '" type="checkbox"' + (checked ? ' checked' : '') + '> ' + label + '</label>';
  }).join('');
  return '<div class="grid2">' +
    crField('世界时间（Long）', '<input id="crTime" type="number" value="' + Number(get('time', 0)) + '">') +
    crField('DayTime', '<input id="crDayTime" type="number" value="' + Number(get('day_time', 0)) + '">') +
    crField('天气', '<select id="crWeather">' +
      [['clear', '晴天'], ['rain', '下雨'], ['thunder', '雷暴']].map(([value, label]) =>
        '<option value="' + value + '"' + (get('weather', 'clear') === value ? ' selected' : '') + '>' + label + '</option>').join('') +
      '</select>') +
    crField('世界边界尺寸（上限 ' + Number(caps.border_size || 59999968) + '）', '<input id="crBorder" type="number" step="0.01" value="' + Number(border) + '">') +
    crField('边界中心 X', '<input id="crBorderX" type="number" step="0.01" value="' + Number(center[0] || 0) + '">') +
    crField('边界中心 Z', '<input id="crBorderZ" type="number" step="0.01" value="' + Number(center[1] || 0) + '">') +
    crField('出生点 X', '<input id="crSpawnX" type="number" value="' + Number(spawn[0] || 0) + '">') +
    crField('出生点 Y', '<input id="crSpawnY" type="number" value="' + Number(spawn[1] || 64) + '">') +
    crField('出生点 Z', '<input id="crSpawnZ" type="number" value="' + Number(spawn[2] || 0) + '">') +
    crField('randomTickSpeed（原版默认 3，上限 ' + Number(caps.random_tick_speed || 4000) + '）', '<input id="crRandomTick" type="number" min="0" max="' + Number(caps.random_tick_speed || 4000) + '" value="' + Number(rules.randomTickSpeed || 3) + '">') +
  '</div>' +
  '<div class="chips" style="margin-top:10px">' + switches + '</div>';
}

function crToolsHtml(sc) {
  const opsRows = sc.ops.map((entry, index) =>
    '<div class="row"><input data-cr-ops="' + index + '" data-field="uuid" type="text" value="' + esc(entry.uuid || '') + '">' +
    '<input data-cr-ops="' + index + '" data-field="name" type="text" value="' + esc(entry.name || '') + '">' +
    '<input data-cr-ops="' + index + '" data-field="level" type="number" min="0" max="4" value="' + Number(entry.level || 0) + '">' +
    '<button class="btn small danger" data-act="cr-del-ops" data-arg="' + index + '">删除</button></div>'
  ).join('');
  const backups = sc.backups.map((item) =>
    '<div class="row"><div class="row-main"><b>' + esc(item.name) + '</b>' +
      '<span class="hint">' + fmtSize(item.size) + ' · ' + fmtTime(item.mtime) + '</span></div>' +
      '<button class="btn small ghost" data-act="cr-restore" data-arg="' + esc(item.path) + '">' +
      (sc.restoreTarget === item.path ? '确认恢复' : '恢复') + '</button></div>'
  ).join('');
  const region = sc.region
    ? '<div class="hint">预扫描：' + Number(sc.region.files) + ' 个 region，' + Number(sc.region.chunks) + ' 个区块，预计替换 ' +
      Number(sc.region.replaced) + ' 个方块。</div><div class="toolbar"><button class="btn small primary" data-act="cr-region-apply">确认执行替换</button></div>'
    : '';
  const adv = (sc.adv || []).map((entry) => {
    const checked = sc.advSelected[entry.id] != null ? sc.advSelected[entry.id] : !!entry.done;
    return '<label class="row"><input data-cr-adv="' + esc(entry.id) + '" type="checkbox"' + (checked ? ' checked' : '') + '>' +
      '<span class="row-main"><b>' + esc(entry.id) + '</b><span class="hint">' +
      (entry.done ? '已完成' : '未完成') + ' · 条件 ' + Number(entry.criteria || 0) + '</span></span></label>';
  }).join('');
  const advHint = (sc.adv || []).length
    ? '共 ' + sc.adv.length + ' 个成就条目，勾选后点击「标记所选完成」。'
    : '当前玩家没有 advancements 数据（该版本或本存档未生成）。';
  const targets = ['1.21.4', '1.21.1', '1.20.6', '1.20.4', '1.20.1', '1.19.4', '1.18.2', '1.17.1',
    '1.16.5', '1.15.2', '1.14.4', '1.13.2', '1.12.2', '1.11.2', '1.10.2', '1.9.4', '1.8.9', '1.7.10',
    '1.6.4', '1.5.2', '1.4.7', '1.2.5'];
  const eras = [['auto', '自动检测'], ['classic', 'Classic 2009'], ['indev', 'Indev 0.31'],
    ['alpha', 'Infdev / Alpha / Beta 1.2'], ['mcregion', 'Beta 1.3 – 1.2.5'], ['anvil', 'Anvil（1.2+）']];
  const convert = sc.convert || { source: sc.world || '', target: '1.21.4', era: 'auto' };
  return '<div class="card" style="margin-bottom:10px"><div class="card-head"><h2>旧格式转换（升级为 Anvil）</h2></div>' +
    '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
    '<div class="field-row"><input id="crConvertSource" type="text" placeholder="旧存档目录或 level.dat" style="flex:1" value="' + esc(convert.source || '') + '">' +
    '<select id="crConvertTarget">' + targets.map((v) =>
      '<option value="' + v + '"' + (v === convert.target ? ' selected' : '') + '>' + v + '</option>').join('') + '</select>' +
    '<select id="crConvertEra">' + eras.map(([v, label]) =>
      '<option value="' + v + '"' + (v === convert.era ? ' selected' : '') + '>' + label + '</option>').join('') + '</select>' +
    '<button class="btn small primary" data-act="cr-convert">转换</button></div>' +
    '<div class="hint">Classic / Indev / Alpha / McRegion 存档无法直接编辑，先在这里升级；1.13+ 会输出 1.12.2 结构由游戏本体完成扁平化。</div>' +
    '</div></div>' +
    '<div class="card" style="margin-bottom:10px"><div class="card-head"><h2>成就树</h2>' +
    '<div class="head-actions"><button class="btn small ghost" data-act="cr-adv-all">全选</button>' +
    '<button class="btn small ghost" data-act="cr-adv-none">清空选择</button>' +
    '<button class="btn small ' + (sc.advConfirm ? 'primary' : 'ghost') + '" data-act="cr-adv-complete">' +
    (sc.advConfirm ? '确认标记完成' : '标记所选完成') + '</button></div></div>' +
    '<div class="card-body"><div class="list" style="max-height:260px;overflow:auto">' + (adv || '<div class="hint">' + esc(advHint) + '</div>') + '</div>' +
    '<div class="hint" style="margin-top:6px">' + esc(advHint) + ' 只修改 achievements 文件里已有的条目。</div></div></div>' +
    '<div class="card" style="margin-bottom:10px"><div class="card-head"><h2>OP 管理（服务端 ops.json）</h2>' +
    '<div class="head-actions"><button class="btn small ghost" data-act="cr-ops-pick">选择目录</button>' +
    '<button class="btn small ghost" data-act="cr-ops-load">读取</button>' +
    '<button class="btn small ghost" data-act="cr-ops-add">添加</button>' +
    '<button class="btn small primary" data-act="cr-ops-save">保存</button></div></div>' +
    '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
    '<input id="crOpsDir" type="text" placeholder="服务端目录（包含 ops.json）" value="' + esc(sc.opsDir || '') + '">' +
    '<div class="list">' + (opsRows || '<div class="hint">暂无 OP 条目</div>') + '</div></div></div>' +
    '<div class="card" style="margin-bottom:10px"><div class="card-head"><h2>全局方块替换</h2></div>' +
    '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
    '<div class="field-row"><input id="crOldBlock" type="text" placeholder="原方块：minecraft:stone 或 1" style="flex:1">' +
    '<input id="crNewBlock" type="text" placeholder="目标方块：minecraft:diamond_block 或 57" style="flex:1">' +
    '<button class="btn small ghost" data-act="cr-region-preview">预扫描</button></div>' + region + '</div></div>' +
    '<div class="card"><div class="card-head"><h2>备份</h2><div class="head-actions">' +
    '<button class="btn small ghost" data-act="cr-backup-load">刷新备份</button>' +
    '<button class="btn small ghost" data-act="cr-open-backup">打开备份目录</button></div></div>' +
    '<div class="card-body"><div class="list">' + (backups || '<div class="hint">本世界暂无创世神备份</div>') + '</div></div></div>';
}

function crItemPayload(item) {
  return {
    id: item.id, slot: Number(item.slot || 0), count: Number(item.count || 1),
    damage: Number(item.damage || 0), enchantments: item.enchantments || [],
    attributes: item.attributes || [], tag_json: item.tag_json || null,
  };
}

function crPreviewHtml(sc) {
  const preview = sc.preview;
  const warnings = (preview.warnings || []).length
    ? '<div class="hint" style="color:#e0a33e">' + esc(CR_OVER_CAP) + '<br>' +
      preview.warnings.map((item) => '· ' + esc(item.message)).join('<br>') + '</div>'
    : '';
  const changes = (preview.changes || []).map((item) => '<div class="hint">· ' + esc(item) + '</div>').join('');
  return '<div class="card" style="border-color:#e0a33e"><div class="card-head"><h2>确认写入</h2></div>' +
    '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' + warnings + changes +
    '<div class="hint">写入前会强制完整备份，失败按事务回滚。</div>' +
    '<div class="toolbar"><button class="btn primary" data-act="cr-apply">确认写入</button>' +
    '<button class="btn ghost" data-act="cr-discard">取消</button></div></div></div>';
}

function crBuildRequest() {
  const sc = S.creator;
  const f = sc.form || {};
  const p = sc.player || {};
  const player = {
    health: f.health != null ? f.health : (p.health != null ? p.health : 20),
    food: f.food != null ? f.food : (p.food != null ? p.food : 5),
    food_level: f.food_level != null ? f.food_level : (p.food_level != null ? p.food_level : 20),
    safe_teleport: !!f.safe_teleport,
    xp_level: Math.round(f.xp_level != null ? f.xp_level : (p.xp_level || 0)),
    pos: f.pos || p.pos || [0, 64, 0],
    game_type: f.game_type != null ? f.game_type : (p.game_type || 0),
    dimension: f.dimension || p.dimension || 'minecraft:overworld',
    inventory: sc.items.map(crItemPayload),
    ender_items: (sc.ender || []).map(crItemPayload),
    attributes: sc.attributes.map((entry) => ({
      name: entry.name, base: Number(entry.base || 0),
      modifiers: (entry.modifiers || []).map((mod) => ({
        name: mod.name || entry.name, amount: Number(mod.amount || 0),
        operation: mod.operation || 'add_value',
      })),
    })),
    effects: sc.effects,
  };
  return { world: sc.world, player_uuid: sc.playerUuid, player: player, level: f.level || {} };
}

ACT['cr-refresh'] = async () => {
  S.creator.loaded = false;
  await renderCreator();
};
ACT['cr-pick-world'] = async () => {
  const res = await call('creator_pick_world');
  if (!res || !res.ok || !res.path) return;
  const name = String(res.path).split(/[\\/]/).filter(Boolean).pop() || res.path;
  S.creator.worlds = [{ name: name, path: res.path }].concat(
    (S.creator.worlds || []).filter((item) => item.path !== res.path)
  );
  await creatorLoadWorld(res.path);
  creatorPaint();
};
ACT['cr-tab'] = (tab) => {
  crCollectForm();
  S.creator.tab = tab;
  creatorPaint();
};
ACT['cr-new-item'] = (store) => {
  const sc = S.creator;
  const kind = store === 'ender' ? 'ender' : 'inventory';
  const list = kind === 'ender' ? (sc.ender || []) : sc.items;
  const used = list.map((item) => Number(item.slot || 0));
  let slot = 0;
  while (used.indexOf(slot) >= 0 && slot < (kind === 'ender' ? 27 : 41)) slot += 1;
  sc.editing = {
    store: kind, index: -1, id: '', slot: slot, count: 1, damage: 0,
    enchantments: [], attributes: [], tag_json: null,
  };
  creatorPaint();
};
ACT['cr-edit-item'] = (arg) => {
  const parts = String(arg || '').split(':');
  const store = parts[0] === 'ender' ? 'ender' : 'inventory';
  const index = Number(parts[1]);
  const list = store === 'ender' ? (S.creator.ender || []) : S.creator.items;
  const item = list[index];
  if (!item) return;
  S.creator.editing = Object.assign({ store: store, index: index }, item);
  creatorPaint();
};
ACT['cr-del-item'] = (arg) => {
  const parts = String(arg || '').split(':');
  const store = parts[0] === 'ender' ? 'ender' : 'inventory';
  const index = Number(parts[1]);
  const list = store === 'ender' ? (S.creator.ender || []) : S.creator.items;
  list.splice(index, 1);
  S.creator.editing = null;
  creatorPaint();
};
ACT['cr-scan'] = async () => {
  S.creator.query = crText('crItemQuery', S.creator.query || '');
  if (S.creator.editing) crCollectEditor();
  const era = (S.creator.state && S.creator.state.era) || '';
  const res = await call('creator_scan_items', S.creator.query, '', era);
  if (!res || !res.ok) { toast((res && res.message) || '扫描失败', 'error'); return; }
  S.creator.catalog = res.items || [];
  S.creator.catalogTotal = res.total || 0;
  creatorPaint();
  toast('已加载 ' + S.creator.catalogTotal + ' 个物品 ID', 'ok');
};
ACT['cr-pick-catalog'] = (id) => {
  if (!S.creator.editing) return;
  const ed = crCollectEditor();
  ed.id = id;
  S.creator.editing = ed;
  creatorPaint();
};
ACT['cr-item-cancel'] = () => { S.creator.editing = null; creatorPaint(); };
function crReadItemAttrs() {
  const rows = [];
  document.querySelectorAll('[data-cr-itemattr]').forEach((node) => {
    const index = Number(node.dataset.crItemattr);
    rows[index] = rows[index] || { name: '', amount: 0, operation: 'add_value', slot: 'any' };
    const field = node.dataset.field;
    if (field === 'amount') rows[index].amount = Number(node.value || 0);
    else rows[index][field] = String(node.value || '').trim();
  });
  return rows.filter((item) => item && item.name);
}

function crCollectEditor() {
  const ed = S.creator.editing;
  if (!ed) return null;
  if (h('crItemId')) ed.id = crText('crItemId');
  if (h('crItemSlot')) ed.slot = Math.round(crNum('crItemSlot'));
  if (h('crItemCount')) ed.count = Math.round(crNum('crItemCount', 1));
  if (h('crItemDamage')) ed.damage = Math.round(crNum('crItemDamage'));
  if (h('crItemEnch')) ed.enchant_text = crText('crItemEnch');
  ed.attributes = crReadItemAttrs();
  return ed;
}

ACT['cr-itemattr-add'] = (name) => {
  const ed = crCollectEditor();
  if (!ed) return;
  ed.attributes = ed.attributes || [];
  ed.attributes.push({
    name: name || 'minecraft:generic.attack_damage',
    amount: 10, operation: 'add_value', slot: 'any',
  });
  S.creator.editing = ed;
  creatorPaint();
};
ACT['cr-del-itemattr'] = (index) => {
  const ed = crCollectEditor();
  if (!ed) return;
  ed.attributes.splice(Number(index), 1);
  S.creator.editing = ed;
  creatorPaint();
};
ACT['cr-item-apply'] = () => {
  const sc = S.creator;
  const ed = sc.editing;
  if (!ed) return;
  const caps = (sc.state && sc.state.vanilla_caps) || {};
  const id = crText('crItemId');
  if (!id) { toast('物品 ID 不能为空', 'error'); return; }
  let enchantments;
  let tagJson = null;
  try {
    enchantments = crParseEnchants(crText('crItemEnch'), Number(caps.enchant_level || 255));
    const raw = crText('crItemRaw');
    if (raw) tagJson = JSON.parse(raw);
  } catch (err) {
    toast(err.message || err, 'error');
    return;
  }
  const entry = {
    id: id, slot: Math.round(crNum('crItemSlot')), count: Math.round(crNum('crItemCount', 1)),
    damage: Math.round(crNum('crItemDamage')), enchantments: enchantments,
    attributes: crReadItemAttrs(), tag_json: tagJson,
  };
  const list = ed.store === 'ender' ? sc.ender : sc.items;
  if (Number(ed.index) >= 0) list[Number(ed.index)] = entry; else list.push(entry);
  sc.editing = null;
  creatorPaint();
};
ACT['cr-add-mod'] = (index) => {
  crCollectRows();
  const attr = S.creator.attributes[Number(index)];
  if (!attr) return;
  attr.modifiers = attr.modifiers || [];
  attr.modifiers.push({ name: attr.name, amount: 0.1, operation: 'add_value' });
  creatorPaint();
};
ACT['cr-del-mod'] = (arg) => {
  crCollectRows();
  const parts = String(arg || '').split(':');
  const attr = S.creator.attributes[Number(parts[0])];
  if (!attr) return;
  (attr.modifiers || []).splice(Number(parts[1]), 1);
  creatorPaint();
};
ACT['cr-add-attr'] = () => {
  crCollectRows();
  S.creator.attributes.push({
    name: 'generic.max_health', base: 20,
    modifiers: [],
  });
  creatorPaint();
};
ACT['cr-del-attr'] = (index) => {
  crCollectRows();
  S.creator.attributes.splice(Number(index), 1);
  creatorPaint();
};
ACT['cr-add-effect'] = () => {
  crCollectRows();
  S.creator.effects.push({ id: 1, amplifier: 0, duration: 200, hide_particles: false });
  creatorPaint();
};
ACT['cr-del-effect'] = (index) => {
  crCollectRows();
  S.creator.effects.splice(Number(index), 1);
  creatorPaint();
};
ACT['cr-preview'] = async () => {
  crCollectForm();
  const res = await call('creator_preview', crBuildRequest());
  if (!res || !res.ok) { toast((res && res.message) || '预览失败', 'error'); return; }
  S.creator.preview = res.preview;
  creatorPaint();
};
ACT['cr-discard'] = () => { S.creator.preview = null; creatorPaint(); };
ACT['cr-apply'] = async () => {
  const sc = S.creator;
  if (!sc.preview) return;
  const res = await call('creator_apply', sc.preview.token);
  if (!res || !res.ok) { toast((res && res.message) || '写入失败', 'error'); return; }
  toast('已写入，备份：' + ((res.result && res.result.backup) || ''), 'ok');
  await creatorLoadWorld(sc.world);
  creatorPaint();
};
function crCollectAdv() {
  const selected = {};
  document.querySelectorAll('[data-cr-adv]').forEach((node) => {
    selected[node.dataset.crAdv] = !!node.checked;
  });
  S.creator.advSelected = selected;
  return Object.keys(selected).filter((key) => selected[key]);
}
ACT['cr-adv-all'] = () => {
  S.creator.advSelected = {};
  (S.creator.adv || []).forEach((entry) => { S.creator.advSelected[entry.id] = true; });
  creatorPaint();
};
ACT['cr-adv-none'] = () => {
  S.creator.advSelected = {};
  (S.creator.adv || []).forEach((entry) => { S.creator.advSelected[entry.id] = false; });
  creatorPaint();
};
ACT['cr-adv-complete'] = async () => {
  const sc = S.creator;
  const selected = crCollectAdv();
  if (!selected.length) { toast('请先勾选要完成的成就', 'error'); return; }
  if (!sc.advConfirm) { sc.advConfirm = true; creatorPaint(); return; }
  const res = await call('creator_complete_advancements', sc.world, sc.playerUuid, selected);
  sc.advConfirm = false;
  if (!res || !res.ok) { toast((res && res.message) || '操作失败', 'error'); return; }
  await creatorLoadAdvancements();
  creatorPaint();
  toast('已处理 ' + ((res.result && res.result.count) || 0) + ' 个成就条目', 'ok');
};
ACT['cr-convert'] = async () => {
  const sc = S.creator;
  const source = crText('crConvertSource', '') || sc.world || '';
  const target = crText('crConvertTarget', '1.21.4');
  const era = crText('crConvertEra', 'auto');
  if (!source) { toast('请先填写旧存档路径', 'error'); return; }
  sc.convert = { source: source, target: target, era: era };
  const res = await call('creator_convert', source, target, era);
  if (!res || !res.ok) { toast((res && res.message) || '转换失败', 'error'); return; }
  toast(res.message || '转换完成', 'ok');
  const report = (res.result && res.result.warnings) || [];
  if (report.length) toast(report.join('；'), 'info');
};
ACT['cr-ops-pick'] = async () => {
  const res = await call('creator_pick_ops_dir');
  if (!res || !res.ok || !res.path) return;
  S.creator.opsDir = res.path;
  creatorPaint();
};
ACT['cr-ops-load'] = async () => {
  const sc = S.creator;
  sc.opsDir = crText('crOpsDir', sc.opsDir || '');
  if (!sc.opsDir) { toast('请先选择服务端目录', 'error'); return; }
  const res = await call('creator_read_ops', sc.opsDir);
  if (!res || !res.ok) { toast((res && res.message) || '读取失败', 'error'); return; }
  sc.ops = res.items || [];
  creatorPaint();
};
ACT['cr-ops-add'] = () => {
  crCollectOps();
  S.creator.ops.push({ uuid: '', name: '', level: 4 });
  creatorPaint();
};
ACT['cr-del-ops'] = (index) => {
  crCollectOps();
  S.creator.ops.splice(Number(index), 1);
  creatorPaint();
};
ACT['cr-ops-save'] = async () => {
  const sc = S.creator;
  sc.opsDir = crText('crOpsDir', sc.opsDir || '');
  if (!sc.opsDir) { toast('请先选择服务端目录', 'error'); return; }
  crCollectOps();
  const res = await call('creator_write_ops', sc.opsDir, sc.ops.filter((item) => item.uuid));
  if (!res || !res.ok) { toast((res && res.message) || '保存失败', 'error'); return; }
  toast('已写入 ' + ((res.result && res.result.path) || 'ops.json'), 'ok');
};
function crCollectOps() {
  const entries = [];
  document.querySelectorAll('[data-cr-ops]').forEach((node) => {
    const index = Number(node.dataset.crOps);
    entries[index] = entries[index] || { uuid: '', name: '', level: 0 };
    const field = node.dataset.field;
    entries[index][field] = field === 'level' ? Number(node.value || 0) : String(node.value).trim();
  });
  S.creator.ops = entries.filter(Boolean);
}
ACT['cr-region-preview'] = async () => {
  const sc = S.creator;
  const res = await call('creator_region_preview', {
    world: sc.world, old_id: crText('crOldBlock'), new_id: crText('crNewBlock'),
  });
  if (!res || !res.ok) { toast((res && res.message) || '预扫描失败', 'error'); return; }
  sc.region = res.preview;
  creatorPaint();
};
ACT['cr-region-apply'] = async () => {
  const sc = S.creator;
  if (!sc.region) return;
  const res = await call('creator_region_apply', sc.region.token);
  if (!res || !res.ok) { toast((res && res.message) || '替换失败', 'error'); return; }
  sc.region = null;
  toast('已替换 ' + ((res.result && res.result.replaced) || 0) + ' 个方块', 'ok');
  creatorPaint();
};
ACT['cr-backup-load'] = async () => {
  const sc = S.creator;
  const res = await call('creator_backups', sc.world);
  if (!res || !res.ok) { toast((res && res.message) || '读取备份失败', 'error'); return; }
  sc.backups = res.items || [];
  creatorPaint();
};
ACT['cr-open-backup'] = async () => {
  const res = await call('open_path', 'backups');
  if (res && res.ok === false) toast(res.message || '无法打开备份目录', 'error');
};
ACT['cr-restore'] = async (path) => {
  const sc = S.creator;
  if (sc.restoreTarget !== path) { sc.restoreTarget = path; creatorPaint(); return; }
  const res = await call('creator_restore', path, sc.world);
  sc.restoreTarget = '';
  if (!res || !res.ok) { toast((res && res.message) || '恢复失败', 'error'); return; }
  toast(res.message || '已恢复备份', 'ok');
  await creatorLoadWorld(sc.world);
  creatorPaint();
};
document.addEventListener('change', (event) => {
  const node = event.target.closest('[data-cr-change]');
  if (!node || !S.creator) return;
  const kind = node.dataset.crChange;
  if (kind === 'world') {
    creatorLoadWorld(node.value).then(() => creatorPaint()).catch((err) => toast(err.message || err, 'error'));
  } else if (kind === 'player') {
    crCollectForm();
    creatorLoadPlayer(node.value)
      .then(() => creatorLoadAdvancements())
      .then(() => creatorPaint())
      .catch((err) => toast(err.message || err, 'error'));
  }
});

/* ---------- 工具箱 ---------- */
function toolVersionSelect() {
  const versions = (S.data && S.data.versions) || [];
  const current = S.selectedVersion || (versions[0] && versions[0].id) || '';
  return '<select id="toolVersion" style="min-width:150px">' +
    (versions.length ? versions.map((v) => '<option value="' + esc(v.id) + '"' + (v.id === current ? ' selected' : '') + '>' + esc(v.id) + '</option>').join('')
      : '<option value="">暂无版本</option>') + '</select>';
}
function noiseModeOf(versionId) {
  const m = /^(\d+)\.(\d+)/.exec(String(versionId || ''));
  if (!m) return 'modern';
  const major = Number(m[1]);
  const minor = Number(m[2]);
  return (major > 1 || (major === 1 && minor >= 18)) ? 'modern' : 'classic';
}
function terrainVersionSelect() {
  const versions = (S.data && S.data.versions) || [];
  if (!versions.length) {
    return '<select id="terrainVersion"><option value="">暂无已安装版本（按最新版噪声）</option></select>';
  }
  const current = S.selectedVersion || versions[0].id;
  return '<select id="terrainVersion">' + versions.map((v) => (
    '<option value="' + esc(v.id) + '"' + (v.id === current ? ' selected' : '') + '>' +
    esc(v.id) + ' · ' + (noiseModeOf(v.id) === 'modern' ? '新版噪声' : '经典噪声') + '</option>'
  )).join('') + '</select>';
}
function renderTools() {
  const feats = (S.data && S.data.features) || {};
  const F = (key) => feats[key] !== false;
  h('view').innerHTML =
    '<div class="page flow"><div style="display:flex;flex-direction:column;gap:12px;padding-right:4px">' +
      (F('deps') ? '<div class="card"><div class="card-head"><h2>依赖补全</h2><div class="head-actions">' + toolVersionSelect() +
        '<button class="btn small primary" data-act="dep-scan">扫描缺失</button></div></div>' +
        '<div class="card-body" id="depBox"><div class="hint">选择版本后扫描缺失的 Java、客户端、依赖库与资源文件，可一键补全。</div></div></div>' : '') +
      '<div class="card"><div class="card-head"><h2>第三方组件</h2><span class="hint">不可内置 / 需单独授权</span></div>' +
        '<div class="card-body" id="moduleBox"><div class="loading"><span class="spinner"></span>读取中…</div></div></div>' +
      (F('modgraph') ? '<div class="card"><div class="card-head"><h2>Mod 关系图</h2><div class="head-actions">' + toolVersionSelect().replace('id="toolVersion"', 'id="modVersion"') +
        '<button class="btn small primary" data-act="mod-scan">扫描</button></div></div>' +
        '<div class="card-body" id="modBox"><div class="hint">扫描当前实例 mods 目录，画出自绘依赖关系图，缺失前置与循环依赖会高亮。</div></div></div>' : '') +
      '<div class="card"><div class="card-head"><h2>存档管理</h2><div class="head-actions">' +
        '<button class="btn small ghost" data-act="saves-import">导入世界</button>' +
        '<button class="btn small ghost" data-act="saves-backup-all">备份全部</button>' +
        '<button class="btn small ghost" data-act="saves-refresh">刷新</button></div></div>' +
        '<div class="card-body" id="savesBox"><div class="loading"><span class="spinner"></span>读取中…</div></div></div>' +
      '<div class="card"><div class="card-head"><h2>存档转换器</h2><div class="head-actions">' +
        '<button class="btn small ghost" data-act="world-pick-dir">选择存档文件夹</button>' +
        '<button class="btn small ghost" data-act="world-pick-zip">选择备份 / 单文件</button>' +
        '<button class="btn small ghost" data-act="world-refresh">重新扫描</button></div></div>' +
        '<div class="card-body" id="worldBox"><div class="loading"><span class="spinner"></span>扫描存档中…</div></div></div>' +
      (F('gallery') ? '<div class="card"><div class="card-head"><h2>截图图库</h2><div class="head-actions">' +
        '<button class="btn small ghost" data-act="gallery-export">导出所选</button>' +
        '<button class="btn small danger" data-act="gallery-delete">删除所选</button>' +
        '<button class="btn small ghost" data-act="open-path" data-arg="screenshots">打开目录</button></div></div>' +
        '<div class="card-body" id="galleryBox"><div class="hint">读取当前实例 screenshots/ 下的截图；点一行即可预览。</div></div></div>' : '') +
      (F('crash') ? '<div class="card"><div class="card-head"><h2>崩溃报告</h2><div class="head-actions">' +
        '<button class="btn small ghost" data-act="crash-copy">复制摘要</button>' +
        '<button class="btn small danger" data-act="crash-delete">删除所选</button>' +
        '<button class="btn small ghost" data-act="open-path" data-arg="crashes">打开目录</button></div></div>' +
        '<div class="card-body" id="crashBox"><div class="hint">启动器会把游戏异常退出的日志归档到 data/logs/crashes/。</div></div></div>' : '') +
      (F('seed_terrain') ? '<div class="card"><div class="card-head"><h2>种子地形预览</h2><span class="hint">复用原版柏林噪声 · Java 计算</span></div>' +
        '<div class="card-body" style="display:flex;flex-direction:column;gap:10px">' +
          '<div class="field-row"><input type="text" id="terrainSeed" placeholder="种子（留空随机）" style="flex:1" />' +
          terrainVersionSelect() +
          '<select id="terrainSize"><option value="128">128</option><option value="256" selected>256</option><option value="512">512</option></select>' +
          '<button class="btn primary" data-act="terrain-run">生成</button></div>' +
          '<div id="terrainBox" class="hint">选择已下载的游戏版本后生成高度图：1.18+ 用新版气候噪声，1.7–1.17 用经典 ImprovedNoise；生成交给 Java 计算，界面不会卡顿。</div>' +
        '</div></div>' : '') +
      '<div class="card"><div class="card-head"><h2>NBT 编辑器</h2><div class="head-actions">' +
        '<button class="btn small primary" data-act="nbt-open">打开文件</button></div></div>' +
        '<div class="card-body"><div id="nbtBox" class="hint">打开 level.dat / playerdata/*.dat 可查看并修改叶子节点；保存前自动生成 .bak 备份。</div></div></div>' +
      '<div class="card"><div class="card-head"><h2>导入与清理</h2></div><div class="card-body">' +
        '<div class="toolbar"><button class="btn small ghost" data-act="import-modpack">导入整合包</button>' +
        '<button class="btn small ghost" data-act="import-external">导入 HMCL / PCL</button>' +
        '<button class="btn small ghost" data-act="tool-log" data-arg="launcher">启动器日志</button>' +
        '<button class="btn small ghost" data-act="tool-log" data-arg="game">游戏日志</button>' +
        '<button class="btn small danger" data-act="clean-game">清理缓存</button></div>' +
        '<div class="hint" style="margin-top:9px">清理会删除 <b>versions</b> 下损坏/未完成的版本与缓存文件，不会动存档与 mods。</div></div></div>' +
      '<div class="card"><div class="card-head"><h2>相关功能</h2><span class="hint">按 Ctrl+K 也能直接搜索</span></div>' +
        '<div class="card-body"><div class="chips">' +
          '<button class="chip" data-act="tool-jump" data-arg="依赖补全">依赖补全</button>' +
          '<button class="chip" data-act="tool-jump" data-arg="Mod 关系图">Mod 关系图</button>' +
          '<button class="chip" data-act="tool-jump" data-arg="存档管理">存档备份</button>' +
          '<button class="chip" data-act="export-script" data-arg="bat">导出启动脚本</button>' +
          '<button class="chip" data-act="nav" data-arg="instances">Mod / 资源包管理</button>' +
          '<button class="chip" data-act="tool-jump" data-arg="种子地形预览">世界种子预览</button>' +
          '<button class="chip" data-act="tool-jump" data-arg="NBT 编辑器">NBT 编辑器</button>' +
          '<button class="chip" data-act="tool-jump" data-arg="崩溃报告">崩溃报告</button>' +
          '<button class="chip" data-act="nav" data-arg="settings">设置 · 常用</button>' +
        '</div><div class="hint" style="margin-top:9px">这些工具都会用到当前选中的版本；在主页切换版本后回来即可。</div></div></div>' +
    '</div></div>';
  loadModules();
  loadSaves();
  loadWorldTool();
  loadGallery();
  loadCrashes();
}
ACT['tool-jump'] = (title) => {
  const headings = Array.from(document.querySelectorAll('#view .card-head h2'));
  const target = headings.find((node) => (node.textContent || '').includes(title));
  const card = target && target.closest('.card');
  if (!card) return;
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  card.classList.add('flash');
  setTimeout(() => card.classList.remove('flash'), 1200);
};
ACT['dep-scan'] = async () => {
  const version = h('toolVersion') && h('toolVersion').value;
  const box = h('depBox');
  box.innerHTML = '<div class="loading"><span class="spinner"></span>正在扫描…</div>';
  let res;
  try { res = await call('dependencies_scan', version || ''); } catch (err) { box.innerHTML = '<div class="empty">' + esc(err.message || err) + '</div>'; return; }
  if (!res.ok) { box.innerHTML = '<div class="empty">' + esc(res.message) + '</div>'; return; }
  const items = res.items || [];
  box.innerHTML =
    '<div class="hint" style="margin-bottom:8px">' + esc(res.summary || (items.length ? '发现 ' + items.length + ' 项缺失' : '依赖完整，无需补全')) + '</div>' +
    (items.length ? '<div class="list">' + items.map((item) =>
      '<div class="row"><div class="row-main"><b>' + esc(item.kind) + '</b><small>' + esc(item.name || '') + '</small>' +
      (item.detail ? '<small class="mono">' + esc(item.detail) + '</small>' : '') + '</div>' +
      '<div class="row-meta">' + esc(String(item.count || 1)) + ' 项</div></div>'
    ).join('') + '</div>' : '');
  if (items.some((i) => i.kind === 'java')) toast('缺少 Java 运行时，请到下载中心安装对应版本', 'error');
};
async function loadModules() {
  const box = h('moduleBox'); if (!box) return;
  let list = [];
  try { list = await call('third_party_modules'); } catch (_) { /* 忽略 */ }
  box.innerHTML = (list || []).length ? '<div class="list">' + list.map((m) =>
    '<div class="row"><div class="row-main"><b>' + esc(m.name) + ' <span class="tag">' + esc(m.license) + '</span></b>' +
      '<small>' + esc(m.summary) + '</small><small class="mono">' + esc(m.path || '') + '</small></div>' +
      '<div class="row-actions">' +
        (m.installed ? '<span class="tag accent">已安装</span>' : '') +
        (m.action === 'install' ? '<button class="btn small primary" data-act="module-install" data-arg="' + A(m.id) + '">' + esc(m.action_text || '下载') + '</button>' : '') +
        (m.action === 'download' ? '<button class="btn small ghost" data-act="go-download" data-arg="java">前往下载</button>' : '') +
        (m.homepage ? '<button class="btn small ghost" data-act="open-url" data-arg="' + A(m.homepage) + '">主页</button>' : '') +
      '</div></div>'
  ).join('') + '</div>' : '<div class="empty">没有需要补全的第三方组件。</div>';
}
ACT['module-install'] = async (id) => {
  const res = await call('install_dependency', id);
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message, 'ok');
  const job = await watchJob(res.job);
  if (job && job.state === 'ok') toast('组件安装完成', 'ok');
  else toast((job && (job.error || job.stage)) || '安装未完成', 'error');
  loadModules();
};
ACT['mod-scan'] = async () => {
  const box = h('modBox');
  box.innerHTML = '<div class="loading"><span class="spinner"></span>正在扫描 mods…</div>';
  let res;
  try { res = await call('mod_scan', (h('modVersion') && h('modVersion').value) || ''); } catch (err) { box.innerHTML = '<div class="empty">' + esc(err.message || err) + '</div>'; return; }
  if (!res.ok) { box.innerHTML = '<div class="empty">' + esc(res.message) + '</div>'; return; }
  const conflicts = res.conflicts || [];
  const missing = (res.nodes || []).filter((n) => n.missing);
  const cycles = res.cycles || [];
  box.innerHTML =
    '<div class="toolbar" style="margin-bottom:8px">' +
      '<span class="tag">' + (res.nodes || []).length + ' 个 Mod</span>' +
      '<span class="tag ' + (missing.length ? 'danger' : 'accent') + '">缺失前置 ' + missing.length + '</span>' +
      '<span class="tag ' + (cycles.length ? 'warn' : 'accent') + '">循环依赖 ' + cycles.length + '</span>' +
      '<span class="tag ' + (conflicts.length ? 'warn' : 'accent') + '">冲突 ' + conflicts.length + '</span>' +
      '<span class="spacer"></span><span class="hint mono">' + esc(res.mods_dir || '') + '</span></div>' +
    drawModGraph(res) +
    (missing.length ? '<div class="dep-list" style="margin-top:10px">' + missing.map((n) =>
      '<div class="dep"><b>' + esc(n.name) + '</b><small class="mono">' + esc(n.id) + '</small><span class="tag danger">缺失</span></div>'
    ).join('') + '</div>' : '') +
    (conflicts.length ? '<div class="list" style="margin-top:8px">' + conflicts.map((c) =>
      '<div class="row"><div class="row-main"><b>' + esc(c.type) + ' · ' + esc(c.modid) + '</b><small>' + esc(c.detail) + '</small>' +
      '<small class="mono">' + esc((c.files || []).join(', ')) + '</small></div><span class="tag warn">建议禁用</span></div>'
    ).join('') + '</div>' : '');
};
function drawModGraph(result) {
  const nodes = result.nodes || []; const edges = result.edges || [];
  if (!nodes.length) return '<div class="empty">mods 目录里没有识别到 Mod。安装 Mod 后再来扫描。</div>';
  const W = 1000, H = 400, cx = W / 2, cy = H / 2;
  const radius = Math.max(110, Math.min(W, H) / 2 - 58);
  const pos = {};
  nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / nodes.length - Math.PI / 2;
    pos[node.id] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });
  const lines = edges.map((edge) => {
    const a = pos[edge.from], b = pos[edge.to];
    if (!a || !b) return '';
    return '<line x1="' + a.x.toFixed(1) + '" y1="' + a.y.toFixed(1) + '" x2="' + b.x.toFixed(1) + '" y2="' + b.y.toFixed(1) +
      '" stroke="' + (edge.ok ? 'rgba(101,212,110,.5)' : 'rgba(224,102,102,.75)') + '" stroke-width="1.3"' +
      ' stroke-dasharray="' + (edge.ok ? '0' : '5 4') + '" />';
  }).join('');
  const dots = nodes.map((node) => {
    const p = pos[node.id];
    const label = String(node.name || node.id).slice(0, 16);
    return '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="' + (node.missing ? 4.5 : 6) +
      '" fill="' + (node.missing ? '#e06666' : '#65d46e') + '" opacity="' + (node.missing ? .6 : .92) + '" />' +
      '<text x="' + (p.x + 9).toFixed(1) + '" y="' + (p.y + 3).toFixed(1) + '" fill="' + (node.missing ? '#e06666' : '#8fa89a') + '">' + esc(label) + '</text>';
  }).join('');
  return '<svg class="graph" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet">' + lines + dots + '</svg>';
}
async function loadSaves() {
  const box = h('savesBox'); if (!box) return;
  let res;
  try { res = await call('saves_list'); } catch (err) { box.innerHTML = '<div class="empty">' + esc(err.message || err) + '</div>'; return; }
  const saves = res.saves || []; const backups = res.backups || [];
  box.innerHTML =
    '<div class="list">' + (saves.length ? saves.map((s) =>
      '<div class="row"><div class="row-main"><b>' + esc(s.name) + '</b><small>' + esc(s.folder) + ' · ' + esc(s.mode || '') + ' · ' + esc(s.version || '') + '</small>' +
      '<small class="mono">' + fmtSize(s.size) + ' · ' + fmtTime(s.last_played) + '</small></div>' +
      '<div class="row-actions"><button class="btn small ghost" data-act="save-nbt" data-arg="' + A(s.folder) + '">NBT</button>' +
      '<button class="btn small ghost" data-act="save-copy" data-arg="' + A(s.folder) + '">复制</button>' +
      '<button class="btn small ghost" data-act="save-export" data-arg="' + A(s.folder) + '">导出</button>' +
      '<button class="btn small ghost" data-act="save-edit" data-arg="' + A(s.folder) + '">编辑</button>' +
      '<button class="btn small ghost" data-act="world-quick" data-arg="' + A(s.folder) + '">转换导入</button>' +
      '<button class="btn small ghost" data-act="save-convert" data-arg="' + A(s.folder) + '">版本</button>' +
      '<button class="btn small ghost" data-act="save-backup" data-arg="' + A(s.folder) + '">备份</button>' +
      '<button class="btn small danger" data-act="save-delete" data-arg="' + A(s.folder) + '">删除</button></div></div>'
    ).join('') : '<div class="empty">当前版本目录下没有存档。</div>') + '</div>' +
    (backups.length ? '<div class="hint" style="margin:12px 0 6px">备份（' + backups.length + '）</div><div class="list">' + backups.map((b) =>
      '<div class="row"><div class="row-main"><b>' + esc(b.world) + (b.auto ? ' <span class="tag">自动</span>' : '') + '</b>' +
      '<small class="mono">' + esc(b.path) + '</small><small>' + fmtSize(b.size) + ' · ' + fmtTime(b.created) + '</small></div>' +
      '<div class="row-actions"><button class="btn small ghost" data-act="world-quick" data-arg="' + A(b.path) + '">转换导入</button>' +
      '<button class="btn small ghost" data-act="saves-restore" data-arg="' + A(b.path) + '">恢复</button></div></div>'
    ).join('') + '</div>' : '');
}
ACT['saves-refresh'] = () => loadSaves();
ACT['saves-import'] = async () => {
  const res = await call('save_import_world');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadSaves();
};
ACT['save-export'] = async (folder) => {
  const res = await call('save_export_world', folder);
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['save-copy'] = async (folder) => {
  const res = await call('save_copy', folder);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadSaves();
};
ACT['save-nbt'] = async (folder) => {
  const instanceId = S.nbtInstance || '';
  S.nbtInstance = '';
  const res = await call('save_nbt', folder, instanceId);
  if (!res.ok) return toast(res.message, 'error');
  S.nbt = res;
  paintNbt();
  const card = h('nbtBox') && h('nbtBox').closest('.card');
  if (card) {
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    card.classList.add('flash');
    setTimeout(() => card.classList.remove('flash'), 1200);
  }
  toast('已打开 ' + res.path, 'ok');
};
ACT['saves-backup-all'] = async () => {
  const res = await call('saves_backup', '');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadSaves();
};
ACT['save-backup'] = async (folder) => {
  const res = await call('saves_backup', folder);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadSaves();
};
ACT['saves-restore'] = async (path) => {
  if (!(await ask('恢复存档', '目标位置已有同名存档时会覆盖，确定继续？'))) return;
  const res = await call('saves_restore', path);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadSaves();
};
ACT['save-delete'] = async (folder) => {
  if (!(await ask('删除存档', '将直接从磁盘删除「' + folder + '」，不可恢复。'))) return;
  const res = await call('saves_delete', folder);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) loadSaves();
};
const SAVE_MODES = [[0, '生存模式'], [1, '创造模式'], [2, '冒险模式'], [3, '旁观模式']];
const SAVE_DIFFS = [[0, '和平'], [1, '简单'], [2, '普通'], [3, '困难']];
const SAVE_WEATHER = [['clear', '晴天'], ['rain', '下雨'], ['thunder', '雷雨']];
function saveOptions(items, selected) {
  return items.map(([value, label]) =>
    '<option value="' + value + '"' + (String(selected) === String(value) ? ' selected' : '') + '>' + label + '</option>'
  ).join('');
}
ACT['save-edit'] = async (folder) => {
  let res;
  try { res = await call('save_meta', folder); } catch (err) { return toast(err.message || err, 'error'); }
  if (!res.ok) return toast(res.message, 'error');
  const m = res.meta || {};
  const rules = m.game_rules || {};
  const spawn = Array.isArray(m.spawn) && m.spawn.length === 3 ? m.spawn.join(',') : '0,64,0';
  const keep = String(rules.keepInventory || '').toLowerCase() === 'true';
  openSheet('编辑存档 · ' + m.name,
    '<div class="form-grid">' +
      '<div class="field"><label>世界名称</label><input id="seName" value="' + esc(m.name) + '" /></div>' +
      '<div class="field"><label>游戏模式</label><select id="seMode">' + saveOptions(SAVE_MODES, m.game_type) + '</select></div>' +
      '<div class="field"><label>难度</label><select id="seDiff">' + saveOptions(SAVE_DIFFS, m.difficulty) + '</select></div>' +
      '<div class="field"><label>天气</label><select id="seWeather">' + saveOptions(SAVE_WEATHER, m.weather) + '</select></div>' +
      '<div class="field"><label>世界时间（0 清晨 / 6000 正午 / 18000 午夜）</label><input id="seTime" type="number" min="0" max="2147483" value="' + Number(m.day_time || 0) + '" /></div>' +
      '<div class="field"><label>出生点 X,Y,Z</label><input id="seSpawn" value="' + esc(spawn) + '" /></div>' +
    '</div>' +
    '<label class="hint" style="display:flex;align-items:center;gap:6px;margin-top:8px"><input type="checkbox" id="seHardcore"' + (m.hardcore ? ' checked' : '') + ' /> 极限模式</label>' +
    '<label class="hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="seCheats"' + (m.allow_commands ? ' checked' : '') + ' /> 允许作弊指令</label>' +
    '<label class="hint" style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="seKeep"' + (keep ? ' checked' : '') + ' /> 死亡不掉落（keepInventory）</label>' +
    '<div class="hint" style="margin-top:10px">当前版本：' + esc(m.version || '未知') + ' · DataVersion ' + Number(m.data_version || 0) + '。保存前会自动备份 level.dat，请先完全退出游戏。</div>',
    '<button class="btn ghost" id="sheetCancel">取消</button><button class="btn primary" id="seOk">保存修改</button>');
  h('sheetCancel').onclick = closeSheet;
  h('seOk').onclick = async () => {
    const parts = String(h('seSpawn').value || '').split(',').map((x) => parseInt(x.trim(), 10));
    if (parts.length !== 3 || parts.some((n) => isNaN(n))) return toast('出生点需要 3 个整数，例如 0,64,0', 'error');
    const changes = {
      name: h('seName').value,
      game_type: Number(h('seMode').value),
      difficulty: Number(h('seDiff').value),
      weather: h('seWeather').value,
      day_time: Number(h('seTime').value || 0),
      spawn: parts,
      hardcore: h('seHardcore').checked,
      allow_commands: h('seCheats').checked,
      game_rules: { keepInventory: h('seKeep').checked ? 'true' : 'false' },
    };
    const r = await call('save_edit', folder, changes);
    toast(r.message, r.ok ? 'ok' : 'error');
    if (r.ok) { closeSheet(); loadSaves(); }
  };
};
ACT['save-convert'] = async (folder) => {
  let res, versions = [];
  try {
    res = await call('save_meta', folder);
    const list = await call('scan_versions');
    versions = (list || []).map((v) => v.id).filter(Boolean);
  } catch (err) { return toast(err.message || err, 'error'); }
  if (!res.ok) return toast(res.message, 'error');
  const m = res.meta || {};
  openSheet('转换存档版本 · ' + m.name,
    '<div class="form-grid">' +
      '<div class="field"><label>目标版本</label><input id="scTarget" list="scVersions" placeholder="例如 1.20.1" value="' + esc(m.version || '') + '" /></div>' +
      '<div class="field"><label>DataVersion（0 表示 1.9 以前）</label><input id="scData" type="number" min="0" max="99999" value="' + Number(m.data_version || 0) + '" /></div>' +
    '</div>' +
    '<datalist id="scVersions">' + versions.map((v) => '<option value="' + esc(v) + '"></option>').join('') + '</datalist>' +
    '<div class="hint" style="margin-top:10px">当前：' + esc(m.version || '未知') + ' · DataVersion ' + Number(m.data_version || 0) + '。转换只改写版本标记，不做区块升级；跨大版本前请整份备份世界目录。写入前会自动备份 level.dat。</div>',
    '<button class="btn ghost" id="sheetCancel">取消</button><button class="btn primary" id="scOk">开始转换</button>');
  h('sheetCancel').onclick = closeSheet;
  h('scOk').onclick = async () => {
    const target = String(h('scTarget').value || '').trim();
    if (!target) return toast('请填写目标版本，例如 1.20.1', 'error');
    const r = await call('save_convert', folder, target, Number(h('scData').value || 0));
    toast(r.message, r.ok ? 'ok' : 'error');
    if (r.ok) { closeSheet(); loadSaves(); }
  };
};

/* ---------- 存档转换器 ---------- */
function worldSourceRows(st) {
  const res = st.scanned || {};
  const rows = [];
  (res.worlds || []).forEach((w) => rows.push({
    value: w.path,
    group: '已检测到存档',
    label: '世界 · ' + w.name + ' · ' + w.format_label + (w.data_version ? ' · DV ' + w.data_version : '') + (w.source ? ' · ' + w.source : ''),
    era: w.era,
  }));
  (res.backups || []).forEach((b) => rows.push({
    value: b.path,
    group: '备份存档',
    label: '备份 · ' + b.name + ' · ' + b.format_label + ' · ' + fmtTime(b.created),
    era: b.era,
  }));
  (st.extra || []).forEach((item) => { if (!rows.some((row) => row.value === item.value)) rows.push(item); });
  return rows;
}
function worldSourceOptions(rows, selected) {
  const groups = new Map();
  rows.forEach((row) => {
    const key = row.group || '手动选择';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  });
  return Array.from(groups.entries()).map(([group, items]) =>
    '<optgroup label="' + esc(group) + '">' + items.map((row) =>
      '<option value="' + esc(row.value) + '"' + (row.value === selected ? ' selected' : '') + '>' + esc(row.label) + '</option>'
    ).join('') + '</optgroup>').join('');
}
async function loadWorldTool(force) {
  const box = h('worldBox'); if (!box) return;
  const st = S.worldTool;
  if (st.scanned && !force) { renderWorldTool(); return; }
  box.innerHTML = '<div class="loading"><span class="spinner"></span>扫描全部存档位置…</div>';
  let res;
  try { res = await call('world_tool_scan'); } catch (err) { box.innerHTML = '<div class="empty">' + esc(err.message || err) + '</div>'; return; }
  if (!res.ok) { box.innerHTML = '<div class="empty">' + esc(res.message || '扫描失败') + '</div>'; return; }
  st.scanned = res;
  const rows = worldSourceRows(st);
  if (!st.source && rows.length) st.source = rows[0].value;
  if (!st.target) st.target = (res.installed || [])[0] || (res.targets || [])[0] || '';
  if (!st.workers) st.workers = res.workers || 4;
  if (!st.output && st.target) {
    const out = await call('world_target_dir', st.target).catch(() => null);
    if (out && out.ok) st.output = out.path;
  }
  renderWorldTool();
}
function renderWorldTool() {
  const box = h('worldBox'); if (!box) return;
  const st = S.worldTool;
  const res = st.scanned || {};
  const rows = worldSourceRows(st);
  const current = rows.find((row) => row.value === st.source) || rows[0] || null;
  if (current && st.source !== current.value) st.source = current.value;
  const installed = new Set(res.installed || []);
  const targets = res.targets || [];
  if (!st.target) st.target = (res.installed || [])[0] || targets[0] || '';
  const targetOptions = targets.map((v) =>
    '<option value="' + esc(v) + '"' + (v === st.target ? ' selected' : '') + '>' + esc(v) + (installed.has(v) ? ' · 已安装' : '') + '</option>'
  ).join('');
  const eraOptions = (res.eras || [{ id: 'auto', name: '自动检测' }]).map((e) =>
    '<option value="' + esc(e.id) + '"' + (e.id === st.era ? ' selected' : '') + '>' + esc(e.name) + '</option>'
  ).join('');
  box.innerHTML =
    '<div class="form-grid">' +
      '<div class="field"><label>要转换的存档</label><select id="worldSource">' +
        (rows.length ? worldSourceOptions(rows, st.source) : '<option value="">没有检测到存档，请点右上角手动选择</option>') +
      '</select>' + (current ? '<div class="hint">' + esc(current.label) + '</div>' : '') + '</div>' +
      '<div class="field"><label>初始版本 / 存档格式</label><select id="worldEra">' + eraOptions + '</select>' +
        '<div class="hint">自动检测失败时再手动指定；2009 年的 Classic 旧二进制会解析并重映射方块 ID。</div></div>' +
      '<div class="field"><label>目标版本</label><select id="worldTarget">' + (targetOptions || '<option value="">没有可用目标版本</option>') + '</select></div>' +
      '<div class="field"><label>输出目录</label><div class="field-row">' +
        '<input id="worldOutput" value="' + esc(st.output) + '" placeholder="默认写入目标版本的 saves 目录" style="flex:1" />' +
        '<button class="btn small ghost" data-act="world-default-out">默认目录</button></div></div>' +
      '<div class="field"><label>并行线程数</label><input id="worldWorkers" type="number" min="1" max="16" value="' + esc(String(st.workers || 4)) + '" />' +
        '<div class="hint">区域/区块文件按线程并行转换，机械硬盘建议 2~4。</div></div>' +
    '</div>' +
    '<div class="toolbar" style="margin-top:8px">' +
      '<button class="btn primary" data-act="world-start"' + (rows.length && st.target ? '' : ' disabled') + '>开始转换</button>' +
      '<button class="btn ghost" data-act="world-backup"' + (rows.length ? '' : ' disabled') + '>备份所选存档</button>' +
      '<span class="hint">旧格式先转成 Anvil 1.12.2 中间格式，再由目标版本首次打开时自动升级；转换结果可直接被目标版本识别。</span>' +
    '</div>' +
    '<div id="worldProgress" style="margin-top:10px"></div>';
  if (st.running || st.result) paintWorldProgress();
  const bind = (id, fn) => { const node = h(id); if (node) node.addEventListener('change', fn); };
  bind('worldSource', (e) => { st.source = e.target.value; renderWorldTool(); });
  bind('worldEra', (e) => { st.era = e.target.value; });
  bind('worldTarget', async (e) => {
    st.target = e.target.value;
    const out = await call('world_target_dir', st.target).catch(() => null);
    if (out && out.ok) { st.output = out.path; const input = h('worldOutput'); if (input) input.value = out.path; }
  });
  bind('worldOutput', (e) => { st.output = e.target.value; });
  bind('worldWorkers', (e) => { st.workers = Number(e.target.value || 0); });
}
function paintWorldProgress(job) {
  const box = h('worldProgress'); if (!box) return;
  const st = S.worldTool;
  const pct = job ? job.percent : st.progress;
  const logs = (job ? job.logs : st.logs) || [];
  const stage = job ? job.stage : (st.running ? '转换中' : (st.result ? '已完成' : ''));
  const result = (job && job.result) || st.result || null;
  box.innerHTML =
    '<div class="progress"><i style="width:' + Math.min(100, Math.max(0, pct || 0)) + '%"></i></div>' +
    '<div class="hint mono" style="margin-top:4px">' + esc(stage + ' · ' + Number(pct || 0).toFixed(1) + '%') + '</div>' +
    (logs.length ? '<div class="hint mono" style="margin-top:6px;max-height:150px;overflow:auto;white-space:pre-wrap">' + logs.map(esc).join('<br>') + '</div>' : '') +
    (st.result && !st.running ? '<div class="hint" style="margin-top:6px">' + esc((st.result.warnings || []).join('；') || '转换完成') + '</div>' : '') +
    (result && result.output ? '<div class="toolbar" style="margin-top:6px"><span class="hint mono" style="flex:1">输出：' + esc(result.output) + '</span>' +
      '<button class="btn small ghost" data-act="world-open" data-arg="' + A(result.output) + '">打开输出目录</button></div>' : '');
}
async function pollWorldJob(jobId) {
  const st = S.worldTool;
  while (st.jobId === jobId) {
    await new Promise((resolve) => setTimeout(resolve, 800));
    let list;
    try { list = await call('tasks'); } catch (_) { continue; }
    const job = (list || []).find((item) => item.id === jobId);
    if (!job) continue;
    st.progress = job.percent;
    st.logs = job.logs || [];
    if (job.state === 'running' || job.state === 'paused') { paintWorldProgress(job); continue; }
    st.running = false;
    st.jobId = '';
    st.result = job.state === 'ok' ? (job.result || {}) : null;
    paintWorldProgress(job);
    if (job.state === 'ok') { toast('存档转换完成', 'ok'); loadSaves(); }
    else toast(job.error || '转换未完成', 'error');
    return;
  }
}
ACT['world-refresh'] = () => loadWorldTool(true);
ACT['world-quick'] = (path) => {
  const st = S.worldTool;
  st.extra = st.extra || [];
  const name = String(path || '').split(/[\\/]/).pop() || path;
  st.extra.push({ value: path, group: '手动选择', label: '手动 · ' + name, era: 'auto' });
  st.source = path;
  st.result = null;
  renderWorldTool();
  const card = h('worldBox') && h('worldBox').closest('.card');
  if (card) {
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    card.classList.add('flash');
    setTimeout(() => card.classList.remove('flash'), 1200);
  }
  toast('已带入存档，选择目标版本后点「开始转换」', 'ok');
};
ACT['world-pick-dir'] = async () => {
  const res = await call('world_pick_dir');
  if (!res.ok) return toast(res.message || '未选择文件夹', 'error');
  const st = S.worldTool;
  st.extra = st.extra || [];
  st.extra.push({ value: res.path, group: '手动选择', label: '手动 · ' + res.world.name + ' · ' + res.world.format_label, era: res.world.era });
  st.source = res.path;
  renderWorldTool();
  toast('已选择存档：' + res.world.name, 'ok');
};
ACT['world-pick-zip'] = async () => {
  const res = await call('world_pick_zip');
  if (!res.ok) return toast(res.message || '未选择文件', 'error');
  const st = S.worldTool;
  st.extra = st.extra || [];
  st.extra.push({ value: res.path, group: '手动选择', label: '手动备份 · ' + res.world.name + ' · ' + res.world.format_label, era: res.world.era });
  st.source = res.path;
  renderWorldTool();
  toast('已选择备份：' + res.world.name, 'ok');
};
ACT['world-backup'] = async () => {
  const st = S.worldTool;
  if (!st.source) return toast('请先选择存档', 'error');
  if (/\.zip$/i.test(st.source)) return toast('所选是备份压缩包，无需再次备份', 'error');
  const res = await call('world_backup', st.source);
  if (!res.ok) return toast(res.message || '备份失败', 'error');
  toast('已备份到 ' + res.path, 'ok');
  await loadWorldTool(true);
};
ACT['world-default-out'] = async () => {
  const st = S.worldTool;
  if (!st.target) return toast('请先选择目标版本', 'error');
  const out = await call('world_target_dir', st.target);
  if (!out.ok) return toast(out.message || '无法获取目录', 'error');
  st.output = out.path;
  const input = h('worldOutput'); if (input) input.value = out.path;
};
ACT['world-start'] = async () => {
  const st = S.worldTool;
  if (st.running) return toast('已有转换任务正在运行', 'error');
  if (!st.source) return toast('请选择要转换的存档', 'error');
  if (!st.target) return toast('请选择目标版本', 'error');
  const res = await call('world_convert_start', st.source, st.era || 'auto', st.target, st.output || '', Number(st.workers || 0));
  if (!res.ok) return toast(res.message || '无法开始转换', 'error');
  const job = res.job || {};
  st.running = true;
  st.jobId = job.id || '';
  st.progress = 0;
  st.logs = job.logs || [];
  st.result = null;
  paintWorldProgress(job.id ? job : null);
  toast('已开始转换：' + (job.title || st.source), 'ok');
  if (st.jobId) pollWorldJob(st.jobId);
};
ACT['world-open'] = async (path) => {
  const res = await call('world_open', path);
  if (!res.ok) toast(res.message || '无法打开目录', 'error');
};

/* ---------- 截图图库 / 崩溃报告 / 地形 / NBT ---------- */
async function loadGallery() {
  const box = h('galleryBox'); if (!box) return;
  let res;
  try { res = await call('gallery_list'); } catch (err) { box.innerHTML = '<div class="empty">' + esc(err.message || err) + '</div>'; return; }
  const items = res.items || [];
  S.galleryAll = items.map((item) => item.path);
  S.gallerySel = '';
  box.innerHTML =
    '<div class="hint mono" style="margin-bottom:6px">' + esc(res.dir || '') + '</div>' +
    (items.length
      ? '<div class="grid2" style="gap:10px;flex:1;min-height:0"><div class="list gallery-list" style="flex:1;max-height:340px;overflow:auto">' +
        items.map((item) =>
          '<div class="row gallery-row" data-act="gallery-pick" data-arg="' + A(item.path) + '"><div class="row-main"><b>' + esc(item.name) + '</b>' +
          '<small>' + fmtSize(item.size) + ' · ' + fmtTime(item.mtime) + '</small></div></div>'
        ).join('') + '</div>' +
        '<div style="flex:1;display:flex;align-items:center;justify-content:center;background:#0d1712;border-radius:10px;min-height:240px">' +
        '<img id="galleryPreview" alt="" style="max-width:100%;max-height:320px;display:none;border-radius:8px" />' +
        '<span id="galleryHint" class="hint">点击左侧截图预览</span></div></div>'
      : '<div class="empty">当前版本还没有截图。游戏里按 F2 截图后会自动出现在这里。</div>');
}
ACT['gallery-pick'] = async (path) => {
  S.gallerySel = path;
  document.querySelectorAll('.gallery-row').forEach((row) => {
    row.classList.toggle('active', decodeURIComponent(row.dataset.arg || '') === path);
  });
  const src = await call('preview', path);
  const img = h('galleryPreview');
  if (img && src) { img.src = src; img.style.display = 'block'; if (h('galleryHint')) h('galleryHint').style.display = 'none'; }
};
ACT['gallery-export'] = async () => {
  const paths = S.gallerySel ? [S.gallerySel] : (S.galleryAll || []);
  if (!paths.length) return toast('还没有可导出的截图', 'error');
  const res = await call('gallery_export', paths);
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['gallery-delete'] = async () => {
  const paths = S.gallerySel ? [S.gallerySel] : [];
  if (!paths.length) return toast('请先点选一张截图', 'error');
  if (!(await ask('删除截图', '将直接从磁盘删除所选截图，不可恢复。确定继续？'))) return;
  const res = await call('gallery_delete', paths);
  toast(res.message, res.ok ? 'ok' : 'error');
  loadGallery();
};

async function loadCrashes() {
  const box = h('crashBox'); if (!box) return;
  let res;
  try { res = await call('crashes_list'); } catch (err) { box.innerHTML = '<div class="empty">' + esc(err.message || err) + '</div>'; return; }
  const items = res.items || [];
  S.crashSel = '';
  box.innerHTML =
    '<div class="hint mono" style="margin-bottom:6px">' + esc(res.dir || '') + '</div>' +
    (items.length
      ? '<div class="grid2" style="gap:10px;flex:1;min-height:0"><div class="list" style="flex:1;max-height:340px;overflow:auto">' +
        items.map((item) =>
          '<div class="row crash-row" data-act="crash-open" data-arg="' + A(item.path) + '"><div class="row-main"><b>' + esc(item.name) + '</b>' +
          '<small>' + fmtSize(item.size) + ' · ' + fmtTime(item.mtime) + '</small></div></div>'
        ).join('') + '</div>' +
        '<div style="flex:1;min-height:240px"><div class="log-box" id="crashText" style="height:100%;max-height:320px">选择左侧日志查看内容…</div></div></div>'
      : '<div class="empty">还没有崩溃日志。游戏异常退出后会自动归档到 data/logs/crashes/。</div>');
}
ACT['crash-open'] = async (path) => {
  S.crashSel = path;
  document.querySelectorAll('.crash-row').forEach((row) => {
    row.classList.toggle('active', decodeURIComponent(row.dataset.arg || '') === path);
  });
  const res = await call('crash_read', path);
  if (h('crashText')) h('crashText').textContent = res.ok ? res.text : (res.message || '读取失败');
};
ACT['crash-copy'] = async () => {
  if (!S.crashSel) return toast('请先点选一份崩溃日志', 'error');
  const res = await call('crash_copy', S.crashSel);
  toast(res.message, res.ok ? 'ok' : 'error');
};
ACT['crash-delete'] = async () => {
  if (!S.crashSel) return toast('请先点选一份崩溃日志', 'error');
  if (!(await ask('删除崩溃日志', '将直接从磁盘删除该日志，确定继续？'))) return;
  const res = await call('crash_delete', [S.crashSel]);
  toast(res.message, res.ok ? 'ok' : 'error');
  loadCrashes();
};

ACT['terrain-run'] = async () => {
  const box = h('terrainBox');
  if (!box) return;
  box.innerHTML = '<div class="loading"><span class="spinner"></span>正在生成高度图…（首次会编译 Java 程序，可能需要多等一会）</div>';
  const res = await call('seed_preview', (h('terrainSeed') && h('terrainSeed').value.trim()) || '',
    '', Number((h('terrainSize') && h('terrainSize').value) || 256),
    (h('terrainVersion') && h('terrainVersion').value) || '');
  if (!res.ok) { box.innerHTML = '<div class="empty">' + esc(res.message) + '</div>'; return; }
  const job = await watchJob(res.job);
  if (job && job.state === 'ok') {
    const result = job.result || {};
    box.innerHTML =
      '<div class="hint">种子 <b class="mono">' + esc(String(result.seed)) + '</b> · ' + esc(String(result.size)) + '×' + esc(String(result.size)) + '</div>' +
      (result.url ? '<img src="' + result.url + '" alt="地形高度图" style="max-width:100%;border-radius:10px;margin-top:8px" />' : '') +
      '<div class="toolbar" style="margin-top:8px"><button class="btn small ghost" data-act="open-path" data-arg="terrain">打开高度图目录</button>' +
      '<button class="btn small ghost" data-act="terrain-run">重新生成</button></div>';
  } else {
    const message = (job && (job.error || job.stage)) || '未知错误';
    box.innerHTML = '<div class="empty">生成失败：' + esc(message) + '</div>';
  }
};

const NBT_TAGS = { 0: 'End', 1: 'Byte', 2: 'Short', 3: 'Int', 4: 'Long', 5: 'Float', 6: 'Double', 7: 'ByteArray', 8: 'String', 9: 'List', 10: 'Compound', 11: 'IntArray', 12: 'LongArray' };
function nbtNodeAction(pointer, label, canAdd) {
  return '<span class="nbt-actions">' +
    '<button class="btn small ghost" data-act="nbt-copy" data-arg="' + A({ pointer: pointer, label: label }) + '">复制</button>' +
    (canAdd ? '<button class="btn small ghost" data-act="nbt-add" data-arg="' + A({ pointer: pointer, label: label }) + '">添加</button>' : '') +
    (pointer.length ? '<button class="btn small danger" data-act="nbt-delete" data-arg="' + A({ pointer: pointer, label: label }) + '">删除</button>' : '') +
    '</span>';
}
function nbtNodeHtml(node, pointer, label, depth) {
  const tag = Number((node && node.tag) || 0);
  const pad = 'padding-left:' + Math.min(depth, 14) * 13 + 'px';
  if (tag === 10) {
    const kids = Object.entries((node.value) || {});
    return '<div class="nbt-head" style="' + pad + '"><b>' + esc(label) + '</b> <span class="tag">Compound</span><small>' + kids.length + ' 项</small>' +
      nbtNodeAction(pointer, label, true) + '</div>' +
      kids.map(([key, value]) => nbtNodeHtml(value, pointer.concat([key]), key, depth + 1)).join('');
  }
  if (tag === 9) {
    const info = node.value || {};
    const items = info.items || [];
    return '<div class="nbt-head" style="' + pad + '"><b>' + esc(label) + '</b> <span class="tag">List</span><small>' + items.length + ' 项（' + esc(NBT_TAGS[info.element] || String(info.element)) + '）</small>' +
      nbtNodeAction(pointer, label, false) + '</div>' +
      items.map((value, index) => nbtNodeHtml(value, pointer.concat([index]), '[' + index + ']', depth + 1)).join('');
  }
  if (tag === 7 || tag === 11 || tag === 12) {
    const arr = node.value || [];
    return '<div class="nbt-head" style="' + pad + '"><b>' + esc(label) + '</b> <span class="tag">' + esc(NBT_TAGS[tag]) + '</span>' +
      '<small class="mono">' + esc(arr.slice(0, 8).join(', ')) + (arr.length > 8 ? ' …（' + arr.length + ' 项）' : '') + '</small>' +
      nbtNodeAction(pointer, label, false) + '</div>';
  }
  return '<div class="nbt-row" style="' + pad + '"><b>' + esc(label) + '</b> <span class="tag">' + esc(NBT_TAGS[tag] || String(tag)) + '</span>' +
    '<small class="mono">' + esc(String(node.value)) + '</small>' +
    '<span class="nbt-actions"><button class="btn small ghost" data-act="nbt-edit" data-arg="' + A({ pointer: pointer, value: node.value, label: label }) + '">修改</button>' +
    nbtNodeAction(pointer, label, false).replace('<span class="nbt-actions">', '') + '</span></div>';
}
function nbtFind(node, pointer) {
  let current = node;
  for (const key of pointer || []) {
    if (!current) return null;
    if (Number(current.tag) === 10) current = (current.value || {})[String(key)];
    else if (Number(current.tag) === 9) current = ((current.value || {}).items || [])[Number(key)];
    else return null;
  }
  return current || null;
}
function paintNbt() {
  const box = h('nbtBox');
  if (!box || !S.nbt) return;
  box.innerHTML =
    '<div class="hint mono" style="margin-bottom:6px">' + esc(S.nbt.path) + ' · 根标签 ' + esc(S.nbt.root) + '</div>' +
    '<div class="nbt-tree">' + nbtNodeHtml(S.nbt.tree, [], S.nbt.root || 'root', 0) + '</div>';
}
ACT['nbt-open'] = async () => {
  const res = await call('nbt_open');
  if (!res.ok) return toast(res.message, 'error');
  S.nbt = res;
  paintNbt();
  toast('已打开 ' + res.path, 'ok');
};
ACT['nbt-edit'] = (arg) => {
  if (!S.nbt) return;
  openSheet('修改 NBT 节点 · ' + (arg.label || ''),
    '<div class="field"><label>新值</label><input type="text" id="nbtValue" value="' + esc(String(arg.value)) + '" /></div>' +
    '<div class="hint" style="margin-top:8px">保存前自动生成 .bak 备份；只修改确定含义的字段。</div>',
    '<button class="btn ghost" id="nbtCancel">取消</button><button class="btn primary" id="nbtSave">保存</button>');
  h('nbtCancel').onclick = closeSheet;
  h('nbtSave').onclick = async () => {
    const res = await call('nbt_edit', S.nbt.path, arg.pointer || [], h('nbtValue').value);
    toast(res.message, res.ok ? 'ok' : 'error');
    if (res.ok) {
      const reload = await call('nbt_read', S.nbt.path);
      if (reload.ok) S.nbt = reload;
      paintNbt();
      closeSheet();
    }
  };
};

ACT['nbt-copy'] = (arg) => {
  if (!S.nbt) return;
  const node = nbtFind(S.nbt.tree, (arg && arg.pointer) || []);
  if (!node) return toast('找不到该节点', 'error');
  copyText(JSON.stringify(node, null, 2));
};
ACT['nbt-delete'] = async (arg) => {
  if (!S.nbt) return;
  const label = (arg && arg.label) || '该节点';
  if (!(await ask('删除 NBT 节点', '将删除「' + label + '」及其全部子项，写回前自动备份为 .bak。'))) return;
  const res = await call('nbt_delete', S.nbt.path, (arg && arg.pointer) || []);
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) {
    const reload = await call('nbt_read', S.nbt.path);
    if (reload.ok) S.nbt = reload;
    paintNbt();
  }
};
ACT['nbt-add'] = (arg) => {
  if (!S.nbt) return;
  openSheet('添加 NBT 标签 · ' + ((arg && arg.label) || '根节点'),
    '<div class="form-grid">' +
      '<div class="field"><label>标签名</label><input id="naName" placeholder="例如 LevelName" /></div>' +
      '<div class="field"><label>类型</label><select id="naTag">' +
        '<option value="8">String</option><option value="3">Int</option><option value="1">Byte</option>' +
        '<option value="2">Short</option><option value="4">Long</option><option value="5">Float</option><option value="6">Double</option>' +
      '</select></div>' +
      '<div class="field"><label>值</label><input id="naValue" placeholder="文本或数字" /></div>' +
    '</div>' +
    '<div class="hint" style="margin-top:8px">只能添加到 Compound 节点下；写回前自动备份为 .bak。</div>',
    '<button class="btn ghost" id="naCancel">取消</button><button class="btn primary" id="naOk">添加</button>');
  h('naCancel').onclick = closeSheet;
  h('naOk').onclick = async () => {
    const res = await call('nbt_add', S.nbt.path, (arg && arg.pointer) || [],
      h('naName').value, Number(h('naTag').value), h('naValue').value);
    toast(res.message, res.ok ? 'ok' : 'error');
    if (res.ok) {
      const reload = await call('nbt_read', S.nbt.path);
      if (reload.ok) S.nbt = reload;
      paintNbt();
      closeSheet();
    }
  };
};

ACT['tool-log'] = async (kind) => {
  const res = await call('logs_tail', kind, 220);
  if (!res.ok) return toast(res.message, 'error');
  openSheet((kind === 'launcher' ? '启动器日志' : '游戏日志'),
    '<div class="hint mono" style="margin-bottom:8px">' + esc(res.path) + '</div>' +
    '<div class="log-box" style="max-height:60vh">' + esc(res.text || '（空）') + '</div>',
    '<button class="btn ghost" id="logCopy">复制</button><button class="btn primary" id="logClose">关闭</button>');
  h('logCopy').onclick = () => copyText(res.text || '');
  h('logClose').onclick = closeSheet;
};
ACT['clean-game'] = async () => {
  if (!(await ask('清理缓存', '将删除损坏/未完成的版本与缓存文件，不会动存档、mods。继续？'))) return;
  const res = await call('clean_game');
  toast(res.message, res.ok ? 'ok' : 'error');
  if (res.ok) { await reloadVersions(true); loadSaves(); }
};
ACT['import-modpack'] = async () => {
  const res = await call('install_modpack_file');
  if (!res.ok) return toast(res.message, 'error');
  toast(res.message, 'ok');
  const job = await watchJob(res.job);
  if (job && job.state === 'ok') {
    toast('整合包安装完成', 'ok');
    await refreshBootstrap();
  } else {
    toast((job && (job.error || job.stage)) || '整合包安装未完成', 'error');
  }
};
ACT['import-external'] = async () => {
  const res = await call('import_external');
  if (!res.ok) return toast(res.message, 'error');
  const versions = res.versions || [];
  openSheet('从 ' + (res.kind || 'HMCL / PCL') + ' 导入',
    '<div class="hint">识别到配置：' + esc(res.name || '') + '<br />目录：<span class="mono">' + esc(res.game_dir || '') + '</span></div>' +
    '<div class="list" style="margin-top:10px;max-height:52vh;overflow:auto">' + (versions.length ? versions.map((v) =>
      '<label class="switch"><span class="switch-text"><b>' + esc(v.name || v.version_id) + '</b>' +
      '<small class="mono">' + esc(v.version_id) + (v.loader ? ' · ' + esc(v.loader) : '') + '</small></span>' +
      '<input type="checkbox" class="extPick" value="' + esc(v.version_id) + '" checked /></label>'
    ).join('') : '<div class="empty">没有可导入的版本。</div>') + '</div>',
    '<button class="btn ghost" id="extCancel">取消</button><button class="btn primary" id="extApply">导入所选</button>');
  h('extCancel').onclick = closeSheet;
  h('extApply').onclick = async () => {
    const ids = Array.from(document.querySelectorAll('.extPick')).filter((n) => n.checked).map((n) => n.value);
    if (!ids.length) return toast('请至少选择一个版本', 'error');
    h('extApply').disabled = true;
    const result = await call('import_external_apply', res.profile_dir, ids);
    h('extApply').disabled = false;
    if (!result.ok) return toast(result.message, 'error');
    closeSheet(); await refreshBootstrap(); toast('导入完成', 'ok');
  };
};

/* ---------- 设置 ---------- */
function sw(key, title, desc, checked) {
  return '<label class="switch"><span class="switch-text"><b>' + esc(title) + '</b><small>' + esc(desc) + '</small></span>' +
    '<input type="checkbox" data-set="' + key + '"' + (checked ? ' checked' : '') + ' /></label>';
}
function settingsTabs() {
  return [['general', '常规'], ['appearance', '外观'], ['download', '下载'], ['extensions', '扩展'], ['advanced', '高级'], ['about', '关于']]
    .map(([id, label]) => [id, T(label)]);
}
async function renderSettings() {
  const tabs = settingsTabs();
  h('view').innerHTML =
    '<div class="settings"><div class="settings-nav">' + tabs.map(([id, label]) =>
      '<button data-act="settings-tab" data-arg="' + id + '">' + esc(label) + '</button>').join('') +
    '</div><div class="settings-body" id="settingsBody"><div class="loading"><span class="spinner"></span>正在读取设置…</div></div></div>';
  syncSettingTabs();
  let cfg;
  try { cfg = await call('settings_get'); } catch (err) {
    h('settingsBody').innerHTML = '<div class="empty">' + esc(err.message || err) + '</div>';
    return;
  }
  S.settingsData = cfg;
  if (!S.settings.tab) S.settings.tab = 'general';
  fillSettingsBody(cfg);
}
function syncSettingTabs() {
  document.querySelectorAll('.settings-nav button').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.arg === (S.settings.tab || 'general'));
  });
}
ACT['settings-tab'] = (tab) => {
  S.settings.tab = tab;
  syncSettingTabs();
  if (S.settingsData) fillSettingsBody(S.settingsData);
  else renderSettings();
};
function fillSettingsBody(cfg) {
  const body = h('settingsBody'); if (!body) return;
  const tab = S.settings.tab || 'general';
  const withView = (tab === 'general' || tab === 'download' || tab === 'advanced');
  const view = S.settings.view === 'all' ? 'all' : 'common';
  const bar = withView
    ? '<div class="settings-viewbar"><div class="chips">' +
        '<button class="chip' + (view === 'common' ? ' active' : '') + '" data-act="settings-view" data-arg="common">常用</button>' +
        '<button class="chip' + (view === 'all' ? ' active' : '') + '" data-act="settings-view" data-arg="all">显示全部</button>' +
      '</div><span class="hint">' + (view === 'all' ? '已展开全部设置项' : '只显示最常用的设置，点「显示全部」查看高级项') + '</span></div>'
    : '';
  if (tab === 'general') body.innerHTML = bar + settingsGeneral(cfg);
  else if (tab === 'appearance') body.innerHTML = settingsAppearance(cfg);
  else if (tab === 'extensions') body.innerHTML = settingsExtensions(cfg);
  else if (tab === 'download') body.innerHTML = bar + settingsDownload(cfg);
  else if (tab === 'advanced') body.innerHTML = bar + settingsAdvanced(cfg);
  else body.innerHTML = settingsAbout(cfg);
  body.classList.toggle('settings-compact', withView && view === 'common');
  applyBackground(cfg.background_image);
  applyDynamicWallpaper(cfg.dynamic_wallpaper);
}
ACT['settings-view'] = (view) => {
  S.settings.view = view === 'all' ? 'all' : 'common';
  if (S.settingsData) fillSettingsBody(S.settingsData);
};
function settingsGeneral(cfg) {
  const javas = ((S.data && S.data.java && S.data.java.list) || []);
  return '<div class="section"><h3>玩家与目录</h3>' +
      '<div class="field"><label>玩家名</label><input type="text" value="' + esc(cfg.player_name) + '" data-set="player_name" /></div>' +
      '<div class="field"><label>界面语言</label><select data-set="language">' +
        (cfg.languages || []).map((item) => '<option value="' + esc(item.code) + '"' + (item.code === cfg.language ? ' selected' : '') + '>' + esc(item.name) + '</option>').join('') +
      '</select><div class="hint">协议、教程与内容检索会按语言切换；设置保存后立即生效。</div></div>' +
      '<div class="field"><label>游戏目录</label><div class="field-row"><input type="text" readonly value="' + esc(cfg.game_dir) + '" style="flex:1" />' +
        '<button class="btn small ghost" data-act="set-game-dir">更改</button>' +
        '<button class="btn small ghost" data-act="open-game-dir">打开</button></div></div>' +
    '</div>' +
    '<div class="section adv-only"><h3>数据目录</h3><div class="hint" style="margin-bottom:8px">可添加多个 .minecraft 目录并快速切换；与经典版共用同一份目录列表。</div>' +
      '<div class="list">' + ((cfg.game_dirs || []).map((d) =>
        '<div class="row"><div class="row-main"><b>' + esc(d.name) + (d.id === cfg.active_game_dir ? ' <span class="tag">使用中</span>' : '') + '</b>' +
        '<small class="mono">' + esc(d.path) + '</small></div><div style="display:flex;gap:6px">' +
        (d.id === cfg.active_game_dir ? '' : '<button class="btn small ghost" data-act="dir-select" data-arg="' + A(d.id) + '">切换</button>') +
        ((cfg.game_dirs || []).length > 1 ? '<button class="btn small danger" data-act="dir-remove" data-arg="' + A(d.id) + '">移除</button>' : '') +
        '</div></div>').join('')) + '</div>' +
      '<div class="toolbar" style="margin-top:8px"><button class="btn small ghost" data-act="dir-add">添加目录</button></div></div>' +
    '<div class="section adv-only"><h3>从其他启动器导入</h3>' +
      '<div class="hint" style="margin-bottom:8px">扫描 PCL / HMCL 的配置目录，把已有版本、内存与启动设置一并搬过来；本启动器已存在的版本会自动跳过。</div>' +
      '<div class="toolbar"><button class="btn small ghost" data-act="import-launcher">扫描并导入…</button></div></div>' +
    '<div class="section"><h3>Java 运行时</h3>' +
      '<div class="field"><label>Java 路径</label><div class="field-row">' +
        '<input type="text" value="' + esc(cfg.java_path || '') + '" placeholder="留空自动选择，或填写 javaw.exe 完整路径" data-set="java_path" style="flex:1" />' +
        '<button class="btn small ghost" data-act="java-pick-file">浏览…</button></div>' +
        '<div class="hint">支持手动指定任意 Java；留空时按版本需求自动挑选。</div></div>' +
      '<div class="list">' + (javas.length ? javas.map((j) =>
        '<div class="row"><div class="row-main"><b>Java ' + esc(String(j.major)) + ' <span class="tag">' + esc(j.vendor || '') + '</span></b>' +
        '<small class="mono">' + esc(j.path) + '</small><small>' + esc(j.version || '') + (j.arch ? ' · ' + esc(j.arch) : '') + '</small></div>' +
        '<button class="btn small ' + (j.path === cfg.java_path ? 'ghost' : 'primary') + '" data-act="java-use" data-arg="' + A(j.path) + '">' +
        (j.path === cfg.java_path ? '使用中' : '使用') + '</button></div>').join('') : '<div class="empty">还没有扫描到 Java。请到「下载中心 → Java」安装。</div>') + '</div>' +
      '<div class="toolbar" style="margin-top:8px"><button class="btn small ghost" data-act="java-rescan">重新扫描</button>' +
        '<button class="btn small ghost" data-act="go-download" data-arg="java">下载 Java</button></div>' +
    '</div>' +
    '<div class="section"><h3>内存（MB）</h3>' +
      '<div class="field-row"><input type="range" min="512" max="16384" step="512" value="' + esc(String(cfg.memory_mb)) + '" data-set="memory_mb" data-number="1" data-live="memValue" data-suffix=" MB" style="flex:1" />' +
        '<b class="mono" id="memValue" style="min-width:74px;text-align:right">' + esc(String(cfg.memory_mb)) + ' MB</b></div>' +
      '<div class="hint">建议不超过物理内存的 70%。低配机器推荐 2~4 GB。</div>' +
      '<div class="toolbar" style="margin-top:8px"><button class="btn small ghost" data-act="mem-auto">按本机配置自动分配</button></div>' +
    '</div>' +
    '<div class="section"><h3>隔离模式</h3><div class="chips">' +
      Object.entries(cfg.isolation_options || {}).map(([key, label]) =>
        '<button class="chip' + (key === cfg.isolation_mode ? ' active' : '') + '" data-act="set-isolation" data-arg="' + key + '">' + esc(label) + '</button>'
      ).join('') + '</div></div>' +
    '<div class="section"><h3>启动行为</h3>' +
      '<div class="field"><label>启动后</label><select data-set="after_launch_action">' +
        Object.entries(cfg.after_options || {}).map(([key, label]) =>
          '<option value="' + key + '"' + (key === cfg.after_launch_action ? ' selected' : '') + '>' + esc(label) + '</option>').join('') +
      '</select></div>' +
      '<div class="field adv-only"><label>进程优先级</label><select data-set="process_priority">' +
        Object.entries(cfg.priority_options || {}).map(([key, label]) =>
          '<option value="' + key + '"' + (key === cfg.process_priority ? ' selected' : '') + '>' + esc(label) + '</option>').join('') +
      '</select></div>' +
      '<div class="field adv-only"><label>预加载 JVM</label>' + sw('preload_jvm', '启动器启动时预热 Java', '默认关闭：会额外常驻一个 Java 进程做预热，低配机器开着反而更占内存', cfg.preload_jvm) +
        '<div class="field-row" style="margin-top:8px"><select data-set="preload_java_path" style="flex:1">' +
          '<option value="">自动（跟随当前 Java）</option>' +
          javas.map((j) => '<option value="' + esc(j.path) + '"' + (j.path === cfg.preload_java_path ? ' selected' : '') + '>Java ' + esc(String(j.major)) + ' · ' + esc(j.vendor || j.arch || '') + '</option>').join('') +
        '</select></div></div>' +
      '<div class="field adv-only"><label>启动动画</label>' + sw('start_animation', '启动游戏时显示启动动画', '关闭后直接进入游戏窗口，减少低配机器的等待感', cfg.start_animation) + '</div>' +
      '<div class="field adv-only"><label>额外 JVM 参数</label><input type="text" value="' + esc(cfg.extra_jvm_args || '') + '" placeholder="-Dfile.encoding=UTF-8 -XX:+UseG1GC" data-set="extra_jvm_args" /></div>' +
      '<div class="field adv-only"><label>额外游戏参数</label><input type="text" value="' + esc(cfg.extra_game_args || '') + '" placeholder="例如 --fullscreen 或 --width 1920" data-set="extra_game_args" /></div>' +
      '<div class="field adv-only"><label>游戏窗口标题</label><input type="text" value="' + esc(cfg.window_title || '') + '" placeholder="留空使用默认标题" data-set="window_title" /></div>' +
    '</div>' +
    '<div class="section"><h3>游戏窗口</h3>' +
      '<div class="field-row">' +
        '<div class="field" style="flex:1"><label>窗口宽度</label><input type="number" min="0" max="16384" value="' + esc(String(cfg.width || 0)) + '" placeholder="0 = 游戏默认" data-set="width" data-number="1" /></div>' +
        '<div class="field" style="flex:1"><label>窗口高度</label><input type="number" min="0" max="16384" value="' + esc(String(cfg.height || 0)) + '" placeholder="0 = 游戏默认" data-set="height" data-number="1" /></div>' +
      '</div>' +
      '<div class="hint">填 0 表示交给游戏自己决定；与经典版的「窗口分辨率」完全一致。</div>' +
    '</div>' +
    '<div class="section"><h3>自动连接服务器</h3>' +
      '<div class="field">' + sw('auto_connect_enabled', '启动后自动进入服务器', '进入世界后直接连接指定服务器，等价于经典版的「自动连接服务器」', cfg.auto_connect_enabled) + '</div>' +
      '<div class="field-row">' +
        '<div class="field" style="flex:2"><label>服务器地址</label><input type="text" value="' + esc(cfg.auto_connect_server || '') + '" placeholder="mc.example.com 或 127.0.0.1" data-set="auto_connect_server" /></div>' +
        '<div class="field" style="flex:1"><label>端口</label><input type="number" min="1" max="65535" value="' + esc(String(cfg.auto_connect_port || 25565)) + '" data-set="auto_connect_port" data-number="1" /></div>' +
      '</div>' +
    '</div>' +
    '<div class="section"><h3>启动器窗口</h3>' +
      '<div class="field">' + sw('keep_launcher_on_game_exit', '游戏退出后保持启动器窗口', '关闭后游戏退出会连同启动器一起结束（与经典版一致）', cfg.keep_launcher_on_game_exit) + '</div>' +
    '</div>';
}
ACT['java-use'] = async (path) => {
  const res = await call('java_select', path);
  if (!res.ok) return toast(res.message, 'error');
  await refreshBootstrap(); renderSettings(); toast('已切换 Java', 'ok');
};
ACT['java-pick-file'] = async () => {
  const res = await call('java_pick');
  if (!res.ok) return toast(res.message || '未选择文件', 'error');
  await refreshBootstrap(); renderSettings(); toast('已切换 Java', 'ok');
};
ACT['open-game-dir'] = async () => {
  const res = await call('open_path', 'game');
  if (!res.ok) toast(res.message, 'error');
};
ACT['set-game-dir'] = async () => {
  const res = await call('set_game_dir', '');
  if (!res.ok) return toast(res.message, 'error');
  await refreshBootstrap(); renderSettings(); toast('游戏目录已更新', 'ok');
};
ACT['mem-auto'] = async () => {
  const res = await call('memory_auto');
  if (!res.ok) return toast(res.message || '检测失败', 'error');
  if (S.data) S.data.memory_mb = res.memory;
  const range = document.querySelector('[data-set="memory_mb"]');
  if (range) range.value = String(res.memory);
  const label = h('memValue');
  if (label) label.textContent = res.memory + ' MB';
  toast('已按本机配置分配 ' + res.memory + ' MB' + (res.summary ? '（' + res.summary + '）' : ''), 'ok');
};
ACT['import-launcher'] = async () => {
  const res = await call('import_scan', '');
  if (!res.ok) return toast(res.message || '未识别到配置', 'error');
  const items = res.versions || [];
  const body = '<div class="hint">识别为 ' + esc(res.kind) + ' · ' + esc(res.gameDir) + ' · 共 ' + items.length + ' 个版本</div>' +
    '<div class="list" style="margin-top:8px">' + items.map((v) =>
      '<label class="row" style="cursor:pointer"><input type="checkbox" class="imp-item" value="' + esc(v.id) + '"' +
      (v.exists ? ' disabled' : ' checked') + ' />' +
      '<div class="row-main"><b>' + esc(v.label) + '</b><small class="mono">' + esc(v.id) +
      (v.exists ? ' · 已存在，跳过' : '') + '</small></div></label>').join('') + '</div>' +
    '<label class="hint" style="display:block;margin-top:10px"><input type="checkbox" id="impSettings" checked /> 同时导入内存 / JVM / 启动设置</label>' +
    ((res.warnings || []).length ? '<div class="hint" style="margin-top:6px">' + esc(res.warnings.join('；')) + '</div>' : '');
  openSheet('从 ' + res.kind + ' 导入版本', body,
    '<button class="btn ghost" id="sheetCancel">取消</button><button class="btn primary" id="impGo">导入所选</button>');
  h('impGo').onclick = async () => {
    const ids = Array.from(document.querySelectorAll('.imp-item:checked')).map((n) => n.value);
    if (!ids.length) return toast('请至少选择一个版本', 'error');
    const keep = h('impSettings') ? h('impSettings').checked : true;
    const out = await call('import_apply', res.path, ids, keep, false);
    if (!out.ok) return toast(out.message || '导入失败', 'error');
    closeSheet();
    const stats = out.stats || {};
    const imported = (stats.imported || []).length;
    const skipped = (stats.skipped || []).length;
    toast('已导入 ' + imported + ' 个版本' + (skipped ? '，跳过 ' + skipped + ' 个' : ''), 'ok');
    await refreshBootstrap(); renderSettings();
  };
};
function accentPicker(cfg, themes) {
  const current = String(cfg.accent_color || '#65d46e').toLowerCase();
  const themeAccent = ((themes || []).find((t) => t.name === cfg.theme_name) || {}).accent || current;
  const presets = ['#65d46e', '#4ea1ff', '#a78bfa', '#f28bb4', '#ff6b6b', '#ffb454', '#2dd4bf', '#f4e04d'];
  return '<div class="field-row">' +
    '<input type="color" data-set="accent_color" value="' + esc(current) + '" style="width:56px;height:34px;padding:2px;flex:none" />' +
    '<input type="text" readonly value="' + esc(current) + '" style="flex:1" />' +
    '<button class="btn small ghost" data-act="accent-set" data-arg="' + A(themeAccent) + '">恢复主题色</button></div>' +
    '<div class="chips" style="margin-top:8px">' + presets.map((color) =>
      '<button class="chip' + (color === current ? ' active' : '') + '" data-act="accent-set" data-arg="' + A(color) + '">' +
      '<span class="swatch" style="background:' + color + '"></span>' + color.toUpperCase() + '</button>').join('') + '</div>' +
    '<div class="hint" style="margin-top:8px">点色块快速取色，或用左侧取色板选任意颜色；修改后立即生效并保存。</div>';
}
function textPicker(cfg) {
  const current = String(cfg.text_color || '').toLowerCase();
  const fallback = String((S.data && S.data.palette && S.data.palette.text) || '#1b2733').toLowerCase();
  const value = /^#[0-9a-f]{6}$/.test(current) ? current : fallback;
  return '<div class="field-row">' +
    '<input type="color" data-set="text_color" value="' + esc(value) + '" style="width:56px;height:34px;padding:2px;flex:none" />' +
    '<input type="text" readonly value="' + (current ? esc(current.toUpperCase()) : '跟随主题（' + esc(value.toUpperCase()) + '）') + '" style="flex:1" />' +
    '<button class="btn small ghost" data-act="text-reset">跟随主题</button></div>' +
    '<div class="hint" style="margin-top:8px">取色板修改正文与次要文字颜色，立即生效；次要文字亮度会自动按比例推导。</div>';
}
function themeChips(themes, activeName, wantLight) {
  return themes.filter((t) => !!t.light === wantLight).map((t) =>
    '<button class="chip' + (t.name === activeName ? ' active' : '') + '" data-act="theme-set" data-arg="' + A(t.name) + '">' +
    '<span class="swatch" style="background:' + esc(t.accent || 'var(--accent)') + '"></span>' + esc(t.name) + '</button>').join('');
}
function settingsAppearance(cfg) {
  const themes = (S.data && S.data.themes) || [];
  const frame = cfg.frame_mode || 'webview';
  const mode = cfg.color_mode || ((S.data && S.data.palette && S.data.palette.light) ? 'light' : 'dark');
  return '<div class="section"><h3>界面框架</h3><div class="chips">' +
      '<button class="chip' + (frame === 'webview' ? ' active' : '') + '" data-act="frame-set" data-arg="' + A('webview') + '">美化版（WebView2，推荐）</button>' +
      '<button class="chip' + (frame === 'classic' ? ' active' : '') + '" data-act="frame-set" data-arg="' + A('classic') + '">经典版（Qt）</button>' +
      '<button class="chip' + (frame === 'electron' ? ' active' : '') + '" data-act="frame-set" data-arg="' + A('electron') + '">独立版（Electron）</button>' +
    '</div><div class="hint" style="margin-top:8px">三套界面共用同一套启动、下载、账号与联机内核；切换后重启启动器生效，不会丢失下载进度或设置。独立版自带 Chromium、不依赖 WebView2，已随主程序内置，首次切换会自动释放，但内存与磁盘占用更高。</div>' +
    '<div class="toolbar" style="margin-top:8px"><button class="btn small ghost" data-act="app-restart">立即重启启动器</button></div></div>' +
    '<div class="section"><h3>明暗模式</h3><div class="chips">' +
      '<button class="chip' + (mode === 'light' ? ' active' : '') + '" data-act="color-mode" data-arg="' + A('light') + '">☀ 明亮</button>' +
      '<button class="chip' + (mode === 'dark' ? ' active' : '') + '" data-act="color-mode" data-arg="' + A('dark') + '">☾ 黑暗</button>' +
    '</div><div class="hint" style="margin-top:8px">标题栏右上角也有快捷切换按钮；明亮与黑暗各自记住上次选中的主题，切回来不会丢观感。</div></div>' +
    '<div class="section"><h3>主题</h3>' +
    '<div class="hint">明亮主题</div>' +
    '<div class="chips" style="margin-top:4px">' + themeChips(themes, cfg.theme_name, true) + '</div>' +
    '<div class="hint" style="margin-top:6px">黑暗主题</div>' +
    '<div class="chips" style="margin-top:4px">' + themeChips(themes, cfg.theme_name, false) + '</div>' +
    '<div class="hint" style="margin-top:8px">切换立即生效；导入过的主题会记录在本地，方便快速切回。</div>' +
    '<div class="toolbar" style="margin-top:8px"><button class="btn small ghost" data-act="theme-import">导入主题 JSON</button>' +
    '<button class="btn small ghost" data-act="theme-export">导出当前主题</button></div></div>' +
    '<div class="section"><h3>主题色</h3>' + accentPicker(cfg, themes) + '</div>' +
    '<div class="section"><h3>字体颜色</h3>' + textPicker(cfg) + '</div>' +
    '<div class="section"><h3>背景图</h3>' +
      '<div class="field-row"><input type="text" readonly value="' + esc(cfg.background_image || '未设置') + '" style="flex:1" />' +
        '<button class="btn small ghost" data-act="bg-pick">选择图片</button><button class="btn small ghost" data-act="bg-clear">清除</button></div>' +
      '<div class="hint" style="margin-top:8px">自定义背景会以暗色蒙版覆盖，保证文字可读。</div></div>' +
    '<div class="section"><h3>动态壁纸</h3>' +
      '<div class="field-row"><input type="text" readonly value="' + esc(cfg.dynamic_wallpaper || '未设置') + '" style="flex:1" />' +
        '<button class="btn small ghost" data-act="wallpaper-pick">选择动态壁纸</button><button class="btn small ghost" data-act="wallpaper-clear">清除</button></div>' +
      '<div class="hint" style="margin-top:8px">支持 MP4 / WebM 视频与 GIF / WebP 动图，循环静音播放；窗口最小化或切到后台时自动暂停。低配机器建议使用 720p 以内的短视频。</div></div>' +
    '<div class="section"><h3>桌面毛玻璃</h3>' +
      sw('glass_see_through', '透视桌面（真·毛玻璃）', '窗口背景真正透明，毛玻璃后面直接显示桌面内容；开启后忽略背景图与动态壁纸，需 Windows 10/11', cfg.glass_see_through) +
      '<div class="field-row" style="margin-top:8px"><label class="hint" style="flex:none">模糊</label>' +
        '<input type="range" min="0" max="64" step="1" value="' + esc(String(cfg.glass_blur == null ? 20 : cfg.glass_blur)) + '" data-set="glass_blur" data-number="1" data-live="glassBlurValue" data-glass-blur-preview="1" style="flex:1" />' +
        '<span class="hint" id="glassBlurValue" style="width:48px;text-align:right">' + esc(String(cfg.glass_blur == null ? 20 : cfg.glass_blur)) + 'px</span></div>' +
      '<div class="field-row" style="margin-top:6px"><label class="hint" style="flex:none">强度</label>' +
        '<input type="range" min="0" max="100" step="1" value="' + esc(String(cfg.glass_strength == null ? 62 : cfg.glass_strength)) + '" data-set="glass_strength" data-number="1" data-live="glassValue" data-glass-preview="1" data-suffix="%" style="flex:1" />' +
        '<span class="hint" id="glassValue" style="width:48px;text-align:right">' + esc(String(cfg.glass_strength == null ? 62 : cfg.glass_strength)) + '%</span></div>' +
      '<div class="hint" style="margin-top:6px">模糊 0 几乎不模糊、64 几乎看不清背景；强度 0 几乎全透明、100 几乎不透明。两者会同时作用在窗口与卡片上，低配机器建议模糊 12px、强度 55% 左右。</div></div>' +
    '<div class="section"><h3>界面细节</h3>' +
      '<div class="field-row"><label class="hint" style="flex:none">背景亮度</label>' +
        '<input type="range" min="70" max="130" step="1" value="' + esc(String(cfg.ui_brightness == null ? 100 : cfg.ui_brightness)) + '" data-set="ui_brightness" data-number="1" data-live="uiBrightnessValue" data-ui-preview="ui_brightness" style="flex:1" />' +
        '<span class="hint" id="uiBrightnessValue" style="width:48px;text-align:right">' + esc(String(cfg.ui_brightness == null ? 100 : cfg.ui_brightness)) + '%</span></div>' +
      '<div class="field-row" style="margin-top:6px"><label class="hint" style="flex:none">卡片圆角</label>' +
        '<input type="range" min="0" max="24" step="1" value="' + esc(String(cfg.ui_radius == null ? 16 : cfg.ui_radius)) + '" data-set="ui_radius" data-number="1" data-live="uiRadiusValue" data-ui-preview="ui_radius" style="flex:1" />' +
        '<span class="hint" id="uiRadiusValue" style="width:48px;text-align:right">' + esc(String(cfg.ui_radius == null ? 16 : cfg.ui_radius)) + 'px</span></div>' +
      '<div class="field-row" style="margin-top:6px"><label class="hint" style="flex:none">按钮大小</label>' +
        '<input type="range" min="85" max="120" step="1" value="' + esc(String(cfg.ui_scale == null ? 100 : cfg.ui_scale)) + '" data-set="ui_scale" data-number="1" data-live="uiScaleValue" data-ui-preview="ui_scale" style="flex:1" />' +
        '<span class="hint" id="uiScaleValue" style="width:48px;text-align:right">' + esc(String(cfg.ui_scale == null ? 100 : cfg.ui_scale)) + '%</span></div>' +
      '<div class="hint" style="margin-top:6px">背景亮度只影响背景与壁纸，不改变文字对比度；按钮大小会同步缩放所有按钮与输入框，低分辨率屏幕建议 90% 左右。</div></div>' +
    '<div class="section"><h3>视觉</h3>' +
      sw('glass_effect', '半透明毛玻璃', '主题色会作为淡色叠加在毛玻璃上；低配显卡可关闭以降低渲染开销', cfg.glass_effect) +
      sw('ui_animations', '界面动画', '关闭后可进一步降低低配机器的渲染开销', cfg.ui_animations) + '</div>';
}
ACT['frame-set'] = async (mode) => {
  const res = await call('switch_frame', mode);
  if (!res.ok) return toast(res.message || '切换失败', 'error');
  if (S.settingsData) S.settingsData.frame_mode = mode;
  if (S.data) S.data.frame_mode = mode;
  fillSettingsBody(S.settingsData || {});
  const label = mode === 'classic' ? '经典版' : (mode === 'electron' ? '独立版（Electron）' : '美化版');
  toast(res.unchanged ? '当前已是该框架' : '已切换为' + label + '，重启启动器后生效', 'ok');
};
ACT['app-restart'] = async () => {
  toast('正在重启启动器…', 'ok');
  try { await call('restart_app'); } catch (err) { /* 进程退出导致连接中断，属正常现象 */ }
};
ACT['theme-set'] = async (name) => {
  const res = await call('set_theme', name);
  if (!res.ok) return toast(res.message, 'error');
  if (res.palette) applyPalette(res.palette);
  if (S.data) { S.data.palette = res.palette || S.data.palette; S.data.theme = name; S.data.color_mode = res.mode || S.data.color_mode; }
  if (S.settingsData) { S.settingsData.theme_name = name; S.settingsData.color_mode = res.mode || S.settingsData.color_mode; fillSettingsBody(S.settingsData); }
  toast('主题已切换到 ' + name, 'ok');
};
ACT['color-mode'] = async (mode) => {
  const want = mode === 'light' ? 'light' : 'dark';
  const res = await call('set_color_mode', want);
  if (!res.ok) return toast(res.message || '切换失败', 'error');
  if (res.palette) applyPalette(res.palette);
  if (S.data) { S.data.palette = res.palette || S.data.palette; S.data.theme = res.theme; S.data.color_mode = res.mode; }
  if (S.settingsData) { S.settingsData.theme_name = res.theme; S.settingsData.color_mode = res.mode; fillSettingsBody(S.settingsData); }
  toast(want === 'light' ? '已切换到明亮模式' : '已切换到黑暗模式', 'ok');
};
ACT['toggle-mode'] = async () => {
  const light = !!(S.data && S.data.palette && S.data.palette.light);
  return ACT['color-mode'](light ? 'dark' : 'light');
};
ACT['accent-set'] = async (color) => {
  const value = String(color || '').trim().toLowerCase();
  if (!/^#[0-9a-f]{6}$/.test(value)) return toast('颜色格式无效', 'error');
  const res = await call('settings_set', { accent_color: value });
  if (!res.ok) return toast(res.message || '保存失败', 'error');
  if (res.palette) applyPalette(res.palette);
  if (S.data) S.data.accent_color = value;
  if (S.settingsData) { S.settingsData.accent_color = value; fillSettingsBody(S.settingsData); }
  toast('主题色已更新', 'ok');
};
ACT['text-reset'] = async () => {
  const res = await call('settings_set', { text_color: '' });
  if (!res.ok) return toast(res.message || '恢复失败', 'error');
  if (res.palette) applyPalette(res.palette);
  if (S.data) S.data.text_color = '';
  if (S.settingsData) { S.settingsData.text_color = ''; fillSettingsBody(S.settingsData); }
  toast('字体颜色已恢复跟随主题', 'ok');
};
ACT['theme-import'] = async () => {
  const res = await call('theme_import');
  if (!res.ok) { if (res.message !== '已取消') toast(res.message || '导入失败', 'error'); return; }
  await refreshBootstrap();
  renderSettings();
  toast(res.message, 'ok');
};
ACT['theme-export'] = async () => {
  const name = (S.settingsData && S.settingsData.theme_name) || (S.data && S.data.theme) || '';
  const res = await call('theme_export', name);
  if (!res.ok) { if (res.message !== '已取消') toast(res.message || '导出失败', 'error'); return; }
  toast(res.message, 'ok');
};
ACT['feature-set'] = async (key) => {
  const current = !!(S.settingsData && S.settingsData.features && S.settingsData.features[key]);
  const res = await call('feature_set', key, !current);
  if (!res.ok) return toast(res.message || '保存失败', 'error');
  if (S.settingsData) S.settingsData.features = res.features;
  if (S.data) S.data.features = res.features;
  navHtml();
  fillSettingsBody(S.settingsData || {});
  toast((FEATURE_LABELS_ACT[key] || key) + (current ? ' 已关闭' : ' 已启用'), 'ok');
};
const FEATURE_LABELS_ACT = {
  home: '主页', download: '下载安装', downloads: '下载中心', download_accel: '下载加速',
  content: '内容中心', modpack: '整合包', account: '账号与皮肤', control: '版本设置',
  loaders: 'Mod 加载器', multiplayer: '联机', browser: '内置浏览器', forbric: 'Forbric 加载器',
  java: 'Java 中心', deps: '依赖补全', modgraph: 'Mod 关系图', wiki: '教程中心',
  bedrock: '基岩版', offline_login: '离线登录', offline_skin: '离线皮肤',
  skin_factory: '皮肤工坊', skin_pack: '皮肤包', seed_terrain: '种子地形',
  gallery: '截图图库', crash: '崩溃报告',
};
ACT['bg-pick'] = async () => {
  const res = await call('pick_background');
  if (!res.ok) return toast(res.message, 'error');
  if (S.settingsData) { S.settingsData.background_image = res.path; fillSettingsBody(S.settingsData); }
  toast('背景图已更新', 'ok');
};
ACT['bg-clear'] = async () => {
  await saveSetting('background_image', '');
  if (S.settingsData) { S.settingsData.background_image = ''; fillSettingsBody(S.settingsData); }
  applyBackground('');
};
ACT['wallpaper-pick'] = async () => {
  const res = await call('pick_dynamic_wallpaper');
  if (!res.ok) { if (res.message !== '未选择动态壁纸') toast(res.message || '选择失败', 'error'); return; }
  if (S.settingsData) S.settingsData.dynamic_wallpaper = res.path;
  applyDynamicWallpaper(res.path);
  if (S.settingsData) fillSettingsBody(S.settingsData);
  toast('动态壁纸已启用', 'ok');
};
ACT['wallpaper-clear'] = async () => {
  await call('clear_dynamic_wallpaper');
  if (S.settingsData) S.settingsData.dynamic_wallpaper = '';
  applyDynamicWallpaper('');
  if (S.settingsData) fillSettingsBody(S.settingsData);
  toast('已清除动态壁纸', 'ok');
};

function settingsExtensions() {
  const items = S.extensions;
  const list = items == null
    ? '<div class="loading"><span class="spinner"></span>正在读取扩展…</div>'
    : items.length
      ? items.map((item) => {
        const meta = [item.version ? 'v' + item.version : '', item.author].filter(Boolean).join(' · ');
        return '<div class="ext-row">' +
          '<span class="ext-icon">' + esc(item.icon || '✚') + '</span>' +
          '<div class="ext-main"><b>' + esc(item.name) + (meta ? ' <span class="tag">' + esc(meta) + '</span>' : '') +
            (item.error ? ' <span class="tag">异常</span>' : '') + '</b>' +
            '<small>' + esc(item.error || item.description || (item.type === 'python' ? '经典版 Python 插件' : '')) + '</small></div>' +
          (item.type === 'web'
            ? '<button class="btn small ' + (item.enabled ? 'ghost' : 'primary') + '" data-act="ext-toggle" data-arg="' + A(item.id) + '">' + (item.enabled ? '停用' : '启用') + '</button>' +
              '<button class="btn small danger" data-act="ext-remove" data-arg="' + A(item.id) + '">删除</button>'
            : '<span class="tag">仅经典版</span>') +
        '</div>';
      }).join('')
      : '<div class="empty">还没有安装扩展。扩展可往侧边栏添加自定义页面，与 Launcher 共用账号、下载与文件接口。</div>';
  return '<div class="section"><h3>已安装扩展</h3>' +
      '<div class="hint" style="margin-bottom:8px">导入 .zip / .mikan-ext 扩展包后，启用项会出现在左侧侧边栏。经典版 data/plugins 下的 Python 插件也会在这里列出。</div>' +
      '<div class="list">' + list + '</div>' +
      '<div class="toolbar" style="margin-top:10px"><button class="btn small primary" data-act="ext-import">导入扩展包</button>' +
        '<button class="btn small ghost" data-act="ext-open-dir">打开扩展目录</button>' +
        '<button class="btn small ghost" data-act="ext-refresh">刷新列表</button></div></div>' +
    '<div class="section"><h3>扩展格式</h3>' +
      '<div class="hint">解压后为一个文件夹，内含 <code>extension.json</code> 与入口 HTML：</div>' +
      '<pre class="md-code">{\n  "id": "my-extension",\n  "name": "我的扩展",\n  "version": "1.0.0",\n  "author": "you",\n  "icon": "✚",\n  "entry": "index.html",\n  "description": "在侧边栏添加自定义页面"\n}</pre>' +
      '<div class="hint">页面运行在沙箱 iframe 中，可通过 <code>parent.postMessage({ mikan: "call", id, method, args }, "*")</code> 调用启动器接口，结果通过 message 事件返回（{ mikan: "result", id, ok, result }）。</div></div>';
}
ACT['ext-import'] = async () => {
  const res = await call('extension_import');
  if (!res.ok) { if (res.message !== '已取消') toast(res.message || '导入失败', 'error'); return; }
  await loadExtensions();
  toast(res.message || '扩展已安装', 'ok');
};
ACT['ext-open-dir'] = async () => {
  const res = await call('extension_open_folder');
  if (!res.ok) toast(res.message || '打开失败', 'error');
};
ACT['ext-refresh'] = async () => { await loadExtensions(); toast('扩展列表已刷新', 'ok'); };
ACT['ext-toggle'] = async (extId) => {
  const item = (S.extensions || []).find((entry) => entry.id === extId);
  if (!item) return;
  const res = await call('extension_toggle', extId, !item.enabled);
  if (!res.ok) return toast(res.message || '操作失败', 'error');
  item.enabled = !!res.enabled;
  navHtml();
  fillSettingsBody(S.settingsData || {});
  toast((res.enabled ? '已启用 ' : '已停用 ') + item.name, 'ok');
};
ACT['ext-remove'] = async (extId) => {
  const item = (S.extensions || []).find((entry) => entry.id === extId);
  if (!item) return;
  if (!(await ask('删除扩展', '确定删除扩展「' + item.name + '」吗？扩展目录中的文件会被移除。'))) return;
  const res = await call('extension_remove', extId);
  if (!res.ok) return toast(res.message || '删除失败', 'error');
  await loadExtensions();
  toast('已删除扩展', 'ok');
};
const SOURCE_MAPPINGS = { bmclapi: 'BMCLAPI 兼容（推荐）', direct: '同路径镜像', none: '不重写（仅用于清单）' };
function sourceRow(s) {
  return '<div class="row"><div class="row-main"><b>' + esc(s.name) +
    (s.builtin ? ' <span class="tag">内置</span>' : '') + (s.selected ? ' <span class="tag">当前</span>' : '') +
    (s.enabled ? '' : ' <span class="tag">已禁用</span>') + '</b>' +
    '<small class="mono">' + esc(s.manifest_url || '—') + '</small>' +
    '<small>' + esc(SOURCE_MAPPINGS[s.mapping] || s.mapping) + (s.download_base ? ' · ' + esc(s.download_base) : '') + '</small></div>' +
    '<div style="display:flex;gap:6px;flex-wrap:wrap">' +
    (s.builtin ? '' : '<button class="btn small ghost" data-act="source-edit" data-arg="' + A(s.id) + '">编辑</button>') +
    '<button class="btn small ghost" data-act="source-test" data-arg="' + A(s.id) + '">测试</button>' +
    (s.selected ? '' : '<button class="btn small ghost" data-act="source-select" data-arg="' + A(s.id) + '">设为当前</button>') +
    (s.builtin ? '' : '<button class="btn small ghost" data-act="source-toggle" data-arg="' + A(s.id) + '">' + (s.enabled ? '禁用' : '启用') + '</button>' +
      '<button class="btn small danger" data-act="source-del" data-arg="' + A(s.id) + '">删除</button>') +
    '</div></div>';
}
function openSourceSheet(id) {
  const sources = (S.settingsData && S.settingsData.sources) || [];
  const s = sources.find((item) => item.id === id) || { name: '', manifest_url: '', mapping: 'bmclapi', download_base: '', api_key_header: 'X-API-Key', api_key: '', enabled: true };
  openSheet(id ? '编辑下载源' : '添加下载源',
    '<div class="field"><label>名称</label><input id="srcName" type="text" value="' + esc(s.name) + '" /></div>' +
    '<div class="field"><label>版本清单地址</label><input id="srcManifest" type="text" value="' + esc(s.manifest_url) + '" placeholder="https://…/version_manifest_v2.json" /></div>' +
    '<div class="field"><label>映射方式</label><select id="srcMapping">' +
      Object.entries(SOURCE_MAPPINGS).map(([key, label]) => '<option value="' + key + '"' + (key === s.mapping ? ' selected' : '') + '>' + esc(label) + '</option>').join('') +
    '</select></div>' +
    '<div class="field"><label>镜像根地址</label><input id="srcBase" type="text" value="' + esc(s.download_base || '') + '" placeholder="https://bmclapi2.bangbang93.com" /></div>' +
    '<div class="field"><label>API Key</label><input id="srcKey" type="text" value="' + esc(s.api_key || '') + '" placeholder="留空表示不需要" /></div>' +
    '<div class="field"><label>API Key 请求头</label><input id="srcHeader" type="text" value="' + esc(s.api_key_header || 'X-API-Key') + '" /></div>',
    '<button class="btn ghost" id="sheetCancel">取消</button><button class="btn primary" id="srcSave">保存</button>');
  h('srcSave').onclick = async () => {
    const payload = {
      name: h('srcName').value.trim(),
      manifest_url: h('srcManifest').value.trim(),
      mapping: h('srcMapping').value,
      download_base: h('srcBase').value.trim(),
      api_key: h('srcKey').value.trim(),
      api_key_header: h('srcHeader').value.trim() || 'X-API-Key',
    };
    const res = await call('source_save', payload, id || '');
    if (!res.ok) return toast(res.message || '保存失败', 'error');
    closeSheet();
    if (S.settingsData) S.settingsData.sources = res.sources;
    fillSettingsBody(S.settingsData || {});
    toast('下载源已保存', 'ok');
  };
}
ACT['source-add'] = () => openSourceSheet('');
ACT['source-edit'] = (id) => openSourceSheet(id);
ACT['source-test'] = async (id) => {
  const res = await call('source_test', id);
  if (!res.ok) return toast(res.message || '测试失败', 'error');
  toast(res.message || '已开始测试，结果见下载中心', 'ok');
};
ACT['source-select'] = async (id) => {
  const res = await call('source_select', id);
  if (!res.ok) return toast(res.message || '设置失败', 'error');
  if (S.settingsData) S.settingsData.sources = res.sources;
  fillSettingsBody(S.settingsData || {}); toast('已设为当前清单源', 'ok');
};
ACT['source-toggle'] = async (id) => {
  const res = await call('source_toggle', id);
  if (!res.ok) return toast(res.message || '操作失败', 'error');
  if (S.settingsData) S.settingsData.sources = res.sources;
  fillSettingsBody(S.settingsData || {});
};
ACT['source-del'] = async (id) => {
  if (!(await ask('删除下载源', '删除后不可恢复，确定继续吗？'))) return;
  const res = await call('source_remove', id);
  if (!res.ok) return toast(res.message || '删除失败', 'error');
  if (S.settingsData) S.settingsData.sources = res.sources;
  fillSettingsBody(S.settingsData || {}); toast('下载源已删除', 'ok');
};
function settingsDownload(cfg) {
  return '<div class="section"><h3>' + esc(T('下载文件夹')) + '</h3>' +
      '<div class="field"><label>' + esc(T('手动下载 / 另存为的文件保存到这里')) + '</label><div class="field-row">' +
        '<input type="text" readonly value="' + esc(cfg.download_dir || '') + '" style="flex:1" />' +
        '<button class="btn small ghost" data-act="download-pick-dir">' + esc(T('更改')) + '</button>' +
        '<button class="btn small ghost" data-act="open-path" data-arg="downloads">' + esc(T('打开')) + '</button>' +
        (cfg.download_dir_custom ? '<button class="btn small ghost" data-act="download-reset-dir">' + esc(T('恢复默认')) + '</button>' : '') +
      '</div></div>' +
      '<div class="hint">' + esc(T('只影响「另存为 / 只下载不安装」的文件；游戏、Mod 与整合包仍写入对应版本目录。')) + '</div>' +
    '</div>' +
    '<div class="section"><h3>并发下载</h3>' +
      '<div class="field"><label>线程数（1 ~ 328，所有下载任务共用）</label><div class="field-row">' +
        '<input type="range" min="1" max="328" step="1" value="' + esc(String(cfg.download_threads)) + '" data-set="download_threads" data-number="1" data-live="threadValue" data-suffix=" 线程" style="flex:1" />' +
        '<b class="mono" id="threadValue" style="min-width:74px;text-align:right">' + esc(String(cfg.download_threads)) + ' 线程</b></div></div>' +
      '<div class="hint">默认 16 线程。网络不稳定时降低线程数可减少失败率，机械硬盘不建议超过 8。</div>' +
    '</div>' +
    '<div class="section adv-only"><h3>限速</h3>' +
      '<div class="field"><label>全局限速（KB/s，0 表示不限）</label>' +
      '<input type="number" min="0" step="100" value="' + esc(String(cfg.download_speed_limit)) + '" data-set="download_speed_limit" data-number="1" /></div>' +
    '</div>' +
    '<div class="section adv-only"><h3>下载源</h3><div class="hint" style="margin-bottom:8px">支持官方源、BMCLAPI 镜像与自定义镜像；按列表顺序自动回退，可随时测试可用性。</div>' +
      '<div class="list">' + (cfg.sources || []).map(sourceRow).join('') + '</div>' +
      '<div class="toolbar" style="margin-top:8px"><button class="btn small ghost" data-act="source-add">＋ 添加自定义源</button></div></div>' +
    '<div class="section adv-only"><h3>内容源与镜像</h3>' +
      '<div class="field"><label>Modrinth API</label><input type="text" value="' + esc(cfg.modrinth_api_base || '') + '" placeholder="https://api.modrinth.com/v2" data-set="modrinth_api_base" /></div>' +
      '<div class="field"><label>Modrinth CDN 镜像</label><input type="text" value="' + esc(cfg.modrinth_cdn_mirror || '') + '" placeholder="留空使用官方 CDN" data-set="modrinth_cdn_mirror" /></div>' +
      '<div class="field"><label>CurseForge API</label><input type="text" value="' + esc(cfg.curseforge_api_base || '') + '" placeholder="https://api.curseforge.com" data-set="curseforge_api_base" /></div>' +
      '<div class="field"><label>CurseForge API Key</label><input type="text" value="' + esc(cfg.curseforge_api_key || '') + '" placeholder="默认已内置" data-set="curseforge_api_key" /></div>' +
      '<div class="field"><label>CurseForge CDN 镜像</label><input type="text" value="' + esc(cfg.curseforge_cdn_mirror || '') + '" placeholder="如 https://mediafilez.forgecdn.net" data-set="curseforge_cdn_mirror" /></div>' +
      '<div class="hint">CDN 镜像仅替换下载域名，不影响 API 请求；修改后立即生效。</div></div>';
}
function settingsAdvanced(cfg) {
  const FEATURE_LABELS = {
    home: '主页', download: '下载安装', downloads: '下载中心', download_accel: '下载加速',
    content: '内容中心', modpack: '整合包', account: '账号与皮肤', control: '版本设置',
    loaders: 'Mod 加载器', multiplayer: '联机', browser: '内置浏览器', forbric: 'Forbric 加载器',
    java: 'Java 中心', deps: '依赖补全', modgraph: 'Mod 关系图', wiki: '教程中心',
    bedrock: '基岩版', offline_login: '离线登录', offline_skin: '离线皮肤',
    skin_factory: '皮肤工坊', skin_pack: '皮肤包', seed_terrain: '种子地形',
    gallery: '截图图库', crash: '崩溃报告',
  };
  return '<div class="section adv-only"><h3>代理</h3>' +
      sw('proxy_enabled', '启用网络代理', '默认关闭：只有下载 / 登录必须经过代理时才需要开启，开启后所有请求都会走代理', cfg.proxy_enabled) +
      '<div class="field" style="margin-top:8px"><label>代理地址</label><input type="text" value="' + esc(cfg.proxy_url) + '" placeholder="http://127.0.0.1:7890" data-set="proxy_url" /></div>' +
      sw('proxy_jvm', '游戏内 JVM 代理', '启动游戏时把代理传给 Java', cfg.proxy_jvm) +
    '</div>' +
    '<div class="section"><h3>游戏优化</h3>' +
      sw('smart_jvm', '智能 JVM 参数', '默认开启：按你的 Java 与游戏版本自动挑 GC 参数；你手动填写 GC 参数时它会自动跳过', cfg.smart_jvm) +
      sw('opt_pre_touch', '预读取资源', '默认开启：大堆（≥4GB）时预触碰内存页减少启动后卡顿；内存很小可以关掉', cfg.opt_pre_touch) +
      sw('opt_fixed_heap', '固定堆大小', '默认关闭：开启后 Xms = Xmx 更稳，但会一直占满分配的内存；内存紧张时保持关闭', cfg.opt_fixed_heap) +
    '</div>' +
    '<div class="section adv-only"><h3>存档与行为</h3>' +
      sw('auto_backup_saves', '启动前自动备份存档', '默认开启：每个存档单独打包到备份目录，备份失败不会阻止启动', cfg.auto_backup_saves) +
      '<div class="field" style="margin-top:8px"><label>备份目录</label><div class="field-row">' +
        '<input type="text" readonly value="' + esc(cfg.backup_dir || '默认（data/backups）') + '" style="flex:1" />' +
        '<button class="btn small ghost" data-act="backup-pick-dir">选择…</button>' +
        '<button class="btn small ghost" data-act="open-path" data-arg="backups">打开</button></div></div>' +
      sw('close_to_tray', '关闭时最小化', '默认关闭：开启后点关闭只是最小化到任务栏，下载不会中断', cfg.close_to_tray) +
      sw('agreement_prompt', '启动时提示用户协议', '关闭后将不再弹出协议确认', cfg.agreement_prompt) +
    '</div>' +
    '<div class="section adv-only"><h3>账号与登录</h3>' +
      '<div class="field"><label>微软 OAuth 客户端 ID</label><input type="text" value="' + esc(cfg.microsoft_client_id || '') + '" data-set="microsoft_client_id" /></div>' +
      '<div class="field"><label>authlib-injector latest.json 地址</label><input type="text" value="' + esc(cfg.authlib_injector_url || '') + '" data-set="authlib_injector_url" /></div>' +
      '<div class="hint">与经典版共用同一份配置；外置登录的服务器地址仍在账号页填写。</div></div>' +
    '<div class="section adv-only"><h3>功能模块</h3><div class="hint" style="margin-bottom:8px">关闭后对应页面 / 入口立即隐藏，功能实现与经典版共用同一套后端。</div><div class="chips">' +
      Object.entries(cfg.features || {}).map(([key, on]) =>
        '<button class="chip' + (on ? ' active' : '') + '" data-act="feature-set" data-arg="' + A(key) + '">' + esc(FEATURE_LABELS[key] || key) + '</button>'
      ).join('') + '</div></div>' +
    '<div class="section"><h3>其他</h3><div class="toolbar">' +
      '<button class="btn small" data-act="restore-last-good">恢复到上次能启动的配置</button>' +
      '<button class="btn small ghost" data-act="config-export">导出配置片段</button>' +
      '<button class="btn small ghost" data-act="config-import">导入配置片段</button></div>' +
      '<div class="hint" style="margin-top:8px">改崩了就用第一项：它会把内存、JVM 参数、隔离模式等恢复到最近一次成功启动时的值。配置片段（.mikan）可以分享给别人抄作业。</div>' +
      '<div class="toolbar" style="margin-top:10px">' +
      '<button class="btn small ghost" data-act="agreement-view">查看用户协议</button>' +
      '<button class="btn small ghost" data-act="open-path" data-arg="data">打开数据目录</button>' +
      '<button class="btn small ghost" data-act="open-path" data-arg="logs">打开日志目录</button></div></div>';
}
async function reloadSettingsAfterApply() {
  try {
    const fresh = await call('settings_get');
    if (fresh && fresh.ok !== false) {
      S.data = Object.assign(S.data || {}, fresh);
      S.settingsData = fresh;
      if (h('settingsBody')) fillSettingsBody(fresh);
    }
  } catch (_) { /* 刷新失败时保留原界面 */ }
}
ACT['restore-last-good'] = async (arg, node) => {
  if (node) node.disabled = true;
  const result = await call('settings_restore_last_good');
  if (node) node.disabled = false;
  if (!result || !result.ok) return toast((result && result.message) || '恢复失败', 'error');
  toast(result.message, 'ok');
  await reloadSettingsAfterApply();
};
ACT['config-export'] = async () => {
  const result = await call('config_export');
  if (!result || !result.ok) return toast((result && result.message) || '导出失败', result && result.message === '已取消' ? 'info' : 'error');
  toast(result.message, 'ok');
};
ACT['config-import'] = async () => {
  const result = await call('config_import');
  if (!result || !result.ok) return toast((result && result.message) || '导入失败', result && result.message === '已取消' ? 'info' : 'error');
  toast(result.message, 'ok');
  await reloadSettingsAfterApply();
};
ACT['agreement-view'] = () => {
  const texts = (S.data && S.data.agreement && S.data.agreement.texts) || {};
  openSheet(texts.title || '用户协议',
    '<div class="agreement-body" style="margin:0"><p>' + esc(texts.intro || '') + '</p>' +
      (texts.sections || []).map(([title, bodyText]) => '<h4>' + esc(title) + '</h4><div>' + esc(bodyText) + '</div>').join('') + '</div>',
    '<button class="btn primary" id="agOk">关闭</button>');
  h('agOk').onclick = closeSheet;
};
function settingsAbout(cfg) {
  const app = (S.data && S.data.app) || '';
  const runtime = (S.data && S.data.runtime) || '';
  return '<div class="section"><h3>MikanCL</h3>' +
      '<div class="detail-hero"><div class="d-main"><b>MikanCL ' + esc(app) + '</b>' +
        '<small>渲染：' + esc(runtime || 'Edge WebView2') + '</small>' +
        '<small>框架：美化版（可在「外观」中随时切回经典版）</small></div></div>' +
      '<div class="hint">双端功能一致：下载、内容、账号、皮肤、联机、工具箱、设置、Java、基岩版、依赖补全全部可用。</div></div>' +
    '<div class="section"><h3>检查更新</h3>' +
      '<div class="field-row"><div style="flex:1"><div class="hint">更新源：GitHub · luohaocheng171/mikanCL（自动抓取 Releases 最新版本）</div></div>' +
        '<button class="btn small" data-act="update-check">检查更新</button></div>' +
      '<div id="updateBox" style="margin-top:10px"></div></div>' +
    '<div class="section"><h3>链接</h3><div class="toolbar">' +
      '<button class="btn small ghost" data-act="open-url" data-arg="' + A('https://github.com/luohaocheng171/mikanCL') + '">GitHub 仓库</button>' +
      '<button class="btn small ghost" data-act="open-url" data-arg="' + A('https://modrinth.com') + '">Modrinth</button>' +
      '<button class="btn small ghost" data-act="open-url" data-arg="' + A('https://www.curseforge.com/minecraft') + '">CurseForge</button></div></div>' +
    '<div class="section"><h3>三套界面说明</h3><div class="hint">经典版、美化版与独立版共用同一份配置、账号、实例与下载内核，可随时在「外观 → 界面框架」切换；切换后重启启动器生效，下载进度与设置不会丢失。独立版自带 Chromium，不依赖 WebView2。</div></div>';
}
ACT['update-check'] = async (arg, node) => {
  const box = h('updateBox');
  if (node) node.disabled = true;
  if (box) box.innerHTML = '<div class="hint">正在连接 GitHub 检查更新…</div>';
  let info = null;
  try { info = await call('update_check'); } catch (err) { info = { ok: false, message: String(err) }; }
  if (node) node.disabled = false;
  if (!box) return;
  if (!info || !info.ok) {
    box.innerHTML = '<div class="hint">' + esc((info && info.message) || '检查更新失败') + '</div>';
    return;
  }
  const notes = String(info.notes || '').trim().slice(0, 1200);
  if (!info.has_update) {
    box.innerHTML = '<div class="hint">当前版本 ' + esc(info.current) + '，已经是最新版本（最新 ' + esc(info.tag) + '）。</div>';
    return;
  }
  box.innerHTML =
    '<div class="detail-hero"><div class="d-main"><b>发现新版本 ' + esc(info.tag) + '</b>' +
      '<small>当前 ' + esc(info.current) + ' · ' + esc(info.published || info.source) + '</small></div>' +
      '<div class="chips"><button class="btn small primary" data-act="update-install" id="updateGo"' +
        (info.downloadable ? '' : ' disabled') + '>下载并更新</button>' +
      '<button class="btn small ghost" data-act="open-url" data-arg="' + A(info.page || '') + '">打开 Release 页面</button></div></div>' +
    (notes ? '<div class="hint" style="white-space:pre-wrap;max-height:180px;overflow:auto;margin-top:8px">' + esc(notes) + '</div>' : '') +
    (info.downloadable ? '' : '<div class="hint" style="margin-top:8px">该版本没有附带 exe，只能到 Releases 手动下载。</div>');
};
ACT['update-install'] = async (arg, node) => {
  if (node) node.disabled = true;
  const result = await call('update_install');
  if (!result || !result.ok) {
    if (node) node.disabled = false;
    return toast((result && result.message) || '无法下载更新', 'error');
  }
  toast(result.message || '已开始下载更新', 'ok');
  S.dlTab = 'tasks';
  watchJob(result.job).then((job) => {
    if (job && job.state === 'failed') toast(job.error || '更新失败', 'error');
    else if (job && job.state === 'ok') toast('更新已就绪，启动器即将关闭并自动替换', 'ok');
  });
};

/* ---------- 教程中心 ---------- */
function mdToHtml(source) {
  const lines = String(source || '').replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let inCode = false;
  let inList = false;
  const inline = (text) => esc(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" data-act="open-url" data-arg="' + '$2' + '">$1</a>');
  const closeList = () => { if (inList) { out.push('</ul>'); inList = false; } };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (/^```/.test(line)) {
      closeList();
      if (inCode) { out.push('</pre>'); inCode = false; }
      else { out.push('<pre class="md-code">'); inCode = true; }
      continue;
    }
    if (inCode) { out.push(esc(line)); continue; }
    if (!line.trim()) { closeList(); continue; }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      out.push('<h' + (level + 1) + '>' + inline(heading[2]) + '</h' + (level + 1) + '>');
      continue;
    }
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    if (bullet) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push('<li>' + inline(bullet[1]) + '</li>');
      continue;
    }
    const numbered = line.match(/^\s*\d+\.\s+(.*)$/);
    if (numbered) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push('<li>' + inline(numbered[1]) + '</li>');
      continue;
    }
    closeList();
    out.push('<p>' + inline(line) + '</p>');
  }
  closeList();
  if (inCode) out.push('</pre>');
  return out.join('');
}
let WIKI_ITEMS = [];
function renderWikiList(filter) {
  const list = h('wikiList');
  if (!list) return;
  const keyword = (filter || '').trim().toLowerCase();
  const items = WIKI_ITEMS.filter((item) => !keyword || (item.title || '').toLowerCase().includes(keyword));
  list.innerHTML = items.length
    ? items.map((item) => '<div class="row wiki-row" data-act="wiki-open" data-arg="' + A(item.slug) + '"><div class="row-main"><b>' + esc(item.title) + '</b></div></div>').join('')
    : '<div class="empty">没有匹配的教程标题。</div>';
}
async function renderWiki() {
  h('view').innerHTML =
    '<div class="page" style="gap:12px"><div class="split" style="flex:1;min-height:0">' +
      '<div class="card" style="width:264px;flex:none"><div class="card-head"><h2>教程目录</h2><span class="hint" id="wikiLang"></span></div>' +
        '<div class="card-body scroll"><input id="wikiSearch" type="text" placeholder="搜索教程标题…" style="margin-bottom:8px" />' +
        '<div class="list" id="wikiList"><div class="loading"><span class="spinner"></span>读取中…</div></div></div></div>' +
      '<div class="card" style="flex:1;min-height:0"><div class="card-head"><h2 id="wikiTitle">教程</h2></div>' +
        '<div class="card-body scroll"><div class="md-body" id="wikiBody"><div class="loading"><span class="spinner"></span>读取中…</div></div></div></div>' +
    '</div></div>';
  let index;
  try { index = await call('wiki_index'); } catch (err) { h('wikiList').innerHTML = '<div class="empty">' + esc(err.message || err) + '</div>'; return; }
  WIKI_ITEMS = index.items || [];
  if (h('wikiLang')) h('wikiLang').textContent = index.language || '';
  if (h('wikiSearch')) h('wikiSearch').addEventListener('input', (event) => renderWikiList(event.target.value));
  renderWikiList('');
  if (WIKI_ITEMS.length) openWiki(WIKI_ITEMS[0].slug);
}
async function openWiki(slug) {
  const res = await call('wiki_read', slug);
  if (!res.ok) { if (h('wikiBody')) h('wikiBody').innerHTML = '<div class="empty">' + esc(res.message) + '</div>'; return; }
  if (h('wikiTitle')) h('wikiTitle').textContent = res.title;
  if (h('wikiBody')) h('wikiBody').innerHTML = mdToHtml(res.markdown);
  document.querySelectorAll('.wiki-row').forEach((row) => row.classList.toggle('active', row.dataset.arg === A(slug)));
}
ACT['wiki-open'] = (slug) => openWiki(slug);

/* ---------- 内置浏览器 ---------- */
const BROWSER_SHORTCUTS = [
  ['B 站', 'https://www.bilibili.com'],
  ['MC Wiki', 'https://zh.minecraft.wiki'],
  ['Modrinth', 'https://modrinth.com'],
  ['CurseForge', 'https://www.curseforge.com/minecraft'],
  ['MCBBS', 'https://www.mcbbs.co'],
  ['GitHub', 'https://github.com/luohaocheng171/mikanCL'],
];
function renderBrowser() {
  h('view').innerHTML =
    '<div class="page" style="gap:12px"><div class="card" style="flex:1;min-height:0">' +
      '<div class="card-head"><h2>内置浏览器</h2><span class="hint">WebView2 内核 · 可直接播放 B 站视频</span></div>' +
      '<div class="card-body" style="gap:14px">' +
        '<div class="field"><label>网址</label><div class="field-row">' +
          '<input type="text" id="browserUrl" placeholder="https://www.bilibili.com" value="https://www.bilibili.com" style="flex:1" />' +
          '<button class="btn primary" data-act="browser-open" data-arg="">打开</button>' +
        '</div><div class="hint" style="margin-top:6px">回车即可打开；关闭浏览器窗口不会影响启动器。</div></div>' +
        '<div class="field"><label>常用站点</label><div class="chips">' +
          BROWSER_SHORTCUTS.map(([name, url]) =>
            '<button class="chip" data-act="browser-open" data-arg="' + A(url) + '">' + esc(name) + '</button>').join('') +
        '</div></div>' +
        '<div class="field"><label>说明</label><div class="hint" style="line-height:1.7">' +
          '内置浏览器使用与美化版界面相同的 Edge WebView2 内核，支持 H.264 / AAC 解码，' +
          '因此可以原生播放 B 站、网易云等站点的音视频，无需跳转到系统浏览器。<br />' +
          '下载、账号登录等需要跳转外部站点确认的操作仍会用系统默认浏览器打开。' +
        '</div></div>' +
      '</div></div></div>';
  const input = h('browserUrl');
  if (input) input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') ACT['browser-open'](input.value.trim());
  });
}
ACT['browser-open'] = async (url) => {
  const target = String(url || (h('browserUrl') ? h('browserUrl').value : '') || '').trim();
  const res = await call('open_browser', target);
  toast(res.ok ? '已打开内置浏览器' : (res.message || '打开失败'), res.ok ? 'ok' : 'error');
};

/* ---------- 背景与窗口 ---------- */
function applyGlassBlur(value) {
  const b = Math.max(0, Math.min(64, Number(value) || 0));
  document.documentElement.style.setProperty('--glass-blur', 'blur(' + b + 'px) saturate(' + Math.round(100 + b * 0.4) + '%)');
  const label = h('glassBlurValue');
  if (label) label.textContent = Math.round(b) + 'px';
}
function applyGlassStrength(value) {
  const s = Math.max(0, Math.min(100, Number(value) || 0));
  const blur = (S.data && S.data.glass_blur != null) ? S.data.glass_blur : Math.round(8 + s * 0.5);
  applyGlassBlur(blur);
  const b = Math.max(0, Math.min(64, Number(blur) || 0));
  // 覆盖完整区间：都为 0 时卡片几乎全透明，强度拉满时几乎不透明；模糊再补一点实心度
  const a = Math.min(0.97, 0.02 + s * 0.0092 + b * 0.0008);
  const a2 = Math.min(0.99, 0.03 + s * 0.0094 + b * 0.0008);
  document.body.style.setProperty('--glass-a', a.toFixed(3));
  document.body.style.setProperty('--glass-a2', a2.toFixed(3));
  const label = h('glassValue');
  if (label) label.textContent = Math.round(s) + '%';
}
function applyUiDetail(cfg) {
  cfg = cfg || {};
  const brightness = Math.max(70, Math.min(130, Number(cfg.ui_brightness == null ? 100 : cfg.ui_brightness) || 100));
  const radius = Math.max(0, Math.min(24, Number(cfg.ui_radius == null ? 16 : cfg.ui_radius)));
  const scale = Math.max(85, Math.min(120, Number(cfg.ui_scale == null ? 100 : cfg.ui_scale) || 100));
  const root = document.documentElement.style;
  root.setProperty('--bg-brightness', (brightness / 100).toFixed(2));
  root.setProperty('--radius', Math.round(radius) + 'px');
  root.setProperty('--ui-scale', (scale / 100).toFixed(2));
  const label = (id, text) => { const el = h(id); if (el) el.textContent = text; };
  label('uiBrightnessValue', Math.round(brightness) + '%');
  label('uiRadiusValue', Math.round(radius) + 'px');
  label('uiScaleValue', Math.round(scale) + '%');
}

function setGlassMode(enabled, strength) {
  const on = !!enabled;
  document.body.classList.toggle('desktop-glass', on);
  applyGlassStrength(strength == null ? 62 : strength);
  // CSS 只是视觉层，真正透出桌面依赖后端 DWM/亚克力；切换时必须重新下发给窗口
  call('glass_apply').catch(() => {});
  if (on) {
    if (_wallpaperEl && _wallpaperEl.tagName === 'VIDEO') {
      try { _wallpaperEl.pause(); } catch (_) { /* 已暂停 */ }
    }
  } else if (S.data) {
    // 关闭后恢复背景图 / 动态壁纸
    applyBackground(S.data.background_image);
    applyDynamicWallpaper(S.data.dynamic_wallpaper);
  }
}
async function applyBackground(path) {
  if (document.body.classList.contains('desktop-glass')) return;
  if (!path) { document.body.classList.remove('has-bg'); return; }
  try {
    const src = await call('preview', path);
    if (!src) return;
    document.documentElement.style.setProperty('--bg-image', 'url("' + src + '")');
    document.body.classList.add('has-bg');
  } catch (_) { /* 背景读取失败保持默认 */ }
}

/* ---------- 动态壁纸 ---------- */
let _wallpaperEl = null;
async function applyDynamicWallpaper(path) {
  if (document.body.classList.contains('desktop-glass')) return;
  const host = h('bgMedia');
  if (!host) return;
  if (!path) {
    host.innerHTML = '';
    document.body.classList.remove('has-dynamic-bg');
    _wallpaperEl = null;
    S.wallpaperPath = '';
    return;
  }
  if (path === S.wallpaperPath && _wallpaperEl) return;
  try {
    const res = await call('wallpaper_media', path);
    if (!res || !res.ok) {
      host.innerHTML = '';
      document.body.classList.remove('has-dynamic-bg');
      return;
    }
    host.innerHTML = '';
    let el;
    if (res.kind === 'video') {
      el = document.createElement('video');
      el.src = res.url;
      el.autoplay = true;
      el.muted = true;
      el.loop = true;
      el.playsInline = true;
      el.disablePictureInPicture = true;
    } else {
      el = document.createElement('img');
      el.src = res.url;
      el.alt = '';
    }
    host.appendChild(el);
    _wallpaperEl = el;
    S.wallpaperPath = path;
    document.body.classList.add('has-dynamic-bg');
  } catch (_) { /* 动态壁纸失败时回退到主题背景 */ }
}
document.addEventListener('visibilitychange', () => {
  if (!_wallpaperEl || _wallpaperEl.tagName !== 'VIDEO') return;
  if (document.hidden) _wallpaperEl.pause();
  else _wallpaperEl.play().catch(() => {});
});

/* 最大化时取消窗口圆角（body.maximized），还原后恢复圆角 */
function syncMaximized(flag) {
  document.body.classList.toggle('maximized', !!flag);
}
async function toggleMaximized() {
  try {
    const result = await call('window_action', 'toggle_max');
    if (result && result.maximized != null) syncMaximized(result.maximized);
  } catch (_) { /* 忽略 */ }
}

h('minBtn').onclick = () => { call('window_action', 'minimize').catch(() => {}); };
h('maxBtn').onclick = () => { toggleMaximized(); };
h('closeBtn').onclick = () => { call('window_action', 'close').catch(() => {}); };
h('brandBtn').onclick = () => setPage('home');
h('railAvatar').onclick = () => setPage('account');

/* ---------- 无边框窗口拖拽缩放 ---------- */
(function bindWindowResize() {
  const MIN_W = 960, MIN_H = 600;
  let session = null;
  document.querySelectorAll('.resize-grips .rg').forEach((grip) => {
    grip.addEventListener('pointerdown', async (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      let rect = await call('window_rect');
      if (!rect || !rect.ok) return;
      if (rect.maximized) {
        await call('window_restore');
        syncMaximized(false);
        rect = await call('window_rect');
        if (!rect || !rect.ok) return;
      }
      session = { dir: grip.dataset.dir || '', rect, sx: event.screenX, sy: event.screenY, frame: null };
      try { grip.setPointerCapture(event.pointerId); } catch (_) { /* 忽略 */ }
    });
  });
  window.addEventListener('pointermove', (event) => {
    if (!session) return;
    if (session.frame) return;
    const { rect, dir } = session;
    const dx = event.screenX - session.sx;
    const dy = event.screenY - session.sy;
    let x = rect.x, y = rect.y, w = rect.w, h = rect.h;
    if (dir.indexOf('e') >= 0) w += dx;
    if (dir.indexOf('s') >= 0) h += dy;
    if (dir.indexOf('w') >= 0) { x += dx; w -= dx; }
    if (dir.indexOf('n') >= 0) { y += dy; h -= dy; }
    if (w < MIN_W) { if (dir.indexOf('w') >= 0) x = rect.x + rect.w - MIN_W; w = MIN_W; }
    if (h < MIN_H) { if (dir.indexOf('n') >= 0) y = rect.y + rect.h - MIN_H; h = MIN_H; }
    session.frame = requestAnimationFrame(() => {
      if (!session) return;
      session.frame = null;
      call('window_set_rect', Math.round(x), Math.round(y), Math.round(w), Math.round(h)).catch(() => {});
    });
  });
  window.addEventListener('pointerup', () => { session = null; });
  window.addEventListener('pointercancel', () => { session = null; });
  const bar = h('titlebar');
  if (bar) bar.addEventListener('dblclick', (event) => {
    if (event.target.closest('.winbtns, button, input, .task-pill')) return;
    toggleMaximized();
  });
})();

/* ---------- 扩展页面与主程序的桥接 ---------- */
window.addEventListener('message', async (event) => {
  const data = event.data;
  if (!data || data.mikan !== 'call' || !data.id) return;
  const source = event.source;
  const reply = (payload) => {
    try { source && source.postMessage(Object.assign({ mikan: 'result', id: data.id }, payload), '*'); } catch (_) { /* 忽略 */ }
  };
  if (typeof data.method !== 'string') { reply({ ok: false, error: 'method 必须是字符串' }); return; }
  try {
    const result = await call(data.method, ...(Array.isArray(data.args) ? data.args : []));
    reply({ ok: true, result });
  } catch (err) {
    reply({ ok: false, error: String((err && err.message) || err) });
  }
});

/* ---------- 全局拖拽导入 ---------- */
let dropHideTimer = null;
function dropOverlay() {
  let node = h('dropOverlay');
  if (node) return node;
  node = document.createElement('div');
  node.id = 'dropOverlay';
  node.className = 'drop-overlay';
  node.innerHTML = '<div class="drop-card"><b>松手即可导入</b>' +
    '<span>支持 Mod（.jar）、整合包（.zip / .mrpack）、资源包、光影包、世界存档，也可以拖入整个 mods 文件夹</span></div>';
  document.body.appendChild(node);
  return node;
}
function showDropOverlay() {
  if (dropHideTimer) { clearTimeout(dropHideTimer); dropHideTimer = null; }
  dropOverlay().classList.add('show');
}
function hideDropOverlay() {
  const node = h('dropOverlay');
  if (node) node.classList.remove('show');
}
if (typeof window !== 'undefined') {
  window.addEventListener('dragenter', (event) => {
    if (!event.dataTransfer || Array.from(event.dataTransfer.types || []).indexOf('Files') < 0) return;
    event.preventDefault();
    showDropOverlay();
  });
  window.addEventListener('dragover', (event) => {
    if (!event.dataTransfer || Array.from(event.dataTransfer.types || []).indexOf('Files') < 0) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    showDropOverlay();
  });
  window.addEventListener('dragleave', (event) => {
    if (event.relatedTarget) return;
    hideDropOverlay();
  });
  window.addEventListener('drop', (event) => {
    event.preventDefault();
    hideDropOverlay();
    dropHideTimer = setTimeout(() => {
      toast('没有读到拖入的文件路径，请点「导入整合包」或到下载中心选择文件', 'error');
    }, 900);
  });
}
window.__mikanDrop = (paths) => {
  const list = (Array.isArray(paths) ? paths : []).map(String).filter(Boolean);
  if (!list.length) return;
  if (dropHideTimer) { clearTimeout(dropHideTimer); dropHideTimer = null; }
  hideDropOverlay();
  openDropSheet(list).catch((err) => toast(err && err.message ? err.message : err, 'error'));
};
async function openDropSheet(paths) {
  const res = await call('drop_prepare', paths);
  if (!res || !res.ok) { toast((res && res.message) || '无法识别拖入内容', 'error'); return; }
  const items = res.items || [];
  const known = items.filter((item) => item.kind);
  if (!known.length) {
    openSheet('无法识别拖入内容',
      '<div class="empty">这些文件不是启动器认识的类型。支持：Mod（.jar）、整合包（.zip / .mrpack / .mikan）、资源包、光影包、世界存档，以及包含它们的文件夹。</div>');
    return;
  }
  const versions = res.versions || [];
  const hasModpack = !!res.has_modpack;
  const needsVersion = known.some((item) => item.kind !== 'modpack');
  const versionOptions = versions.map((version) =>
    '<option value="' + esc(version.id) + '">' + esc(version.label || version.id) + '</option>').join('');
  const list = known.map((item) =>
    '<div class="drop-item"><span class="tag">' + esc(item.label) + '</span>' +
    '<span class="drop-name" title="' + esc(item.path) + '">' + esc(item.name) + '</span></div>').join('');
  const unknown = items.length - known.length;
  const body =
    '<div style="display:flex;flex-direction:column;gap:12px">' +
      '<div class="hint">共识别 ' + known.length + ' 项' + (unknown > 0 ? '，已忽略 ' + unknown + ' 个无法识别的文件' : '') + '</div>' +
      '<div class="drop-list">' + list + '</div>' +
      (hasModpack
        ? '<div class="section" style="padding:10px 12px;border-radius:10px;background:rgba(255,255,255,.05)">' +
            '<h3 style="margin:0 0 6px">整合包安装方式</h3>' +
            '<label class="hint" style="display:flex;align-items:flex-start;gap:8px;margin-bottom:6px">' +
              '<input type="radio" name="dropMode" value="new" checked /> <span><b>下载全新版本安装</b><br/>自动下载整合包要求的原版 + 加载器，创建独立实例，不影响现有整合包。</span></label>' +
            '<label class="hint" style="display:flex;align-items:flex-start;gap:8px">' +
              '<input type="radio" name="dropMode" value="attach" /> <span><b>附加到已有版本</b><br/>把整合包内容直接写进下面选中的版本，适合补装或覆盖。</span></label>' +
          '</div>'
        : '') +
      ((needsVersion || hasModpack)
        ? '<div class="field-row"><span class="hint" style="flex:none">目标版本</span>' +
            (versions.length
              ? '<select id="dropVersion" style="flex:1"><option value="">请选择已安装版本…</option>' + versionOptions + '</select>'
              : '<span class="hint" style="flex:1">还没有安装任何游戏版本</span>') +
            (versions.length ? '' : '<button class="btn small" data-act="nav" data-arg="download">去下载版本</button>') +
          '</div>'
        : '') +
      (versions.length ? '' : '<div class="hint">仅拖入整合包时可以直接「下载全新版本安装」，无需先装游戏版本。</div>') +
    '</div>';
  openSheet('导入拖入内容',
    body,
    '<button class="btn ghost" id="dropCancel">取消</button>' +
    '<button class="btn primary" id="dropGo">开始导入</button>');
  const modes = h('sheetBody').querySelectorAll('input[name="dropMode"]');
  const syncMode = () => {
    const select = h('dropVersion');
    if (!select) return;
    const mode = Array.from(modes).find((node) => node.checked);
    select.disabled = !!(hasModpack && mode && mode.value === 'new');
  };
  modes.forEach((node) => node.addEventListener('change', syncMode));
  h('dropCancel').onclick = closeSheet;
  h('dropGo').onclick = async () => {
    const modeNode = Array.from(modes).find((node) => node.checked);
    const mode = modeNode ? modeNode.value : 'new';
    const select = h('dropVersion');
    const versionId = select ? select.value : '';
    const onlyPacks = !needsVersion;
    if (!onlyPacks && mode !== 'new' && !versionId) {
      toast(hasModpack ? '请选择要附加的已有版本' : '请选择要导入到的游戏版本', 'error');
      return;
    }
    closeSheet();
    const result = await call('drop_run', known.map((item) => item.path), versionId, mode);
    if (!result || !result.ok) { toast((result && result.message) || '导入失败', 'error'); return; }
    toast(result.message || '已开始导入', 'ok');
    setPage('download');
    S.dlTab = 'tasks';
    watchJob(result.job).then(async (job) => {
      if (job && job.state === 'ok') toast('拖入内容已导入完成', 'ok');
      else if (job && job.state === 'failed') toast(job.error || '导入失败', 'error');
      await refreshBootstrap();
      pollTasks();
    });
  };
}

/* ---------- 全局命令面板（Ctrl+K） ---------- */
const PALETTE_ITEMS = [
  { label: '主页', page: 'home', keys: '启动 主页 开始 游戏' },
  { label: '下载中心 · 任务', page: 'download', keys: '下载 任务 进度' },
  { label: '下载游戏版本', page: 'download', tab: 'game', keys: '安装 原版 快照 minecraft' },
  { label: '下载 Java', page: 'download', tab: 'java', keys: 'java jdk jre 运行时' },
  { label: '下载 Mod 加载器', page: 'download', tab: 'loader', keys: 'forge fabric neoforge quilt liteloader 加载器' },
  { label: '基岩版', page: 'download', tab: 'bedrock', keys: '基岩 bedrock 手机版' },
  { label: '内容中心', page: 'content', keys: '内容 搜索 下载 mod' },
  { label: '整合包中心', page: 'content', kind: 'modpack', keys: '整合包 modpack 一键安装' },
  { label: '搜 Mod', page: 'content', kind: 'mod', keys: 'mod 模组 前置' },
  { label: '搜资源包', page: 'content', kind: 'resourcepack', keys: '资源包 材质 pack' },
  { label: '搜光影包', page: 'content', kind: 'shader', keys: '光影 shader 画质' },
  { label: '实例管理', page: 'instances', keys: '实例 版本 目录 隔离' },
  { label: '账号与皮肤', page: 'account', keys: '账号 登录 皮肤 正版 离线' },
  { label: '皮肤工坊', page: 'skin', keys: '皮肤 绘制 3d 画布' },
  { label: '联机', page: 'servers', keys: '联机 服务器 陶瓦' },
  { label: '教程中心', page: 'wiki', keys: '教程 帮助 文档 指南' },
  { label: '内置浏览器', page: 'browser', keys: '浏览器 b站 视频 网页' },
  { label: '工具箱', page: 'tools', keys: '工具 实用' },
  { label: '依赖补全', page: 'tools', jump: '依赖补全', keys: '依赖 缺失 扫描 补全' },
  { label: 'Mod 关系图', page: 'tools', jump: 'Mod 关系图', keys: 'mod 冲突 前置 关系' },
  { label: '存档备份', page: 'tools', jump: '存档管理', keys: '存档 备份 恢复 saves' },
  { label: '世界种子预览', page: 'tools', jump: '种子地形预览', keys: '种子 seed 地形 地图' },
  { label: 'NBT 编辑器', page: 'tools', jump: 'NBT 编辑器', keys: 'nbt level.dat 数据 编辑' },
  { label: '截图图库', page: 'tools', jump: '截图图库', keys: '截图 相册 图片' },
  { label: '崩溃报告', page: 'tools', jump: '崩溃报告', keys: '崩溃 报错 日志 crash' },
  { label: '清理缓存', page: 'tools', jump: '导入与清理', keys: '清理 缓存 修复' },
  { label: '设置 · 常规', page: 'settings', tab: 'general', keys: '设置 内存 目录 语言 玩家名' },
  { label: '设置 · 外观', page: 'settings', tab: 'appearance', keys: '主题 毛玻璃 皮肤 壁纸 亮度 圆角 按钮大小' },
  { label: '设置 · 下载', page: 'settings', tab: 'download', keys: '线程 限速 镜像 下载源' },
  { label: '设置 · 扩展', page: 'settings', tab: 'extensions', keys: '扩展 插件' },
  { label: '设置 · 高级', page: 'settings', tab: 'advanced', keys: '高级 代理 智能 jvm 功能模块' },
  { label: '设置 · 关于与更新', page: 'settings', tab: 'about', keys: '关于 版本 更新 升级' },
  { label: '安装整合包（选择目标）', page: 'content', kind: 'modpack', keys: '整合包 已有版本 全新安装' },
  { label: '半透明 UI 材质包', page: 'content', keys: '毛玻璃 ui 材质包 替换' },
  { label: '切换实例', page: 'instances', keys: '切换 实例 目录' },
];
function paletteMatches(query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return PALETTE_ITEMS.slice(0, 12);
  return PALETTE_ITEMS.filter((item) =>
    (item.label + ' ' + item.keys).toLowerCase().includes(q)).slice(0, 12);
}
function paletteOpen() {
  let box = h('cmdPalette');
  if (!box) {
    box = document.createElement('div');
    box.id = 'cmdPalette';
    box.className = 'cmd-overlay';
    box.innerHTML = '<div class="cmd-box"><input id="cmdInput" type="text" placeholder="搜索功能，例如：种子 / 皮肤 / 整合包 / 内存" />' +
      '<div class="cmd-list" id="cmdList"></div>' +
      '<div class="cmd-foot"><span>↑↓ 选择 · Enter 跳转 · Esc 关闭</span><span>Ctrl+K</span></div></div>';
    document.body.appendChild(box);
    box.addEventListener('click', (event) => { if (event.target === box) paletteClose(); });
    h('cmdInput').addEventListener('input', () => paletteRender(h('cmdInput').value));
    h('cmdInput').addEventListener('keydown', (event) => {
      const list = Array.from(document.querySelectorAll('#cmdList .cmd-item'));
      const active = document.querySelector('#cmdList .cmd-item.active');
      const index = list.indexOf(active);
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        if (!list.length) return;
        list.forEach((node) => node.classList.remove('active'));
        const target = list[Math.min(list.length - 1, index + 1)] || list[0];
        if (target) target.classList.add('active');
        paletteScroll();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        list.forEach((node) => node.classList.remove('active'));
        const target = list[Math.max(0, index - 1)] || list[0];
        if (target) target.classList.add('active');
        paletteScroll();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        const pick = document.querySelector('#cmdList .cmd-item.active') ||
          document.querySelector('#cmdList .cmd-item');
        if (pick) pick.click();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        paletteClose();
      }
    });
  }
  box.classList.add('show');
  const input = h('cmdInput');
  if (input) { input.value = ''; input.focus(); }
  paletteRender('');
}
function paletteScroll() {
  const active = document.querySelector('#cmdList .cmd-item.active');
  if (active) active.scrollIntoView({ block: 'nearest' });
}
function paletteRender(query) {
  const list = h('cmdList');
  if (!list) return;
  const items = paletteMatches(query);
  list.innerHTML = items.length ? items.map((item, index) =>
    '<button class="cmd-item' + (index === 0 ? ' active' : '') + '" data-index="' + index + '">' +
      '<span>' + esc(item.label) + '</span><small>' + esc(item.keys.split(' ').slice(0, 3).join(' · ')) + '</small></button>'
  ).join('') : '<div class="empty" style="padding:18px">没有匹配的功能，试试「下载」「皮肤」「整合包」。</div>';
  list.querySelectorAll('.cmd-item').forEach((node) => {
    node.addEventListener('click', () => {
      const item = items[Number(node.dataset.index)];
      if (item) paletteRun(item);
    });
  });
}
function paletteRun(item) {
  paletteClose();
  if (item.page === 'content' && item.kind) {
    S.content = Object.assign(S.content || {}, { kind: item.kind, offset: 0 });
    setPage('content');
    return;
  }
  if (item.page === 'settings' && item.tab) {
    S.settings.tab = item.tab;
    setPage('settings');
    return;
  }
  if (item.page === 'download' && item.tab) {
    S.dlTab = item.tab;
    setPage('download');
    return;
  }
  setPage(item.page);
  if (item.jump) setTimeout(() => ACT['tool-jump'](item.jump), 260);
}
function paletteClose() { const box = h('cmdPalette'); if (box) box.classList.remove('show'); }
window.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === 'k') {
    event.preventDefault();
    paletteOpen();
  } else if (event.key === 'Escape') {
    paletteClose();
  }
});

/* ---------- 空状态「下一步」小教程 ---------- */
const GUIDE_STEPS = {
  download: [
    '在下载中心 → 游戏版本选一个正式版安装（第一次建议 1.20.1 或最新正式版）。',
    '装完回主页点「启动」；如果提示缺 Java，会自动引导到下载中心 → Java。',
    '想装 mod 时，先在下载中心装 Forge / Fabric / NeoForge，再去内容中心搜索 mod。',
  ],
  content: [
    '在上方搜索框输入 Mod / 整合包 / 资源包 / 光影包名称，或直接把 .jar 拖进窗口。',
    '搜索时用「版本 / 加载器」筛选，结果会按兼容性过滤，避免装错。',
    '点安装后会进入下载任务，可暂停、断点续传；完成后自动写入对应版本目录。',
  ],
  modpack: [
    '在整合包中心挑一个整合包，点「安装」。',
    '安装方式有两种：下载全新版本（独立实例，推荐）或附加到已有版本（覆盖补装）。',
    '下载完成后会自动建实例并出现在主页版本列表，直接启动即可。',
  ],
  home: [
    '先把游戏版本装好：下载中心 → 游戏版本 → 选版本 → 安装。',
    '也可以直接拖入整合包，启动器会自动帮你把原版和加载器一起装好。',
    '装好后回主页选中版本点「启动」，剩余的前置与 Java 会由启动前检查提醒。',
  ],
};
ACT.guide = (kind) => {
  const steps = GUIDE_STEPS[kind] || GUIDE_STEPS.home;
  openSheet('下一步怎么做',
    '<div class="section" style="padding:4px 2px">' +
      steps.map((text, index) =>
        '<div style="display:flex;gap:10px;margin-bottom:12px"><b style="flex:none;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;background:color-mix(in srgb, var(--accent) 28%, transparent);font-size:12px">' +
        (index + 1) + '</b><span class="hint" style="flex:1;line-height:1.7">' + esc(text) + '</span></div>').join('') +
      '<div class="hint">拖入文件时，启动器会先问你要导入到哪个游戏版本，不会乱写目录。</div>' +
    '</div>',
    '<button class="btn" data-act="nav" data-arg="wiki">看完整教程</button>' +
    '<button class="btn" data-act="nav" data-arg="modpack">安装整合包</button>' +
    '<button class="btn primary" data-act="guide-download">去下载游戏版本</button>');
};
ACT['guide-download'] = () => { closeSheet(); S.dlTab = 'game'; setPage('download'); };

let bootAttempts = 0;
function start() {
  if (S.booted) return;
  const a = api();
  if (!a || typeof a.bootstrap !== 'function') {
    // 首次启动 WebView2 时桥接可能晚几百毫秒注入，持续轮询直到后端就绪
    bootAttempts += 1;
    if (bootAttempts > 60) {
      h('view').innerHTML = '<div class="empty">初始化失败：美化版后端尚未就绪</div>';
      return;
    }
    setTimeout(start, 400);
    return;
  }
  S.booted = true;
  boot();
}
window.addEventListener('pywebviewready', start);
start();

