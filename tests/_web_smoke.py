"""美化版前端离屏冒烟：用 QtWebEngine 加载 index.html，捕获 JS 错误并试跑关键渲染函数。

只验证「脚本能解析执行、新增的创世神子页函数不抛异常」，不连后端。
用法：python tests/_web_smoke.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "mc_launcher" / "ui_web" / "web" / "index.html"

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage  # noqa: E402


class Page(QWebEnginePage):
    def __init__(self):
        super().__init__()
        self.errors: list[str] = []
        self.done = False

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self.errors.append(f"console:{line}: {message}")


PROBE = r"""
(function () {
  const out = [];
  function probe(name, fn) {
    try { const r = fn(); out.push(name + ':ok:' + (typeof r === 'string' ? r.length : 'n/a')); }
    catch (e) { out.push(name + ':ERR:' + (e && e.message)); }
  }
  // 造一个最小创世神状态，避免依赖后端
  if (!S.creator) S.creator = { tab: 'quick', world: '', state: { version: '1.21.4' }, items: [], ender: [],
    attributes: [], effects: [], ops: [], opsDir: '', backups: [], buildBlocks: [], preview: null, pending: [] };
  S.creator.tab = 'quick';
  probe('crQuickHtml', () => crQuickHtml(S.creator));
  S.creator.tab = 'nbt';
  probe('crNbtHtml', () => crNbtHtml(S.creator));
  probe('crToolsHtml', () => crToolsHtml(S.creator));
  probe('crSyncNbsWorld', () => crSyncNbsWorld());
  probe('nbsRefresh', () => nbsRefresh());
  // 皮肤笔刷：加亮/加深/喷枪/镜像 + 直线/矩形/椭圆
  probe('studio-tools', () => {
    const cv = document.createElement('canvas'); cv.width = 64; cv.height = 64;
    const ctx = cv.getContext('2d');
    S.studio = S.studio || {}; S.studio.color = '#3fa45b'; S.studio.mirror = true;
    ['pencil', 'lighten', 'darken', 'spray', 'eraser'].forEach((t) => {
      S.studio.tool = t; studioStampPixel(ctx, 10, 10, false);
    });
    S.studio.tool = 'line'; studioDrawShape(ctx, 'line', 1, 1, 20, 20, null);
    S.studio.tool = 'rect'; studioDrawShape(ctx, 'rect', 5, 5, 30, 25, null);
    S.studio.tool = 'ellipse'; studioDrawShape(ctx, 'ellipse', 10, 10, 40, 40, null);
    return 'ok';
  });
  // 种子世界：用假的预览结果渲染地图、结构标记与搜索列表
  probe('seed-render', () => {
    S.data = S.data || { versions: [{ id: '1.21.4' }] };
    S.seed = {
      version: '1.21.4', seed: '123', radius: 2048, size: 512, layer: 'height',
      query: '', running: false, selected: '', limits: null,
      result: {
        seed: 123, size: 512, radius: 2048, center: [0, 0],
        height_url: '', biome_url: '',
        height: { min: 60, max: 92 },
        structures: [
          { name: '村庄', kind: 'village', x: 120, z: -240, biome: '平原' },
          { name: '要塞', kind: 'stronghold', x: -300, z: 40, biome: '任意' },
        ],
      },
    };
    renderSeed();
    seedPaintMarkers();
    seedPaintList();
    S.seed.query = '要塞';
    seedPaintMarkers();
    seedPaintList();
    return String(document.querySelectorAll('.seed-dot').length) + '/' +
      String(document.querySelectorAll('.seed-row').length);
  });
  // 版本噪声：徽标 / 提示 / 限高文案都要带上该版本的噪声档位，换版本后旧图作废
  probe('seed-noise-era', () => {
    S.data = S.data || { versions: [{ id: '1.14.4' }, { id: '1.20.1' }] };
    S.seed = {
      version: '1.14.4', seed: '114514', radius: 2048, size: 512, layer: 'height',
      query: '', running: false, selected: '', gameResult: null,
      limits: { label: '1.2 – 1.17（0 ~ 255）', sea_level: 63, min_y: 0, max_y: 255,
                era: 3, noise_label: '海洋版地形' },
      result: {
        seed: 114514, size: 512, radius: 2048, center: [0, 0], version: '1.14.4',
        era: 3, era_label: '1.13–1.17（海洋版地形）',
        height_url: '', biome_url: '', height: { min: 42, max: 133 }, structures: [],
      },
    };
    renderSeed();
    const badge = (seedMapSourceLabel() || '');
    if (badge.indexOf('海洋版') < 0) throw new Error('徽标未显示版本噪声：' + badge);
    if (seedMapHintText().indexOf('海洋版') < 0) throw new Error('提示未显示版本噪声');
    const limitsText = seedLimitsText();
    if (limitsText.indexOf('噪声') < 0 || limitsText.indexOf('海洋版') < 0) {
      throw new Error('限高文案未显示噪声：' + limitsText);
    }
    // 换版本必须把上一版的地图清掉（不同版本地形完全不同）
    const select = document.getElementById('seedVersion');
    if (!select) throw new Error('缺少版本下拉');
    select.value = '1.20.1';
    select.dispatchEvent(new Event('change'));
    if (S.seed.result) throw new Error('换版本后旧地图没作废');
    if (S.seed.selected) throw new Error('换版本后选中项没清空');
    return limitsText;
  });
  // 存档来源的地图：图片框 + 标记点必须共用同一个框（修错位），并显示来源标记
  probe('seed-save-map', () => {
    S.seed = {
      version: '1.14.4', seed: '', radius: 2048, size: 384, layer: 'height', query: '',
      running: false, selected: '', limits: null, gameResult: null,
      view: { cx: 0, cz: 0, span: 512, size: 384 },
      save: { path: 'D:/saves/demo', name: '114514-1.14.4', chunks_done: 529,
              chunks_total: 529, center: [0, 0], bounds: [-208, -208, 208, 208] },
      result: {
        source: 'save', name: '114514-1.14.4', seed: '114514', radius: 256,
        center: [0, 0], size: 384, layer: 'height', image_url: '',
        span: 512, px: 384, covered: 0.72, chunks_done: 529, chunks_total: 529,
        height: { min: 64, max: 106 }, truncated: false,
        structures: [{ name: '废弃矿井', kind: 'mineshaft', color: '#b08968', x: 0, z: 0, biome: 'plains' },
                     { name: '要塞', kind: 'stronghold', x: 104, z: 0, biome: '' }],
        biomes: [{ kind: 'biome', name: 'plains', x: -30, z: -95, chunks: 287, color: '#8db360' }],
      },
    };
    S.seed.query = '';
    renderSeed();
    seedPaintMarkers();
    seedPaintList();
    const frame = document.getElementById('seedMapFrame');
    if (!frame) throw new Error('缺少地图框 seed-map-frame');
    if (!document.querySelector('.seed-badge.live')) throw new Error('缺少存档实时渲染标记');
    if (document.querySelectorAll('.seed-dot').length !== 3) throw new Error('标记点数量不对');
    if (document.querySelectorAll('.seed-dot.biome').length !== 1) throw new Error('群系应该是圆形标记');
    if (!document.querySelector('.seed-row i.shape-tri')) throw new Error('建筑列表缺少三角图标');
    if (!document.querySelector('.seed-row i.shape-cir')) throw new Error('群系列表缺少圆形图标');
    // 工具条：缩放 / 坐标 / 继续渲染 / 查找
    if (!document.getElementById('seedRenderStatus')) throw new Error('缺少渲染状态');
    if (!document.getElementById('seedJumpX') || !document.getElementById('seedFindTarget')) {
      throw new Error('缺少坐标或查找控件');
    }
    // 中心点必须落在 50%，右边缘的点必须贴近 79.5%（半径 256 → 104/512）
    const pct = (x, z) => seedPct(x, z);
    const mid = pct(0, 0), edge = pct(104, 0);
    if (Math.abs(mid[0] - 50) > 0.01 || Math.abs(mid[1] - 50) > 0.01) throw new Error('中心点偏移：' + mid);
    if (Math.abs(edge[0] - 70.3) > 0.05) throw new Error('边缘点偏移：' + edge);
    if (seedKindLabel(S.seed.result.structures[0]) !== '废弃矿井') throw new Error('结构名未取后端返回名');
    if (seedKindColor(S.seed.result.structures[0]) !== '#b08968') throw new Error('结构色未取后端返回值');
    if (seedMapSourceLabel().indexOf('存档') < 0) throw new Error('来源标签不对');
    if (seedMapHintText().indexOf('视野') < 0) throw new Error('提示未显示视野');
    for (const act of ['seed-expand', 'seed-find', 'seed-find-next', 'seed-jump', 'seed-zoom', 'seed-map-saves']) {
      if (typeof ACT[act] !== 'function') throw new Error('动作未注册：' + act);
    }
    return String(frame.style.width) + '/' + String(frame.style.height);
  });

  // 存档地图会话：继续渲染 / 找目标后的状态合并不整页重绘
  probe('seed-save-session', () => {
    S.page = 'seed';
    S.seed.found = null;
    const payload = {
      ok: true, source: 'save', name: 'demo', center: [-320, 180], radius: 512, span: 1024,
      px: 384, layer: 'biome', covered: 0.41, chunks_done: 900, chunks_total: 1200,
      height: { min: 60, max: 90 }, structures: [], biomes: [],
      session: { path: 'D:/saves/demo', chunks_done: 900, chunks_total: 1200, bounds: [-600, -600, 600, 600] },
      found: { kind: 'village', name: '村庄', x: -320, z: 180 },
    };
    seedApplyView(payload);
    if (S.seed.view.cx !== -320 || S.seed.view.span !== 1024) throw new Error('视窗未跟随命中点');
    if (!S.seed.save || S.seed.save.chunks_done !== 900) throw new Error('会话状态未合并');
    if (!S.seed.found || S.seed.found.x !== -320) throw new Error('命中结果未记录');
    const hint = document.getElementById('seedFindHint');
    if (!hint || hint.textContent.indexOf('村庄') < 0) throw new Error('查找提示未更新');
    if (document.getElementById('seedRenderStatus').textContent.indexOf('900') < 0) {
      throw new Error('渲染状态未刷新');
    }
    return hint.textContent;
  });

  probe('mob-card', () => {
    S.creator.mobs = {
      rows: [
        { id: 'minecraft:zombie', uuid: '1111aaaa-2222-3333-4444-555566667777', pos: [1.5, 64, 1.5],
          health: 20, max_health: 20, attack_damage: 3, movement_speed: 0.23, armor: 2,
          trades: [], edits: { max_health: 40 } },
        { id: 'minecraft:villager', uuid: '8888bbbb-2222-3333-4444-555566667777', pos: [4.5, 64, 4.5],
          health: 20, max_health: 20, attack_damage: 0, movement_speed: 0.5, armor: 0, level: 2,
          trades: [{ index: 0, buy: { id: 'minecraft:emerald', count: 12 }, sell: { id: 'minecraft:bread', count: 1 },
                     max_uses: 12, uses: 0, special_price: 0 }],
          edits: { trades: { 0: { buy_count: 6 } } } },
      ],
      meta: { files: 1, chunks: 4, total: 2, elapsed: 0.2, truncated: false, version: '1.20.1' },
      loading: false, dimension: 'overworld', filter: '', picked: { 0: true }, open: { 1: true },
      token: '', preview: { token: 't', mobs: 1, files: ['a'], changes: ['僵尸 · 1111aaaa · 最大生命 40'] }, error: '',
    };
    const html = crMobCard(S.creator);
    const tools = crToolsHtml(S.creator);
    if (html.length < 1000 || tools.indexOf('生物数值（存档内生物）') < 0) throw new Error('mob card 渲染异常');
    return String(html.length);
  });
  // 五语言 DOM 自动翻译 + API 浏览器新增的开发者面板
  probe('i18n-dev-panel', () => {
    const previous = S.data.language;
    const box = document.createElement('div');
    box.innerHTML = '<span>刷新</span><span data-act="keep-me">启动游戏</span>';
    document.body.appendChild(box);
    S.data.language = 'en_US'; applyI18n(box);
    if (box.textContent.indexOf('Refresh') < 0) throw new Error('英文词典未生效');
    if (box.querySelector('[data-act]').getAttribute('data-act') !== 'keep-me') throw new Error('属性被误改');
    S.data.language = 'ja_JP'; applyI18n(box);
    if (box.textContent.indexOf('ゲームを起動') < 0) throw new Error('切换语言未重译');
    S.data.language = 'zh_CN'; applyI18n(box);
    if (box.textContent.indexOf('刷新') < 0) throw new Error('回退中文失败');
    S.data.language = previous;
    S.apix.dev = {
      chat: { token: 'tk', plan: [{ method: 'launch', risk: 'launch', explain: '启动 1.20.1', ready: true }], reply: '计划已生成' },
      pending: null,
      webhook: { url: 'https://example.com/hook', enabled: true, events: ['game_crash'], has_secret: true },
      events: [{ event: 'download_success', time: '01:00:00' }], deliveries: [{ event: 'game_crash', ok: true }],
      ws: { ws_endpoint: 'ws://127.0.0.1:1234/ws', ws_clients: 1 },
      caps: { note: '不读取游戏进程内存', methods: ['game_player_state', 'game_teleport'] },
      cli: { entry: 'python mikan_cli.py', discovery: 'data/api_gateway.json', commands: ['mikan status'] },
      rcon: { host: '127.0.0.1', port: 25575, has_password: true },
      uri: { registered: false },
    };
    const html = devCardsHtml();
    for (const needle of ['对话式 API', 'Webhook', 'WebSocket', '命令行与游戏联动', '确认执行']) {
      if (html.indexOf(needle) < 0) throw new Error('开发者面板缺卡片：' + needle);
    }
    if (typeof ACT['apix-chat-plan'] !== 'function' || typeof ACT['apix-webhook-save'] !== 'function') {
      throw new Error('新动作未注册');
    }
    box.remove();
    return String(html.length);
  });
  return out.join('|');
})();
"""


def main() -> int:
    app = QApplication.instance() or QApplication([])
    page = Page()
    page.setUrl(QUrl.fromLocalFile(str(WEB)))

    state = {"done": False}

    def on_load(ok: bool) -> None:
        if state["done"]:
            return
        state["done"] = True
        page.runJavaScript(PROBE, lambda result: finish(result))

    def finish(result) -> None:
        print("probe:", result)
        if page.errors:
            print("JS ERRORS:")
            for err in page.errors:
                print("  ", err)
        ok = bool(result) and ":ERR:" not in str(result) and not page.errors
        print("RESULT:", "PASS" if ok else "FAIL")
        app.exit(0 if ok else 1)

    page.loadFinished.connect(on_load)
    QTimer.singleShot(30000, lambda: app.exit(2))
    code = app.exec()
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
