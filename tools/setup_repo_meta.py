#!/usr/bin/env python3
"""
一次性补齐 GitHub 仓库元信息：描述 + topics + Release（含 zip 资产）。

用法：
    python setup_repo_meta.py --token ghp_xxxxxxxx
    python setup_repo_meta.py --token ghp_xxx --dry-run    # 只看要发什么请求

Token 需要 classic PAT 的 `public_repo`（或 fine-grained 的 Administration: RW + Contents: RW）。
token 只在内存中使用，不落盘、不写日志。
"""
import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request as ur

OWNER = 'qidian777'
REPO = 'dynamic-flow-diagram'
API = f'https://api.github.com/repos/{OWNER}/{REPO}'
UPLOAD = f'https://uploads.github.com/repos/{OWNER}/{REPO}'

# 常见本地代理端口（Clash / V2Ray / SS 等）
PROXY_CANDIDATES = ['http://127.0.0.1:7897', 'http://127.0.0.1:7890',
                    'http://127.0.0.1:10809', 'http://127.0.0.1:8080']
_OPENER = None


def log(msg):
    print(msg, flush=True)


def _probe(proxy):
    """用一个最短请求测试代理是否真能到 GitHub。"""
    handler = ur.ProxyHandler({}) if proxy is None else ur.ProxyHandler({'http': proxy, 'https': proxy})
    op = ur.build_opener(handler)
    try:
        req = ur.Request('https://api.github.com/zen', headers={'User-Agent': 'probe'})
        with op.open(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_opener(forced=None):
    """按 环境变量 → 常见本地端口 → 直连 的顺序找一个能通 GitHub 的出口。"""
    global _OPENER
    if _OPENER is not None:
        return _OPENER

    if forced:
        cands = [forced]
    else:
        env = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
        cands = ([env] if env else []) + PROXY_CANDIDATES + [None]

    for p in cands:
        label = p or '直连'
        log(f'  探测出口：{label} ...')
        if _probe(p):
            log(f'  ✓ 可用：{label}\n')
            handler = ur.ProxyHandler({}) if p is None else ur.ProxyHandler({'http': p, 'https': p})
            _OPENER = ur.build_opener(handler)
            return _OPENER
    raise SystemExit(
        '✗ 所有出口都连不上 api.github.com。\n'
        '  请先确认代理软件在运行，然后用 --proxy 指定，例如：\n'
        '    python scripts/setup_repo_meta.py --token ghp_xxx --proxy http://127.0.0.1:7897')


DESCRIPTION = ('Turn Visio/process descriptions into a single-file interactive HTML flow diagram — '
               'Agent Skill for training, review and role walkthrough')
HOMEPAGE = 'https://github.com/qidian777/dynamic-flow-diagram'
TOPICS = ['agent-skill', 'claude-skills', 'visio', 'vsdx', 'flowchart',
          'process-diagram', 'swimlane', 'diagram-as-code', 'html-widget', 'training']
TAG = 'v1.0.0'
RELEASE_NAME = 'v1.0.0 — 首版：七条铁律 + 模板骨架 + vsdx 解析 + 截图自查'
RELEASE_BODY = """首个可用版本。

## 包含什么

- **SKILL.md** — 五步工作流 + 7 条铁律（都是从 7 轮真实返工里提炼的）
- **assets/template.html** — 可直接改数据的工作骨架，改 5 个常量就是你的流程图
- **scripts/parse_vsdx.py** — `.vsdx`（zip/OOXML）→ JSON，不需要装 Visio
- **scripts/shot.js** — Playwright 截图自查：气泡是否遮挡节点、是否被裁切、控制台报错、体积
- **references/** — 布局规则、交互规范、交付验收清单

## 安装

- Claude Code：`git clone https://github.com/qidian777/dynamic-flow-diagram.git ~/.claude/skills/dynamic-flow-diagram`
- WorkBuddy 技能市场：上传下方 `dynamic-flow-diagram.zip`

## 已验证

- 模板通过 `scripts/shot.js` 全项自查
- 解析器用一个真实的 4 页 `.vsdx` 测试通过（页映射、形状、连线、文本）
- CI：`validate_skill.py` + `node --check` + Playwright 冒烟渲染
"""


def req(url, method='GET', payload=None, token=None, ctype='application/json',
        raw=None, accept='application/vnd.github+json'):
    headers = {'Accept': accept, 'User-Agent': 'skill-meta-setup'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None
    if raw is not None:
        data = raw
        headers['Content-Type'] = ctype
    elif payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = ctype
    r = ur.Request(url, data=data, method=method, headers=headers)
    op = get_opener()
    try:
        with op.open(r, timeout=60) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body.strip().startswith(b'{') or body.strip().startswith(b'[') else body
    except ur.HTTPError as e:
        detail = e.read().decode('utf-8', 'ignore')[:300]
        raise SystemExit(f'✗ {method} {url}\n  HTTP {e.code}: {detail}')
    except ur.URLError as e:
        raise SystemExit(f'✗ {method} {url}\n  网络错误：{e.reason}\n  试试 --proxy http://127.0.0.1:7897')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--token', default=os.environ.get('GITHUB_TOKEN'))
    ap.add_argument('--proxy', help='手动指定代理，如 http://127.0.0.1:7897（不填则自动探测）')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    print(f'目标仓库：{OWNER}/{REPO}\n', flush=True)
    if a.dry_run:
        print('【dry-run】将执行：', flush=True)
        print(f'  1. PATCH {API}  → description / homepage')
        print(f'  2. PUT   {API}/topics  → {len(TOPICS)} 个 topics')
        print(f'  3. POST  {API}/releases  → {TAG}')
        print(f'  4. POST  {UPLOAD}/releases/<id>/assets  → dist/dynamic-flow-diagram.zip')
        return
    if not a.token:
        raise SystemExit('缺少 token：用 --token 传入，或设置 GITHUB_TOKEN 环境变量')

    log('检查网络出口：')
    get_opener(a.proxy)

    # 1. 描述 + homepage
    st, d = req(API, 'PATCH', {'description': DESCRIPTION, 'homepage': HOMEPAGE}, a.token)
    log(f'✓ 描述已设置（HTTP {st}）')

    # 2. topics
    st, d = req(f'{API}/topics', 'PUT', {'names': TOPICS}, a.token)
    log(f'✓ topics 已设置 {len(d.get("names", []))} 个：{", ".join(d.get("names", []))}')

    # 3. Release（tag 已存在时会自动关联）
    st, rel = req(f'{API}/releases', 'POST',
                  {'tag_name': TAG, 'name': RELEASE_NAME, 'body': RELEASE_BODY,
                   'draft': False, 'prerelease': False}, a.token)
    log(f'✓ Release 已创建：{rel["html_url"]}')

    # 4. 上传 zip 资产（dist 在仓库根，需从 scripts/ 回退一级）
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    zip_path = os.path.join(root, 'dist', 'dynamic-flow-diagram.zip')
    if not os.path.exists(zip_path):
        log(f'⚠ 未找到 {zip_path}，跳过资产上传（可在仓库根执行 python -m zipfile 重新打包）')
        return
    with open(zip_path, 'rb') as f:
        blob = f.read()
    st, asset = req(f'{UPLOAD}/releases/{rel["id"]}/assets?name=dynamic-flow-diagram.zip',
                    'POST', token=a.token, ctype='application/zip', raw=blob)
    log(f'✓ 资产已上传：{asset["browser_download_url"]}（{len(blob)//1024} KB）')
    log('\n完成。检查：')
    log(f'  {API}  → description / topics')
    log(f'  https://github.com/{OWNER}/{REPO}/releases')


if __name__ == '__main__':
    main()
