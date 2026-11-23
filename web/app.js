(function () {
  const MACROS = {
    '\\R': '\\mathbb{R}', '\\C': '\\mathbb{C}', '\\Q': '\\mathbb{Q}', '\\Z': '\\mathbb{Z}',
    '\\N': '\\mathbb{N}', '\\F': '\\mathbb{F}', '\\Rn': '\\mathbb{R}^n', '\\Rm': '\\mathbb{R}^m',
    '\\vect': '\\mathbf{#1}', '\\zero': '\\mathbf{0}',
    '\\Span': '\\operatorname{Span}', '\\rank': '\\operatorname{rank}', '\\nullity': '\\operatorname{nullity}',
    '\\tr': '\\operatorname{trace}', '\\RREF': '\\operatorname{RREF}', '\\ColRank': '\\operatorname{ColRank}',
    '\\RowRank': '\\operatorname{RowRank}', '\\dist': '\\operatorname{dist}',
    '\\Null': '\\operatorname{Null}', '\\Range': '\\operatorname{Range}',
    '\\Col': 'C', '\\Nul': 'N', '\\Row': 'R',
    '\\inner': '\\left\\langle #1,#2\\right\\rangle',
    '\\norm': '\\left\\lVert #1\\right\\rVert',
    '\\abs': '\\left\\lvert #1\\right\\rvert',
    '\\T': '^{\\mathsf{T}}',
    '\\conj': '\\overline{#1}',
    '\\coord': '\\left[#1\\right]_{#2}',
    '\\aug': '\\left[\\,#1\\;\\middle|\\;#2\\,\\right]',
    '\\rowop': '\\xrightarrow{\\;#1\\;}',
    '\\Ri': 'R_{#1}'
  };
  'abcdenpqrsuvwxyz'.split('').forEach(function (c) { MACROS['\\v' + c] = '\\mathbf{' + c + '}'; });

  const toFa = function (n) { return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[d]; }); };
  const views = Array.from(document.querySelectorAll('.view'));
  const crumb = document.getElementById('crumb');

  function renderMath(root) {
    if (!window.katex) return;
    const els = root.querySelectorAll('.math:not([data-done])');
    const warn = console.warn;
    console.warn = function (msg) { if (typeof msg === 'string' && msg.indexOf('No character metrics') === 0) return; warn.apply(console, arguments); };
    els.forEach(function (el) {
      const display = el.classList.contains('display');
      try {
        window.katex.render(el.textContent, el, {
          displayMode: display, macros: Object.assign({}, MACROS), throwOnError: false, strict: 'ignore', output: 'html'
        });
      } catch (e) { }
      if (!display) {
        el.classList.add('keep');
        if (el.getBoundingClientRect().width > window.innerWidth * 0.42) el.classList.remove('keep');
      }
      el.setAttribute('data-done', '');
    });
    console.warn = warn;
  }

  function tocMarkup(currentId) {
    let out = '<ol>';
    TOC.forEach(function (ch) {
      const cur = ch.id === currentId;
      out += '<li class="toc-ch"><a href="#' + ch.id + '"' + (cur ? ' aria-current="page"' : '') + (ch.label ? '' : ' class="no-num"') + '>' +
        (ch.label ? '<span class="toc-num">' + ch.label + '</span>' : '') + '<span>' + ch.title + '</span></a>';
      if (cur && ch.sections.length) {
        out += '<ol class="toc-secs">';
        ch.sections.forEach(function (s) {
          out += '<li><a href="#' + s.id + '">' + (s.num ? '<span class="sn">' + s.num + '</span>' : '') + s.title + '</a></li>';
        });
        out += '</ol>';
      }
      out += '</li>';
    });
    return out + '</ol>';
  }

  function updateToc(currentId) {
    const html = tocMarkup(currentId);
    document.getElementById('toc-side').innerHTML = html;
    document.getElementById('toc-drawer').innerHTML = html;
  }

  function buildHome() {
    const grid = document.getElementById('chapter-grid');
    let out = '';
    TOC.forEach(function (ch) {
      if (ch.id === 'preface') return;
      const secs = ch.sections.slice(0, 4).map(function (s) { return '<li>' + s.title + '</li>'; }).join('');
      out += '<li class="chapter-card"><span class="cc-num">' + ch.label + '</span><a href="#' + ch.id + '">' + ch.title + '</a><ul>' + secs + '</ul></li>';
    });
    grid.innerHTML = out;
  }

  const FA_CHARS = '\\u0600-\\u06FF\\u200c';
  let termRe = null;

  function buildTermRe() {
    const keys = Object.keys(TERMS).sort(function (a, b) { return b.length - a.length; });
    if (!keys.length) return null;
    const alt = keys.map(function (k) { return k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|');
    return new RegExp('(?<![' + FA_CHARS + '])(' + alt + ')((?:\\u200c?(?:ی|هایی|های|ها))?)(?![' + FA_CHARS + '])', 'g');
  }

  const SKIP = 'h1,h2,h3,h4,.box-title,.math,.katex,a,[lang="en"],script,style,.tt,.pager,.chapter-head,table.glossary';

  function annotateTerms(view) {
    if (view.hasAttribute('data-terms') || view.id === 'appendix' || view.id === 'home') return;
    view.setAttribute('data-terms', '');
    if (!termRe) termRe = buildTermRe();
    if (!termRe) return;
    const walker = document.createTreeWalker(view, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!n.nodeValue || n.nodeValue.length < 3) return NodeFilter.FILTER_REJECT;
        const p = n.parentElement;
        if (!p || p.closest(SKIP)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (node) {
      const text = node.nodeValue;
      termRe.lastIndex = 0;
      let m, last = 0, frag = null;
      while ((m = termRe.exec(text))) {
        if (!frag) frag = document.createDocumentFragment();
        if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        const span = document.createElement('span');
        span.className = 'tt';
        span.tabIndex = 0;
        span.setAttribute('data-en', TERMS[m[1]]);
        span.textContent = m[0];
        frag.appendChild(span);
        last = m.index + m[0].length;
      }
      if (frag) {
        if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
        node.parentNode.replaceChild(frag, node);
      }
    });
  }

  const tip = document.createElement('div');
  tip.className = 'term-tip';
  tip.setAttribute('role', 'tooltip');
  tip.hidden = true;
  document.body.appendChild(tip);
  let tipTimer = 0;
  let tipY = 0;

  function showTip(el) {
    clearTimeout(tipTimer);
    tipY = window.pageYOffset;
    tip.textContent = el.getAttribute('data-en');
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    let left = r.left + r.width / 2 - t.width / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - t.width - 8));
    let top = r.top - t.height - 8;
    if (top < 8) top = r.bottom + 8;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }

  function hideTip() { clearTimeout(tipTimer); tip.hidden = true; }

  document.addEventListener('mouseover', function (e) {
    const el = e.target.closest && e.target.closest('.tt');
    if (el) showTip(el);
  });
  let lastTouch = 0;
  document.addEventListener('touchstart', function () { lastTouch = Date.now(); }, { passive: true });
  document.addEventListener('mouseout', function (e) {
    if (Date.now() - lastTouch < 1200) return;
    if (e.target.closest && e.target.closest('.tt')) hideTip();
  });
  document.addEventListener('focusin', function (e) {
    const el = e.target.closest && e.target.closest('.tt');
    if (el) showTip(el);
  });
  document.addEventListener('focusout', function () {
    if (Date.now() - lastTouch < 1200) return;
    hideTip();
  });
  document.addEventListener('click', function (e) {
    const el = e.target.closest && e.target.closest('.tt');
    if (el) {
      showTip(el);
      tipTimer = setTimeout(hideTip, 2800);
    } else {
      hideTip();
    }
  });
  window.addEventListener('scroll', function () {
    if (!tip.hidden && Math.abs(window.pageYOffset - tipY) > 24) hideTip();
  }, { passive: true });

  function show(viewId, target) {
    let view = null;
    views.forEach(function (v) {
      const on = v.id === viewId;
      v.hidden = !on;
      if (on) view = v;
    });
    if (!view) return;
    annotateTerms(view);
    renderMath(view);
    updateToc(viewId);
    const entry = TOC.find(function (c) { return c.id === viewId; });
    crumb.textContent = entry ? (entry.label ? entry.label + ' · ' : '') + entry.title : '';
    if (target && target !== view) {
      requestAnimationFrame(function () {
        target.scrollIntoView({ block: 'start' });
        if (target.classList.contains('box')) {
          target.classList.remove('flash');
          void target.offsetWidth;
          target.classList.add('flash');
        }
      });
    } else {
      window.scrollTo(0, 0);
    }
  }

  function route() {
    let id = '';
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (e) { id = ''; }
    if (!id) return show('home');
    const el = document.getElementById(id);
    if (!el) return show('home');
    const view = el.closest('.view');
    if (!view) return show('home');
    show(view.id, el);
  }

  buildHome();
  window.addEventListener('hashchange', route);
  route();

  const drawer = document.getElementById('drawer');
  const openBtn = document.getElementById('drawer-open');
  const closeBtn = document.getElementById('drawer-close');
  const scroller = drawer.querySelector('.Drawer-scroller');
  const sheet = drawer.querySelector('.Drawer-sheet');
  const page = [document.querySelector('.layout'), document.querySelector('.topbar')];
  const closedLeft = function () { return -scroller.scrollWidth; };

  async function openDrawer() {
    if (!drawer.showPopover) return;
    drawer.showPopover();
    if (!CSS.supports('scroll-initial-target', 'nearest')) {
      scroller.scrollTo({ left: closedLeft(), behavior: 'instant' });
      await new Promise(function (r) { requestAnimationFrame(function () { requestAnimationFrame(r); }); });
    }
    scroller.scrollTo({ left: 0, behavior: 'auto' });
  }
  function closeDrawer() {
    if (!drawer.matches(':popover-open')) return;
    scroller.scrollTo({ left: closedLeft(), behavior: 'auto' });
  }
  function onOpened() {
    page.forEach(function (p) { p.inert = true; });
    openBtn.setAttribute('aria-expanded', 'true');
    sheet.focus();
  }
  function onClosed() {
    if (drawer.matches(':popover-open')) drawer.hidePopover();
    page.forEach(function (p) { p.inert = false; });
    if (openBtn.getAttribute('aria-expanded') === 'true') openBtn.focus();
    openBtn.setAttribute('aria-expanded', 'false');
  }
  const threshold = 1 / window.innerWidth;
  new IntersectionObserver(function (entries) {
    const e = entries[entries.length - 1];
    if (e.intersectionRatio < threshold) onClosed();
    if (e.intersectionRatio === 1) onOpened();
  }, { root: drawer, threshold: [threshold, 1] }).observe(sheet);

  if (!CSS.supports('animation-timeline: scroll()')) {
    scroller.addEventListener('scroll', function () {
      const ratio = 1 - Math.abs(scroller.scrollLeft) / sheet.offsetWidth;
      drawer.style.setProperty('--drawer-backdrop', Math.max(0, Math.min(1, ratio)));
    });
  }
  openBtn.addEventListener('click', openDrawer);
  closeBtn.addEventListener('click', closeDrawer);
  drawer.addEventListener('click', function (e) {
    if (!sheet.contains(e.target)) closeDrawer();
    else if (e.target.closest('a')) closeDrawer();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeDrawer(); });
})();
