#!/usr/bin/env python3
"""构建技能发布包 dist/dynamic-flow-diagram.zip

白名单打包：只收技能运行必需的文件。仓库内的维护脚本（tools/）、CI 配置、
截图、dist 自身一律排除 —— 这正是 v1.0.1 修复的问题：一次性运维脚本
setup_repo_meta.py 曾被打进发布包，随技能分发给每个用户。

用法：
    python tools/package.py          # 打包到 dist/
    python tools/package.py --check  # 只校验现有包，不重新生成（CI 用）
"""
import argparse
import glob
import hashlib
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_NAME = 'dynamic-flow-diagram'
OUT = os.path.join(ROOT, 'dist', f'{PKG_NAME}.zip')

# 白名单：只有列在这里的文件才会进入发布包
INCLUDE = [
    'SKILL.md',
    'README.md',
    'LICENSE',
    'assets/template.html',
    'references/*.md',
    'scripts/parse_vsdx.py',
    'scripts/shot.js',
    'scripts/validate_skill.py',
]

# 无论白名单如何，这些路径一律禁止入包（防回归）
DENY = ('tools/', 'docs/', 'dist/', '.github/', '__pycache__', '.pyc', '.git/')


def collect():
    files = []
    for pat in INCLUDE:
        for p in sorted(glob.glob(os.path.join(ROOT, pat))):
            rel = os.path.relpath(p, ROOT).replace('\\', '/')
            if any(d in rel for d in DENY):
                raise SystemExit(f'✗ 白名单命中了禁止入包路径：{rel}')
            files.append(rel)
    missing = [p for p in INCLUDE if not glob.glob(os.path.join(ROOT, p))]
    if missing:
        raise SystemExit('✗ 缺少必需文件：' + ', '.join(missing))
    return files


def norm(b):
    """行尾归一：Windows 检出为 CRLF、Linux 为 LF，比较内容时忽略差异。"""
    return b.replace(b'\r\n', b'\n')


def skill_version():
    with open(os.path.join(ROOT, 'SKILL.md'), encoding='utf-8') as f:
        m = re.search(r'^version:\s*(\S+)', f.read(), re.M)
    return m.group(1) if m else 'unknown'


FIXED_DATE = (2026, 1, 1, 0, 0, 0)   # 固定时间戳，保证同一份源码在任意机器/系统打出同一字节


def build(files):
    """确定性打包：内容相同则 zip 字节完全一致（便于 CI 用 git diff 校验）。"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            info = zipfile.ZipInfo(f'{PKG_NAME}/{rel}', date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            with open(os.path.join(ROOT, rel), 'rb') as f:
                z.writestr(info, f.read())
    return OUT


def verify():
    """校验包内容：必需文件齐全、无禁止文件、README 与 SKILL.md 版本一致。"""
    errors = []
    with zipfile.ZipFile(OUT) as z:
        names = z.namelist()
        for n in names:
            if any(d in n for d in DENY):
                errors.append(f'包内含禁止文件：{n}')
        wanted = {f'{PKG_NAME}/{f}' for f in collect()}
        for w in sorted(wanted - set(names)):
            errors.append(f'缺少文件：{w}')
        extra = sorted(set(names) - wanted)
        if extra:
            errors.append('包内含白名单之外的条目：' + ', '.join(extra))

        # 逐文件比对内容哈希：跨 OS / Python 版本都能判定包是否与源码同步
        stale = []
        for rel in collect():
            with open(os.path.join(ROOT, rel), 'rb') as f:
                disk = hashlib.md5(norm(f.read())).hexdigest()
            inside = hashlib.md5(norm(z.read(f'{PKG_NAME}/{rel}'))).hexdigest()
            if disk != inside:
                stale.append(rel)
        if stale:
            errors.append('包内文件落后于源码（请重跑 python tools/package.py）：' + ', '.join(stale))

        ver = skill_version()
        skill_md = z.read(f'{PKG_NAME}/SKILL.md').decode('utf-8')
        readme = z.read(f'{PKG_NAME}/README.md').decode('utf-8')
        if f'version: {ver}' not in skill_md:
            errors.append('SKILL.md 版本与源码不一致')
        if ver not in readme:
            errors.append(f'README 未提及当前版本号 {ver}（发布说明需同步）')
        if '<your-name>' in readme:
            errors.append('README 仍含占位符 <your-name>')

    size_kb = os.path.getsize(OUT) / 1024
    print(f'版本：{ver} | 文件：{len(names)} 个 | 体积：{size_kb:.1f} KB')
    with open(OUT, 'rb') as f:
        print('md5：' + hashlib.md5(f.read()).hexdigest())
    for e in errors:
        print('✗ ' + e)
    return not errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只校验现有包，不重新生成')
    a = ap.parse_args()

    if not a.check:
        files = collect()
        build(files)
        print(f'已生成 {os.path.relpath(OUT, ROOT)}')
    elif not os.path.exists(OUT):
        raise SystemExit('✗ dist 下没有包，先运行 python tools/package.py')

    if not verify():
        sys.exit(1)
    print('✓ 发布包校验通过')


if __name__ == '__main__':
    main()
