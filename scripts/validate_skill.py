#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_skill.py — 技能包自检（CI 用，也可本地跑）

检查：
  1. SKILL.md 存在且 frontmatter 齐全（name/description/version/author…）
  2. name 与目录名一致、版本符合 SemVer
  3. SKILL.md 引用的资源文件真实存在（@references/... @assets/... @scripts/...）
  4. 脚本可编译、模板含关键实现（气泡避让 / 冻结泳道 / 标准图形）

用法：python scripts/validate_skill.py [技能目录]
"""
import sys, os, re, py_compile, json

REQUIRED = ['name', 'display_name', 'description', 'version', 'author']
SEMVER = re.compile(r'^\d+\.\d+\.\d+([\-+][\w.]+)?$')


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
                           os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    errors, warns = [], []

    skill_md = os.path.join(root, 'SKILL.md')
    if not os.path.isfile(skill_md):
        print('✗ 缺少 SKILL.md'); sys.exit(1)
    text = open(skill_md, encoding='utf-8').read()

    m = re.match(r'^---\r?\n(.*?)\r?\n---', text, re.S)
    if not m:
        errors.append('SKILL.md 缺少 YAML frontmatter')
        fm = ''
    else:
        fm = m.group(1)

    for k in REQUIRED:
        if not re.search(rf'^{k}\s*:', fm, re.M):
            errors.append(f'frontmatter 缺少字段：{k}')

    name = (re.search(r'^name\s*:\s*(.+)$', fm, re.M) or [None, ''])[1].strip()
    if name and name != os.path.basename(root):
        errors.append(f'name({name}) 与目录名({os.path.basename(root)}) 不一致')

    ver = (re.search(r'^version\s*:\s*(.+)$', fm, re.M) or [None, ''])[1].strip()
    if ver and not SEMVER.match(ver):
        errors.append(f'version 不是 SemVer：{ver}')

    # SKILL.md 里 @ 引用的文件必须存在
    for ref in set(re.findall(r'@((?:references|assets|scripts)/[\w./-]+)', text)):
        if not os.path.isfile(os.path.join(root, ref)):
            errors.append(f'引用的文件不存在：{ref}')

    # 脚本语法
    for py in re.findall(r'[\w./-]+\.py', text):
        p = os.path.join(root, py)
        if os.path.isfile(p):
            try:
                py_compile.compile(p, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(f'语法错误 {py}：{e.msg}')

    # 模板关键实现
    tpl = os.path.join(root, 'assets', 'template.html')
    if os.path.isfile(tpl):
        t = open(tpl, encoding='utf-8').read()
        for key, desc in [('shapeSVG', '标准流程图图形'),
                          ('syncLaneBar', '冻结泳道条'),
                          ('showTip', '悬停气泡'),
                          ('playTimer', '流程演示')]:
            if key not in t:
                errors.append(f'template.html 缺少 {desc}（{key}）')
        if 'hits(' not in t:
            warns.append('template.html 未检测到气泡避让逻辑')

    print(f'技能目录：{root}')
    print(f'名称：{name}  版本：{ver}')
    if warns:
        print('提示：'); [print('  ⚠', w) for w in warns]
    if errors:
        print('校验失败：'); [print('  ✗', e) for e in errors]
        sys.exit(1)
    print('✓ 校验通过')


if __name__ == '__main__':
    main()
