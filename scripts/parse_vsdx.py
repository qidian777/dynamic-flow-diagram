#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_vsdx.py — 把 Visio .vsdx 解析成可建模的 JSON

用法：
    python parse_vsdx.py <file.vsdx>              # 列出所有页 + 每页节点/连线统计
    python parse_vsdx.py <file.vsdx> --page 3     # 输出第 3 页完整 JSON
    python parse_vsdx.py <file.vsdx> --page 3 -o page3.json

输出结构：
    {
      "page": {"id":"3","name":"样衣管控流程（优化版）"},
      "shapes": [{"id","master","x","y","w","h","text"}],   # 坐标已转 px，y 轴翻转
      "edges":  [{"from","to","text"}],
      "texts":  [{"id","text"}]                              # 长文本块（流程说明）
    }

说明：
    * .vsdx 本质是 zip（OOXML），直接读 XML，无需装 Visio
    * PinX/PinY 是形状中心点，单位英寸，×96 得像素
    * Visio y 轴向上，这里已翻转为 HTML 的 y 轴向下
"""
import sys, json, zipfile, argparse, re
import xml.etree.ElementTree as ET

NS = {'v': 'http://schemas.microsoft.com/office/visio/2012/main'}
V = '{%s}' % NS['v']


def px(v):
    try:
        return round(float(v) * 96, 1)
    except (TypeError, ValueError):
        return None


def cell(shape, name):
    c = shape.find(f"v:Cell[@N='{name}']", NS)
    return c.get('V') if c is not None else None


def shape_text(shape):
    t = shape.find('v:Text', NS)
    if t is None:
        return ''
    s = ''.join(t.itertext())
    return re.sub(r'\s+\n', '\n', s).strip()


def list_pages(z):
    pages_xml = z.read('visio/pages/pages.xml').decode('utf-8', 'ignore')
    root = ET.fromstring(pages_xml)
    rel_root = ET.fromstring(z.read('visio/pages/_rels/pages.xml.rels').decode('utf-8', 'ignore'))
    rel_map = {r.get('Id'): r.get('Target') for r in rel_root}
    # zip 里实际存在的页面文件
    page_files = sorted(n for n in z.namelist()
                        if re.fullmatch(r'visio/pages/page\d+\.xml', n))
    claimed = set()
    pages = []
    for p in root.findall('.//v:Page', NS):
        pid = p.get('ID')
        rel = p.find('v:Rel', NS)
        rid = rel.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id') \
            if rel is not None else None
        target = rel_map.get(rid) if rid else None
        if target:
            target = 'visio/pages/' + target.replace('\\', '/').lstrip('/')
        pages.append({'id': pid, 'name': p.get('Name') or p.get('NameU') or f'Page{pid}',
                      'file': target})
    # rid 缺失或映射失效的页，按顺序分配未认领的文件
    used = {p['file'] for p in pages if p['file'] and p['file'] in page_files}
    free = [f for f in page_files if f not in used]
    for p in pages:
        if not p['file'] or p['file'] not in page_files:
            if free:
                p['file'] = free.pop(0)
            else:
                p['file'] = None
    return pages


def parse_page(z, page):
    root = ET.fromstring(z.read(page['file']).decode('utf-8', 'ignore'))

    raw = []
    for sh in root.findall('.//v:Shapes/v:Shape', NS):
        sid = sh.get('ID')
        raw.append({
            'id': sid,
            'master': sh.get('Master'),
            'x': px(cell(sh, 'PinX')),
            'y': px(cell(sh, 'PinY')),
            'w': px(cell(sh, 'Width')),
            'h': px(cell(sh, 'Height')),
            'text': shape_text(sh),
            'type': sh.get('Type'),          # Shape / Group / Foreign
        })

    # y 轴翻转
    ys = [s['y'] for s in raw if s['y'] is not None]
    max_y = max(ys) if ys else 0
    for s in raw:
        if s['y'] is not None:
            s['y'] = round(max_y - s['y'], 1)

    # 连线
    edges = []
    for c in root.findall('.//v:Connects/v:Connect', NS):
        edges.append({'from': c.get('FromSheet'), 'to': c.get('ToSheet'), 'text': ''})
    # 把连线的文字挂到边上（连线的 FromSheet 就是线形状本身）
    by_id = {s['id']: s for s in raw}
    for e in edges:
        s = by_id.get(e['from'])
        if s and s['text']:
            e['text'] = s['text']

    # 母版名（判断形状类型）
    masters = {}
    try:
        mroot = ET.fromstring(z.read('visio/masters/masters.xml').decode('utf-8', 'ignore'))
        for m in mroot.findall('.//v:Master', NS):
            masters[m.get('ID')] = m.get('NameU') or m.get('Name')
    except KeyError:
        pass
    for s in raw:
        s['master_name'] = masters.get(s['master'], '')

    shapes = [s for s in raw if not (s['type'] == 'Shape' and s['w'] and s['w'] <= 2)]
    texts = [{'id': s['id'], 'text': s['text']} for s in raw if len(s['text']) > 40]

    return {'page': {'id': page['id'], 'name': page['name']},
            'shapes': shapes, 'edges': edges, 'texts': texts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('--page', type=str, default=None, help='页 ID 或页名关键字')
    ap.add_argument('-o', '--out', default=None)
    a = ap.parse_args()

    with zipfile.ZipFile(a.file) as z:
        pages = list_pages(z)
        if not a.page:
            print('页签列表：')
            for p in pages:
                try:
                    d = parse_page(z, p)
                    print(f"  {p['id']:>3}  {p['name']}   "
                          f"形状 {len(d['shapes'])} / 连线 {len(d['edges'])}")
                except Exception as ex:
                    print(f"  {p['id']:>3}  {p['name']}   [解析失败] {ex}")
            print('\n用 --page <ID> 导出某一页的 JSON')
            return
        target = None
        for p in pages:
            if p['id'] == a.page or a.page in (p['name'] or ''):
                target = p
                break
        if target is None:
            sys.exit(f'找不到页：{a.page}')
        data = parse_page(z, target)

    out = json.dumps(data, ensure_ascii=False, indent=2)
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(out)
        print(f'已写入 {a.out}：形状 {len(data["shapes"])} / 连线 {len(data["edges"])} / 长文本 {len(data["texts"])}')
    else:
        print(out)


if __name__ == '__main__':
    main()
