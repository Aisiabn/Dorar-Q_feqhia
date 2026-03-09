"""
موسوعة القواعد الفقهية — dorar.net/qfiqhia
مخرج: ملفات Markdown
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import os
import traceback

BASE     = "https://dorar.net"
INDEX    = "https://dorar.net/qfiqhia"
DELAY    = 1.0
OUT_DIR  = "dorar_md"

TEST_PAGES = None if os.environ.get("TEST_PAGES") == "None" else (
    int(os.environ["TEST_PAGES"]) if os.environ.get("TEST_PAGES") else None
)

_TIP_RE    = re.compile(r'\x01(\d+)\x01')
MD_HEADING = {1:"#", 2:"##", 3:"###", 4:"####", 5:"#####", 6:"######"}

CHILD_LABELS = {
    2: ("فصل",  "فصلان",  "فصول"),
    3: ("مبحث", "مبحثان", "مباحث"),
    4: ("مطلب", "مطلبان", "مطالب"),
}
NUM_WORDS = ['','واحد','اثنان','ثلاثة','أربعة','خمسة',
             'ستة','سبعة','ثمانية','تسعة','عشرة']

def count_label(n, child_level):
    sing, dual, plur = CHILD_LABELS.get(child_level, ("قسم","قسمان","أقسام"))
    if n == 1: return f"{sing} واحد"
    if n == 2: return dual
    if 3 <= n <= 10: return f"{NUM_WORDS[n]} {plur}"
    return f"{n} {plur}"

def safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:80]

# ─── الصفحات الملحقة ─────────────────────────────────────────
FRONT_PAGES_SPEC = [
    {"url": "https://dorar.net/article/2117", "title": "منهج العمل في الموسوعة",  "level": 1, "file_id": "front_01"},
    {"url": "https://dorar.net/article/2118", "title": "اعتماد منهجية الموسوعة", "level": 1, "file_id": "front_02"},
]
BACK_PAGES_SPEC = [
    {"url": "https://dorar.net/refs/qfiqhia", "title": "المراجع المعتمدة", "level": 1, "file_id": "back_01"},
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

def extract_markdown(html: str, title: str, level: int, url: str) -> str:
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
        span.replace_with(f"﴿{span.get_text(strip=True)}﴾")
    for span in content_div.find_all("span", class_="hadith"):
        span.replace_with(f"«{span.get_text(strip=True)}»")
    for span in content_div.find_all("span", class_="title-2"):
        span.replace_with(f"\n#### {span.get_text(strip=True)}\n")
    for span in content_div.find_all("span", class_="title-1"):
        span.replace_with(f"\n##### {span.get_text(strip=True)}\n")
    for a in content_div.find_all("a"):
        if re.search(r"السابق|التالي|انظر أيضا|الرابط المختصر|مشاركة", a.get_text(strip=True)):
            a.decompose()

    raw = content_div.get_text(separator="\n")
    footnotes  = []
    fn_counter = [1]

    def replace_marker(m):
        tid  = int(m.group(1))
        body = tips_map.get(tid, '')
        n    = fn_counter[0]
        footnotes.append((n, body))
        fn_counter[0] += 1
        return f"[^{n}]"

    raw = _TIP_RE.sub(replace_marker, raw)
    raw = re.sub(r'[ \t]+', ' ', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw).strip()

    hashes = MD_HEADING.get(level, "###")
    lines  = [f"{hashes} {title}", "", f"> المصدر: {url}", "", raw, ""]
    if footnotes:
        lines += ["---", "**الهوامش**", ""]
        for n, body in footnotes:
            lines.append(f"[^{n}]: {body}")
    return "\n".join(lines)


def fetch_extra_pages(session, specs):
    result = []
    for spec in specs:
        html = get_page(session, spec["url"], referer=INDEX)
        if not html:
            print(f"  [SKIP] {spec['url']}"); continue
        fetched_title = get_page_title(html)
        title = fetched_title if fetched_title else spec["title"]
        md    = extract_markdown(html, title, spec["level"], spec["url"])
        print(f"  [ملحق] {title}")
        result.append({
            "pid"       : spec["file_id"],
            "url"       : spec["url"],
            "title"     : title,
            "level"     : spec["level"],
            "breadcrumb": [title],
            "md"        : md,
            "extra"     : True,
        })
        time.sleep(DELAY)
    return result


def build_section_tree(real_pages):
    sections, order = {}, []
    for page in real_pages:
        if page.get("extra"): continue
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

def make_index_md(sec):
    title, level, children = sec["title"], sec["level"], sec["children"]
    hashes = MD_HEADING.get(level, "##")
    label  = count_label(len(children), level + 1)
    lines  = [f"{hashes} {title}", "", f"وفيه {label}:", ""]
    for i, c in enumerate(children, 1):
        lines.append(f"{i}. {c}")
    return "\n".join(lines)

def page_filepath(breadcrumb, pid, is_index=False):
    parts = [safe_filename(p) for p in breadcrumb]
    if is_index:
        folder = os.path.join(OUT_DIR, *parts)
        return os.path.join(folder, "_index.md")
    else:
        folder = os.path.join(OUT_DIR, *parts[:-1]) if len(parts) > 1 else OUT_DIR
        return os.path.join(folder, f"{pid}_{parts[-1]}.md")

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        session = make_session()
        print("① تهيئة الجلسة...")
        get_page(session, BASE, referer=BASE); time.sleep(1.5)

        print("\n② جلب صفحة الفهرس...")
        html_index = get_page(session, INDEX, referer=BASE); time.sleep(2)
        if not html_index: raise SystemExit("فشل جلب الفهرس")

        print("\n③-أ جلب صفحات البداية...")
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
            level = len(breadcrumb)
            page_count += 1
            print(f"  [{page_count}] L{level}({lvl_names.get(level,'؟')}) | {title[:50]}")

            real_pages.append({
                "pid"       : pid,
                "url"       : current_url,
                "title"     : title,
                "level"     : level,
                "breadcrumb": breadcrumb,
                "md"        : extract_markdown(html, title, level, current_url),
            })

            if TEST_PAGES and page_count >= TEST_PAGES:
                print(f"\n  [اختبار] توقف عند {TEST_PAGES}"); break
            current_url = get_next_link(html)

        print("\n③-ج جلب صفحات النهاية (المراجع)...")
        real_pages += fetch_extra_pages(session, BACK_PAGES_SPEC)

        print(f"\n④ كتابة الملفات...")
        sections    = build_section_tree(real_pages)
        written_idx = set()
        idx_count   = 0

        # صفحات البداية → مباشرة في OUT_DIR
        for page in real_pages:
            if page.get("extra"):
                fname = safe_filename(page["title"]) + ".md"
                write_file(os.path.join(OUT_DIR, fname), page["md"])
                continue

            bc = page["breadcrumb"]
            for depth in range(min(3, len(bc) - 1)):
                key = (depth + 1, bc[depth])
                if key not in written_idx and key in sections:
                    written_idx.add(key)
                    path = page_filepath(bc[:depth+1], None, is_index=True)
                    write_file(path, make_index_md(sections[key]))
                    idx_count += 1

            path = page_filepath(bc, page["pid"])
            write_file(path, page["md"])

        # المراجع → مباشرة في OUT_DIR
        print(f"\n✔ اكتمل: {page_count} صفحة + {idx_count} فهرس")
        print(f"  المجلد: {os.path.abspath(OUT_DIR)}")

    except SystemExit as e: print(e)
    except Exception: traceback.print_exc()