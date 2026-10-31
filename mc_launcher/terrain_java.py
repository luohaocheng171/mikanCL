"""地形高度图生成：调用原生 Java（内嵌 TerrainGen.java），不再使用 Python 噪声。

流程：
1. 首次使用时把 TerrainGen.java 写入 data/terrain；
2. 优先用 javac 编译为 class 并缓存，之后直接 `java -cp` 运行；
3. 没有 javac 但 Java 11+ 时，使用单文件源码启动 `java TerrainGen.java`；
4. Java 输出 heightmap.bin（每像素 1 字节）与 heightmap.png（彩色预览）。

Java 由启动器已检测到的运行时列表（含用户自行设置的 Java）中挑选，不联网。

两种噪声模式（参数固定，不提供任何可调项）：
- 经典（0）：1.7–1.17 的 NoiseGeneratorOctaves / ImprovedNoise；
- 新版（1）：1.18+ 的 Xoroshiro128++ 随机源与气候噪声（大陆性 / 侵蚀度 / 奇异度）。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import DATA_DIR

SOURCE_VERSION = "5"

JAVA_SOURCE = r'''// MikanCL TerrainGen (source version 5)
//
// 经典模式（1.7–1.17）：与 Minecraft NoiseGeneratorOctaves 相同的 ImprovedNoise
// （256 置换表 + 16 向梯度表），octave 按原版频率 ×2 / 振幅 ×0.5 叠加。
// 新版模式（1.18+）：Minecraft 1.18 起换用 Xoroshiro128++ 随机源，地形由气候噪声
// （大陆性 continentalness / 侵蚀度 erosion / 奇异度 weirdness）经样条合成；本程序
// 按同样的噪声结构与固定尺度生成高度，不提供任何额外可调参数。
// 两种模式都不包含生物群系、地形样条数据与密度函数，仅用于出生点附近的高度示意。
import java.awt.image.BufferedImage;
import java.io.File;
import java.io.FileOutputStream;
import java.util.Random;
import javax.imageio.ImageIO;

public class TerrainGen {
    /** 与 Minecraft 各版本噪声类一致的最小随机源接口。 */
    interface Rng {
        double nextDouble();
        int nextInt(int bound);
    }

    /** 经典版本（Java Random）适配。 */
    static final class JavaRng implements Rng {
        private final Random random;

        JavaRng(Random random) {
            this.random = random;
        }

        public double nextDouble() {
            return this.random.nextDouble();
        }

        public int nextInt(int bound) {
            return this.random.nextInt(bound);
        }
    }

    /** 1.18+ 世界生成使用的 Xoroshiro128++。 */
    static final class Xoroshiro implements Rng {
        private long lo;
        private long hi;

        Xoroshiro(long seed) {
            this.lo = seed;
            this.hi = seed ^ 0x6A09E667F3BCC909L;
        }

        long nextLong() {
            long l0 = this.lo;
            long l1 = this.hi;
            long result = Long.rotateLeft(l0 + l1, 17) + l0;
            l1 ^= l0;
            this.lo = Long.rotateLeft(l0, 49) ^ l1 ^ (l1 << 21);
            this.hi = Long.rotateLeft(l1, 28);
            return result;
        }

        public double nextDouble() {
            return (this.nextLong() >>> 11) * 0x1.0p-53;
        }

        public int nextInt(int bound) {
            if (bound <= 0) {
                return 0;
            }
            return (int) ((this.nextLong() >>> 1) % bound);
        }
    }

    /** ImprovedNoise：256 置换表 + 16 向梯度表，1.7–1.17 与 1.18 共用同一套核心算法。 */
    static final class Perlin {
        private static final double[] GRAD_X = {1,-1,1,-1,1,-1,1,-1,0,0,0,0,1,0,-1,0};
        private static final double[] GRAD_Y = {1,1,-1,-1,0,0,0,0,1,-1,1,-1,1,-1,1,-1};
        private static final double[] GRAD_Z = {0,0,0,0,1,1,-1,-1,1,1,-1,-1,0,1,0,-1};
        private final int[] p = new int[512];
        final double xo;
        final double yo;
        final double zo;

        Perlin(Rng rng) {
            this.xo = rng.nextDouble() * 256.0D;
            this.yo = rng.nextDouble() * 256.0D;
            this.zo = rng.nextDouble() * 256.0D;
            for (int i = 0; i < 256; i++) {
                this.p[i] = i;
            }
            for (int i = 0; i < 256; i++) {
                int j = rng.nextInt(256 - i) + i;
                int k = this.p[i];
                this.p[i] = this.p[j];
                this.p[j] = k;
                this.p[i + 256] = this.p[i];
            }
        }

        private static double lerp(double t, double a, double b) {
            return a + t * (b - a);
        }

        private static double grad(int hash, double x, double y, double z) {
            int i = hash & 15;
            return GRAD_X[i] * x + GRAD_Y[i] * y + GRAD_Z[i] * z;
        }

        double noise(double x, double y, double z) {
            double d0 = x + this.xo;
            double d1 = y + this.yo;
            double d2 = z + this.zo;
            int i = (int) Math.floor(d0);
            int j = (int) Math.floor(d1);
            int k = (int) Math.floor(d2);
            int l = i & 255;
            int i1 = j & 255;
            int j1 = k & 255;
            d0 -= i;
            d1 -= j;
            d2 -= k;
            double u = d0 * d0 * d0 * (d0 * (d0 * 6.0D - 15.0D) + 10.0D);
            double v = d1 * d1 * d1 * (d1 * (d1 * 6.0D - 15.0D) + 10.0D);
            double w = d2 * d2 * d2 * (d2 * (d2 * 6.0D - 15.0D) + 10.0D);
            int a = this.p[l] + i1;
            int b = this.p[l + 1] + i1;
            int c = this.p[a] + j1;
            int d = this.p[a + 1] + j1;
            int e = this.p[b] + j1;
            int f = this.p[b + 1] + j1;
            double x00 = lerp(u, grad(this.p[c], d0, d1, d2),
                    grad(this.p[e], d0 - 1.0D, d1, d2));
            double x10 = lerp(u, grad(this.p[d], d0, d1 - 1.0D, d2),
                    grad(this.p[f], d0 - 1.0D, d1 - 1.0D, d2));
            double x01 = lerp(u, grad(this.p[c + 1], d0, d1, d2 - 1.0D),
                    grad(this.p[e + 1], d0 - 1.0D, d1, d2 - 1.0D));
            double x11 = lerp(u, grad(this.p[d + 1], d0, d1 - 1.0D, d2 - 1.0D),
                    grad(this.p[f + 1], d0 - 1.0D, d1 - 1.0D, d2 - 1.0D));
            double y0 = lerp(v, x00, x10);
            double y1 = lerp(v, x01, x11);
            return lerp(w, y0, y1);
        }
    }

    /** 多个 Perlin 副本按原版方式叠加（频率 ×2、振幅 ×0.5）。 */
    static final class Octaves {
        private final Perlin[] generators;
        private final double norm;

        Octaves(Rng rng, int octaves) {
            this.generators = new Perlin[octaves];
            double sum = 0.0D;
            double amp = 1.0D;
            for (int i = 0; i < octaves; i++) {
                this.generators[i] = new Perlin(rng);
                sum += amp;
                amp *= 0.5D;
            }
            this.norm = sum == 0.0D ? 1.0D : 1.0D / sum;
        }

        double sample(double x, double z) {
            double total = 0.0D;
            double amplitude = 1.0D;
            double frequency = 1.0D;
            for (int i = 0; i < this.generators.length; i++) {
                total += this.generators[i].noise(x * frequency, z * frequency, 0.0D) * amplitude;
                amplitude *= 0.5D;
                frequency *= 2.0D;
            }
            return total * this.norm;
        }
    }

    /** 经典（1.7–1.17）地形：单个 8 octave 主噪声，基准波长约 384 格。 */
    static final class ClassicTerrain {
        private final Octaves noise;

        ClassicTerrain(long seed) {
            this.noise = new Octaves(new JavaRng(new Random(seed)), 8);
        }

        double height(double x, double z) {
            double n = this.noise.sample(x / 384.0D, z / 384.0D);
            return 64.0D + n * 42.0D;
        }
    }

    /** 新版（1.18+）地形：三组气候噪声合成，尺度与海洋阈值固定。 */
    static final class ModernTerrain {
        private final Octaves continental;
        private final Octaves erosion;
        private final Octaves weirdness;

        ModernTerrain(long seed) {
            Xoroshiro rng = new Xoroshiro(seed);
            this.continental = new Octaves(rng, 6);
            this.erosion = new Octaves(rng, 4);
            this.weirdness = new Octaves(rng, 4);
        }

        double height(double x, double z) {
            double c = this.continental.sample(x / 1024.0D, z / 1024.0D);
            double e = this.erosion.sample(x / 256.0D, z / 256.0D);
            double w = this.weirdness.sample(x / 128.0D, z / 128.0D);
            double base;
            double amp;
            if (c < -0.20D) {
                // 海洋：大陆性越低越深，起伏很小
                base = 58.0D + (c + 0.20D) * 90.0D;
                amp = 5.0D;
            } else {
                // 陆地：大陆性抬升基础高度，侵蚀度越低起伏越大（山地）
                double inland = Math.min(1.0D, (c + 0.20D) / 1.20D);
                base = 64.0D + inland * 28.0D;
                double flat = Math.max(0.0D, Math.min(1.0D, (e + 1.0D) * 0.5D));
                amp = 6.0D + (1.0D - flat) * 52.0D;
            }
            return base + w * amp * 0.45D;
        }
    }

    private static int[] color(double v) {
        if (v < 0.32D) return new int[] {54, 110, 180};
        if (v < 0.38D) return new int[] {232, 210, 140};
        if (v < 0.62D) {
            double t = (v - 0.38D) / 0.24D;
            return new int[] {(int) (86 - t * 20), (int) (140 + t * 30), (int) (70 - t * 10)};
        }
        if (v < 0.80D) {
            double t = (v - 0.62D) / 0.18D;
            return new int[] {(int) (120 + t * 30), (int) (100 + t * 30), (int) (70 + t * 10)};
        }
        double t = Math.min(1.0D, (v - 0.80D) / 0.20D);
        return new int[] {(int) (200 + t * 55), (int) (200 + t * 55), (int) (210 + t * 45)};
    }

    private static void run(long seed, int size, int mode, String pngPath, String binPath)
            throws Exception {
        ClassicTerrain classic = mode == 0 ? new ClassicTerrain(seed) : null;
        ModernTerrain modern = mode == 0 ? null : new ModernTerrain(seed);

        // 第一遍：计算每列高度并记录极值（用于把本帧地形归一化到可读的对比度）
        float[] heights = new float[size * size];
        double min = Double.MAX_VALUE;
        double max = -Double.MAX_VALUE;
        for (int row = 0; row < size; row++) {
            for (int col = 0; col < size; col++) {
                double h = classic != null ? classic.height(col, row) : modern.height(col, row);
                heights[row * size + col] = (float) h;
                if (h < min) min = h;
                if (h > max) max = h;
            }
        }
        double span = max - min;
        if (span < 1.0E-6D) span = 1.0D;

        // 第二遍：写入高度字节与彩色预览
        BufferedImage image = new BufferedImage(size, size, BufferedImage.TYPE_INT_RGB);
        byte[] line = new byte[size];
        try (FileOutputStream out = new FileOutputStream(binPath)) {
            for (int row = 0; row < size; row++) {
                for (int col = 0; col < size; col++) {
                    double v = (heights[row * size + col] - min) / span;
                    if (v < 0.0D) v = 0.0D;
                    if (v > 1.0D) v = 1.0D;
                    int b = (int) Math.round(v * 255.0D);
                    line[col] = (byte) b;
                    int[] c = color(v);
                    image.setRGB(col, row, (c[0] << 16) | (c[1] << 8) | c[2]);
                }
                out.write(line);
            }
        }
        ImageIO.write(image, "png", new File(pngPath));
        System.out.println("OK");
    }

    public static void main(String[] args) {
        try {
            long seed = Long.parseLong(args[0]);
            int size = Integer.parseInt(args[1]);
            int mode = Integer.parseInt(args[2]);
            String pngPath = args[3];
            String binPath = args[4];
            run(seed, size, mode, pngPath, binPath);
        } catch (OutOfMemoryError error) {
            System.err.println("OUT_OF_MEMORY");
            System.exit(3);
        } catch (Exception error) {
            error.printStackTrace();
            System.exit(2);
        }
    }
}
'''



class TerrainJavaError(RuntimeError):
    pass


def terrain_dir() -> Path:
    return DATA_DIR / "terrain"


def _create_flags() -> int:
    if sys.platform == "win32":
        return 0x08000000  # CREATE_NO_WINDOW
    return 0


def _source_path() -> Path:
    folder = terrain_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "TerrainGen.java"
    marker = folder / ".source_version"
    stale = not path.exists()
    try:
        stale = stale or marker.read_text(encoding="utf-8").strip() != SOURCE_VERSION
    except OSError:
        stale = True
    if stale:
        path.write_text(JAVA_SOURCE, encoding="utf-8")
        try:
            marker.write_text(SOURCE_VERSION, encoding="utf-8")
        except OSError:
            pass
        class_file = folder / "TerrainGen.class"
        if class_file.exists():
            try:
                class_file.unlink()
            except OSError:
                pass
    return path


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_create_flags(),
    )


def _javac_for(java_path: str) -> str | None:
    folder = Path(java_path).parent
    candidate = folder / ("javac.exe" if sys.platform == "win32" else "javac")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("javac")
    return found or None


def candidate_javas(ctx=None, java_path: str = "") -> list[str]:
    """按优先级收集可用的 java 可执行文件。"""
    result: list[str] = []

    def add(path: str) -> None:
        if path and os.path.exists(path) and os.path.normcase(path) not in {
            os.path.normcase(p) for p in result
        }:
            result.append(path)

    javas = getattr(ctx, "javas", None) if ctx is not None else None
    if javas:
        try:
            for info in sorted(javas, key=lambda j: -int(getattr(j, "major", 0))):
                add(str(getattr(info, "path", "") or ""))
        except Exception:  # noqa: BLE001
            pass
    add(java_path)
    add(shutil.which("java") or "")
    return result


def generate_heightmap_java(
    seed: int,
    size: int = 256,
    mode: int = 0,
    *,
    ctx=None,
    java_path: str = "",
    timeout: int | None = None,
) -> bytes:
    """调用 Java 生成 size×size 高度图，返回每像素 1 字节的高度数据（0-255）。

    mode：0 = 经典（1.7–1.17），1 = 新版（1.18+）。两种模式的噪声参数均为原版固定值。
    """
    size = max(16, int(size))
    if timeout is None:
        # 面积越大耗时越久：512 以内 2 分钟，更大给 15 分钟
        timeout = 120 if size <= 512 else 900
    source = _source_path()
    folder = source.parent
    png_path = folder / "heightmap.png"
    bin_path = folder / "heightmap.bin"
    args = [
        str(int(seed)),
        str(size),
        "0" if int(mode) == 0 else "1",
        str(png_path),
        str(bin_path),
    ]

    errors: list[str] = []
    javas = candidate_javas(ctx, java_path)
    if not javas:
        raise TerrainJavaError(
            "未检测到可用的 Java 运行时，请先在「Java 运行时」页安装或指定 Java。"
        )

    for java in javas:
        javac = _javac_for(java)
        class_file = folder / "TerrainGen.class"
        try:
            if javac:
                if not class_file.exists():
                    compiled = _run(
                        [javac, "-encoding", "UTF-8", "-d", str(folder), str(source)],
                        timeout=timeout,
                    )
                    if compiled.returncode != 0:
                        errors.append(
                            f"javac 编译失败：{(compiled.stderr or compiled.stdout).strip()[:400]}"
                        )
                        continue
                result = _run(
                    [java, "-cp", str(folder), "TerrainGen"] + args, timeout=timeout
                )
            else:
                # Java 11+ 支持单文件源码启动，免编译
                result = _run([java, str(source)] + args, timeout=timeout)
            if result.returncode != 0:
                errors.append(
                    f"{Path(java).name} 运行失败：{(result.stderr or result.stdout).strip()[:400]}"
                )
                continue
            data = bin_path.read_bytes()
            if len(data) != size * size:
                errors.append(f"Java 输出尺寸不符：{len(data)} != {size * size}")
                continue
            return data
        except subprocess.TimeoutExpired:
            errors.append(f"{Path(java).name} 生成超时（>{timeout}s）")
        except OSError as exc:
            errors.append(f"{Path(java).name} 无法启动：{exc}")

    raise TerrainJavaError("；".join(errors) or "Java 地形生成失败。")


__all__ = [
    "TerrainJavaError",
    "candidate_javas",
    "generate_heightmap_java",
    "JAVA_SOURCE",
]
