# 工作台模式规格（v2.0.0）

从"一张流程图"到"一个流程宇宙"。工作台把公司所有流程装进**一个 HTML 文件**，
提供总览、索引、跨流程跳转、岗位统计、一致性检查五个视图。

## 一、数据模型：中央清单 manifest

整个流程宇宙只有一个数据源（YAML 或 JSON），三层结构：

```yaml
meta:
  org: 公司名
  title: 工作台标题
  subtitle: 一句话说明
  version: "1.0"

dictionaries:              # 全局字典 —— 一切统计与筛选的口径
  departments: [{id, name}]
  roles: [{id, name, dept, color}]   # color 是角色的主题色，全工作台统一
  systems: [{id, name}]

terms:                     # 术语别名组 —— canonical 是唯一正确叫法
  - {canonical: 设备台账, aliases: [设备档案, 设备清册]}

flows:
  - id: 唯一id（全局唯一）
    name: 流程名
    role: main             # 可选，标记首页总览用的主流程（最多一个）
    dept: 归属部门id
    summary: 一段话说明
    lanes: [role_id...]    # 左右分栏顺序，元素是角色 id
    phases: [{id, name}]   # 纵向分段
    nodes:
      - id: 全局唯一（建议前缀区分流程，如 m1 / p1 / r1）
        phase: 阶段id
        lane: 角色id       # 决定节点在哪一列
        type: start|proc|dec|data|db|sub|end
        text: 节点文字（最多两行，超了拆节点）
        role: 角色id       # 责任岗位（岗位统计按它聚合）
        system: 系统id     # 可选；线下动作用 —
        note: 操作说明（悬停气泡 + 抽屉显示）
        sub: {flow: 目标流程id, node: 目标节点id}   # 仅 type:sub 需要
    edges:
      - {from: 节点id, to: 节点id, label: 分支条件}  # label 可选
```

**三条建模纪律**（违反必返工）：
1. 节点 id 全局唯一——跨流程跳转靠它定位，重复会被构建脚本拒绝
2. `lane` 引用角色字典——岗位统计和筛选共用这套口径，自造列名等于断开统计
3. `sub.node` 尽量写——不写也能跳（落到全图），但断链检查和精准落点都依赖它

## 二、坐标不手写：自动布局

节点坐标由前端布局引擎计算，manifest 里**没有 x/y**。算法两步：

1. **DFS 标回边**（如"换货后重新到货"），回边不参与分层——否则下游节点的
   step 会沿环无限增大，布局直接坏掉
2. **最长路径分层**：step(n) = max(step(前驱))+1；y = PAD_Y + step×GAP_Y，
   x 由 lane 序号决定；同 (step, lane) 冲突时自动横向/纵向让位

阶段带的纵向范围 = 该阶段内节点的 step 范围。泳道条、阶段带、节点三者在
同一坐标系，天然对齐。

**fitView 是宽度优先的**：流程图天然是长条，高度放不下时宁可让用户纵向拖动，
也不把文字缩到看不清（s < 0.62 时改按宽度适配、顶部对齐）。这是 v1 教训的
推广——"适应窗口"不等于"缩到最小"。

## 三、一致性检查规则

构建脚本 `build_workbench.py` 负责体检，结果随数据注入 HTML 的报告页：

| 级别 | code | 规则 |
|---|---|---|
| 🔴 error | BROKEN_SUBFLOW | sub.flow 指向不存在的流程 |
| 🔴 error | BROKEN_SUBNODE | sub.node 在目标流程中不存在 |
| 🟡 warning | TERM_ALIAS | 节点文本出现 aliases 里的旧叫法 |
| 🟡 warning | SELF_APPROVE | 同流程同角色，前面"提交/拟定"、后面"审批/签批" |
| 🟡 warning | ROLE_MISMATCH | 同一动作词（验收/审批/核销…）在不同流程分给不同角色 |
| 🟡 warning | NO_ROLE / UNKNOWN_ROLE / UNKNOWN_SYSTEM | 字典引用缺失 |
| 🔵 info | DUP_SYSTEM | 两个系统名相似度 ≥72%，疑似重复登记 |
| 🔵 info | ORPHAN_FLOW | 没被任何流程引用、也不是主流程 |
| 🔵 info | SUBFLOW_NO_ANCHOR | sub 只写了流程没写落点节点 |

分工原则：**校验（validate）管清单写错没有，错了直接崩；检查（check）管业务
有没有毛病，只报告不阻断**。术语以声明为主——自动相似度猜测误报太多，
只保留字典层的重复登记检测。

## 四、五个视图

| 路由 | 视图 | 关键交互 |
|---|---|---|
| `#/home` | 总览 | 主流程按阶段分列的价值流；子流程节点虚框可进入；角色卡显示"n 个动作 · m 张流程" |
| `#/flows` | 索引 | 关键词搜（流程名+说明+节点文本，命中显示"命中 n 处"）；部门/角色/系统三筛选并联 |
| `#/flow/:id?n=node` | 流程详情 | v1 全套体验 + 阶段筛选 + 演示；抽屉里"进入子流程"按钮 |
| `#/role/:id` | 岗位视角 | 分布条形图 + 按流程分组的动作清单，每条可跳到流程中的位置 |
| `#/issues` | 一致性报告 | 按级别分组，点条目跳到问题所在的节点 |

**跨流程导航（面包屑栈）**：点击 sub 节点 → 当前流程压栈 → 跳到目标流程指定
节点并高亮；"返回"按钮出栈；面包屑可点任意一层直达（栈截断到该层）。直接从
索引/首页进入流程时栈清空。

## 五、构建命令

```bash
python scripts/build_workbench.py <manifest> -o out/工作台.html
python scripts/build_workbench.py <manifest> --check     # 只体检
python scripts/build_workbench.py <manifest> --strict    # 有 error 退出码 1
node scripts/shot_workbench.js <html> <shots目录>        # 截图自查（7 图 + 断言）
```

`--strict` 用于 CI：断链不清零不许发布。

## 六、交付前验收（工作台专用）

在 `qa-checklist.md` 通用项之外加四条：
1. `shot_workbench.js` 全部断言通过（数量、跳转、返回、筛选收窄）
2. 报告页错误数为 0，或客户书面确认接受
3. 跨流程跳转后面包屑与高亮正确，返回不迷路
4. 抽屉在切换视图时收起，不残留上个流程的内容

## 七、三种取材入口 → 同一份 manifest

| 入口 | 做法 |
|---|---|
| vsdx 多页 | `parse_vsdx.py` 逐页导出 JSON，人工把每页挂进 flows，补 sub 引用 |
| Excel 清单 | 客户按列填（流程/阶段/泳道/类型/文字/角色/系统/说明），脚本转 manifest |
| 口述建模 | 像 v1 一样对话抽取，直接写 manifest |

入口不同，终点相同：**manifest 是唯一事实，HTML 只是构建产物**。
