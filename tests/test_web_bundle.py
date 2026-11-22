"""前端单文件 app.js 的静态体检：能加载、动作有处理、页面有渲染函数。

以前出现过「拼接代码时把 renderBackups 整段删掉」→ 一进主页就
``初始化失败：renderBackups is not defined``。这类错误人工看不出来，
但用 Node 把脚本跑一遍（桩掉 DOM）立刻就能抓到，所以锁成测试。

没有 Node 的环境自动跳过。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "mc_launcher" / "ui_web" / "web" / "app.js"
CHECK = Path(__file__).resolve().parent / "_web_loadcheck.js"


class LoadTest(unittest.TestCase):
    def test_script_loads_without_reference_error(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node，跳过前端加载检查")
        proc = subprocess.run([node, str(CHECK)], cwd=str(ROOT), capture_output=True,
                              text=True, timeout=120)
        self.assertIn("LOAD OK", proc.stdout, msg=(proc.stdout or "") + (proc.stderr or ""))

    def test_every_data_act_has_handler(self):
        src = APP.read_text(encoding="utf-8")
        acts = set(re.findall(r'data-act="([a-z0-9-]+)"', src))
        handled = set(re.findall(r"ACT\['([a-z0-9-]+)'\]", src))
        # guide / nav 是纯导航按钮，没绑定动作时点击会被安全忽略
        missing = sorted(a for a in acts - handled - {"guide", "nav"})
        self.assertEqual(missing, [], f"这些 data-act 没有处理函数：{missing}")

    def test_voxel_fluid_and_refill_wiring(self):
        src = APP.read_text(encoding="utf-8")
        # 按用户要求：旧版正方形地图 + 矿透，但保留半透明水体（能看水底）
        self.assertIn("EX3D_FS_TEX_A", src)
        self.assertIn("const trans = alloc(transN, true)", src)
        self.assertIn("alphaOf(mat)", src)
        # 仍然不要动态瓦片 / 刷新续跑 / 抽稀
        self.assertNotIn("ex3d-refill", src)
        self.assertNotIn("dynamicTiles", src)
        self.assertNotIn("chunk_step", src)
        self.assertIn("ACT['ex3d-xray']", src)
        # 旧版标志：渲染方式下拉 + 方块分类面板
        self.assertIn("生成方块视图", src)
        self.assertIn("方块分类", src)

    def test_page_handlers_exist(self):
        src = APP.read_text(encoding="utf-8")
        # 路由表一行里塞了好几个 key: renderXxx，不能按行首匹配
        routes = re.findall(r"\b\w+:\s*(render[A-Za-z0-9]+)\s*,", src)
        self.assertGreater(len(set(routes)), 15)
        for name in routes:
            defined = re.search(rf"^(?:async\s+)?function\s+{name}\s*\(", src, re.M)
            self.assertIsNotNone(defined, f"路由用到的 {name} 没有定义")


if __name__ == "__main__":
    unittest.main()
