# 第三方资源与授权

## 环境光 HDRI（`assets/`）

三张 1K HDR 环境贴图，均来自 **PolyHaven**，授权为 **CC0（公共领域）**，
可商用、可再分发、无需署名（此处仍列出以示来源）。

| 文件 | PolyHaven 资源 | 授权 | 用途 |
|---|---|---|---|
| `neon_photostudio_1k.hdr` | Neon Photostudio | CC0 | 展示片主光（霓虹影棚） |
| `studio_small_09_1k.hdr` | Studio Small 09 | CC0 | 备选影棚光 |
| `brown_photostudio_02_1k.hdr` | Brown Photostudio 02 | CC0 | 备选暖调影棚光 |

下载地址格式：`https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/<name>_1k.hdr`
PolyHaven 授权说明：<https://polyhaven.com/license>

## 模型与代码

- `src/` 下全部生成器代码、`chibi_maid_USER.blend` 模型、`renders/` 下的渲染与视频，
  均为本项目原创产出（详见仓库根 `LICENSE`）。
- **未使用**任何第三方模型、贴图、材质库或扫描资产；角色几何 100% 由代码计算。

## 角色设定

角色外形参考自用户提供的 7 张设定图。**该参考图不在本仓库内**，
其版权归原插画作者所有；本仓库仅包含依据其比例与结构重新程序化建模的结果。

## 工具链

| 工具 | 版本 | 用途 |
|---|---|---|
| Blender | 5.2 LTS | 建模 / 渲染（EEVEE） |
| Python | 3.13（Blender 内置） | 生成脚本 |
| ffmpeg | 任意近期版本 | 视频编码 / 字幕烧入 |
