#!/usr/bin/env python3
"""Build the web version of the notes from the LaTeX sources.

Usage (from the repository root, after `make` so build/jozve.aux exists):
    cd web && npm install && cd ..
    python3 web/build.py

Outputs:
    site/index.html     full page for GitHub Pages
    site/artifact.html  the same page without the document skeleton
    site/jozve.pdf      copy of the PDF
"""
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
OUT = os.path.join(ROOT, 'site')
TMP = os.path.join(ROOT, 'build', 'web')

CHAPTERS = [
    ('preface', 'tex/preface.tex', None),
    ('ch-0', 'chapters/ch00-prelim.tex', 0),
    ('ch-1', 'chapters/ch01-linear-equations.tex', 1),
    ('ch-2', 'chapters/ch02-echelon-forms.tex', 2),
    ('ch-3', 'chapters/ch03-vector-spaces.tex', 3),
    ('ch-4', 'chapters/ch04-subspaces.tex', 4),
    ('ch-5', 'chapters/ch05-linear-independence.tex', 5),
    ('ch-6', 'chapters/ch06-basis-dimension.tex', 6),
    ('ch-7', 'chapters/ch07-rank.tex', 7),
    ('ch-8', 'chapters/ch08-inner-product.tex', 8),
    ('appendix', 'chapters/appendix.tex', 'a'),
]

NUMBERED = {'definition': 'تعریف', 'theorem': 'قضیه', 'lemma': 'لم', 'corollary': 'نتیجه',
            'example': 'مثال', 'exercise': 'تمرین'}
UNNUMBERED = {'note': 'نکته', 'warning': 'مراقب باشید!', 'intuition': 'شهود', 'summary': 'جمع‌بندی'}
PROOFS = {'proof': 'اثبات', 'solution': 'پاسخ'}

FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa(s):
    return str(s).translate(FA_DIGITS).replace('-', '\u200f-\u200f')


def match_brace(s, i):
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == '\\':
            j += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ValueError('unbalanced braces at %d' % i)


def match_bracket(s, i):
    depth = 0
    j = i + 1
    while j < len(s):
        c = s[j]
        if c == '\\':
            j += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        elif c == ']' and depth == 0:
            return j
        j += 1
    raise ValueError('unbalanced bracket at %d' % i)


def skip_ws(s, i):
    while i < len(s) and s[i] in ' \t\n':
        i += 1
    return i


def replace_cmd(s, name, nargs, fn):
    out = []
    i = 0
    pat = re.compile(r'\\' + name + r'(?![A-Za-z])')
    while True:
        m = pat.search(s, i)
        if not m:
            out.append(s[i:])
            break
        out.append(s[i:m.start()])
        j = m.end()
        args = []
        ok = True
        for _ in range(nargs):
            j = skip_ws(s, j)
            if j >= len(s) or s[j] != '{':
                ok = False
                break
            k = match_brace(s, j)
            args.append(s[j + 1:k])
            j = k + 1
        if not ok:
            out.append(s[m.start():m.end()])
            i = m.end()
            continue
        out.append(fn(*args))
        i = j
    return ''.join(out)


def load_labels():
    labels = {}
    aux = os.path.join(ROOT, 'build', 'jozve.aux')
    for line in open(aux, encoding='utf-8'):
        m = re.match(r'\\newlabel\{([^}]*)\}\{\{([^}]*)\}', line)
        if m:
            labels[m.group(1)] = m.group(2)
    return labels


def simplify_tabular(s):
    def repl(m):
        spec = m.group(1)
        spec = re.sub(r'[><@]\{(?:[^{}]|\{[^{}]*\})*\}', '', spec)
        spec = re.sub(r'[pmb]\{[^}]*\}', 'l', spec)
        spec = re.sub(r'[^lcr]', '', spec)
        return '\\begin{tabular}{%s}' % spec

    out = []
    i = 0
    while True:
        k = s.find('\\begin{tabular}{', i)
        if k < 0:
            out.append(s[i:])
            break
        out.append(s[i:k])
        b = k + len('\\begin{tabular}')
        e = match_brace(s, b)
        out.append(repl(re.match(r'(.*)', s[b + 1:e], re.S)))
        i = e + 1
    return ''.join(out)


def strip_wrapper_cmd(s, name, nargs_before):
    """\\name{a}{b}{content} -> content (content is the last argument)."""
    return replace_cmd(s, name, nargs_before + 1, lambda *a: a[-1])


class Converter:
    def __init__(self):
        self.labels = load_labels()
        self.figures = []
        self.ref_map = {}

    def ref_text(self, label):
        num = self.labels.get(label)
        if num is None:
            print('warning: missing label', label, file=sys.stderr)
            num = '??'
        return '\\href{#REF-%s}{%s}' % (label, fa(num))

    def preprocess(self, src, chap_num):
        s = src
        s = re.sub(r'(?<!\\)%[^\n]*', '', s)
        s = re.sub(r'\\newcommand\{\\gl\}\[2\]\{[^\n]*\n', '\n', s)

        def take_fig(m):
            self.figures.append(m.group(0))
            return '\n\nJZFIG:%d\n\n' % (len(self.figures) - 1)
        s = re.sub(r'\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}', take_fig, s, flags=re.S)

        title = None
        m = re.search(r'\\chapter\*?\{', s)
        if m:
            b = m.end() - 1
            e = match_brace(s, b)
            title = s[b + 1:e]
            s = s[:m.start()] + s[e + 1:]
        s = re.sub(r'\\label\{ch:[^}]*\}', '', s)
        s = replace_cmd(s, 'addcontentsline', 3, lambda *a: '')
        s = replace_cmd(s, 'markboth', 2, lambda *a: '')
        s = replace_cmd(s, 'needspace', 1, lambda *a: '')
        s = replace_cmd(s, 'renewcommand', 2, lambda *a: '')
        s = s.replace('\\begingroup', '').replace('\\endgroup', '')
        s = re.sub(r'\\begin\{multicols\}\{\d+\}', '', s).replace('\\end{multicols}', '')
        s = strip_wrapper_cmd(s, 'resizebox', 2)
        s = re.sub(r'\\setlength\{[^}]*\}\{[^}]*\}', '', s)
        s = re.sub(r'\\\\\[[0-9.]+(mm|pt|em|cm)\]', r'\\\\', s)
        s = re.sub(r'\\(smallskip|medskip|bigskip|noindent|hfill|centering|par)(?![A-Za-z])', ' ', s)
        s = re.sub(r'\\vspace\{[^}]*\}', '', s)
        s = re.sub(r'\\(semifont|lightfont|headfont|mediumfont|small|normalsize|large|Large|scriptsize|footnotesize)(?![A-Za-z])', '', s)

        s = replace_cmd(s, 'ref', 1, self.ref_text)
        s = replace_cmd(s, 'term', 2, lambda a, b: '\\textbf{%s} (\\foreignlanguage{english}{%s})' % (a, b))
        s = replace_cmd(s, 'enterm', 1, lambda a: '(\\foreignlanguage{english}{%s})' % a)
        s = replace_cmd(s, 'en', 1, lambda a: '\\foreignlanguage{english}{%s}' % a)
        s = replace_cmd(s, 'lr', 1, lambda a: '\\foreignlanguage{english}{%s}' % a)
        s = replace_cmd(s, 'fa', 1, lambda a: a)
        s = replace_cmd(s, 'rl', 1, lambda a: a)
        s = replace_cmd(s, 'hl', 1, lambda a: '\\textbf{%s}' % a)
        s = replace_cmd(s, 'textcolor', 2, lambda c, a: a)
        s = replace_cmd(s, 'paragraph', 1, lambda a: '\\textbf{%s} ' % a)
        s = replace_cmd(s, 'gl', 2, lambda a, b: '\n\nJZGL %s JZSEP %s\n\n' % (a, b))
        s = re.sub(r'\\newcommand\{\\gl\}\[2\]', '', s)

        s = s.replace('\\begin{enumerate}[label=(\\alph*)]', '\\begin{enumerate}[(a)]')
        s = s.replace('\\begin{enumerate}[label=(\\roman*)]', '\\begin{enumerate}[(i)]')
        s = s.replace('\\begin{enumerate}[label=\\roman*.]', '\\begin{enumerate}[i.]')
        s = s.replace('\\begin{enumerate}[resume]', '\\begin{enumerate}\n\\setcounter{enumi}{4}')
        s = simplify_tabular(s)

        counter = [0]

        def box_open(m):
            kind = m.group(1)
            j = m.end()
            opt = ''
            if j < len(s_ref[0]) and s_ref[0][j] == '[':
                k = match_bracket(s_ref[0], j)
                opt = s_ref[0][j + 1:k]
                j = k + 1
            return kind, opt, j

        out = []
        s_ref = [s]
        i = 0
        pat = re.compile(r'\\begin\{(%s|keyformula)\}' % '|'.join(list(NUMBERED) + list(UNNUMBERED) + list(PROOFS)))
        while True:
            m = pat.search(s, i)
            if not m:
                out.append(s[i:])
                break
            out.append(s[i:m.start()])
            kind, opt, j = box_open(m)
            label = ''
            k = skip_ws(s, j)
            lm = re.match(r'\\label\{([^}]*)\}', s[k:])
            if lm:
                label = lm.group(1)
                j = k + lm.end()
            if kind == 'keyformula':
                out.append('\n\nJZKEY\n\n')
            elif kind in PROOFS:
                out.append('\n\nJZPROOF:%s\n\n' % kind)
                if opt.strip():
                    out.append('JZBOXTITLE %s\n\n' % opt)
            else:
                num = ''
                if kind in NUMBERED:
                    counter[0] += 1
                    if chap_num is None:
                        num = fa('2-5')
                    elif chap_num == 'a':
                        num = 'آ-' + fa(counter[0])
                    else:
                        num = fa('%s-%d' % (chap_num, counter[0]))
                out.append('\n\nJZBOX:%s:%s:%s\n\n' % (kind, num, label))
                if opt.strip():
                    out.append('JZBOXTITLE %s\n\n' % opt)
            i = j
        s = ''.join(out)
        s = re.sub(r'\\end\{(%s|keyformula)\}' % '|'.join(list(NUMBERED) + list(UNNUMBERED) + list(PROOFS)),
                   '\n\nJZCLOSE\n\n', s)
        return title, s

    def pandoc(self, tex, prefix):
        r = subprocess.run(['pandoc', '-f', 'latex', '-t', 'html5', '--katex', '--section-divs',
                            '--shift-heading-level-by=1', '--wrap=none', '--id-prefix=' + prefix],
                           input=tex.encode('utf-8'), capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode())
        if r.stderr:
            for line in r.stderr.decode().splitlines():
                if 'Skipped' not in line:
                    print('pandoc:', line, file=sys.stderr)
        return r.stdout.decode('utf-8')

    def postprocess(self, h, view_id, chap_num):
        h = re.sub(r'style="text-align: left;"', 'style="text-align: start;"', h)
        h = re.sub(r'style="text-align: right;"', 'style="text-align: end;"', h)
        h = re.sub(r'<table>', '<div class="table-wrap"><table>', h)
        h = re.sub(r'</table>', '</table></div>', h)

        def fig(m):
            return '<figure class="fig"><img src="%s" alt="" loading="lazy" decoding="async"></figure>' % self.fig_uri(int(m.group(1)))
        h = re.sub(r'<p>JZFIG:(\d+)</p>', fig, h)

        def box(m):
            kind, num, label = m.group(1), m.group(2), m.group(3)
            title = m.group(5)
            name = NUMBERED.get(kind) or UNNUMBERED.get(kind)
            ident = ''
            if label:
                bid = re.sub(r'[^A-Za-z0-9-]', '-', label)
                self.ref_map[label] = bid
                ident = ' id="%s"' % bid
            head = '<span class="box-kind">%s%s</span>' % (name, (' ' + num) if num else '')
            if title:
                head += ' <span class="box-name">(%s)</span>' % title
            return '<div class="box box-%s"%s><div class="box-title">%s</div><div class="box-body">' % (kind, ident, head)
        h = re.sub(r'<p>JZBOX:(\w+):([^:<]*):([^<]*)</p>\s*(<p>JZBOXTITLE (.*?)</p>)?', box, h, flags=re.S)

        def proof(m):
            kind = m.group(1)
            title = m.group(3)
            lab = PROOFS[kind] + ((' ' + title) if title else '')
            return '<div class="box-%s"><div class="box-body"><span class="proof-label">%s.</span> ' % (kind, lab)
        h = re.sub(r'<p>JZPROOF:(\w+)</p>\s*(<p>JZBOXTITLE (.*?)</p>)?', proof, h, flags=re.S)
        h = h.replace('<p>JZKEY</p>', '<div class="keyformula"><div class="box-body">')
        h = h.replace('<p>JZCLOSE</p>', '</div></div>')
        h = re.sub(r'(<span class="proof-label">[^<]*</span> )\s*<p>', r'<p>\1', h)

        def gl(m):
            items = re.findall(r'<p>JZGL (.*?) JZSEP (.*?)</p>', m.group(0), flags=re.S)
            rows = ''.join('<div class="gl-row"><dt lang="en" dir="ltr">%s</dt><dd>%s</dd></div>' % (a.strip(), b.strip()) for a, b in items)
            return '<dl class="glossary">%s</dl>' % rows
        h = re.sub(r'(?:<p>JZGL .*?</p>\s*)+', gl, h, flags=re.S)

        h = re.sub(r'<section id="([^"]*)" class="(level\d[^"]*)">\s*<h(\d)([^>]*)>', r'<section class="\2"><h\3 id="\1"\4>', h)
        sec = [0, 0]
        cn = 'a' if chap_num == 'a' else chap_num

        def heading(m):
            level, attrs, inner = int(m.group(1)), m.group(2), m.group(3)
            old = re.search(r'id="([^"]*)"', attrs)
            unnumbered = 'unnumbered' in attrs
            num = ''
            if level == 2 and not unnumbered:
                sec[0] += 1
                sec[1] = 0
                new_id = 's-%s-%d' % (cn, sec[0])
                if chap_num is not None:
                    num = ('آ' if chap_num == 'a' else fa(chap_num)) + '-' + fa(sec[0])
            elif level == 3 and not unnumbered:
                sec[1] += 1
                new_id = 's-%s-%d-%d' % (cn, sec[0], sec[1])
                if chap_num is not None:
                    num = ('آ' if chap_num == 'a' else fa(chap_num)) + '-' + fa(sec[0]) + '-' + fa(sec[1])
            else:
                new_id = '%s-h-%d' % (view_id, m.start())
            if chap_num is None:
                new_id = 'pre-%d-%d' % (level, m.start())
            return '<h%d id="%s" data-num="%s">%s%s</h%d>' % (
                level, new_id, num, ('<span class="secnum">%s</span>' % num) if num else '', inner, level), (old.group(1) if old else None), new_id

        out = []
        i = 0
        for m in re.finditer(r'<h([2-6])([^>]*)>(.*?)</h\1>', h, flags=re.S):
            out.append(h[i:m.start()])
            text, old, new_id = heading(m)
            out.append(text)
            if old:
                self.ref_map[old.split(view_id + '-', 1)[-1]] = new_id
            i = m.end()
        out.append(h[i:])
        h = ''.join(out)
        h = re.sub(r'<section id="[^"]*" class="(level\d)( unnumbered)?">', r'<section class="\1">', h)
        h = re.sub(r'<p><br />', '<p>', h)
        h = h.replace('<hr />', '')
        return h

    def fig_uri(self, k):
        path = os.path.join(TMP, 'fig-%02d.svg' % (k + 1))
        data = open(path, 'rb').read()
        return 'data:image/svg+xml;base64,' + base64.b64encode(data).decode()

    def build_figures(self):
        os.makedirs(TMP, exist_ok=True)
        doc = ['\\documentclass[11pt]{book}', '\\usepackage[active,tightpage]{preview}', '\\input{tex/preamble}',
               '\\PreviewEnvironment{tikzpicture}', '\\setlength\\PreviewBorder{4pt}', '\\begin{document}']
        for f in self.figures:
            doc.append(f)
            doc.append('')
        doc.append('\\end{document}')
        open(os.path.join(TMP, 'figs.tex'), 'w', encoding='utf-8').write('\n'.join(doc))
        for _ in range(2):
            r = subprocess.run(['xelatex', '-interaction=nonstopmode', '-halt-on-error', '-output-directory=' + TMP,
                                os.path.join(TMP, 'figs.tex')], cwd=ROOT, capture_output=True)
            if r.returncode != 0:
                print(r.stdout.decode()[-3000:], file=sys.stderr)
                raise RuntimeError('figure build failed')
        pdf = os.path.join(TMP, 'figs.pdf')
        for k in range(len(self.figures)):
            out = os.path.join(TMP, 'fig-%02d.svg' % (k + 1))
            subprocess.run(['pdftocairo', '-svg', '-f', str(k + 1), '-l', str(k + 1), pdf, out], check=True)
            svg = open(out, encoding='utf-8').read()
            svg = re.sub(r'(\d+\.\d{2})\d+', r'\1', svg)
            svg = re.sub(r'>\s+<', '><', svg)
            open(out, 'w', encoding='utf-8').write(svg)


def katex_css():
    base = os.path.join(WEB, 'node_modules', 'katex', 'dist')
    css = open(os.path.join(base, 'katex.min.css'), encoding='utf-8').read()

    def font(m):
        name = m.group(1)
        data = open(os.path.join(base, 'fonts', name + '.woff2'), 'rb').read()
        return 'src:url(data:font/woff2;base64,%s) format("woff2")' % base64.b64encode(data).decode()
    css = re.sub(r'src:url\(fonts/([A-Za-z0-9_-]+)\.woff2\) format\("woff2"\)(,url\([^)]*\) format\("[a-z]+"\))*', font, css)
    return css


def main():
    conv = Converter()
    parts = []
    for view_id, path, num in CHAPTERS:
        src = open(os.path.join(ROOT, path), encoding='utf-8').read()
        title, tex = conv.preprocess(src, num)
        parts.append((view_id, num, title, tex))
    conv.build_figures()

    views = []
    for view_id, num, title, tex in parts:
        body = conv.pandoc(tex, view_id + '-')
        body = conv.postprocess(body, view_id, num)
        views.append({'id': view_id, 'num': num, 'title': title, 'html': body})

    def fix_refs(h):
        def r(m):
            label = m.group(1)
            target = conv.ref_map.get(label)
            if not target:
                print('warning: unresolved ref', label, file=sys.stderr)
                return 'href="#home"'
            return 'href="#%s"' % target
        return re.sub(r'href="#[^"]*?REF-([^"]+)"', r, h)

    for v in views:
        v['html'] = fix_refs(v['html'])
        v['title'] = re.sub(r'\\[A-Za-z]+\{([^}]*)\}', r'\1', v['title'] or '')
        sections = re.findall(r'<h2 id="([^"]*)" data-num="([^"]*)">(?:<span class="secnum">[^<]*</span>)?(.*?)</h2>', v['html'], flags=re.S)
        v['sections'] = [{'id': a, 'num': b, 'title': re.sub(r'<[^>]+>', '', c)} for a, b, c in sections]

    template = open(os.path.join(WEB, 'template.html'), encoding='utf-8').read()
    style = open(os.path.join(WEB, 'style.css'), encoding='utf-8').read()
    app = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()

    chapter_html = []
    for v in views:
        if v['id'] == 'preface':
            label = ''
        elif v['num'] == 'a':
            label = 'پیوست'
        else:
            label = 'فصل ' + fa(v['num'])
        nav_idx = views.index(v)
        prev_v = views[nav_idx - 1] if nav_idx > 0 else None
        next_v = views[nav_idx + 1] if nav_idx + 1 < len(views) else None
        nav = '<nav class="pager" aria-label="فصل قبل و بعد">'
        nav += ('<a class="pager-prev" href="#%s"><span>قبلی</span>%s</a>' % (prev_v['id'], html.escape(prev_v['title']))) if prev_v else '<a class="pager-prev" href="#home"><span>قبلی</span>صفحه‌ی اول</a>'
        nav += ('<a class="pager-next" href="#%s"><span>بعدی</span>%s</a>' % (next_v['id'], html.escape(next_v['title']))) if next_v else ''
        nav += '</nav>'
        chapter_html.append(
            '<article class="view chapter" id="%s" hidden>'
            '<header class="chapter-head"><p class="chapter-label">%s</p><h1>%s</h1><span class="chapter-mark" aria-hidden="true">%s</span></header>'
            '%s%s</article>' % (v['id'], label, html.escape(v['title']), ('آ' if v['num'] == 'a' else fa(v['num'])) if v['num'] is not None else '', v['html'], nav))

    toc = [{'id': v['id'], 'label': ('' if v['id'] == 'preface' else ('پیوست' if v['num'] == 'a' else 'فصل ' + fa(v['num']))),
            'title': v['title'], 'sections': v['sections']} for v in views]

    page = template
    page = page.replace('/*KATEX_CSS*/', katex_css())
    page = page.replace('/*STYLE*/', style)
    page = page.replace('<!--CHAPTERS-->', '\n'.join(chapter_html))
    page = page.replace('/*TOC_JSON*/', json.dumps(toc, ensure_ascii=False))
    page = page.replace('/*APP_JS*/', app)

    os.makedirs(OUT, exist_ok=True)
    pdf_local = 'jozve.pdf'
    full = page.replace('{{PDF_URL}}', pdf_local)
    art = page.replace('{{PDF_URL}}', 'https://github.com/radanmohseni86-ctrl/Linear-algebra/blob/ccr-42ffc7e1-6vj25y/jozve.pdf')
    head = ('<!doctype html>\n<html lang="fa" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="description" content="جزوه‌ی کامل درس جبر خطی (CE282) دانشگاه صنعتی شریف، با اثبات‌ها، مثال‌های حل‌شده و تمرین.">\n'
            '<meta property="og:title" content="جزوه‌ی جبر خطی">\n'
            '<meta property="og:description" content="جزوه‌ی درس جبر خطی (CE282) دانشگاه صنعتی شریف: از دستگاه معادلات تا ضرب داخلی و نُرم.">\n'
            '<meta property="og:type" content="website">\n'
            '<meta name="theme-color" content="#1d4e89">\n')
    full_doc = head + full.replace('<!--BODY-->', '</head>\n<body>', 1) + '\n</body>\n</html>\n'
    art_doc = art.replace('<!--BODY-->', '', 1)
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(full_doc)
    open(os.path.join(OUT, 'artifact.html'), 'w', encoding='utf-8').write(art_doc)
    open(os.path.join(OUT, '.nojekyll'), 'w').write('')
    shutil.copy(os.path.join(ROOT, 'jozve.pdf'), os.path.join(OUT, 'jozve.pdf'))
    print('figures:', len(conv.figures))
    print('index.html: %.1f KB' % (os.path.getsize(os.path.join(OUT, 'index.html')) / 1024))


if __name__ == '__main__':
    main()
