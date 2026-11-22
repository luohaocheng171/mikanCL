"""v5.5.9：噪声预览按版本分档 + 真实方块 Y 校准的回归测试。

这套测试把「预览必须像原版」拆成可验证的断言：
1. 版本 → 噪声档位映射（Beta / 1.2–1.6 / 1.7–1.12 / 1.13–1.17 / 1.18+）；
2. 每档的高度分布（海平面上下比例、中位数、峰谷）落在真实存档量级；
3. 同一颗种子在不同档位必须画出不同地形（这就是「噪声取决于版本」）；
4. 同一版本 + 同一颗种子必须完全可复现。
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mc_launcher.terrain_java import (  # noqa: E402
    NOISE_ERAS,
    SOURCE_VERSION,
    generate_world_map_java,
    noise_era_for_version,
    version_height_limits,
)


def _find_java() -> str:
    if sys.platform == "win32":
        for base in (r"C:\Program Files\Zulu", r"C:\Program Files\Java",
                     r"C:\Program Files\Eclipse Adoptium"):
            root = Path(base)
            if not root.is_dir():
                continue
            for folder in sorted(root.iterdir(), reverse=True):
                exe = folder / "bin" / "java.exe"
                if exe.is_file():
                    return str(exe)
    return shutil.which("java") or ""


JAVA = _find_java()


def _render(era: int, size: int = 128, radius: float = 1024.0, seed: int = 114514) -> dict:
    profile = NOISE_ERAS[era]
    return generate_world_map_java(
        seed, size, 1 if era >= 4 else 0,
        center_x=0.0, center_z=0.0, radius=radius,
        sea_level=profile["sea_level"], min_y=profile["min_y"], max_y=profile["max_y"],
        java_path=JAVA, era=era, timeout=300,
    )


def _bytes(payload: bytes) -> bytes:
    return bytes(payload)


class EraMappingTest(unittest.TestCase):
    def test_versions_cover_five_eras(self):
        cases = {
            "rd-161348": 0, "a1.2.6": 0, "b1.8.1": 0, "1.1": 0,
            "1.2.5": 1, "1.6.4": 1,
            "1.7.10": 2, "1.12.2": 2,
            "1.13.2": 3, "1.14.4": 3, "1.16.5": 3, "1.17.1": 3,
            "1.18": 4, "1.19.4": 4, "1.20.1": 4,
        }
        for version, era in cases.items():
            self.assertEqual(noise_era_for_version(version), era, version)

    def test_unknown_versions_use_current_noise(self):
        self.assertEqual(noise_era_for_version(""), 4)
        self.assertEqual(noise_era_for_version("26.1-snapshot-3"), 4)

    def test_limits_follow_era(self):
        beta = version_height_limits("b1.8.1")
        self.assertEqual((beta["min_y"], beta["max_y"], beta["sea_level"]), (0, 127, 64))
        classic = version_height_limits("1.14.4")
        self.assertEqual((classic["min_y"], classic["max_y"], classic["sea_level"]), (0, 255, 63))
        modern = version_height_limits("1.20.1")
        self.assertEqual((modern["min_y"], modern["max_y"], modern["sea_level"]), (-64, 319, 63))
        # 三套文案各司其职：限高范围 / 版本档位 / 噪声短名
        self.assertIn("0 ~ 255", classic["label"])
        self.assertIn("海洋版", classic["era_label"])
        self.assertEqual(classic["noise_label"], "海洋版地形")

    def test_every_era_described(self):
        self.assertEqual(sorted(NOISE_ERAS), [0, 1, 2, 3, 4])
        for era, row in NOISE_ERAS.items():
            self.assertTrue(row["label"], era)
            self.assertLess(row["min_y"], row["sea_level"])
            self.assertLess(row["sea_level"], row["max_y"])


class SourceContractTest(unittest.TestCase):
    def test_source_version_bumped(self):
        # 版本号跟随 terrain_java.SOURCE_VERSION：改了 JAVA_SOURCE 就要一起往上加，
        # 否则旧 .class 不会失效。当前为 10（v5.5.10 平滑了预览噪声的细节倍频）。
        self.assertEqual(SOURCE_VERSION, "10")

    def test_source_has_era_table(self):
        from mc_launcher.terrain_java import JAVA_SOURCE

        for token in ("static Era era(int id)", "terrain.height(", "seaLevel + (raw - seaLevel)",
                      "pixelBlocks", "nearWater("):
            self.assertIn(token, JAVA_SOURCE, token)

    def test_colour_bands_use_absolute_height(self):
        from mc_launcher.terrain_java import JAVA_SOURCE

        # 关键回归：不能再有「整图 min-max 归一化」式的高度映射
        self.assertNotIn("(heights[row * size + col] - min) / span", JAVA_SOURCE)
        self.assertIn("double delta = y - sea;", JAVA_SOURCE)


@unittest.skipIf(not JAVA, "本机没有可用的 Java，跳过真实出图测试")
class RenderCalibrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {era: _render(era) for era in (0, 2, 3, 4)}

    def test_heights_within_version_limits(self):
        for era, result in self.results.items():
            profile = NOISE_ERAS[era]
            info = result["height"]
            self.assertGreaterEqual(info["observed_min_y"], profile["min_y"], era)
            self.assertLessEqual(info["observed_max_y"], profile["max_y"], era)

    def test_plains_sit_around_sea_level(self):
        # 真实存档（1.14.4 出生点 529 区块）实测中位数 67、p90 72；
        # 预览允许更崎岖，但中位数必须贴着海平面，不能整图飘到天上或沉到海底
        for era in (2, 3):
            info = self.results[era]["height"]
            sea = NOISE_ERAS[era]["sea_level"]
            self.assertGreater(info["average_y"], sea + 1, era)
            self.assertLess(info["average_y"], sea + 16, era)

    def test_beta_never_exceeds_old_world_height(self):
        self.assertLessEqual(self.results[0]["height"]["observed_max_y"], 127)

    def test_ocean_and_land_both_present(self):
        # 直接按高度字节换算回方块 Y，避免直方图分桶太粗导致的误判
        for era, result in self.results.items():
            info = result["height"]
            low, high = info["min_y"], info["max_y"]
            span = max(1, high - low)
            sea = NOISE_ERAS[era]["sea_level"]
            water = land = 0
            for value in result["heightmap"]:
                y = low + (value / 255.0) * span
                if y < sea - 0.5:
                    water += 1
                else:
                    land += 1
            total = water + land
            self.assertGreater(total, 0)
            self.assertGreater(water / total, 0.02, f"era {era} 几乎没有水域")
            self.assertGreater(land / total, 0.05, f"era {era} 几乎没有陆地")

    def test_noise_depends_on_version(self):
        payloads = {era: _bytes(result["heightmap"]) for era, result in self.results.items()}
        eras = sorted(payloads)
        for index, left in enumerate(eras):
            for right in eras[index + 1:]:
                self.assertNotEqual(payloads[left], payloads[right],
                                    f"era {left} 与 era {right} 画出了同一张图")

    def test_same_version_is_reproducible(self):
        again = _render(3)
        self.assertEqual(_bytes(again["heightmap"]), _bytes(self.results[3]["heightmap"]))

    def test_png_is_valid(self):
        for era, result in self.results.items():
            data = Path(result["heightmap_png"]).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", era)
            width, height = struct.unpack(">II", data[16:24])
            self.assertEqual((width, height), (result["size"], result["size"]))

    def test_era_label_reported(self):
        for era, result in self.results.items():
            self.assertEqual(result["era"], era)
            self.assertEqual(result["era_label"], NOISE_ERAS[era]["label"])

    def test_biome_legend_has_river(self):
        names = [row["name"] for row in self.results[3]["legend"]]
        self.assertIn("河流", names)


class CompileTest(unittest.TestCase):
    @unittest.skipIf(not JAVA, "本机没有可用的 Java，跳过编译测试")
    def test_embedded_source_compiles(self):
        from mc_launcher.terrain_java import JAVA_SOURCE

        javac = Path(JAVA).with_name("javac.exe" if sys.platform == "win32" else "javac")
        compiler = str(javac) if javac.is_file() else (shutil.which("javac") or "")
        if not compiler:
            self.skipTest("没有 javac")
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "TerrainGen.java"
            source.write_text(JAVA_SOURCE, encoding="utf-8")
            done = subprocess.run(
                [compiler, "-encoding", "UTF-8", "-d", folder, str(source)],
                capture_output=True, text=True, timeout=180,
            )
            self.assertEqual(done.returncode, 0, (done.stderr or done.stdout)[:800])


if __name__ == "__main__":
    unittest.main()
