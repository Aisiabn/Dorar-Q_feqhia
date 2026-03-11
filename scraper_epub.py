"""
موسوعة القواعد الفقهية — dorar.net/qfiqhia
مخرج: ملف EPUB
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
OUT_DIR  = "dorar_qfiqhia"
EPUB_OUT = os.path.join(OUT_DIR, "موسوعة_القواعد_الفقهية.epub")

TEST_PAGES = None if os.environ.get("TEST_PAGES") == "None" else (
    int(os.environ["TEST_PAGES"]) if os.environ.get("TEST_PAGES") else None
)

_TIP_RE = re.compile(r'\x01(\d+)\x01')
HTML_HEADING = {1:"h1", 2:"h2", 3:"h3", 4:"h4", 5:"h5", 6:"h6"}
INDEX_LEVELS = {1, 2, 3}

CHILD_LABELS = {
    2: ("فصل",  "فصلان",  "فصول"),
    3: ("مبحث", "مبحثان", "مباحث"),
    4: ("مطلب", "مطلبان", "مطالب"),
}
NUM_WORDS = ['', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة',
             'ستة', 'سبعة', 'ثمانية', 'تسعة', 'عشرة']

def count_label(n, child_level):
    sing, dual, plur = CHILD_LABELS.get(child_level, ("قسم", "قسمان", "أقسام"))
    if n == 1: return f"{sing} واحد"
    if n == 2: return dual
    if 3 <= n <= 10: return f"{NUM_WORDS[n]} {plur}"
    return f"{n} {plur}"

def short_hash(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:8]

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
.footnotes {
    margin-top: 2.5em; padding-top: 0.8em;
    border-top: 2px solid #bdc3c7; font-size: 0.88em; color: #555;
}
.footnotes p { margin:0.35em 0; line-height: 1.6; }
sup { font-size: 0.75em; line-height: 0; }
sup a { color:#2980b9; text-decoration:none; }
.fn-backref { color:#999; font-size:0.85em; text-decoration:none; margin-right:0.3em; }
.source-link { display:block; margin-top:0.5em; font-size:0.8em; color:#999; }
hr { border:none; border-top:1px solid #ddd; margin:1.5em 0; }
"""

# ─── الصفحات الملحقة ─────────────────────────────────────────
FRONT_PAGES_SPEC = [
    {"url": "https://dorar.net/article/2117", "title": "منهج العمل في الموسوعة",  "level": 1, "file_id": "p00001_front"},
    {"url": "https://dorar.net/article/2118", "title": "اعتماد منهجية الموسوعة", "level": 1, "file_id": "p00002_front"},
]
BACK_PAGES_SPEC = [
    {"url": "https://dorar.net/refs/qfiqhia", "title": "المراجع المعتمدة", "level": 1, "file_id": "p99999_back"},
]

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
            if r.status_code == 200:
                return r.text
            if r.status_code in (429, 503, 520, 521, 522, 524):
                wait = attempt * 10
                print(f"  [retry {attempt}/{retries}] انتظار {wait}s...")
                time.sleep(wait)
                continue
            return ""
        except Exception as e:
            print(f"  [ERR attempt {attempt}] {url} — {e}")
            time.sleep(attempt * 5)
    print(f"  [FAILED] {url}")
    return ""

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
    if t:
        return t.get_text().split(" - ")[0].strip()
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

def convert_inner_soup(soup_tag):
    for inner in soup_tag.find_all("span", class_="aaya"):
        inner.replace_with(f"﴿{inner.get_text(strip=True)}﴾")
    for inner in soup_tag.find_all("span", class_="hadith"):
        inner.replace_with(f"«{inner.get_text(strip=True)}»")
    for inner in soup_tag.find_all("span", class_="sora"):
        t = inner.get_text(strip=True)
        if t: inner.replace_with(f" {t} ")

def get_tip_text(tip) -> str:
    for attr in ("data-original-title", "data-content", "data-tippy-content"):
        val = tip.get(attr, "").strip()
        if val:
            s = BeautifulSoup(val, "html.parser")
            convert_inner_soup(s)
            return re.sub(r'\s+', ' ', s.get_text()).strip()
    text = re.sub(r'\s+', ' ', tip.get_text()).strip()
    return re.sub(r'^\s*\[?\d+\]?\s*', '', text).strip()

def _clean_sora(span) -> str:
    return re.sub(r'[\ue000-\uf8ff]', '', span.get_text(strip=True)).strip()

def extract_content(html: str, page_id: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "form"]):
        tag.decompose()

    cntnt = soup.find("div", id="cntnt") or \
            soup.find("div", class_="card-body") or \
            soup.find("body") or soup

    for sel in ["div.card-title", "div.dorar-bg-lightGreen", "div.collapse",
                "div.smooth-scroll", "div.white.z-depth-1", "span.scroll-pos",
                "div.d-flex.justify-content-between", "#enc-tip"]:
        for tag in cntnt.select(sel): tag.decompose()

    for h3 in cntnt.find_all("h3", id="more-titles"):
        nxt = h3.find_next_sibling("ul")
        if nxt: nxt.decompose()
        h3.decompose()

    content_div = cntnt.find("div", class_=lambda c: c and "w-100" in c and "mt-4" in c) \
                  or cntnt

    for span in content_div.find_all("span", class_="sora"):
        span.replace_with(f" {_clean_sora(span)} ")

    tips_map, tip_counter = {}, [1]
    for tip in reversed(list(content_div.find_all("span", class_="tip"))):
        tip_text = get_tip_text(tip)
        if tip_text:
            tips_map[tip_counter[0]] = tip_text
            tip.replace_with(f"\x01{tip_counter[0]}\x01")
            tip_counter[0] += 1
        else:
            tip.decompose()

    for span in content_div.find_all("span", class_="aaya"):
        span.replace_with(f'<span class="aaya">﴿{span.get_text(strip=True)}﴾</span>')
    for span in content_div.find_all("span", class_="hadith"):
        span.replace_with(f'<span class="hadith">«{span.get_text(strip=True)}»</span>')
    for span in content_div.find_all("span", class_="title-2"):
        span.replace_with(f'<h4>{span.get_text(strip=True)}</h4>')
    for span in content_div.find_all("span", class_="title-1"):
        span.replace_with(f'<h5>{span.get_text(strip=True)}</h5>')
    for a in content_div.find_all("a"):
        if re.search(r"السابق|التالي|انظر أيضا|الرابط المختصر|مشاركة", a.get_text(strip=True)):
            a.decompose()

    all_footnotes     = []
    global_fn_counter = [1]
    raw_text          = content_div.get_text(separator="\n")

    def replace_marker(m):
        tid    = int(m.group(1))
        body   = tips_map.get(tid, '')
        n      = global_fn_counter[0]
        fn_id  = f"fn-{page_id}-{n}"
        ref_id = f"ref-{page_id}-{n}"
        all_footnotes.append((fn_id, ref_id, n, body))
        global_fn_counter[0] += 1
        return f'<sup id="{ref_id}"><a href="#{fn_id}">[{n}]</a></sup>'

    processed = _TIP_RE.sub(replace_marker, raw_text)
    processed = re.sub(r'[ \t]+', ' ', processed)
    processed = re.sub(r'\n{3,}', '\n\n', processed)

    html_parts = []
    for para in re.split(r'\n{2,}', processed.strip()):
        para = para.strip()
        if para:
            html_parts.append(para if para.startswith('<h') else f'<p>{para}</p>')

    footnotes_html = ""
    if all_footnotes:
        fn_lines = ['<div class="footnotes">', '<hr/>', '<p><strong>الهوامش</strong></p>']
        for fn_id, ref_id, n, body in all_footnotes:
            fn_lines.append(f'<p id="{fn_id}"><a class="fn-backref" href="#{ref_id}">↑</a><sup>[{n}]</sup> {body}</p>')
        fn_lines.append('</div>')
        footnotes_html = "\n".join(fn_lines)

    return {"text_html": "\n".join(html_parts), "footnotes_html": footnotes_html, "fn_count": len(all_footnotes)}


def build_real_page_html(title, level, url, parsed):
    htag = HTML_HEADING.get(level, "h3")
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


def extract_refs_content(html: str) -> dict:
    """مستخرج خاص لصفحة refs/qfiqhia — كل مرجع في <article class='border-bottom'>"""
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select("article.border-bottom")
    parts = []
    for art in articles:
        h5    = art.find("h5")
        title = h5.get_text(strip=True) if h5 else ""
        fields = []
        for strong in art.find_all("strong"):
            label = strong.get_text(strip=True).rstrip(":")
            span  = strong.find("span")
            value = span.get_text(strip=True) if span else ""
            if value and value != "بدون":
                fields.append(f"{label}: {value}")
        meta = " | ".join(fields)
        parts.append(f"<p><strong>{title}</strong><br/>{meta}</p>")
    return {"text_html": "\n".join(parts), "footnotes_html": "", "fn_count": 0}


def fetch_extra_pages(session, specs):
    result = []
    for spec in specs:
        html = get_page(session, spec["url"], referer=INDEX)
        if not html:
            print(f"  [SKIP] {spec['url']}")
            continue
        fetched_title = get_page_title(html)
        title = fetched_title if fetched_title else spec["title"]

        # صفحة المراجع لها مستخرج خاص
        if "refs/" in spec["url"]:
            parsed = extract_refs_content(html)
        else:
            parsed = extract_content(html, page_id=spec["file_id"])

        print(f"  [ملحق] {title}  → {parsed['fn_count']} هامش")
        result.append({
            "file_id"     : spec["file_id"],
            "url"         : spec["url"],
            "title"       : title,
            "level"       : spec["level"],
            "breadcrumb"  : [title],
            "is_index"    : False,
            "html_content": build_real_page_html(title, spec["level"], spec["url"], parsed),
        })
        time.sleep(DELAY)
    return result


# ─── صفحات الفهرس ────────────────────────────────────────────
def build_section_tree(real_pages):
    sections, order = {}, []
    for page in real_pages:
        bc = page["breadcrumb"]
        for depth in range(min(3, len(bc) - 1)):
            lvl, title = depth + 1, bc[depth]
            key = (lvl, title)
            if key not in sections:
                sections[key] = {"title": title, "level": lvl, "children": []}
                order.append(key)
            if depth + 1 < len(bc):
                child = bc[depth + 1]
                if child not in sections[key]["children"]:
                    sections[key]["children"].append(child)
    return {k: sections[k] for k in order}

def make_index_page_html(sec):
    title, level, children = sec["title"], sec["level"], sec["children"]
    htag  = HTML_HEADING.get(level, "h2")
    label = count_label(len(children), level + 1)
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

def build_final_pages(real_pages, sections):
    inserted, final = set(), []
    for page in real_pages:
        bc = page["breadcrumb"]
        for depth in range(min(3, len(bc) - 1)):
            key = (depth + 1, bc[depth])
            if key not in inserted and key in sections:
                inserted.add(key)
                sec = sections[key]
                fid = f"idx{depth+1}_{short_hash(sec['title'])}"
                final.append({
                    "file_id"     : fid,
                    "title"       : sec["title"],
                    "level"       : sec["level"],
                    "breadcrumb"  : bc[:depth + 1],
                    "is_index"    : True,
                    "html_content": make_index_page_html(sec),
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
            if i < len(stack) and stack[i][0] == t: common = i + 1
            else: break
        stack = stack[:common]
        for i in range(common, len(ancestors)):
            children = []
            parent = stack[i-1][1] if i > 0 else root
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
                parent_list = stack[-2][1] if len(stack) >= 2 else root
                for i, e in enumerate(parent_list):
                    if isinstance(e, tuple) and e[0].title == page["title"]:
                        parent_list[i] = (epub.Section(page["title"], href=href), e[1])
                        break
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
        else:
            result.append(e)
    return result


def build_epub(pages):
    book = epub.EpubBook()
    book.set_identifier("dorar-qfiqhia-2025")
    book.set_title("موسوعة القواعد الفقهية")
    book.set_language("ar")
    book.add_author("الدرر السنية")
    book.set_direction("rtl")

    css_item = epub.EpubItem(uid="book_css", file_name="styles/book.css",
                             media_type="text/css", content=BOOK_CSS.encode("utf-8"))
    book.add_item(css_item)

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
    cover.content = cover_html.encode("utf-8")
    cover.add_item(css_item)
    book.add_item(cover)

    epub_items = [cover]
    for page in pages:
        item = epub.EpubHtml(uid=page["file_id"],
                             file_name=f"pages/{page['file_id']}.xhtml",
                             lang="ar", direction="rtl")
        item.content = page["html_content"].encode("utf-8")
        item.add_item(css_item)
        book.add_item(item)
        epub_items.append(item)

    book.toc   = build_toc(pages)
    book.spine = ["nav"] + epub_items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    os.makedirs(OUT_DIR, exist_ok=True)
    epub.write_epub(EPUB_OUT, book)
    print(f"\n  ✔ EPUB: {EPUB_OUT}  |  {len(pages)} صفحة  |  ~{os.path.getsize(EPUB_OUT)//1024} KB")


if __name__ == "__main__":
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        session = make_session()
        print("① تهيئة الجلسة...")
        get_page(session, BASE, referer=BASE); time.sleep(1.5)

        print("\n② جلب صفحة الفهرس...")
        html_index = get_page(session, INDEX, referer=BASE); time.sleep(2)
        if not html_index: raise SystemExit("فشل جلب الفهرس")

        print("\n③-أ جلب صفحات البداية (منهج + اعتماد)...")
        real_pages = fetch_extra_pages(session, FRONT_PAGES_SPEC)

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
            parsed = extract_content(html, page_id=f"p{pid}")
            page_count += 1
            print(f"  [{page_count}] L{level}({lvl_names.get(level,'؟')}) | {title[:50]}  → {parsed['fn_count']} هامش")

            real_pages.append({
                "file_id"     : f"p{pid:05d}",
                "url"         : current_url,
                "title"       : title,
                "level"       : level,
                "breadcrumb"  : breadcrumb,
                "is_index"    : False,
                "html_content": build_real_page_html(title, level, current_url, parsed),
            })

            if TEST_PAGES and page_count >= TEST_PAGES:
                print(f"\n  [اختبار] توقف عند {TEST_PAGES}"); break
            current_url = get_next_link(html)

        print("\n③-ج جلب صفحات النهاية (المراجع)...")
        real_pages += fetch_extra_pages(session, BACK_PAGES_SPEC)

        print(f"\n④ بناء صفحات الفهارس...")
        sections  = build_section_tree(real_pages)
        all_pages = build_final_pages(real_pages, sections)
        idx_count = sum(1 for p in all_pages if p.get("is_index"))
        print(f"   {idx_count} فهرس + {page_count} فعلية + {len(real_pages)-page_count} ملحق = {len(all_pages)} إجمالاً")

        print(f"\n⑤ بناء الـ EPUB...")
        build_epub(all_pages)
        print("\n✔ اكتمل.")
    except SystemExit as e: print(e)
    except Exception: traceback.print_exc()