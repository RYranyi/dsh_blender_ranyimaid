# dsh_blender_ranyimaid · Q 版小女仆（全程序化 3D 模型）

> 从空场景出发，用 Python 在 Blender 5.2 里**一行一行算出**一个高精度 Q 版女仆：
> 没有导入任何模型、贴图或资产，全部几何 / 材质 / 灯光 / 相机由代码生成。

| 全身 | 面部 | 背面 | 俯视 | 仰视 |
|:--:|:--:|:--:|:--:|:--:|
| ![全身](https://gh-proxy.com/https://raw.githubusercontent.com/RYranyi/dsh_blender_ranyimaid/main/renders/preview/01_full_body.png) | ![面部](https://gh-proxy.com/https://raw.githubusercontent.com/RYranyi/dsh_blender_ranyimaid/main/renders/preview/02_face.png) | ![背面](https://gh-proxy.com/https://raw.githubusercontent.com/RYranyi/dsh_blender_ranyimaid/main/renders/preview/03_back.png) | ![俯视](https://gh-proxy.com/https://raw.githubusercontent.com/RYranyi/dsh_blender_ranyimaid/main/renders/preview/04_top_view.png) | ![仰视](https://gh-proxy.com/https://raw.githubusercontent.com/RYranyi/dsh_blender_ranyimaid/main/renders/preview/05_low_view.png) |

> 预览图经 `gh-proxy.com` 镜像加载：GitHub 会把外链图片转由 `camo.githubusercontent.com` 在服务端抓取，因此本地即使无法直连 `raw.githubusercontent.com` 也能正常显示。直链：`renders/preview/`。

- 🎬 **成品视频**：[`renders/maid_intro_60s.mp4`](renders/maid_intro_60s.mp4) — 1280×720 / 24fps / 60s / 中文字幕
- 🧍 **模型工程**：[`chibi_maid_USER.blend`](chibi_maid_USER.blend) — Blender 5.2 直接打开
- 🧩 **生成源码**：[`src/`](src/) — 可一键重建整个模型

---

## 1. 成品规格

| 项目 | 数值 |
|---|---|
| 总高 | 1.00 m（Q 版手办比例） |
| 头身比 | 头高占 **39.5%**，头宽 **46.3%** H |
| 网格 | **≈ 74 万面 / 74 万顶点** |
| 材质 | 17 套全程序化材质（零贴图） |
| 朝向 | 面朝 **−Y**，Z 向上，脚底 z = 0 |
| 渲染 | EEVEE，色彩管理 Standard |

## 2. 一分钟展示片

成片结构（远 → 近 → 远，15 个机位）：

```
0-5s    全身远景        5-9.5s   全身 3/4
9.5-13s 上半身          13-17s   面部特写 90mm
17-20s  领子 + 肩荷叶边  20-24s   泡泡袖 + 袖口
24-28s  围裙 + 荷叶边    28-32s   裙摆 + 内衬
32-36s  袜子 + 乐福鞋    36-40s   背带 + 蝴蝶结
40-44s  全身正背        44-49s   俯视（+55°）
49-53s  仰视（−18°）    53-57s   全身回扫
57-60s  收尾拉远
```

光影：PolyHaven **CC0** 霓虹影棚 HDRI + 金属展台 + 青色发光环 + 双色灯条。
字幕源：[`subtitles.ass`](subtitles.ass)（改文案不必重渲，用 ffmpeg 重烧即可）。

## 3. 目录结构

```
.
├─ chibi_maid_USER.blend      # 模型工程（成品）
├─ renders/
│   └─ maid_intro_60s.mp4     # 一分钟展示片
├─ subtitles.ass              # 字幕（ASS，可重烧）
├─ assets/                    # CC0 HDRI 环境光（见 docs/03-assets.md）
├─ src/                       # 生成器源码
│   ├─ build.py               # 装配入口：拼装 + 打灯 + 出图 + 存盘
│   ├─ mprop.py               # 比例与配色常量（唯一数值源头）
│   ├─ mhead.py               # 头部：超椭圆头形 + 五官贴面 + 眼睛堆栈
│   ├─ mhair.py               # 头发：发帽 + 整片刘海 + 鬓角
│   ├─ mbody.py               # 身体：躯干 / 四肢 / 手 / 脚（含脚趾）
│   ├─ mcloth.py              # 服装：裙 / 领 / 袖 / 围裙 / 内裤 / 袜 / 鞋 / 头饰
│   ├─ mmat.py                # 材质工厂
│   ├─ mcore.py               # 几何基元与渲染工具
│   └─ lib/                   # 独立模块（荷叶边 / 蝴蝶结 / 鞋 / 手）
└─ docs/
    ├─ 01-modeling.md         # 完整建模流程（含算法与坑）
    ├─ 02-requirements.md     # 需求演进（关键提示词整合）
    └─ 03-assets.md           # 第三方资源与授权
```

## 4. 重建

```bash
# 完整重建（生成 + 出图 + 存盘）
blender -b --factory-startup --python src/build.py

# 只生成不渲染
MAID_RENDER=0 blender -b --factory-startup --python src/build.py

# 出特写
MAID_VIEWS=close MAID_RES=760 MAID_SAMPLES=64 blender -b --python src/build.py
```

环境变量：`MAID_RENDER` / `MAID_RES` / `MAID_SAMPLES` / `MAID_VIEWS=body|close`。

> ⚠️ `build.py` 是**从零重建**，会覆盖 `chibi_maid.blend`。若在成品上手工微调过，
> 请勿直接重建；应改为「打开既有 .blend → 只改目标物体 → 存回」的增量流程。

## 5. 设计要点（详见 docs/01-modeling.md）

- **头**：超椭圆截面放样（前脸 flattening q≈4.2），五官贴面用解析曲面 `face_y(x,z)` 共形。
- **眼**：虹膜用**逐顶点颜色渐变**（无 UV / 无贴图），厚上睫 + 外挑 + 双高光 + 眼角红。
- **发**：发帽 + **一整片**连续刘海（不是碎发片）+ 鬓角，发梢收尖。
- **衣**：围裙是**一张连续曲面**（胸片→腰带→裙摆）再与肩带合并为单物体。
- **袜**：袜子 = 腿/脚表面偏移壳，脚部 +2 mm、小腿 +5 mm，杜绝穿模。
- **鞋**：乐福鞋程序化鞋楦，鞋口前缘抬高包住脚背。

## 6. 已知不足

1. 头发是壳片 + 圆角，未做发丝级（hair curves）细节。
2. 布料褶皱是数学调制，非布料解算。
3. 手部近看指节偏软。
4. 面部细节靠几何 + 顶点色，未做贴图级绘制。

## 7. 授权

- **源代码**（`src/`）：**MIT** — 见 [`LICENSE`](LICENSE)
- **模型与渲染素材**（`.blend`、`renders/`）：**CC BY 4.0** — 保留署名即可商用
- **HDRI**（`assets/`）：**CC0**，来自 PolyHaven，来源见 [`docs/03-assets.md`](docs/03-assets.md)
- 角色设定参考图版权归原作者，**本仓库不含该参考图**

## 8. 仓库信息

| 项 | 值 |
|---|---|
| 建议仓库名 | `dsh_blender_ranyimaid` |
| 建议 topics | `blender` `procedural-modeling` `python` `eevee` `chibi` `3d-character` |
| 建议简介 | 全程序化 Q 版女仆 3D 模型 · Blender 5.2 + Python，零外部资产 |
