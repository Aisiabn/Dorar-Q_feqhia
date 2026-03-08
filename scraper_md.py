"""
موسوعة القواعد الفقهية — dorar.net/qfiqhia
مخرج: ملفات Markdown — الهوامش في نهاية كل صفحة مرتبطة بمواضعها
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import os
import traceback

BASE    = "https://dorar.net"
INDEX   = "https://dorar.net/qfiqhia"
DELAY   = 1.0
OUT_DIR = "dorar_qfiqhia"

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
HEADING = {1:"##", 2:"###", 3:"####", 4:"#####", 5:"######", 6:"#######"}

def detect_level(title):
    clean = title.strip().lstrip("#").strip()
    for lvl, pat in LEVEL_PATTERNS:
        if pat.search(clean): return lvl
    return 3

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

def _clean_sora(span) -> str:
    text = span.get_text(strip=True)
    text = re.sub(r'\s*\uf\w+\s*','', text).strip()
    return text

def extract_content(html: str, page_id: str) -> dict:
    """
    page_id: معرّف فريد للصفحة لتجنب تعارض أرقام الهوامش بين الصفحات
    يُعيد النص مع مراجع الهوامش، والهوامش كقائمة جاهزة للطباعة في نهاية الصفحة
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

    # span.sora
    for span in content_div.find_all("span", class_="sora"):
        span.replace_with(f" {_clean_sora(span)} ")

    # الحواشي — نستخدم page_id كـ prefix للـ anchor لضمان الفرادة
    tips_map, tip_counter = {}, [1]
    for tip in reversed(list(content_div.find_all("span", class_="tip"))):
        tip_text = get_tip_text(tip)
        if tip_text:
            tips_map[tip_counter[0]] = tip_text
            tip.replace_with(f"\x01{tip_counter[0]}\x01")
            tip_counter[0] += 1
        else:
            tip.decompose()

    # تحويل العلامات
    for span in content_div.find_all("span", class_="aaya"):
        span.replace_with(f"﴿{span.get_text(strip=True)}﴾")
    for span in content_div.find_all("span", class_="hadith"):
        span.replace_with(f"«{span.get_text(strip=True)}»")
    for span in content_div.find_all("span", class_="title-2"):
        span.replace_with(f"\n#### {span.get_text(strip=True)}\n")
    for span in content_div.find_all("span", class_="title-1"):
        span.replace_with(f"\n##### {span.get_text(strip=True)}\n")
    for i in range(1,7):
        for h in content_div.find_all(f"h{i}"):
            h.replace_with(f"\n{'#'*(i+2)} {h.get_text(strip=True)}\n")
    for p in content_div.find_all("p"):
        p.insert_before("\n\n"); p.insert_after("\n\n")
    for a in content_div.find_all("a"):
        if re.search(r"السابق|التالي|انظر أيضا|الرابط المختصر|مشاركة", a.get_text(strip=True)):
            a.decompose()

    # النص مع مراجع الهوامش — anchor فريد: {page_id}-fn{N}
    footnotes  = []   # قائمة نصوص جاهزة للطباعة
    fn_counter = [1]
    text       = content_div.get_text(separator="\n", strip=False)

    def replace_marker(m, _t=tips_map, _f=footnotes, _c=fn_counter, _pid=page_id):
        tid  = int(m.group(1))
        body = _t.get(tid, '')
        n    = _c[0]
        # مرجع في النص: [^{pid}-fn{N}]
        # تعريف الهامش: [^{pid}-fn{N}]: النص
        _f.append(f"[^{_pid}-fn{n}]: {body}")
        ref = f" [^{_pid}-fn{n}]"
        _c[0] += 1
        return ref

    text = _TIP_RE.sub(replace_marker, text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'(?<!\n)\n(?![\n#>﴿«\d])', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    return {"text": text, "footnotes": footnotes}


def fix_multiline_footnotes(text):
    lines, result, fn_def = text.splitlines(), [], re.compile(r'^\[\^')
    i = 0
    while i < len(lines):
        line = lines[i]
        if fn_def.match(line):
            parts = [line.rstrip()]; i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt == '' or fn_def.match(nxt): break
                parts.append(nxt.strip()); i += 1
            result.append(' '.join(p for p in parts if p))
        else:
            result.append(line); i += 1
    return '\n'.join(result)


def save_markdown(pages, file_num):
    if not pages: return
    top      = pages[0]
    safe     = re.sub(r'[^\w\u0600-\u06FF]','_', top["title"])[:50]
    filepath = os.path.join(OUT_DIR, f"{file_num:04d}_{safe}.md")

    lines = [f"# {top['title']}\n\n> {top['url']}\n\n---\n\n"]
    total_fn = 0

    for page in pages:
        heading = HEADING.get(page["level"], "####")

        # ── عنوان الصفحة + رابط المصدر
        lines.append(f"{heading} {page['title']}\n\n")
        lines.append(f"> {page['url']}\n\n")

        # ── المحتوى
        if page.get("text"):
            lines.append(f"{page['text']}\n\n")

        # ── هوامش الصفحة مباشرة بعد محتواها
        if page.get("footnotes"):
            total_fn += len(page["footnotes"])
            for fn in page["footnotes"]:
                lines.append(f"{fn}\n")
            lines.append("\n")

        lines.append("---\n\n")

    content = fix_multiline_footnotes("".join(lines))
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    total = sum(len(p.get("text","")) for p in pages)
    print(f"  ✔ {filepath}  |  {len(pages)} صفحة  |  ~{total//1024} KB  |  {total_fn} هامش")


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
        current_group, file_num = [], 1
        page_count, visited = 0, set()
        lvl_names = {1:"باب",2:"فصل",3:"مبحث",4:"مطلب",5:"فرع",6:"مسألة"}

        while current_url and current_url not in visited:
            visited.add(current_url)
            pid  = get_id_from_url(current_url) or page_count
            html = get_page(session, current_url, referer=INDEX); time.sleep(DELAY)
            if not html: break

            title  = get_page_title(html)
            level  = detect_level(title)
            # page_id فريد لكل صفحة لتجنب تعارض anchors الهوامش
            parsed = extract_content(html, page_id=f"p{pid}")
            page_count += 1
            print(f"  [{page_count}] L{level}({lvl_names.get(level,'؟')}) | "
                  f"{title[:50]}  → {len(parsed['text'])} حرف | {len(parsed['footnotes'])} هامش")

            if level == 1 and current_group:
                save_markdown(current_group, file_num)
                file_num += 1; current_group = []

            current_group.append({"url": current_url, "title": title,
                                  "level": level, **parsed})

            if TEST_PAGES and page_count >= TEST_PAGES:
                print(f"\n  [اختبار] توقف عند {TEST_PAGES}"); break
            current_url = get_next_link(html)

        if current_group:
            save_markdown(current_group, file_num)

        print(f"\n✔ اكتمل: {page_count} صفحة → {file_num} ملف")
    except SystemExit as e: print(e)
    except Exception: traceback.print_exc()