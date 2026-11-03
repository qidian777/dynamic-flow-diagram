# 交互清单与实现要点

## 一、必备交互（缺一个都会被打回）

| 交互 | 触发 | 行为 | 备注 |
|---|---|---|---|
| 阶段筛选 | 顶部标签 | 聚焦一个阶段，其余淡出（opacity .14） | 淡出不是隐藏，保留全局方位感 |
| 按岗位筛选 | 侧栏切换 | 非该岗位节点与连线淡出 | 讲"某个人要做什么"时唯一有效手段 |
| 悬停说明 | 鼠标悬停节点 | 气泡显示编号/岗位/系统/一句话说明 | **必须放左右两侧** |
| 详情抽屉 | 点击节点 | 右侧滑出：类型、岗位、系统、操作说明、上下游（可点击跳转） | 打开时画布右移让位 |
| 流程演示 | 顶部按钮 | 逐步高亮 + 连线流动 + 进度提示，再点停止 | 结束回全图 |
| 缩放平移 | 滚轮 / 拖拽空白 | 以鼠标为锚点 | 显示当前百分比 |
| 适应窗口 | 按钮 | 全图居中 | 预留冻结条高度 |
| 冻结泳道条 | 常驻 | 顶部固定，横向跟随画布 | 见铁律 4 |
| 流程说明弹窗 | 顶部按钮 | 展示原始文字说明全文 | 原文分组结构要保留 |

## 二、悬停气泡的正确实现

```js
function showTip(node){
  tip.innerHTML = buildHTML(node);
  tip.classList.add('on');
  const r = el.getBoundingClientRect();
  const tw = tip.offsetWidth, th = tip.offsetHeight, gap = 14;

  // 1) 优先右侧，空间不足翻左侧
  let x, side;
  const roomR = innerWidth - (r.right + gap), roomL = r.left - gap;
  if (roomR >= tw)         { x = r.right + gap; side = 'r'; }
  else if (roomL >= tw)    { x = r.left - gap - tw; side = 'l'; }
  else if (roomR >= roomL) { x = innerWidth - tw - 10; side = 'r'; }
  else                     { x = 10; side = 'l'; }

  // 2) 垂直与节点居中（不要放上下！）
  let y = r.top + r.height/2 - th/2;
  y = Math.max(64, Math.min(y, innerHeight - th - 10));

  // 3) 与其他节点相交则沿垂直方向找最近空档
  const others = [...document.querySelectorAll('.node:not(.ghost)')]
    .map(e => e.getBoundingClientRect())
    .filter(o => !(o.right < x - 6 || o.left > x + tw + 6));   // 只关心同列
  const hits = yy => others.some(o => {
    const b = {l:x, r:x+tw, t:yy, b:yy+th};
    return b.l < o.right-4 && b.r > o.left+4 && b.t < o.bottom-4 && b.b > o.top+4;
  });
  if (hits(y)) {
    const y0 = r.top + r.height/2 - th/2;
    for (let off = 18; off < innerHeight; off += 18) {
      if (y0 + off <= innerHeight - th - 10 && !hits(y0 + off)) { y = y0 + off; break; }
      if (y0 - off >= 64 && !hits(y0 - off))                    { y = y0 - off; break; }
    }
  }
  tip.style.left = x + 'px';
  tip.style.top  = y + 'px';
}
```

要点：
- `pointer-events: none`，否则气泡会抢走 hover 导致闪烁
- 动画用 `opacity` + 轻微位移，不要用 `transform: scale` 动整体定位
- 拖动节点、演示播放中要 `return`，否则气泡跟着乱飞

## 三、踩坑记录

| 坑 | 现象 | 修法 |
|---|---|---|
| 气泡压在流程上 | 用户第一眼就说"挡住了" | 改左右侧 + 避让（见上） |
| 迷你地图挡图 | 缩略图压在画布右下 | 直接删，别挪位置 |
| 侧栏挤占画布 | 窄窗口 `right: 372px` 后图被压扁 | 用 `position:absolute` 覆盖 + 默认收起 |
| 节点拖走了线不动 | 坐标写了两份 | 只信数据层坐标，drag 后 `drawAll()` |
| 气泡在窄窗口被裁 | 只做了水平夹紧 | 垂直也要夹紧，顶部留 64px 给页头 |
| 判断节点文字溢出 | 菱形内接矩形小 | 高度 96px + 左右 padding 34px + 字号降到 11.8px + 隐藏副标题 |
| marker 颜色改不动 | CSS 变量在 marker 内不继承 | 注册三个 marker，切换 `marker-end` |
| 演示卡在中间态 | 停止时没复位 | `stopPlay()` 里清所有 `.playing` / `.live` 并 `fitView()` |
| 阶段筛选后布局散 | 重新 fit 时用了全图边界 | 只按可见节点算边界 |

## 四、性能与体积

- 全部内联，无外部字体、无 CDN。中文字体用系统栈：`-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`
- 40 个节点以内：DOM 渲染即可，不需要 canvas
- 连线重绘用 documentFragment 或整体重建 SVG innerHTML，别逐条 append
- 目标体积：单文件 60–120 KB，超过 200 KB 说明塞了不该塞的东西（比如 base64 图片）
