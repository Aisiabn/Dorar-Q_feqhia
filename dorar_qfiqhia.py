"""
موسوعة القواعد الفقهية — dorar.net/qfiqhia
مخرج: EPUB + ملفات Markdown
"""

import requests
import hashlib
from bs4 import BeautifulSoup
import re
import time
import os
import traceback
from ebooklib import epub

BASE     = "https://dorar.net"
INDEX    = "https://dorar.net/qfiqhia"
DELAY    = 1.0
EPUB_DIR = "dorar_qfiqhia"
MD_DIR   = "dorar_md"
EPUB_OUT = os.path.join(EPUB_DIR, "موسوعة_القواعد_الفقهية.epub")

TEST_PAGES = None if os.environ.get("TEST_PAGES") == "None" else (
    int(os.environ["TEST_PAGES"]) if os.environ.get("TEST_PAGES") else None
)

_TIP_RE    = re.compile(r'\x01(\d+)\x01')
HTML_HDR   = {1:"h1", 2:"h2", 3:"h3", 4:"h4", 5:"h5", 6:"h6"}
MD_HDR     = {1:"#",  2:"##", 3:"###", 4:"####", 5:"#####", 6:"######"}
INDEX_LVLS = {1, 2, 3}

CHILD_LABELS = {
    2: ("فصل",  "فصلان",  "فصول"),
    3: ("مبحث", "مبحثان", "مباحث"),
    4: ("مطلب", "مطلبان", "مطالب"),
}
NUM_WORDS = ['','واحد','اثنان','ثلاثة','أربعة','خمسة',
             'ستة','سبعة','ثمانية','تسعة','عشرة']

def count_label(n, cl):
    s, d, p = CHILD_LABELS.get(cl, ("قسم","قسمان","أقسام"))
    if n == 1: return f"{s} واحد"
    if n == 2: return d
    if 3 <= n <= 10: return f"{NUM_WORDS[n]} {p}"
    return f"{n} {p}"

def short_hash(s):
    return hashlib.md5(s.encode()).hexdigest()[:8]

def safe_fn(name):
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    return re.sub(r'\s+', '_', name.strip())[:80]

# ─── الصفحات الملحقة ─────────────────────────────────────────
FRONT_SPEC = [
    {"url": "https://dorar.net/article/2117", "title": "منهج العمل في الموسوعة",  "level": 1, "file_id": "p00001_front"},
    {"url": "https://dorar.net/article/2118", "title": "اعتماد منهجية الموسوعة", "level": 1, "file_id": "p00002_front"},
]
BACK_SPEC = [
    {"url": "https://dorar.net/refs/qfiqhia", "title": "المراجع المعتمدة", "level": 1, "file_id": "p99999_back"},
]

BOOK_CSS = """\
body {
    direction: rtl;
    font-family: "Amiri", "Traditional Arabic", "Scheherazade New", "Arial", sans-serif;
    font-size: 1.1em; line-height: 1.9;
    margin: 1.5em 2em; color: #1a1a1a; background: #fafaf8;
}
h1,h2,h3,h4,h5,h6 { font-size:1.1em; font-weight:bold; margin-top:1.4em; margin-bottom:0.4em; color:#2c3e50; }
p  { margin:0.6em 0; text-align:justify; }
ol,ul { margin:0.5em 0 0.5em 1.5em; }
li { margin:0.3em 0; }
.aaya   { font-size:1.15em; color:#1a5276; font-weight:bold; }
.hadith { color:#1e8449; font-style:italic; }
.footnotes { margin-top:2.5em; padding-top:0.8em; border-top:2px solid #bdc3c7; font-size:0.88em; color:#555; }
.footnotes p { margin:0.35em 0; line-height:1.6; }
sup { font-size:0.75em; line-height:0; }
sup a { color:#2980b9; text-decoration:none; }
.fn-backref { color:#999; font-size:0.85em; text-decoration:none; margin-right:0.3em; }
.source-link { display:block; margin-top:0.5em; font-size:0.8em; color:#999; }
hr { border:none; border-top:1px solid #ddd; margin:1.5em 0; }
"""

# ─── الجلسة ───────────────────────────────────────────────────
def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    })
    return s

def get_page(session, url, referer=INDEX, retries=4):
    session.headers["Referer"] = referer
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=20)
            print(f"  [{r.status_code}] {url}")
            if r.status_code == 200: return r.text
            if r.status_code in (429, 503, 520, 521, 522, 524):
                wait = attempt * 10
                print(f"  [retry {attempt}/{retries}] انتظار {wait}s...")
                time.sleep(wait); continue
            return ""
        except Exception as e:
            print(f"  [ERR attempt {attempt}] {url} — {e}")
            time.sleep(attempt * 5)
    print(f"  [FAILED] {url}"); return ""

SECTION_RE = re.compile(r"^/qfiqhia/(\d+)(?:/|$)")

def get_id_from_url(url):
    m = SECTION_RE.match(url.replace(BASE, ""))
    return int(m.group(1)) if m else None

def get_first_link(html):
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=SECTION_RE):
        return BASE + a["href"]
    return f"{BASE}/qfiqhia/1"

def get_page_title(html):
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].split(" - ", 1)[0].strip()
    t = soup.find("title")
    if t: return t.get_text().split(" - ")[0].strip()
    return ""

def get_next_link(html):
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=SECTION_RE):
        if "التالي" in a.get_text():
            return BASE + a["href"]
    return None

def get_breadcrumb(html):
    soup = BeautifulSoup(html, "html.parser")
    for sel in ["ol.breadcrumb li", "ul.breadcrumb li",
                "nav[aria-label='breadcrumb'] li", ".breadcrumb-item"]:
        items = soup.select(sel)
        if items:
            texts = [i.get_text(strip=True) for i in items if i.get_text(strip=True)]
            return texts[2:]
    return []

# ─── استخراج المحتوى ─────────────────────────────────────────
def convert_inner(tag):
    for s in tag.find_all("span", class_="aaya"):
        s.replace_with(f"﴿{s.get_text(strip=True)}﴾")
    for s in tag.find_all("span", class_="hadith"):
        s.replace_with(f"«{s.get_text(strip=True)}»")
    for s in tag.find_all("span", class_="sora"):
        t = s.get_text(strip=True)
        if t: s.replace_with(f" {t} ")

def get_tip_text(tip):
    for attr in ("data-original-title","data-content","data-tippy-content"):
        val = tip.get(attr,"").strip()
        if val:
            s = BeautifulSoup(val,"html.parser")
            convert_inner(s)
            return re.sub(r'\s+',' ',s.get_text()).strip()
    text = re.sub(r'\s+',' ',tip.get_text()).strip()
    return re.sub(r'^\s*\[?\d+\]?\s*','',text).strip()

def clean_sora(span):
    return re.sub(r'[\ue000-\uf8ff]','',span.get_text(strip=True)).strip()

def get_content_div(html):
    soup = BeautifulSoup(html,"html.parser")
    for tag in soup.find_all(["nav","header","footer","script","style","form"]):
        tag.decompose()
    cntnt = soup.find("div",id="cntnt") or soup.find("div",class_="card-body") or soup.find("body") or soup
    for sel in ["div.card-title","div.dorar-bg-lightGreen","div.collapse",
                "div.smooth-scroll","div.white.z-depth-1","span.scroll-pos",
                "div.d-flex.justify-content-between","#enc-tip"]:
        for t in cntnt.select(sel): t.decompose()
    for h3 in cntnt.find_all("h3",id="more-titles"):
        n = h3.find_next_sibling("ul")
        if n: n.decompose()
        h3.decompose()
    return cntnt.find("div", class_=lambda c: c and "w-100" in c and "mt-4" in c) or cntnt

def prepare_content(cd):
    """تحضير عناصر المحتوى المشتركة."""
    for span in cd.find_all("span", class_="sora"):
        span.replace_with(f" {clean_sora(span)} ")
    tips_map, tip_counter = {}, [1]
    for tip in reversed(list(cd.find_all("span", class_="tip"))):
        tt = get_tip_text(tip)
        if tt:
            tips_map[tip_counter[0]] = tt
            tip.replace_with(f"\x01{tip_counter[0]}\x01")
            tip_counter[0] += 1
        else:
            tip.decompose()
    for span in cd.find_all("span", class_="aaya"):
        span.replace_with(f"﴿{span.get_text(strip=True)}﴾")
    for span in cd.find_all("span", class_="hadith"):
        span.replace_with(f"«{span.get_text(strip=True)}»")
    for a in cd.find_all("a"):
        if re.search(r"السابق|التالي|انظر أيضا|الرابط المختصر|مشاركة", a.get_text(strip=True)):
            a.decompose()
    return tips_map

def extract_content_epub(html, page_id):
    cd       = get_content_div(html)
    tips_map = prepare_content(cd)
    for span in cd.find_all("span", class_="title-2"):
        span.replace_with(f'<h4>{span.get_text(strip=True)}</h4>')
    for span in cd.find_all("span", class_="title-1"):
        span.replace_with(f'<h5>{span.get_text(strip=True)}</h5>')

    fns, fn_c = [], [1]
    raw = cd.get_text(separator="\n")

    def rep(m):
        body = tips_map.get(int(m.group(1)),'')
        n = fn_c[0]
        fid, rid = f"fn-{page_id}-{n}", f"ref-{page_id}-{n}"
        fns.append((fid, rid, n, body)); fn_c[0] += 1
        return f'<sup id="{rid}"><a href="#{fid}">[{n}]</a></sup>'

    raw = _TIP_RE.sub(rep, raw)
    raw = re.sub(r'[ \t]+',' ',raw); raw = re.sub(r'\n{3,}','\n\n',raw)
    parts = []
    for p in re.split(r'\n{2,}', raw.strip()):
        p = p.strip()
        if p: parts.append(p if p.startswith('<h') else f'<p>{p}</p>')

    fn_html = ""
    if fns:
        fl = ['<div class="footnotes">','<hr/>','<p><strong>الهوامش</strong></p>']
        for fid,rid,n,body in fns:
            fl.append(f'<p id="{fid}"><a class="fn-backref" href="#{rid}">↑</a><sup>[{n}]</sup> {body}</p>')
        fl.append('</div>'); fn_html = "\n".join(fl)
    return {"text_html":"\n".join(parts), "footnotes_html":fn_html, "fn_count":len(fns)}

def extract_content_md(html, title, level, url):
    cd       = get_content_div(html)
    tips_map = prepare_content(cd)
    for span in cd.find_all("span", class_="title-2"):
        span.replace_with(f"\n#### {span.get_text(strip=True)}\n")
    for span in cd.find_all("span", class_="title-1"):
        span.replace_with(f"\n##### {span.get_text(strip=True)}\n")

    fns, fn_c = [], [1]
    raw = cd.get_text(separator="\n")

    def rep(m):
        body = tips_map.get(int(m.group(1)),'')
        n = fn_c[0]; fns.append((n,body)); fn_c[0] += 1
        return f"[^{n}]"

    raw = _TIP_RE.sub(rep, raw)
    raw = re.sub(r'[ \t]+',' ',raw); raw = re.sub(r'\n{3,}','\n\n',raw).strip()
    h   = MD_HDR.get(level,"###")
    lines = [f"{h} {title}", "", f"> المصدر: {url}", "", raw, ""]
    if fns:
        lines += ["---","**الهوامش**",""]
        for n,body in fns: lines.append(f"[^{n}]: {body}")
    return "\n".join(lines)

# ─── مستخرج المراجع ──────────────────────────────────────────
def extract_refs_epub(html):
    soup     = BeautifulSoup(html,"html.parser")
    articles = soup.select("article.border-bottom")
    parts    = []
    for i, art in enumerate(articles, 1):
        h5    = art.find("h5")
        title = re.sub(r'^\d+[-–]\s*','', h5.get_text(strip=True)) if h5 else ""
        fields = []
        for strong in art.find_all("strong"):
            span  = strong.find("span")
            value = span.get_text(strip=True) if span else ""
            if value and value != "بدون": fields.append(value)
        meta = ". ".join(fields)
        parts.append(f'<p><strong>{i}- {title}.</strong> {meta}.</p>')
    return {"text_html":"\n".join(parts), "footnotes_html":"", "fn_count":0}

def extract_refs_md(html):
    soup     = BeautifulSoup(html,"html.parser")
    articles = soup.select("article.border-bottom")
    lines    = ["# المراجع المعتمدة",""]
    for i, art in enumerate(articles, 1):
        h5    = art.find("h5")
        title = re.sub(r'^\d+[-–]\s*','', h5.get_text(strip=True)) if h5 else ""
        fields = []
        for strong in art.find_all("strong"):
            span  = strong.find("span")
            value = span.get_text(strip=True) if span else ""
            if value and value != "بدون": fields.append(value)
        meta = ". ".join(fields)
        lines.append(f"**{i}- {title}.** {meta}."); lines.append("")
    return "\n".join(lines)

# ─── بناء HTML صفحة EPUB ─────────────────────────────────────
def page_html(title, level, url, parsed):
    htag = HTML_HDR.get(level,"h3")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ar" lang="ar" dir="rtl">
<head><meta charset="utf-8"/><title>{title}</title>
<link rel="stylesheet" type="text/css" href="../styles/book.css"/></head>
<body>
  <{htag}>{title}</{htag}>
  <a class="source-link" href="{url}">{url}</a><hr/>
  {parsed['text_html']}
  {parsed['footnotes_html']}
</body></html>"""

def index_page_html(sec):
    title, level, children = sec["title"], sec["level"], sec["children"]
    htag  = HTML_HDR.get(level,"h2")
    label = count_label(len(children), level+1)
    items = "\n    ".join(f"<li>{c}</li>" for c in children)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ar" lang="ar" dir="rtl">
<head><meta charset="utf-8"/><title>{title}</title>
<link rel="stylesheet" type="text/css" href="../styles/book.css"/></head>
<body>
  <{htag}>{title}</{htag}><hr/>
  <p>وفيه {label}:</p>
  <ol>{items}</ol>
</body></html>"""

def index_md(sec):
    title, level, children = sec["title"], sec["level"], sec["children"]
    h     = MD_HDR.get(level,"##")
    label = count_label(len(children), level+1)
    lines = [f"{h} {title}", "", f"وفيه {label}:", ""]
    for i, c in enumerate(children, 1): lines.append(f"{i}. {c}")
    return "\n".join(lines)

# ─── جلب الصفحات الملحقة ─────────────────────────────────────
def fetch_extra(session, specs):
    result = []
    for spec in specs:
        html = get_page(session, spec["url"], referer=INDEX)
        if not html:
            print(f"  [SKIP] {spec['url']}"); continue
        fetched = get_page_title(html)
        title   = fetched if (fetched and "الدرر السنية" not in fetched) else spec["title"]
        is_refs = "refs/" in spec["url"]

        parsed = extract_refs_epub(html) if is_refs else extract_content_epub(html, spec["file_id"])
        md     = extract_refs_md(html)   if is_refs else extract_content_md(html, title, spec["level"], spec["url"])

        print(f"  [ملحق] {title}  → {parsed['fn_count']} هامش")
        result.append({
            "file_id"     : spec["file_id"],
            "url"         : spec["url"],
            "title"       : title,
            "level"       : spec["level"],
            "breadcrumb"  : [title],
            "is_index"    : False,
            "html_content": page_html(title, spec["level"], spec["url"], parsed),
            "md"          : md,
            "pid"         : spec["file_id"],
        })
        time.sleep(DELAY)
    return result

# ─── شجرة الأقسام وصفحات الفهرس ─────────────────────────────
def build_section_tree(pages):
    sections, order = {}, []
    for page in pages:
        if page.get("extra"): continue
        bc = page["breadcrumb"]
        for d in range(min(3, len(bc)-1)):
            lvl, title = d+1, bc[d]
            key = (lvl, title)
            if key not in sections:
                sections[key] = {"title":title, "level":lvl, "children":[]}
                order.append(key)
            child = bc[d+1] if d+1 < len(bc) else None
            if child and child not in sections[key]["children"]:
                sections[key]["children"].append(child)
    return {k: sections[k] for k in order}

def build_final_pages(real_pages, sections):
    inserted, final = set(), []
    for page in real_pages:
        bc = page["breadcrumb"]
        for d in range(min(3, len(bc)-1)):
            key = (d+1, bc[d])
            if key not in inserted and key in sections:
                inserted.add(key)
                sec = sections[key]
                fid = f"idx{d+1}_{short_hash(sec['title'])}"
                final.append({
                    "file_id"     : fid,
                    "title"       : sec["title"],
                    "level"       : sec["level"],
                    "breadcrumb"  : bc[:d+1],
                    "is_index"    : True,
                    "html_content": index_page_html(sec),
                    "md"          : index_md(sec),
                    "pid"         : fid,
                })
        final.append(page)
    return final

# ─── TOC ─────────────────────────────────────────────────────
def build_toc(pages):
    root, stack = [], []

    def get_children(ancestors):
        nonlocal stack, root
        common = 0
        for i, t in enumerate(ancestors):
            if i < len(stack) and stack[i][0] == t: common = i+1
            else: break
        stack = stack[:common]
        for i in range(common, len(ancestors)):
            children = []
            parent   = stack[i-1][1] if i > 0 else root
            parent.append((epub.Section(ancestors[i], href="#"), children))
            stack.append((ancestors[i], children))
        return stack[-1][1] if stack else root

    for page in pages:
        bc        = page["breadcrumb"]
        href      = f"pages/{page['file_id']}.xhtml"
        ancestors = bc[:-1]
        link      = epub.Link(href=href, title=page["title"], uid=page["file_id"])
        if not ancestors:
            root.append(link)
        else:
            children = get_children(ancestors)
            if page.get("is_index") and stack:
                pl = stack[-2][1] if len(stack) >= 2 else root
                for i, e in enumerate(pl):
                    if isinstance(e, tuple) and e[0].title == page["title"]:
                        pl[i] = (epub.Section(page["title"], href=href), e[1]); break
            children.append(link)
    return _flatten_toc(root)

def _flatten_toc(entries):
    result = []
    for e in entries:
        if isinstance(e, tuple):
            sec, children = e
            flat = _flatten_toc(children)
            result.append((sec, flat) if flat else
                          epub.Link(href=sec.href, title=sec.title, uid=sec.title[:30]))
        else: result.append(e)
    return result

# ─── كتابة EPUB ──────────────────────────────────────────────
def write_epub(pages):
    book = epub.EpubBook()
    book.set_identifier("dorar-qfiqhia-2025")
    book.set_title("موسوعة القواعد الفقهية")
    book.set_language("ar")
    book.add_author("الدرر السنية")
    book.set_direction("rtl")

    css = epub.EpubItem(uid="book_css", file_name="styles/book.css",
                        media_type="text/css", content=BOOK_CSS.encode())
    book.add_item(css)

    cover_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ar" dir="rtl">
<head><meta charset="utf-8"/><title>موسوعة القواعد الفقهية</title>
<link rel="stylesheet" type="text/css" href="styles/book.css"/></head>
<body style="text-align:center;padding-top:3em;">
  <h1>موسوعة القواعد الفقهية</h1><p>الدرر السنية</p>
  <p><a href="{INDEX}">{INDEX}</a></p>
  <p>عدد الصفحات: {len(pages)}</p>
</body></html>"""
    cover = epub.EpubHtml(uid="cover", file_name="cover.xhtml", lang="ar", direction="rtl")
    cover.content = cover_html.encode(); cover.add_item(css)
    book.add_item(cover)

    items = [cover]
    for page in pages:
        item = epub.EpubHtml(uid=page["file_id"],
                             file_name=f"pages/{page['file_id']}.xhtml",
                             lang="ar", direction="rtl")
        item.content = page["html_content"].encode()
        item.add_item(css); book.add_item(item); items.append(item)

    book.toc   = build_toc(pages)
    book.spine = ["nav"] + items
    book.add_item(epub.EpubNcx()); book.add_item(epub.EpubNav())
    os.makedirs(EPUB_DIR, exist_ok=True)
    epub.write_epub(EPUB_OUT, book)
    print(f"\n  ✔ EPUB: {EPUB_OUT}  |  {len(pages)} صفحة  |  ~{os.path.getsize(EPUB_OUT)//1024} KB")

# ─── كتابة Markdown ───────────────────────────────────────────
def md_filepath(breadcrumb, pid, is_index=False):
    parts = [safe_fn(p) for p in breadcrumb]
    if is_index:
        return os.path.join(MD_DIR, *parts, "_index.md")
    folder = os.path.join(MD_DIR, *parts[:-1]) if len(parts) > 1 else MD_DIR
    return os.path.join(folder, f"{pid}_{parts[-1]}.md")

def write_md_files(pages):
    written_idx = set()
    idx_count   = 0
    for page in pages:
        bc = page["breadcrumb"]
        if page.get("is_index"):
            path = md_filepath(bc, None, is_index=True)
        elif len(bc) == 1:
            # صفحة ملحقة → مباشرة في جذر MD_DIR
            path = os.path.join(MD_DIR, f"{safe_fn(page['title'])}.md")
        else:
            path = md_filepath(bc, page["pid"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(page["md"])

# ─── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        os.makedirs(EPUB_DIR, exist_ok=True)
        os.makedirs(MD_DIR,   exist_ok=True)
        session = make_session()

        print("① تهيئة الجلسة...")
        get_page(session, BASE, referer=BASE); time.sleep(1.5)

        print("\n② جلب صفحة الفهرس...")
        html_index = get_page(session, INDEX, referer=BASE); time.sleep(2)
        if not html_index: raise SystemExit("فشل جلب الفهرس")

        print("\n③-أ جلب صفحات البداية...")
        real_pages = fetch_extra(session, FRONT_SPEC)

        current_url = get_first_link(html_index)
        print(f"\n③-ب تتبع الموسوعة من: {current_url}\n{'='*60}")
        page_count = 0
        visited    = set()
        lvl_names  = {1:"باب",2:"فصل",3:"مبحث",4:"مطلب",5:"فرع",6:"مسألة"}

        while current_url and current_url not in visited:
            visited.add(current_url)
            pid  = get_id_from_url(current_url) or page_count
            html = get_page(session, current_url, referer=INDEX); time.sleep(DELAY)
            if not html: break

            title      = get_page_title(html)
            breadcrumb = get_breadcrumb(html)
            if not breadcrumb or breadcrumb[-1] != title:
                breadcrumb.append(title)
            level  = len(breadcrumb)
            parsed = extract_content_epub(html, page_id=f"p{pid}")
            md     = extract_content_md(html, title, level, current_url)
            page_count += 1
            print(f"  [{page_count}] L{level}({lvl_names.get(level,'؟')}) | {title[:50]}  → {parsed['fn_count']} هامش")

            real_pages.append({
                "file_id"     : f"p{pid:05d}",
                "url"         : current_url,
                "title"       : title,
                "level"       : level,
                "breadcrumb"  : breadcrumb,
                "is_index"    : False,
                "html_content": page_html(title, level, current_url, parsed),
                "md"          : md,
                "pid"         : pid,
            })

            if TEST_PAGES and page_count >= TEST_PAGES:
                print(f"\n  [اختبار] توقف عند {TEST_PAGES}"); break
            current_url = get_next_link(html)

        print("\n③-ج جلب صفحات النهاية (المراجع)...")
        real_pages += fetch_extra(session, BACK_SPEC)

        print(f"\n④ بناء صفحات الفهارس...")
        sections  = build_section_tree(real_pages)
        all_pages = build_final_pages(real_pages, sections)
        idx_count = sum(1 for p in all_pages if p.get("is_index"))
        print(f"   {idx_count} فهرس + {page_count} فعلية + {len(real_pages)-page_count} ملحق = {len(all_pages)} إجمالاً")

        print(f"\n⑤ كتابة EPUB...")
        write_epub(all_pages)

        print(f"\n⑥ كتابة Markdown...")
        write_md_files(all_pages)
        print(f"  ✔ MD: {os.path.abspath(MD_DIR)}")

        print("\n✔ اكتمل.")
    except SystemExit as e: print(e)
    except Exception: traceback.print_exc()