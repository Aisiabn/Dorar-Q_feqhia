"""
اختبار الاستخراج على صفحة واحدة — أرسل الـ output لتأكيد صحة النتيجة
"""

import requests
from bs4 import BeautifulSoup
import re

BASE     = "https://dorar.net"
TEST_URL = "https://dorar.net/qfiqhia/6/%D8%A7%D9%84%D9%85%D8%B3%D8%A3%D9%84%D8%A9-%D8%A7%D9%84%D8%A3%D9%88%D9%84%D9%89-%D8%AA%D8%B9%D8%B1%D9%8A%D9%81-%D8%A7%D9%84%D9%82%D8%A7%D8%B9%D8%AF%D8%A9-%D9%84%D8%BA%D8%A9"
_TIP_RE  = re.compile(r'\x01(\d+)\x01')

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    "Referer": BASE,
})

r    = session.get(TEST_URL, timeout=20)
html = r.text
soup = BeautifulSoup(html, "html.parser")

# ── العنوان
og = soup.find("meta", property="og:title")
title = og["content"].split(" - ", 1)[-1].strip() if og and og.get("content") else "؟"
print(f"العنوان: {title}\n{'='*60}")

# ── تنظيف
for tag in soup.find_all(["nav","header","footer","script","style","form"]):
    tag.decompose()

cntnt = soup.find("div", id="cntnt") or soup.find("div", class_="card-body")

for sel in ["div.card-title","div.dorar-bg-lightGreen",
            "div.collapse","div.smooth-scroll","div.white.z-depth-1"]:
    for tag in cntnt.select(sel): tag.decompose()

for a in cntnt.find_all("a"):
    if re.search(r"السابق|التالي|انظر أيضا|الرابط المختصر|مشاركة|اعتماد|المراجع",
                 a.get_text(strip=True)):
        a.decompose()

content_div = cntnt.find("div", class_=lambda c: c and "w-100" in c and "mt-4" in c) or cntnt

# ── الحواشي
def get_tip_text(tip):
    for attr in ("data-original-title","title","data-content","data-tippy-content"):
        val = tip.get(attr,"").strip()
        if val:
            s = BeautifulSoup(val,"html.parser")
            return re.sub(r'\s+',' ', s.get_text()).strip()
    return re.sub(r'\s+',' ', tip.get_text(strip=True)).strip()

tips_map, tip_counter = {}, [1]
for tip in reversed(list(content_div.find_all("span", class_="tip"))):
    txt = get_tip_text(tip)
    if txt:
        tips_map[tip_counter[0]] = txt
        tip.replace_with(f"\x01{tip_counter[0]}\x01")
        tip_counter[0] += 1
    else:
        tip.decompose()

# ── تحويل العلامات
for span in content_div.find_all("span", class_="aaya"):
    span.replace_with(f"﴿{span.get_text(strip=True)}﴾")
for span in content_div.find_all("span", class_="sora"):
    t = span.get_text(strip=True)
    if t: span.replace_with(f" {t} ")
for span in content_div.find_all("span", class_="hadith"):
    span.replace_with(f"«{span.get_text(strip=True)}»")
for span in content_div.find_all("span", class_="title-2"):
    span.replace_with(f"\n#### {span.get_text(strip=True)}\n")
for span in content_div.find_all("span", class_="title-1"):
    span.replace_with(f"\n##### {span.get_text(strip=True)}\n")

# ── النص
footnotes = []
fn_counter = [1]
text = content_div.get_text(separator="\n", strip=False)

def replace_marker(m):
    tid  = int(m.group(1))
    body = tips_map.get(tid,'')
    footnotes.append(f"[^{fn_counter[0]}]: {body}")
    ref  = f" [^{fn_counter[0]}]"
    fn_counter[0] += 1
    return ref

text = _TIP_RE.sub(replace_marker, text)
text = re.sub(r'[ \t]+',' ', text)
text = re.sub(r'\n{3,}','\n\n', text)
text = re.sub(r'(?<!\n)\n(?![\n#>﴿«\d])',' ', text)
text = re.sub(r'\n{3,}','\n\n', text).strip()

# ── النتيجة
print("── النص المستخرج ──")
print(text)
print(f"\n── الحواشي ({len(footnotes)}) ──")
for fn in footnotes:
    print(fn[:120])