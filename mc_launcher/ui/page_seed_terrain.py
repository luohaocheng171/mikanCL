"""世界种子与地形预览：输入种子 → 原生 Java 生成高度图 → QWebEngineView 3D 渲染。

高度图交给内嵌的 Java 程序（TerrainGen.java）计算：启动器自动编译（javac 缓存）
或使用 Java 11+ 的单文件源码启动，避免 Python 端大规模噪声运算造成卡顿甚至崩溃。
渲染用内联 WebGL 把地形画成 Minecraft 风格的方块（体素柱：平顶 + 阶梯侧面），
支持按钮 / 鼠标旋转、缩放、平移与自动旋转，无外部 CDN 依赖，
适配 PyInstaller 单文件打包（setHtml + baseUrl）。
若 QtWebEngine 不可用，回退为 Java 生成的 2D 彩色高度图预览。
"""

from __future__ import annotations

import base64
import shutil
import time
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..config import DATA_DIR
from ..terrain_java import terrain_dir, generate_heightmap_java
from .widgets import page_header

try:  # WebEngine 在部分精简环境下可能缺失，提供回退
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except Exception:  # pragma: no cover - 环境依赖
    _HAS_WEBENGINE = False


# 说明：模板使用 __SIZE__ / __B64__ / __LEVELS__ / __HINT__ / __GLFAIL__ 占位符，
# 通过 str.replace 注入（JS 含大量花括号，不能用 str.format）。
_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;height:100%;background:#1e1e24;color:#eee;
font-family:Segoe UI,Arial,sans-serif;overflow:hidden}
#info{position:absolute;top:8px;left:10px;font-size:12px;opacity:.85;pointer-events:none}
canvas{display:block;width:100%;height:100%}
</style></head><body>
<div id="info">__HINT__</div>
<script>
const SIZE=__SIZE__;
const LEVELS=__LEVELS__;
const RAW="__B64__";
const HEIGHTS=Uint8Array.from(atob(RAW),c=>c.charCodeAt(0));

const canvas=document.createElement('canvas');
document.body.appendChild(canvas);
const gl=canvas.getContext('webgl')||canvas.getContext('experimental-webgl');
if(!gl){document.body.innerHTML='<div style="padding:20px">__GLFAIL__</div>';throw new Error('webgl unavailable');}
gl.getExtension('OES_element_index_uint');

const vs=`
attribute vec3 aPos; attribute vec3 aCol;
uniform mat4 uMvp; varying vec3 vCol;
void main(){gl_Position=uMvp*vec4(aPos,1.0); vCol=aCol;}`;
const fs=`precision mediump float; varying vec3 vCol;
void main(){gl_FragColor=vec4(vCol,1.0);}`;

function compile(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);return s;}
const prog=gl.createProgram();
gl.attachShader(prog,compile(gl.VERTEX_SHADER,vs));
gl.attachShader(prog,compile(gl.FRAGMENT_SHADER,fs));
gl.linkProgram(prog);gl.useProgram(prog);

// ---- 体素柱几何：每柱一个顶面，仅当邻居更低时补阶梯侧面（Minecraft 方块风） ----
function hColor(v){
  if(v<0.32)return [0.21,0.43,0.71];
  if(v<0.38)return [0.91,0.82,0.55];
  if(v<0.62){const t=(v-0.38)/0.24;return [0.34-t*0.08,0.55+t*0.12,0.27-t*0.04];}
  if(v<0.80){const t=(v-0.62)/0.18;return [0.47+t*0.12,0.39+t*0.12,0.27+t*0.04];}
  const t=Math.min(1,(v-0.80)/0.20);return [0.78+t*0.22,0.78+t*0.22,0.82+t*0.18];
}
const SEA=Math.max(1,Math.round(LEVELS*0.35));   // 海平面（对应约 62 格）
const U=0.9/LEVELS;                              // 每层的世界高度
const CELL=2/SIZE;                               // 每格（1 像素）的世界宽度
const H=new Int16Array(SIZE*SIZE);
for(let z=0;z<SIZE;z++){
  for(let x=0;x<SIZE;x++){
    const v=HEIGHTS[z*SIZE+x]/255;
    H[z*SIZE+x]=(v<0.35)?SEA:Math.max(SEA,Math.round(v*LEVELS));  // 海洋压平到海平面
  }
}
// 尺寸很大时按步长降采样，避免顶点数量过多拖垮显卡
const STEP=Math.max(1,Math.ceil(SIZE/512));
const N=Math.ceil(SIZE/STEP);
const RH=new Int16Array(N*N);
const HC=new Float64Array(N*N);
for(let r=0;r<N;r++){
  for(let c=0;c<N;c++){
    const z=Math.min(SIZE-1,r*STEP),x=Math.min(SIZE-1,c*STEP);
    RH[r*N+c]=H[z*SIZE+x];
    HC[r*N+c]=HEIGHTS[z*SIZE+x]/255;
  }
}
function hAt(x,z){return (x<0||z<0||x>=N||z>=N)?0:RH[z*N+x];}

const positions=[];const colors=[];const indices=[];
function quad(p1,p2,p3,p4,c){
  const base=positions.length/3;
  positions.push(p1[0],p1[1],p1[2],p2[0],p2[1],p2[2],p3[0],p3[1],p3[2],p4[0],p4[1],p4[2]);
  for(let i=0;i<4;i++)colors.push(c[0],c[1],c[2]);
  indices.push(base,base+1,base+2,base,base+2,base+3);
}
const W=CELL*STEP;                               // 降采样后每列的世界宽度
for(let z=0;z<N;z++){
  for(let x=0;x<N;x++){
    const h=RH[z*N+x];if(h<=0)continue;
    const x0=(x-N/2)*W,x1=x0+W;
    const z0=(z-N/2)*W,z1=z0+W;
    const yt=h*U;
    const c=hColor(HC[z*N+x]);
    const cx=[c[0]*0.60,c[1]*0.60,c[2]*0.60];   // x 向侧面压暗
    const cz=[c[0]*0.78,c[1]*0.78,c[2]*0.78];   // z 向侧面压暗
    quad([x0,yt,z0],[x0,yt,z1],[x1,yt,z1],[x1,yt,z0],c);                       // 顶面
    const s0=hAt(x,z+1)*U; if(s0<yt)quad([x0,yt,z1],[x0,s0,z1],[x1,s0,z1],[x1,yt,z1],cz); // +z
    const s1=hAt(x,z-1)*U; if(s1<yt)quad([x1,yt,z0],[x1,s1,z0],[x0,s1,z0],[x0,yt,z0],cz); // -z
    const s2=hAt(x+1,z)*U; if(s2<yt)quad([x1,yt,z1],[x1,s2,z1],[x1,s2,z0],[x1,yt,z0],cx); // +x
    const s3=hAt(x-1,z)*U; if(s3<yt)quad([x0,yt,z0],[x0,s3,z0],[x0,s3,z1],[x0,yt,z1],cx); // -x
  }
}
const pBuf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pBuf);
gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(positions),gl.STATIC_DRAW);
const aPos=gl.getAttribLocation(prog,'aPos');
gl.enableVertexAttribArray(aPos);gl.vertexAttribPointer(aPos,3,gl.FLOAT,false,0,0);
const cBuf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,cBuf);
gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(colors),gl.STATIC_DRAW);
const aCol=gl.getAttribLocation(prog,'aCol');
gl.enableVertexAttribArray(aCol);gl.vertexAttribPointer(aCol,3,gl.FLOAT,false,0,0);
const iBuf=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,iBuf);
const idxCount=indices.length;
gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(indices),gl.STATIC_DRAW);

const uMvp=gl.getUniformLocation(prog,'uMvp');

// 简易矩阵工具
function mat4Multiply(a,b){
  const o=new Array(16);
  for(let r=0;r<4;r++)for(let c=0;c<4;c++){
    o[c*4+r]=a[0*4+r]*b[c*4+0]+a[1*4+r]*b[c*4+1]+a[2*4+r]*b[c*4+2]+a[3*4+r]*b[c*4+3];
  }
  return o;
}
function mat4Perspective(fov,aspect,near,far){
  const f=1/Math.tan(fov/2);const nf=1/(near-far);
  return [f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0];
}
function mat4LookAt(eye,target,up){
  const z0=eye[0]-target[0],z1=eye[1]-target[1],z2=eye[2]-target[2];
  let len=Math.hypot(z0,z1,z2);const z=[z0/len,z1/len,z2/len];
  const x0=up[1]*z[2]-up[2]*z[1],x1=up[2]*z[0]-up[0]*z[2],x2=up[0]*z[1]-up[1]*z[0];
  len=Math.hypot(x0,x1,x2);const x=[x0/len,x1/len,x2/len];
  const y=[z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]];
  return [x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,
    -(x[0]*eye[0]+x[1]*eye[1]+x[2]*eye[2]),
    -(y[0]*eye[0]+y[1]*eye[1]+y[2]*eye[2]),
    -(z[0]*eye[0]+z[1]*eye[1]+z[2]*eye[2]),1];
}

let rotY=0.6,rotX=0.5,dist=2.6,panX=0,panY=0,autoRot=false;
// 供启动器按钮调用的交互 API（不依赖鼠标）
window.mikanRotate=function(dx,dy){rotY+=dx;rotX=Math.max(-1.2,Math.min(1.2,rotX+dy));};
window.mikanZoom=function(f){dist=Math.max(1.0,Math.min(8,dist*f));};
window.mikanPan=function(dx,dy){panX+=dx;panY+=dy;};
window.mikanReset=function(){rotY=0.6;rotX=0.5;dist=2.6;panX=0;panY=0;};
window.mikanAuto=function(b){autoRot=!!b;};

let dragging=false,lastX=0,lastY=0,button=0;
canvas.addEventListener('mousedown',e=>{dragging=true;lastX=e.clientX;lastY=e.clientY;button=e.button;});
window.addEventListener('mouseup',()=>dragging=false);
window.addEventListener('mousemove',e=>{
  if(!dragging)return;
  const dx=e.clientX-lastX,dy=e.clientY-lastY;lastX=e.clientX;lastY=e.clientY;
  if(button===2){panX+=dx*0.002;panY-=dy*0.002;}
  else{rotY+=dx*0.01;rotX+=dy*0.01;rotX=Math.max(-1.2,Math.min(1.2,rotX));}
});
canvas.addEventListener('wheel',e=>{e.preventDefault();mikanZoom(e.deltaY>0?1.1:0.9);},{passive:false});
canvas.addEventListener('contextmenu',e=>e.preventDefault());
canvas.addEventListener('dblclick',()=>mikanReset());

function resize(){
  const dpr=window.devicePixelRatio||1;
  canvas.width=canvas.clientWidth*dpr;canvas.height=canvas.clientHeight*dpr;
  gl.viewport(0,0,canvas.width,canvas.height);
}
window.addEventListener('resize',resize);resize();

function draw(){
  if(autoRot)rotY+=0.004;
  gl.clearColor(0.12,0.12,0.14,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  gl.enable(gl.DEPTH_TEST);
  const aspect=canvas.width/Math.max(1,canvas.height);
  const proj=mat4Perspective(0.9,aspect,0.01,100);
  const eye=[Math.sin(rotY)*Math.cos(rotX)*dist+panX,Math.sin(rotX)*dist+0.4+panY,Math.cos(rotY)*Math.cos(rotX)*dist];
  const view=mat4LookAt(eye,[panX,panY,0],[0,1,0]);
  const mvp=mat4Multiply(proj,view);
  gl.uniformMatrix4fv(uMvp,false,new Float32Array(mvp));
  gl.drawElements(gl.TRIANGLES,idxCount,gl.UNSIGNED_INT,0);
  requestAnimationFrame(draw);
}
draw();
</script></body></html>
"""


class TerrainWorker(QThread):
    """在后台线程调用 Java 生成高度图，避免阻塞界面。"""

    done = Signal(bytes, int)
    failed = Signal(str)

    def __init__(self, ctx, seed: int, size: int, mode: int, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.seed = seed
        self.size = size
        self.mode = mode

    def run(self) -> None:  # noqa: D401
        try:
            data = generate_heightmap_java(
                self.seed,
                size=self.size,
                mode=self.mode,
                ctx=self.ctx,
                java_path=str(getattr(self.ctx.config, "java_path", "") or ""),
            )
            self.done.emit(data, self.size)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class SeedTerrainPage(QWidget):
    # 尺寸数字不设上限，但超过这个边长后 Java 内存与渲染开销都不可控，生成前拦截
    _max_pixels = 4096

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._web = None
        self._fallback_label: QLabel | None = None
        self._last_data: bytes | None = None
        self._last_size = 256
        self._worker: TerrainWorker | None = None
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(16)
        header, _ = page_header(
            self.tr("世界种子"),
            self.tr("输入种子，启动器调用本机 Java（与 Minecraft 相同的柏林噪声算法与参数）"
                   "生成出生点附近的 3D 地形，无需进入游戏"),
        )
        outer.addWidget(header)

        body = QVBoxLayout()
        body.setSpacing(12)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        ctrl.addWidget(QLabel(self.tr("种子")))
        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText(self.tr("可填数字或任意文本，留空随机"))
        ctrl.addWidget(self.seed_edit, 1)
        ctrl.addWidget(QLabel(self.tr("尺寸")))
        self.size_spin = QSpinBox()
        # 默认 256×256（生存范围）；数字不设上限，面积越大生成越久
        self.size_spin.setRange(32, 2147483647)
        self.size_spin.setSingleStep(32)
        self.size_spin.setValue(256)
        self.size_spin.setToolTip(self.tr("尺寸越大，生成越久"))
        ctrl.addWidget(self.size_spin)
        ctrl.addWidget(QLabel(self.tr("噪声版本")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self.tr("经典（1.7–1.17）"), 0)
        self.mode_combo.addItem(self.tr("新版（1.18+）"), 1)
        ctrl.addWidget(self.mode_combo)
        self.gen_btn = QPushButton(self.tr("生成地形"))
        self.gen_btn.setObjectName("Primary")
        self.gen_btn.clicked.connect(self._generate)
        ctrl.addWidget(self.gen_btn)
        export_btn = QPushButton(self.tr("导出高度图 PNG"))
        export_btn.clicked.connect(self._export_png)
        ctrl.addWidget(export_btn)
        body.addLayout(ctrl)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        body.addWidget(self.progress)

        if _HAS_WEBENGINE:
            self._web = QWebEngineView()
            self._web.setMinimumHeight(420)
            body.addWidget(self._web, 1)
            body.addLayout(self._build_view_bar())
        else:
            self._fallback_label = QLabel(self.tr("当前环境未启用 QtWebEngine，将以 2D 高度图预览。"))
            self._fallback_label.setAlignment(Qt.AlignCenter)
            self._fallback_label.setMinimumHeight(420)
            body.addWidget(self._fallback_label, 1)

        tip = QLabel(
            self.tr(
                "说明：高度图由启动器调用本机 Java 运行时（内嵌 TerrainGen 程序）计算。"
                "「经典」使用 1.7–1.17 的 ImprovedNoise（256 置换表 + 16 向梯度表）"
                "与 8 层 octave 叠加（频率 ×2、振幅 ×0.5）；「新版」使用 1.18 起的 "
                "Xoroshiro128++ 随机源与气候噪声（大陆性 / 侵蚀度 / 奇异度）。"
                "两种模式的噪声参数均为原版固定值，不提供起伏等可调项；但不含生物群系、"
                "地形样条与密度函数，仍属非官方地形示意，仅供挑选种子时参考，"
                "与游戏内实际地形可能存在差异。"
            )
        )
        tip.setObjectName("Tiny")
        tip.setWordWrap(True)
        body.addWidget(tip)

        outer.addLayout(body, 1)

    # ------------------------------------------------------------------
    def _build_view_bar(self) -> QHBoxLayout:
        """3D 视图的交互按钮栏：不用鼠标也能旋转 / 缩放 / 平移 / 复位。"""
        bar = QHBoxLayout()
        bar.setSpacing(4)

        def _btn(text: str, script: str, tip: str = "") -> QPushButton:
            b = QPushButton(text)
            b.setObjectName("GhostCompact")
            b.setFixedHeight(28)
            b.setMinimumWidth(30)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(lambda _=False, s=script: self._js(s))
            return b

        bar.addWidget(QLabel(self.tr("视角")))
        bar.addWidget(_btn("◀", "mikanRotate(-0.26,0)", self.tr("向左旋转")))
        bar.addWidget(_btn("▶", "mikanRotate(0.26,0)", self.tr("向右旋转")))
        bar.addWidget(_btn("▲", "mikanRotate(0,0.15)", self.tr("抬高视角")))
        bar.addWidget(_btn("▼", "mikanRotate(0,-0.15)", self.tr("压低视角")))
        bar.addSpacing(10)
        bar.addWidget(QLabel(self.tr("缩放")))
        bar.addWidget(_btn("＋", "mikanZoom(0.85)", self.tr("放大")))
        bar.addWidget(_btn("－", "mikanZoom(1.18)", self.tr("缩小")))
        bar.addSpacing(10)
        bar.addWidget(QLabel(self.tr("平移")))
        bar.addWidget(_btn("←", "mikanPan(-0.15,0)"))
        bar.addWidget(_btn("→", "mikanPan(0.15,0)"))
        bar.addWidget(_btn("↑", "mikanPan(0,0.15)"))
        bar.addWidget(_btn("↓", "mikanPan(0,-0.15)"))
        bar.addSpacing(10)
        reset_btn = QPushButton(self.tr("复位视角"))
        reset_btn.setObjectName("GhostCompact")
        reset_btn.setFixedHeight(28)
        reset_btn.clicked.connect(lambda: self._js("mikanReset()"))
        bar.addWidget(reset_btn)
        auto_box = QCheckBox(self.tr("自动旋转"))
        auto_box.toggled.connect(lambda on: self._js(f"mikanAuto({'true' if on else 'false'})"))
        bar.addWidget(auto_box)
        bar.addStretch(1)
        return bar

    def _js(self, script: str) -> None:
        """在 3D 视图中执行脚本；无 WebEngine 时静默忽略。"""
        if _HAS_WEBENGINE and self._web is not None:
            try:
                self._web.page().runJavaScript(script)
            except Exception:
                pass

    def _seed_to_int(self, text: str) -> int:
        text = (text or "").strip()
        if not text:
            return int(time.time() * 1000) & 0x7FFFFFFFFFFFFFFF
        try:
            # 种子是 64 位有符号整数，位数不设上限
            value = int(text)
        except ValueError:
            # 文本种子按 Minecraft 的习惯取 Java String.hashCode()（32 位有符号）
            hashed = 0
            for ch in text:
                hashed = (hashed * 31 + ord(ch)) & 0xFFFFFFFF
            if hashed >= 0x80000000:
                hashed -= 0x100000000
            return hashed
        return max(-(1 << 63), min((1 << 63) - 1, value))

    def _generate(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        size = int(self.size_spin.value())
        if size > self._max_pixels:
            QMessageBox.warning(
                self,
                APP_NAME,
                self.tr("尺寸过大，最多支持 {0}×{0}，请调小后再生成。").format(
                    self._max_pixels
                ),
            )
            return
        seed = self._seed_to_int(self.seed_edit.text())
        self.seed_edit.setText(str(seed))
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.gen_btn.setEnabled(False)

        worker = TerrainWorker(
            self.ctx, seed, size, int(self.mode_combo.currentData()), self
        )
        worker.done.connect(self._on_terrain_ready)
        worker.failed.connect(self._on_terrain_failed)
        worker.finished.connect(lambda w=worker: self._release_worker(w))
        self._worker = worker
        worker.start()

    def _on_terrain_ready(self, data: bytes, size: int) -> None:
        self._last_data = data
        self._last_size = size
        if _HAS_WEBENGINE and self._web is not None:
            b64 = base64.b64encode(data).decode("ascii")
            html = (
                _HTML_TEMPLATE.replace("__SIZE__", str(size))
                .replace("__LEVELS__", "16")
                .replace("__HINT__", self.tr("按钮或拖动旋转 · 滚轮缩放 · 右键平移 · 双击复位"))
                .replace("__GLFAIL__", self.tr("WebGL 不可用"))
                .replace("__B64__", b64)
            )
            self._web.setHtml(html, baseUrl=DATA_DIR.as_uri())
        elif self._fallback_label is not None:
            png = terrain_dir() / "heightmap.png"
            if png.exists():
                pix = QPixmap(str(png)).scaledToWidth(max(320, size * 4))
                self._fallback_label.setPixmap(pix)
                self._fallback_label.setText("")
        self._finish_progress()

    def _on_terrain_failed(self, message: str) -> None:
        self._finish_progress()
        QMessageBox.warning(self, self.tr("地形生成失败"), message)

    def _finish_progress(self) -> None:
        self.progress.setVisible(False)
        self.gen_btn.setEnabled(True)

    def _release_worker(self, worker: QThread) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def _export_png(self) -> None:
        png = terrain_dir() / "heightmap.png"
        if self._last_data is None or not png.exists():
            QMessageBox.information(self, APP_NAME, self.tr("请先生成一次地形。"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("导出高度图"), str(Path.home() / "terrain.png"), "PNG 图片 (*.png)"
        )
        if not path:
            return
        try:
            shutil.copyfile(png, path)
        except OSError:
            QMessageBox.warning(self, APP_NAME, self.tr("保存失败。"))

    def shutdown(self) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(3000)
        if self._web is not None:
            try:
                self._web.setHtml("")
            except Exception:
                pass


__all__ = ["SeedTerrainPage"]
