#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_workbench.py — 流程清单(manifest) → 单文件 HTML 工作台

用法:
    python build_workbench.py examples/demo-manifest.yaml -o out/工作台.html
    python build_workbench.py examples/demo-manifest.yaml --check    # 只体检不产出
    python build_workbench.py examples/demo-manifest.yaml --strict   # 有 error 则退出码 1

设计要点:
  1. 校验与检查分离 —— 校验不过直接崩（清单写错了），检查不通过只报告（业务有问题）
  2. 三类检查：断链(error) / 术语(warning) / 职责冲突(warning) + 未登记实体(info)
  3. 问题清单随数据一起注入 HTML，报告页直接渲染，不需要二次处理
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML：pip install pyyaml")

HERE = Path(__file__).resolve().parent
TPL_CANDIDATES = [
    HERE.parent / "assets" / "workbench.html",
    HERE / "workbench.html",
]
PLACEHOLDER = "/*__WORKBENCH_DATA__*/"

# 动作词库：用于职责冲突检测
SUBMIT_WORDS = ["提交", "申请", "拟定", "发起", "编制", "填报"]
APPROVE_WORDS = ["审批", "签批", "批准", "审核", "核准", "终审"]
ACTION_WORDS = ["验收", "审批", "签批", "核销", "鉴定", "点检"]


# --------------------------------------------------------------------------
# 载入
# --------------------------------------------------------------------------
def load_manifest(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("清单顶层必须是对象（meta / dictionaries / terms / flows）")
    return data


def norm_sys(v):
    """'—' 和空串统一成 None，避免统计时出现假系统。"""
    if v is None:
        return None
    s = str(v).strip()
    return None if s in ("", "—", "-", "无", "None") else s


# --------------------------------------------------------------------------
# 校验：清单本身写错了吗（不通过就没法继续）
# --------------------------------------------------------------------------
def validate(m: dict) -> list:
    fatal = []
    for key in ("meta", "dictionaries", "flows"):
        if key not in m:
            fatal.append(f"缺少顶层字段：{key}")

    dicts = m.get("dictionaries") or {}
    role_ids = {r["id"] for r in dicts.get("roles") or []}
    sys_ids = {s["id"] for s in dicts.get("systems") or []}
    dept_ids = {d["id"] for d in dicts.get("departments") or []}

    seen_flow, seen_node = set(), {}
    for f in m.get("flows") or []:
        fid = f.get("id")
        if not fid:
            fatal.append("有流程缺少 id")
            continue
        if fid in seen_flow:
            fatal.append(f"流程 id 重复：{fid}")
        seen_flow.add(fid)
        if not f.get("nodes") and not f.get("registry"):
            fatal.append(f"流程 {fid} 没有任何节点（如属手册登记、暂无图形，请标 registry: true）")
        phase_ids = {p["id"] for p in f.get("phases") or []}
        for n in f.get("nodes") or []:
            nid = n.get("id")
            if not nid:
                fatal.append(f"流程 {fid} 有节点缺少 id")
                continue
            if nid in seen_node:
                fatal.append(f"节点 id 全局重复：{nid}（{seen_node[nid]} 与 {fid}）")
            seen_node[nid] = fid
            if n.get("phase") not in phase_ids:
                fatal.append(f"节点 {nid} 的 phase「{n.get('phase')}」不在流程 {fid} 的阶段表里")
            if n.get("lane") and n["lane"] not in role_ids and n["lane"] not in dept_ids:
                fatal.append(f"节点 {nid} 的 lane「{n['lane']}」既不是已登记角色，也不是已登记部门")
        ids = {n.get("id") for n in f.get("nodes") or []}
        for e in f.get("edges") or []:
            for end in ("from", "to"):
                if e.get(end) not in ids:
                    fatal.append(f"流程 {fid} 的连线 {e.get('from')}→{e.get('to')} 端点 {e.get(end)} 不存在")
    for f in m.get("flows") or []:
        if f.get("dept") and f["dept"] not in dept_ids:
            fatal.append(f"流程 {f.get('id')} 的部门「{f['dept']}」未登记")
    return fatal


# --------------------------------------------------------------------------
# 检查：业务上有没有问题（报告出来，不阻断）
# --------------------------------------------------------------------------
def collect_text(n: dict) -> str:
    return " ".join(str(n.get(k) or "") for k in ("text", "note"))


def check(m: dict) -> list:
    issues = []
    dicts = m.get("dictionaries") or {}
    roles = {r["id"]: r for r in dicts.get("roles") or []}
    systems = {s["id"]: s for s in dicts.get("systems") or []}
    sys_names = {s["name"] for s in dicts.get("systems") or []}
    flows = m.get("flows") or []
    flow_by_id = {f["id"]: f for f in flows}
    node_index = {}
    for f in flows:
        for n in f.get("nodes") or []:
            node_index[n["id"]] = (f, n)

    def add(level, code, flow_id, node_id, title, detail, target=None):
        issues.append({
            "level": level, "code": code, "flow": flow_id, "node": node_id,
            "title": title, "detail": detail, "target": target,
        })

    # ---- 1. 断链：子流程引用不存在的流程 / 节点 ----
    for f in flows:
        for n in f.get("nodes") or []:
            sub = n.get("sub")
            if not sub:
                continue
            tf, tn = sub.get("flow"), sub.get("node")
            if tf not in flow_by_id:
                add("error", "BROKEN_SUBFLOW", f["id"], n["id"],
                    f"指向不存在的流程「{tf}」",
                    f"节点「{n['text']}」引用了流程 {tf}，但清单里没有这张流程。"
                    f"点击时会跳不过去，需要补建流程或修正引用。")
                continue
            target_ids = {x["id"] for x in flow_by_id[tf].get("nodes") or []}
            if tn and tn not in target_ids:
                add("error", "BROKEN_SUBNODE", f["id"], n["id"],
                    f"指向 {tf} 中不存在的节点「{tn}」",
                    f"节点「{n['text']}」引用了 {tf}.{tn}，但该流程里没有这个节点。")
            elif not tn:
                add("info", "SUBFLOW_NO_ANCHOR", f["id"], n["id"],
                    "子流程未指定入口节点",
                    f"节点「{n['text']}」只引用了流程 {tf}，没指定落到哪个节点，"
                    f"跳转后只能看到全图。建议补上 node 字段。")

    # ---- 2. 角色 / 系统引用 ----
    for f in flows:
        for n in f.get("nodes") or []:
            rid = n.get("role")
            if not rid:
                add("warning", "NO_ROLE", f["id"], n["id"],
                    "节点没有责任角色",
                    f"「{n['text']}」没有 role 字段，岗位视角统计会漏掉这一步。")
            elif rid not in roles:
                add("warning", "UNKNOWN_ROLE", f["id"], n["id"],
                    f"角色「{rid}」未登记",
                    f"节点「{n['text']}」用了没在 dictionaries.roles 里登记的角色，"
                    f"统计与筛选中会被当成独立角色。")
            sid = norm_sys(n.get("system"))
            if sid and sid not in systems:
                add("warning", "UNKNOWN_SYSTEM", f["id"], n["id"],
                    f"系统「{sid}」未登记",
                    f"节点「{n['text']}」用的系统不在字典里，筛选项会缺失。")

    # ---- 3. 术语一致性（声明式） ----
    term_hit = {}
    for grp in m.get("terms") or []:
        canon = grp.get("canonical")
        for alias in grp.get("aliases") or []:
            for f in flows:
                for n in f.get("nodes") or []:
                    txt = collect_text(n)
                    if alias in txt:
                        term_hit.setdefault((canon, alias), []).append((f, n))
    for (canon, alias), hits in term_hit.items():
        f0, n0 = hits[0]
        add("warning", "TERM_ALIAS", f0["id"], n0["id"],
            f"「{alias}」应统一为「{canon}」",
            f"在 {len(hits)} 处出现旧叫法："
            + "、".join(f"{fn['name']}·{nn['text']}" for fn, nn in hits[:4])
            + ("…" if len(hits) > 4 else "")
            + f"。同一概念多种叫法会让新人以为它们是不同东西，建议全量替换为「{canon}」。")

    # ---- 4. 字典自查：两个系统名高度相似，疑似同一系统登记了两次 ----
    from difflib import SequenceMatcher
    sys_list = list(systems.values())
    for i, a in enumerate(sys_list):
        for b in sys_list[i + 1:]:
            na, nb = str(a.get("name") or ""), str(b.get("name") or "")
            if not na or not nb:
                continue
            r = SequenceMatcher(None, na, nb).ratio()
            if 0.72 <= r < 1:
                add("info", "DUP_SYSTEM", None, None,
                    f"「{na}」与「{nb}」名称高度相似",
                    f"相似度 {r:.0%}。如果它们其实是同一套系统，合并字典项；"
                    f"否则筛选器里会出现两个只差一个字的选项，用户每次都要猜。")

    # ---- 5. 自我审批：同一流程里，同一角色先提交后审批 ----
    for f in flows:
        nodes = f.get("nodes") or []
        by_id = {n.get("id"): n for n in nodes}
        # 只沿真实连线往下找两跳，避免把顺序无关的两个节点误判成「先提后批」
        adj = {}
        for e in f.get("edges") or []:
            adj.setdefault(e.get("from"), []).append(e.get("to"))
        seen = set()
        for a in nodes:
            if not any(w in str(a.get("text", "")) for w in SUBMIT_WORDS):
                continue
            reach, frontier = [], [a.get("id")]
            for _ in range(2):
                nxt = []
                for x in frontier:
                    for y in adj.get(x, []):
                        if y in by_id and y not in reach:
                            reach.append(y)
                            nxt.append(y)
                frontier = nxt
            for bid in reach:
                b = by_id.get(bid) or {}
                if a.get("role") != b.get("role"):
                    continue
                if not any(w in str(b.get("text", "")) for w in APPROVE_WORDS):
                    continue
                if (f["id"], bid) in seen:
                    continue
                seen.add((f["id"], bid))
                add("warning", "SELF_APPROVE", f["id"], b["id"],
                    f"{roles.get(a.get('role'), {}).get('name', a.get('role'))} 自己提自己批",
                    f"「{a['text']}」与「{b['text']}」都由同一角色执行。"
                    f"除非制度上明确允许，否则应拆给两个角色，避免自我审批。")

    # ---- 6. 同类动作跨流程角色不一致 ----
    action_role = {}
    for f in flows:
        for n in f.get("nodes") or []:
            t = str(n.get("text", ""))
            for w in ACTION_WORDS:
                if w in t:
                    action_role.setdefault(w, {}).setdefault(n.get("role"), []).append((f, n))
    for w, by_role in action_role.items():
        if len(by_role) < 2:
            continue
        parts = []
        for rid, hits in by_role.items():
            f0, n0 = hits[0]
            parts.append(f"{roles.get(rid, {}).get('name', rid)}→「{n0['text']}」")
        f0, n0 = next(iter(by_role.values()))[0]
        add("warning", "ROLE_MISMATCH", f0["id"], n0["id"],
            f"「{w}」这个动作分给了 {len(by_role)} 个角色",
            "；".join(parts) + f"。同类动作由不同角色承担，通常意味着职责边界没定清楚，"
            "或者只是叫法不同。建议确认后统一。")

    # ---- 7. 孤立流程 ----
    referenced = {n.get("sub", {}).get("flow") for f in flows for n in f.get("nodes") or [] if n.get("sub")}
    mains = {f["id"] for f in flows if f.get("role") == "main"}
    for f in flows:
        if f["id"] not in referenced and f["id"] not in mains:
            add("info", "ORPHAN_FLOW", f["id"], None,
                "没有任何流程引用它",
                f"「{f['name']}」没有被其他流程的子节点引用，也不在首页总览上。"
                f"它只能从索引页进入，确认是否符合预期。")

    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda x: (order[x["level"]], x["flow"] or "", x["node"] or ""))
    return issues


# --------------------------------------------------------------------------
# 统计：给首页和索引页用的聚合数字
# --------------------------------------------------------------------------
def stats(m: dict) -> dict:
    flows = m.get("flows") or []
    role_count = {}
    sys_count = {}
    for f in flows:
        for n in f.get("nodes") or []:
            if n.get("role"):
                role_count[n["role"]] = role_count.get(n["role"], 0) + 1
            if n.get("system"):
                sys_count[n["system"]] = sys_count.get(n["system"], 0) + 1
    return {
        "flows": len(flows),
        "nodes": sum(len(f.get("nodes") or []) for f in flows),
        "edges": sum(len(f.get("edges") or []) for f in flows),
        "roles": len((m.get("dictionaries") or {}).get("roles") or []),
        "systems": len((m.get("dictionaries") or {}).get("systems") or []),
        "role_nodes": role_count,
        "sys_nodes": sys_count,
    }


# --------------------------------------------------------------------------
# 产出
# --------------------------------------------------------------------------
def build_html(m: dict, issues: list) -> str:
    tpl = None
    for p in TPL_CANDIDATES:
        if p.exists():
            tpl = p.read_text(encoding="utf-8")
            break
    if tpl is None:
        sys.exit(f"找不到模板 workbench.html，查找过：{[str(p) for p in TPL_CANDIDATES]}")
    if PLACEHOLDER not in tpl:
        sys.exit(f"模板里缺少数据占位符 {PLACEHOLDER}")

    payload = {
        "meta": m.get("meta") or {},
        "dictionaries": m.get("dictionaries") or {},
        "terms": m.get("terms") or [],
        "flows": m.get("flows") or [],
        "issues": issues,
        "stats": stats(m),
    }
    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    js = js.replace("</", "<\\/")          # 防止正文里的 </script> 提前闭合
    return tpl.replace(PLACEHOLDER, f"const D = {js};")


def report(issues: list, m: dict, stream=sys.stdout):
    icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}
    n = {k: sum(1 for i in issues if i["level"] == k) for k in ("error", "warning", "info")}
    print(f"\n清单：{m['meta'].get('title', '(未命名)')}", file=stream)
    st = stats(m)
    print(f"规模：{st['flows']} 张流程 · {st['nodes']} 个节点 · {st['edges']} 条连线 · "
          f"{st['roles']} 个角色 · {st['systems']} 个系统", file=stream)
    if not issues:
        print("检查：未发现问题 ✅", file=stream)
        return
    print(f"检查：{n['error']} 个错误 · {n['warning']} 个警告 · {n['info']} 个提示", file=stream)
    for i in issues:
        loc = i["flow"] or ""
        if i["node"]:
            loc += f" · {i['node']}"
        print(f"  {icon[i['level']]} [{i['code']}] {loc}  {i['title']}", file=stream)


def main():
    ap = argparse.ArgumentParser(description="流程清单 → 单文件 HTML 工作台")
    ap.add_argument("manifest", help="manifest 文件（.yaml / .json）")
    ap.add_argument("-o", "--out", help="输出 HTML 路径")
    ap.add_argument("--check", action="store_true", help="只体检，不产出 HTML")
    ap.add_argument("--strict", action="store_true", help="存在 error 时退出码为 1")
    args = ap.parse_args()

    path = Path(args.manifest)
    if not path.exists():
        sys.exit(f"找不到清单文件：{path}")

    m = load_manifest(path)

    fatal = validate(m)
    if fatal:
        print("清单校验未通过，先修这些：", file=sys.stderr)
        for f in fatal:
            print("  ✗", f, file=sys.stderr)
        sys.exit(2)

    issues = check(m)
    report(issues, m)

    if args.check:
        return

    out = Path(args.out) if args.out else path.with_name(f"{m['meta'].get('title', '流程工作台')}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    html = build_html(m, issues)
    out.write_text(html, encoding="utf-8")
    print(f"\n已生成：{out}  ({len(html.encode('utf-8')) / 1024:.1f} KB)")

    if args.strict and any(i["level"] == "error" for i in issues):
        sys.exit(1)


if __name__ == "__main__":
    main()
