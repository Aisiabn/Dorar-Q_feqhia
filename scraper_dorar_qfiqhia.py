"""
موسوعة القواعد الفقهية — dorar.net/qfiqhia
- التنقل التسلسلي عبر زر "التالي"
- اكتشاف المستوى الهرمي من العنوان (باب/فصل/مبحث/مطلب/فرع/مسألة)
- حواشي (tips) مطابق للكود المرجعي تماماً
- تجميع الصفحات في ملفات بحسب الباب/القسم الرئيسي
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import os
import traceback

# ── إعدادات ───────────────────────────────────────────────────────
BASE    = "https://dorar.net"
INDEX   = "https://dorar.net/qfiqhia"
DELAY   = 1.0
OUT_DIR = "dorar_qfiqhia"

TEST_PAGES = None if os.environ.get("TEST_PAGES") == "None" else (
    int(os.environ["TEST_PAGES"]) if os.environ.get("TEST_PAGES") else None
)

_TIP_RE = re.compile(r'\x01(\d+)\x01')

# ── هرم المستويات ─────────────────────────────────────────────────
# الكلمات المفتاحية في العنوان → (رقم المستوى، عمق heading في markdown)
#   المستوى 1 = حد الملف الجديد (باب، قسم، تمهيد مستقل)
#   المستوى 2-6 = مقاطع داخل الملف
LEVEL_PATTERNS = [
    (1, re.compile(r'^(الباب|القسم|الكتاب|تمهيد)\b')),
    (2, re.compile(r'^(الفصل|المقدمة)\b')),
    (3, re.compile(r'^(المبحث)\b')),
    (4, re.compile(r'^(المطلب)\b')),
    (5, re.compile(r'^(الفرع)\b')),
    (6, re.compile(r'^(المسألة|التنبيه|الفائدة|المَسألة|مَسألة)\b')),
]

# عمق heading لكل مستوى: 1→##, 2→###, ...6→#######
HEADING = {1: "##", 2: "###", 3: "####", 4: "#####", 5: "######", 6: "#######"}


def detect_level(title: str) -> int:
    """اكتشف المستوى الهرمي من العنوان. إذا لم يُعرف → 3 (مبحث افتراضي)."""
    clean = title.strip().lstrip("#").strip()
    for lvl, pat in LEVEL_PATTERNS:
        if pat.search(clean):
            return lvl
    return 3  # افتراضي


# ── الجلسة ────────────────────────────────────────────────────────
def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent"               : "Mozilla/5.0 (Windows NT 6.1; WOW64) "
                                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                                     "Chrome/109.0.0.0 Safari/537.36",
        "Accept"                   : "text/html,application/xhtml+xml,application/xml;"
                                     "q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language"          : "ar,en-US;q=0.9,en;q=0.8",
        "Connection"               : "keep-alive",
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


# ── نمط الرابط ───────────────────────────────────────────────────
SECTION_RE = re.compile(r"^/qfiqhia/(\d+)(?:/|$)")


def get_id_from_url(url: str) -> int | None:
    path = url.replace(BASE, "")
    m = SECTION_RE.match(path)
    return int(m.group(1)) if m else None


# ── الفهرس: جلب أول رابط ─────────────────────────────────────────
def get_first_link(html: str) -> str | None:
    """أول رابط قاعدة في صفحة الفهرس."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=SECTION_RE):
        return BASE + a["href"]
    # احتياطي: أول ID معروف
    return f"{BASE}/qfiqhia/1"


def get_page_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    og   = soup.find("meta", property="og:title")
    if og and og.get("content"):
        parts = og["content"].split(" - ", 1)
        return parts[-1].strip()
    t = soup.find("title")
    if t:
        parts = t.get_text().split(" - ")
        return parts[-1].strip()
    return ""


def get_next_link(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=SECTION_RE):
        if "التالي" in a.get_text():
            return BASE + a["href"]
    return None


# ── استخراج المحتوى (مطابق للكود المرجعي) ────────────────────────
def convert_inner_soup(soup_tag):
    for inner in soup_tag.find_all("span", class_="aaya"):
        inner.replace_with(f"﴿{inner.get_text(strip=True)}﴾")
    for inner in soup_tag.find_all("span", class_="hadith"):
        inner.replace_with(f"«{inner.get_text(strip=True)}»")
    for inner in soup_tag.find_all("span", class_="sora"):
        t = inner.get_text(strip=True)
        if t:
            inner.replace_with(f" {t} ")


def get_tip_text(tip) -> str:
    _marker = re.compile(r'\x01\d+\x01')
    for attr in ("data-original-title", "title", "data-content", "data-tippy-content"):
        val = tip.get(attr, "").strip()
        if val:
            inner_soup = BeautifulSoup(val, "html.parser")
            convert_inner_soup(inner_soup)
            result = re.sub(r'\s+', ' ', inner_soup.get_text()).strip()
            return _marker.sub('', result).strip()
    convert_inner_soup(tip)
    result = re.sub(r'\s+', ' ', tip.get_text(strip=True)).strip()
    return _marker.sub('', result).strip()


def extract_content(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "form"]):
        tag.decompose()
    for pat in [
        re.compile(r"\bmodal\b"),
        re.compile(r"\balert-dorar\b"),
        re.compile(r"\btitle-manhag\b"),
        re.compile(r"\bdefault-gradient\b"),
        re.compile(r"\bfooter-copyright\b"),
        re.compile(r"\bcard-personal\b"),
    ]:
        for tag in soup.find_all(True, class_=pat):
            tag.decompose()

    # اختيار block المحتوى
    block = None
    card  = soup.find("div", class_="card-body")
    if card:
        for pane in card.find_all("div", class_="tab-pane"):
            if "active" not in pane.get("class", []):
                continue
            if pane.find("article") or len(pane.get_text(strip=True)) > 200:
                block = pane
                break
        if not block:
            for pane in card.find_all("div", class_="tab-pane"):
                if pane.find("article"):
                    block = pane
                    break
        if not block:
            best, best_len = None, 0
            for pane in card.find_all("div", class_="tab-pane"):
                t = len(pane.get_text(strip=True))
                if t > best_len:
                    best_len, best = t, pane
            if best_len > 200:
                block = best

    if not block:
        block = soup.find("body") or soup

    articles = block.find_all("article")
    if not articles:
        articles = soup.find_all("article") or [block]

    all_text  = []
    footnotes = []

    for art in articles:

        # ── 1. استخرج الحواشي (tips) أولاً — مطابق للكود المرجعي
        tips_map    = {}
        tip_counter = [1]
        for tip in reversed(list(art.find_all("span", class_="tip"))):
            tip_text = get_tip_text(tip)
            if tip_text:
                tips_map[tip_counter[0]] = tip_text
                tip.replace_with(f"\x01{tip_counter[0]}\x01")
                tip_counter[0] += 1
            else:
                tip.decompose()

        # ── 2. تحويل العلامات الدلالية
        for span in art.find_all("span", class_="aaya"):
            span.replace_with(f"﴿{span.get_text(strip=True)}﴾")
        for span in art.find_all("span", class_="sora"):
            span.replace_with(f" {span.get_text(strip=True)} ")
        for span in art.find_all("span", class_="hadith"):
            span.replace_with(f"«{span.get_text(strip=True)}»")
        for span in art.find_all("span", class_="title-2"):
            span.replace_with(f"\n#### {span.get_text(strip=True)}\n")
        for span in art.find_all("span", class_="title-1"):
            span.replace_with(f"\n##### {span.get_text(strip=True)}\n")

        for a in art.find_all("a"):
            if re.search(r"السابق|التالي|الصفحة|المراجع|اعتماد", a.get_text()):
                a.decompose()

        for i in range(1, 7):
            for h in art.find_all(f"h{i}"):
                h.replace_with(f"\n{'#' * (i + 2)} {h.get_text(strip=True)}\n")

        for p in art.find_all("p"):
            p.insert_before("\n\n")
            p.insert_after("\n\n")

        # ── 3. استخرج النص واستبدل علامات الحواشي بـ [^N]
        text     = art.get_text(separator="\n", strip=False)
        local_fn = [len(footnotes) + 1]

        def replace_marker(m, _tips=tips_map, _fns=footnotes, _ctr=local_fn):
            tid  = int(m.group(1))
            body = _tips.get(tid, '')
            _fns.append(f"[^{_ctr[0]}]: {body}")
            ref  = f" [^{_ctr[0]}]"
            _ctr[0] += 1
            return ref

        text = _TIP_RE.sub(replace_marker, text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'(?<!\n)\n(?![\n#>﴿«\d])', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        if text:
            all_text.append(text)

    clean = re.sub(r'\n{3,}', '\n\n', "\n\n".join(all_text)).strip()
    return {"text": clean, "footnotes": footnotes}


# ── ترقيم الحواشي وإصلاح الملاحظات متعددة الأسطر ─────────────────
def fix_multiline_footnotes(text: str) -> str:
    lines  = text.splitlines()
    result = []
    fn_def = re.compile(r'^\[\^\d+\]:')
    i = 0
    while i < len(lines):
        line = lines[i]
        if fn_def.match(line):
            parts = [line.rstrip()]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt == '' or fn_def.match(nxt):
                    break
                parts.append(nxt.strip())
                i += 1
            result.append(' '.join(p for p in parts if p))
        else:
            result.append(line)
            i += 1
    return '\n'.join(result)


def renum(text: str, fns: list, global_fn_ref: list) -> tuple:
    if not fns:
        return text, []
    local_map = {}
    for fn in fns:
        m = re.match(r'\[\^(\d+)\]:', fn)
        if m and m.group(1) not in local_map:
            local_map[m.group(1)] = global_fn_ref[0]
            global_fn_ref[0] += 1
    for loc in local_map:
        text = re.sub(
            rf'(?<!\d)\[\^{re.escape(loc)}\](?!\d)',
            f'\x02{loc}\x02',
            text
        )
    for loc, gbl in local_map.items():
        text = text.replace(f'\x02{loc}\x02', f'[^{gbl}]')
    new_fns = []
    for fn in fns:
        m = re.match(r'\[\^(\d+)\]:(.*)', fn, re.DOTALL)
        if m:
            loc = m.group(1)
            gbl = local_map.get(loc)
            if gbl is not None:
                new_fns.append(f"[^{gbl}]:{m.group(2)}")
    return text, new_fns


# ── حفظ ملف باب/قسم رئيسي ────────────────────────────────────────
def save_markdown(pages: list, file_num: int) -> str:
    """
    pages: قائمة من dict بالشكل:
        {"url", "title", "level", "text", "footnotes"}
    """
    if not pages:
        return ""

    top      = pages[0]
    safe     = re.sub(r'[^\w\u0600-\u06FF]', '_', top["title"])[:50]
    filename = f"{file_num:04d}_{safe}.md"
    filepath = os.path.join(OUT_DIR, filename)

    lines         = [f"# {top['title']}\n\n> {top['url']}\n\n---\n\n"]
    all_footnotes = []
    global_fn_ref = [1]

    for page in pages:
        lvl     = page["level"]
        heading = HEADING.get(lvl, "####")
        lines.append(f"{heading} {page['title']}\n\n")
        lines.append(f"> {page['url']}\n\n")

        if page.get("text"):
            text, fns = renum(page["text"], page.get("footnotes", []), global_fn_ref)
            lines.append(f"{text}\n\n")
            all_footnotes.extend(fns)

        lines.append("---\n\n")

    if all_footnotes:
        lines.append("\n")
        for fn in all_footnotes:
            lines.append(f"{fn}\n")

    content = fix_multiline_footnotes("".join(lines))
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    total = sum(len(p.get("text", "")) for p in pages)
    print(f"\n  ✔ {filepath}  |  {len(pages)} صفحة  "
          f"|  ~{total//1024} KB  |  {len(all_footnotes)} حاشية")
    return filepath


# ── التشغيل الرئيسي ───────────────────────────────────────────────
if __name__ == "__main__":
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        session = make_session()

        # ① تهيئة الجلسة
        print("① تهيئة الجلسة...")
        get_page(session, BASE, referer=BASE)
        time.sleep(1.5)

        # ② جلب الفهرس → أول رابط
        print("\n② جلب صفحة الفهرس...")
        html_index = get_page(session, INDEX, referer=BASE)
        time.sleep(2)
        if not html_index:
            raise SystemExit("فشل جلب صفحة الفهرس")

        current_url = get_first_link(html_index)
        if not current_url:
            raise SystemExit("لم يُعثر على أي رابط في الفهرس")

        print(f"\n③ بدء التتبع من: {current_url}\n{'='*60}")

        current_group  = []   # الصفحات المجمّعة في الملف الحالي
        file_num       = 1
        page_count     = 0
        visited        = set()

        while current_url and current_url not in visited:
            visited.add(current_url)

            # تحقق من الملف الموجود
            pid = get_id_from_url(current_url)

            html = get_page(session, current_url, referer=INDEX)
            time.sleep(DELAY)
            if not html:
                current_url = None
                break

            title  = get_page_title(html)
            level  = detect_level(title)
            parsed = extract_content(html)

            page_count += 1
            lvl_names  = {1:"باب", 2:"فصل", 3:"مبحث", 4:"مطلب", 5:"فرع", 6:"مسألة"}
            print(f"  [{page_count}] L{level}({lvl_names.get(level,'؟')}) "
                  f"| {title[:50]}  →  {len(parsed['text'])} حرف  "
                  f"| {len(parsed['footnotes'])} حاشية")

            # إذا وصلنا مستوى 1 جديد → احفظ المجموعة السابقة وابدأ جديدة
            if level == 1 and current_group:
                save_markdown(current_group, file_num)
                file_num += 1
                current_group = []

            current_group.append({
                "url"      : current_url,
                "title"    : title,
                "level"    : level,
                "text"     : parsed["text"],
                "footnotes": parsed["footnotes"],
            })

            # حد الاختبار
            if TEST_PAGES and page_count >= TEST_PAGES:
                print(f"\n  [وضع الاختبار] توقف عند {TEST_PAGES} صفحة")
                break

            current_url = get_next_link(html)

        # احفظ آخر مجموعة
        if current_group:
            save_markdown(current_group, file_num)

        print(f"\n✔ اكتمل: {page_count} صفحة → {file_num} ملف في {OUT_DIR}/")

    except SystemExit as e:
        print(e)
    except Exception:
        traceback.print_exc()
