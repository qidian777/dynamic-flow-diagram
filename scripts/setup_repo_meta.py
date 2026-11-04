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
import sys
import urllib.request as ur

OWNER = 'qidian777'
REPO = 'dynamic-flow-diagram'
API = f'https://api.github.com/repos/{OWNER}/{REPO}'
UPLOAD = f'https://uploads.github.com/repos/{OWNER}/{REPO}'

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
    try:
        with ur.open(r, timeout=90) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body.strip().startswith(b'{') or body.strip().startswith(b'[') else body
    except ur.HTTPError as e:
        detail = e.read().decode('utf-8', 'ignore')[:300]
        raise SystemExit(f'✗ {method} {url}\n  HTTP {e.code}: {detail}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--token', default=os.environ.get('GITHUB_TOKEN'))
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    print(f'目标仓库：{OWNER}/{REPO}\n')
    if a.dry_run:
        print('【dry-run】将执行：')
        print(f'  1. PATCH {API}  → description / homepage')
        print(f'  2. PUT   {API}/topics  → {len(TOPICS)} 个 topics')
        print(f'  3. POST  {API}/releases  → {TAG}')
        print(f'  4. POST  {UPLOAD}/releases/<id>/assets  → dist/dynamic-flow-diagram.zip')
        return
    if not a.token:
        raise SystemExit('缺少 token：用 --token 传入，或设置 GITHUB_TOKEN 环境变量')

    # 1. 描述 + homepage
    st, d = req(API, 'PATCH', {'description': DESCRIPTION, 'homepage': HOMEPAGE}, a.token)
    print(f'✓ 描述已设置（HTTP {st}）')

    # 2. topics
    st, d = req(f'{API}/topics', 'PUT', {'names': TOPICS}, a.token)
    print(f'✓ topics 已设置 {len(d.get("names", []))} 个：{", ".join(d.get("names", []))}')

    # 3. Release（tag 已存在时会自动关联）
    st, rel = req(f'{API}/releases', 'POST',
                  {'tag_name': TAG, 'name': RELEASE_NAME, 'body': RELEASE_BODY,
                   'draft': False, 'prerelease': False}, a.token)
    print(f'✓ Release 已创建：{rel["html_url"]}')

    # 4. 上传 zip 资产
    zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'dist', 'dynamic-flow-diagram.zip')
    if not os.path.exists(zip_path):
        print(f'⚠ 未找到 {zip_path}，跳过资产上传')
        return
    with open(zip_path, 'rb') as f:
        blob = f.read()
    st, asset = req(f'{UPLOAD}/releases/{rel["id"]}/assets?name=dynamic-flow-diagram.zip',
                    'POST', token=a.token, ctype='application/zip', raw=blob)
    print(f'✓ 资产已上传：{asset["browser_download_url"]}（{len(blob)//1024} KB）')
    print('\n完成。检查：')
    print(f'  {API}  → description / topics')
    print(f'  https://github.com/{OWNER}/{REPO}/releases')


if __name__ == '__main__':
    main()
