# 布局与解析规则

## 一、解析 .vsdx

`.vsdx` 就是 zip 包（OOXML）。解压后关键文件：

```
visio/pages/pages.xml              页签列表（Page 的 Name / NameU）
visio/pages/_rels/pages.xml.rels   Page ID → pageN.xml 的映射
visio/pages/pageN.xml              形状、文本、连线、连接关系
visio/masters/masters.xml          母版（判断形状类型的最佳依据）
visio/masters/masterN.xml
```

提取要点：

| 要什么 | 在哪 | 注意 |
|---|---|---|
| 形状文本 | `Shape/Text` 的 itertext | 可能被拆成多个 `TextRun`，要拼接 |
| 位置坐标 | `Shape/Cell[@N='PinX'/'PinY'/'Width'/'Height']` 的 `V` | 单位是英寸，×96 转像素 |
| 形状类型 | `Shape/@Master` → 查 masters.xml 的 `NameU` | 母版名常含 Decision/Process/Start |
| 连线拓扑 | `Connects/Connect[@FromSheet][@ToSheet]` | 连线上也有 `BeginX`，两个都要 |
| 连线标签 | 连线自己的 `Text` | 是/否、外协/自制就在这里 |

跑 `scripts/parse_vsdx.py <file.vsdx> [页码]` 会输出 JSON，含 shapes / edges / texts 三块。

**多页文件**：先列出所有页名让用户选。经验上"优化版/最新版"页结构最完整，但不要替用户决定。

**坐标系**：Visio 的 PinX/PinY 是形状中心点，y 轴向上；HTML 的 y 轴向下。转换 `y_html = maxY - y_visio`。

## 二、栅格参数

泳道纵向分段、阶段列表横向，参数如下（单位 px，画布逻辑坐标）：

| 项 | 值 | 说明 |
|---|---|---|
| 节点宽 | 206 | 中文 12.5px 约 14 字/行 |
| 节点高（作业） | 56 | 两行文字 |
| 节点高（判断） | 96 | 约 1.7 倍，菱形内接矩形小 |
| 同行节点间距 | 40 | 连线标签有地方站 |
| 相邻步骤纵向间距 | 84 | 节点高 56 + 空隙 28 |
| 泳道宽 | 340 / 420 / 400 | 按该泳道节点数分配，最少 300 |
| 泳道间隙 | 0 | 相邻泳道用不同底色区分，不留缝 |
| 阶段区间顶部留白 | 60 | 阶段标题位置 |
| 阶段之间的间隔 | 70 | 阶段色带切换处 |

## 三、排布原则

1. **主路径一列**：一条主流程在同一条竖直线上，从上往下。分支节点向右（或左）展开成一个新的列。
2. **判断节点的两条出口**：向下（主路径/是）、向右（分支/否），标签贴在出口 1/3 处。
3. **跨泳道不斜插**：跨泳道连线只走水平 + 垂直，用圆角折线，不用斜线。
4. **同列节点对齐**：同一列的节点 x 必须完全相等，靠右对齐的列取同一条基准线，视觉上才整齐。
5. **不让连线穿过节点**：排完后看每条线是否压到任何节点矩形，压到就调整 y 间距或把节点右移一列。

## 四、连线路径算法

三种情况，按 dx / dy 大小判断：

```js
const dx = b.x - a.x, dy = b.y - a.y;

// 1) 上下（|dx| < 30）：直线 + 轻微弯曲
if (Math.abs(dx) < 30) {
  const y1 = a.y + a.h/2, y2 = b.y - b.h/2;
  return `M${a.x},${y1} C${a.x},${y1 + (y2-y1)*0.45} ${b.x},${y2 - (y2-y1)*0.45} ${b.x},${y2}`;
}

// 2) 左右（|dy| < 20）：水平 S 曲线
if (Math.abs(dy) < 20) {
  const x1 = a.x + a.w/2*Math.sign(dx), x2 = b.x - b.w/2*Math.sign(dx);
  return `M${x1},${a.y} C${x1 + (x2-x1)*0.45},${a.y} ${x2 - (x2-x1)*0.45},${b.y} ${x2},${b.y}`;
}

// 3) 斜向：先下后横再下的圆角折线
const y1 = a.y + a.h/2, ym = y1 + 26;
return `M${a.x},${y1} L${a.x},${ym-8} Q${a.x},${ym} ${a.x+8},${ym} L${b.x-8},${ym} Q${b.x},${ym} ${b.x},${ym+8} L${b.x},${b.y - b.h/2}`;
```

箭头用 `<marker>`，颜色需要跟随状态时**每种颜色注册一个 marker**（`ar` / `ar-hot` / `ar-live`），运行时切换 `marker-end`，不要试图给 marker 上 CSS 变量（多数浏览器不生效）。

## 五、缩放平移

- 变换只作用在一个 `#stage` 层：`translate(x,y) scale(s)`，DOM 节点与 SVG 在同一层，天然同步
- 滚轮缩放以鼠标位置为锚点：`x = mx - (mx - x) * (s2/s1)`
- 「适应窗口」要预留顶部冻结条高度（约 34px），否则内容和冻结条重叠
- 节点拖拽时除以 `view.s` 换算回逻辑坐标
