"""
موسوعة القواعد الفقهية — dorar.net/qfiqhia
مخرج: ملف EPUB — الهوامش في نهاية كل صفحة مرتبطة بمواضعها
"""

import requests
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

LEVEL_PATTERNS = [
    (1, re.compile(r'^(الباب|القسم|الكتاب|تمهيد)\b')),
    (2, re.compile(r'^(الفصل|المقدمة)\b')),
    (3, re.compile(r'^(المبحث)\b')),
    (4, re.compile(r'^(المطلب)\b')),
    (5, re.compile(r'^(الفرع)\b')),
    (6, re.compile(r'^(المسألة|التنبيه|الفائدة|المَسألة|مَسألة)\b')),
]
HTML_HEADING = {1:"h1", 2:"h2", 3:"h3", 4:"h4", 5:"h5", 6:"h6"}

def detect_level(title):
    clean = title.strip().lstrip("#").strip()
    for lvl, pat in LEVEL_PATTERNS:
        if pat.search(clean): return lvl
    return 3

BOOK_CSS = """\
body {
    direction: rtl;
    font-family: "Amiri", "Traditional Arabic", "Scheherazade New", "Arial", sans-serif;
    font-size: 1.1em; line-height: 1.9;
    margin: 1.5em 2em; color: #1a1a1a; background: #fafaf8;
}
h1,h2,h3,h4,h5,h6 { font-weight:bold; margin-top:1.4em; margin-bottom:0.4em; color:#2c3e50; }
h1 { font-size:1.6em; border-bottom:2px solid #7f8c8d; padding-bottom:0.3em; }
h2 { font-size:1.4em; } h3 { font-size:1.25em; }
h4 { font-size:1.1em; } h5,h6 { font-size:1em; color:#555; }
p  { margin:0.6em 0; text-align:justify; }
.aaya   { font-size:1.15em; color:#1a5276; font-weight:bold; }
.hadith { color:#1e8449; font-style:italic; }
.footnotes {
    margin-top: 2.5em;
    padding-top: 0.8em;
    border-top: 2px solid #bdc3c7;
    font-size: 0.88em;
    color: #555;
}
.footnotes p { margin:0.35em 0; line-height: 1.6; }
sup { font-size: 0.75em; line-height: 0; }
sup a { color:#2980b9; text-decoration:none; }
.fn-backref { color:#999; font-size:0.85em; text-decoration:none; margin-right:0.3em; }
.source-link { display:block; margin-top:0.5em; font-size:0.8em; color:#999; }
hr { border:none; border-top:1px solid #ddd; margin:1.5em 0; }
"""

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s

def get_page(session, url, referer=INDEX):
    session.headers["Referer"] = referer
    try:
        r = session.get(url, timeout=20)
        print(f"  [{r.status_code}] {url}")
        return r.text if r.status_code == 200 else ""
    except Exception as e:
        print(f"  [ERR] {url} — {e}")
        return ""

SECTION_RE = re.compile(r"^/qfiqhia/(\d+)(?:/|$)")

def get_id_from_url(url):
    m = SECTION_RE.match(url.replace(BASE,""))
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
        return og["content"].split(" - ", 1)[-1].strip()
    t = soup.find("title")
    if t: return t.get_text().split(" - ")[-1].strip()
    return ""

def get_next_link(html):
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=SECTION_RE):
        if "التالي" in a.get_text():
            return BASE + a["href"]
    return None

def convert_inner_soup(soup_tag):
    for inner in soup_tag.find_all("span", class_="aaya"):
        inner.replace_with(f"﴿{inner.get_text(strip=True)}﴾")
    for inner in soup_tag.find_all("span", class_="hadith"):
        inner.replace_with(f"«{inner.get_text(strip=True)}»")
    for inner in soup_tag.find_all("span", class_="sora"):
        t = inner.get_text(strip=True)
        if t: inner.replace_with(f" {t} ")

def get_tip_text(tip) -> str:
    for attr in ("data-original-title","data-content","data-tippy-content"):
        val = tip.get(attr,"").strip()
        if val:
            s = BeautifulSoup(val,"html.parser")
            convert_inner_soup(s)
            return re.sub(r'\s+',' ', s.get_text()).strip()
    text = re.sub(r'\s+',' ', tip.get_text()).strip()
    text = re.sub(r'^\s*\[?\d+\]?\s*','', text).strip()
    return text

# ✅ الإصلاح: استبدال \uf\w+ غير الصالحة بنطاق Unicode PUA الصحيح
_PUA_RE = re.compile(r'[\ue000-\uf8ff]')

def _clean_sora(span) -> str:
    text = span.get_text(strip=True)
    text = _PUA_RE.sub('', text).strip()
    return text

def extract_content(html: str, page_id: str) -> dict:
    """
    page_id: معرّف فريد للصفحة — يُستخدم كـ prefix لـ anchors الهوامش
    كل هامش: anchor في النص  id="ref-{page_id}-{n}"
              تعريف في الأسفل id="fn-{page_id}-{n}"
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["nav","header","footer","script","style","form"]):
        tag.decompose()

    cntnt = soup.find("div", id="cntnt") or \
            soup.find("div", class_="card-body") or \
            soup.find("body") or soup

    for sel in ["div.card-title","div.dorar-bg-lightGreen","div.collapse",
                "div.smooth-scroll","div.white.z-depth-1","span.scroll-pos",
                "div.d-flex.justify-content-between","#enc-tip"]:
        for tag in cntnt.select(sel): tag.decompose()

    for h3 in cntnt.find_all("h3", id="more-titles"):
        nxt = h3.find_next_sibling("ul")
        if nxt: nxt.decompose()
        h3.decompose()

    content_div = cntnt.find("div", class_=lambda c: c and "w-100" in c and "mt-4" in c) \
                  or cntnt

    for span in content_div.find_all("span", class_="sora"):
        span.replace_with(f" {_clean_sora(span)} ")

    # الحواشي
    tips_map, tip_counter = {}, [1]
    for tip in reversed(list(content_div.find_all("span", class_="tip"))):
        tip_text = get_tip_text(tip)
        if tip_text:
            tips_map[tip_counter[0]] = tip_text
            tip.replace_with(f"\x01{tip_counter[0]}\x01")
            tip_counter[0] += 1
        else:
            tip.decompose()

    # تحويل العلامات → HTML
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

    # النص مع مراجع الهوامش — anchors فريدة بـ page_id
    all_footnotes     = []   # [(fn_anchor, ref_anchor, نص)]
    global_fn_counter = [1]
    raw_text          = content_div.get_text(separator="\n")

    def replace_marker(m, _t=tips_map, _f=all_footnotes,
                       _c=global_fn_counter, _pid=page_id):
        tid      = int(m.group(1))
        body     = _t.get(tid, '')
        n        = _c[0]
        fn_id    = f"fn-{_pid}-{n}"    # anchor الهامش في الأسفل
        ref_id   = f"ref-{_pid}-{n}"   # anchor المرجع في النص
        _f.append((fn_id, ref_id, n, body))
        ref = (f'<sup id="{ref_id}">'
               f'<a href="#{fn_id}">[{n}]</a>'
               f'</sup>')
        _c[0] += 1
        return ref

    processed = _TIP_RE.sub(replace_marker, raw_text)
    processed = re.sub(r'[ \t]+', ' ', processed)
    processed = re.sub(r'\n{3,}', '\n\n', processed)

    html_parts = []
    for para in re.split(r'\n{2,}', processed.strip()):
        para = para.strip()
        if para:
            html_parts.append(para if para.startswith('<h') else f'<p>{para}</p>')

    # قسم الهوامش في نهاية الصفحة مع رابط رجوع لكل هامش
    footnotes_html = ""
    if all_footnotes:
        fn_lines = ['<div class="footnotes">',
                    '<hr/>',
                    '<p><strong>الهوامش</strong></p>']
        for fn_id, ref_id, n, body in all_footnotes:
            fn_lines.append(
                f'<p id="{fn_id}">'
                f'<a class="fn-backref" href="#{ref_id}">↑</a>'
                f'<sup>[{n}]</sup> {body}'
                f'</p>'
            )
        fn_lines.append('</div>')
        footnotes_html = "\n".join(fn_lines)

    return {
        "text_html"     : "\n".join(html_parts),
        "footnotes_html": footnotes_html,
        "fn_count"      : len(all_footnotes),
    }


def build_epub_html(title, level, url, parsed):
    htag = HTML_HEADING.get(level, "h3")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ar" lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="../styles/book.css"/>
</head>
<body>
  <{htag}>{title}</{htag}>
  <a class="source-link" href="{url}">{url}</a>
  <hr/>
  {parsed['text_html']}
  {parsed['footnotes_html']}
</body>
</html>"""


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
  <h1>موسوعة القواعد الفقهية</h1>
  <p>الدرر السنية</p>
  <p><a href="{INDEX}">{INDEX}</a></p>
  <p>عدد الصفحات: {len(pages)}</p>
</body></html>"""
    cover = epub.EpubHtml(uid="cover", file_name="cover.xhtml", lang="ar", direction="rtl")
    cover.content = cover_html.encode("utf-8")
    cover.add_item(css_item)
    book.add_item(cover)

    epub_items  = [cover]
    toc_entries = []

    for page in pages:
        item = epub.EpubHtml(uid=page["file_id"],
                             file_name=f"pages/{page['file_id']}.xhtml",
                             lang="ar", direction="rtl")
        item.content = page["html_content"].encode("utf-8")
        item.add_item(css_item)
        book.add_item(item)
        epub_items.append(item)

        lvl = page["level"]
        if lvl == 1:
            sec = epub.Section(page["title"], href=f"pages/{page['file_id']}.xhtml")
            toc_entries.append((sec, []))
        else:
            indent = "  " * (lvl - 1)
            link   = epub.Link(href=f"pages/{page['file_id']}.xhtml",
                               title=indent + page["title"], uid=page["file_id"])
            parent = next((toc_entries[i] for i in range(len(toc_entries)-1,-1,-1)
                           if isinstance(toc_entries[i], tuple)), None)
            if parent: parent[1].append(link)
            else:       toc_entries.append(link)

    def flatten_toc(entries):
        result = []
        for e in entries:
            if isinstance(e, tuple):
                sec, children = e
                result.append((sec, flatten_toc(children)) if children else sec)
            else: result.append(e)
        return result

    book.toc   = flatten_toc(toc_entries)
    book.spine = ["nav"] + epub_items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    os.makedirs(OUT_DIR, exist_ok=True)
    epub.write_epub(EPUB_OUT, book)
    print(f"\n  ✔ EPUB: {EPUB_OUT}  |  {len(pages)} صفحة  "
          f"|  ~{os.path.getsize(EPUB_OUT)//1024} KB")


if __name__ == "__main__":
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        session = make_session()
        print("① تهيئة الجلسة...")
        get_page(session, BASE, referer=BASE); time.sleep(1.5)
        print("\n② جلب صفحة الفهرس...")
        html_index = get_page(session, INDEX, referer=BASE); time.sleep(2)
        if not html_index: raise SystemExit("فشل جلب الفهرس")

        current_url = get_first_link(html_index)
        print(f"\n③ بدء التتبع من: {current_url}\n{'='*60}")
        all_pages, page_count, visited = [], 0, set()
        lvl_names = {1:"باب",2:"فصل",3:"مبحث",4:"مطلب",5:"فرع",6:"مسألة"}

        while current_url and current_url not in visited:
            visited.add(current_url)
            pid  = get_id_from_url(current_url) or page_count
            html = get_page(session, current_url, referer=INDEX); time.sleep(DELAY)
            if not html: break

            title  = get_page_title(html)
            level  = detect_level(title)
            parsed = extract_content(html, page_id=f"p{pid}")
            page_count += 1
            print(f"  [{page_count}] L{level}({lvl_names.get(level,'؟')}) | "
                  f"{title[:50]}  → {parsed['fn_count']} هامش")

            all_pages.append({
                "file_id"     : f"p{pid:05d}",
                "url"         : current_url,
                "title"       : title,
                "level"       : level,
                "html_content": build_epub_html(title, level, current_url, parsed),
            })

            if TEST_PAGES and page_count >= TEST_PAGES:
                print(f"\n  [اختبار] توقف عند {TEST_PAGES}"); break
            current_url = get_next_link(html)

        print(f"\n④ بناء الـ EPUB ({len(all_pages)} صفحة)...")
        build_epub(all_pages)
        print("\n✔ اكتمل.")
    except SystemExit as e: print(e)
    except Exception: traceback.print_exc()