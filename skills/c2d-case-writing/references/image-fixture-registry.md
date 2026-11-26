# 图片素材登记表（image-fixture-registry）

> **真实图片链接的单一来源。** 用例正文里的图片链接只能取自本表，或按本表「自备规范」新增槽位并回填。
> 禁止在用例里临时编 URL、用占位符、或引用本地路径——那会让用例在别人机器上直接失效。

## 一、已实测的固定槽位（2026-11-26 核验）

全部为**图片直链**，无需登录、无防盗链，可直接写进用例与被测系统。实测结果见末列。

| 槽位 | 直链 | 格式 | 尺寸 | 体积 | 实测 |
|---|---|---|---|---|---|
| `FIX-1X1` | `https://picsum.photos/1/1` | jpeg | 1×1 | 726B | 200 image/jpeg |
| `FIX-SQUARE` | `https://picsum.photos/id/1015/300/300` | jpeg | 300×300 | 19KB | 200 image/jpeg |
| `FIX-3X1` | `https://picsum.photos/id/1015/1200/400` | jpeg | 1200×400 | 103KB | 200 image/jpeg |
| `FIX-ULTRAWIDE` | `https://picsum.photos/id/1015/3000/10` | jpeg | 3000×10 | 9.8KB | 200 image/jpeg |
| `FIX-HUGE` | `https://picsum.photos/id/1025/4096/4096` | jpeg | 4096×4096 | 2.6MB | 200 image/jpeg |
| `FIX-WEBP` | `https://picsum.photos/seed/c2d/100/100.webp` | webp | 100×100 | 2.9KB | 200 image/webp |
| `FIX-PNG` | `https://placehold.co/600x400.png` | png | 600×400 | 7.3KB | 200 image/png |
| `FIX-WEBP-MIN` | `https://placehold.co/100x100.webp` | webp | 100×100 | 318B | 200 image/webp |
| `FIX-SVG` | `https://placehold.co/200x200.svg` | svg | 200×200 | 3.2KB | 200 image/svg+xml |
| `FIX-ALPHA` | `https://placehold.co/100x100/transparent/000.png` | png | 100×100 | 795B | 200，带透明通道 |
| `FIX-SOLID-BLACK` | `https://placehold.co/400x300/000000/FFFFFF.png` | png | 400×300 | 6.1KB | 200，纯黑底白字 |
| `FIX-BROKEN-404` | `https://picsum.photos/id/99999/300/300` | — | — | 21B | **404 text/plain** |
| `FIX-BROKEN-HTML` | `https://placehold.co/abc.png` | — | — | 724B | **404 text/html** |

三条使用纪律：

1. **`picsum.photos` 会 302 跳转到 `fastly.picsum.photos/...?hmac=...`**——校验链接时必须跟随重定向（`curl -L` / `urllib` 默认行为），但用例里**只写 `picsum.photos` 原 URL**，不要写跳转后带签名的地址（签名会变，写死就失效）。
2. `FIX-BROKEN-*` 两个槽位是**故意失败**的样本，用于「加载失败回退」场景。引用它们的用例必须在「被测图片」段写 `expect_status: 404`，否则闸门会把它判成坏链。
3. 同一张图跨用例复用没问题，但**同一场景组内不要全用同一张图**——测不出差异（闸门对"单图复用 >3 次"给告警）。

## 二、自备槽位规范（缺特征时新增）

现有 13 个槽位覆盖不到的特征（特定裁切位置、特定文字、指定色值、带方向的主体、内网可访问等），按以下规范新增：

- **命名**：`FIX-{特征}` 全大写连字符，如 `FIX-FACE-CENTER`、`FIX-QUADRANT`、`FIX-CJK-FILENAME`
- **必填四要素**：直链 / 格式 / 尺寸 / **能触发什么规则**（写明对应 `IMG-*` 编号）
- **存放**：优先项目图床或 OSS 长期直链；公网不稳定时用公司 CDN。**不得用临时签名 URL**（过期即失效）
- **回填**：新增后立刻补进本表并重跑 `scripts/check_image_links.py` 核验，实测通过才算登记

需要特定内容图的场景（如「四象限不同色块」用于判断裁错位置），推荐自己用 SVG 生成再上传——比找图快且特征精确：

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">
  <rect width="200" height="200" fill="#E24B4A"/><rect x="200" width="200" height="200" fill="#1D9E75"/>
  <rect y="200" width="200" height="200" fill="#378ADD"/><rect x="200" y="200" width="200" height="200" fill="#EF9F27"/>
</svg>
```

## 三、待补槽位（本项目多半需要，先标 TODO）

| 需要的能力 | 缺什么槽位 | 补齐方式 |
|---|---|---|
| 判断裁剪焦点是否正确 | `FIX-FACE-OFFCENTER`（主体明显偏一侧的人像） | 自备并上传 |
| 观察旋转是否失真 | `FIX-GRID`（网格线或直角框） | 用上节 SVG 生成 |
| 中文/空格文件名 | `FIX-CJK-FILENAME`（文件名含中文与空格） | 项目图床自建目录 |
| 防盗链拒绝 | `FIX-HOTLINK-BLOCKED`（限制 Referer 的图） | 需运维配一条规则 |
| 内网被测环境可访问 | `FIX-INTRA-*` | TODO：向运维索取内网图床地址与访问方式 |

## 四、链接核验

```bash
python3 <skill目录>/scripts/check_image_links.py 测试用例_C2D图片_markmap.md
```

输出每条链接的 `状态码 / Content-Type / 体积 / 判定`，异常项退出码 1。定稿前必跑；产品代码里生成的图片链接同理，可把生成的 HTML 路径一并传入。
