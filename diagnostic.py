"""
تشخيص بنية HTML لصفحة من موسوعة القواعد الفقهية
شغّله وأرسل لي الـ output كاملاً
"""

import requests
from bs4 import BeautifulSoup
import re

BASE = "https://dorar.net"
# صفحة تحتوي محتوى فعلي
TEST_URL = "https://dorar.net/qfiqhia/6/%D8%A7%D9%84%D9%85%D8%B3%D8%A3%D9%84%D8%A9-%D8%A7%D9%84%D8%A3%D9%88%D9%84%D9%89-%D8%AA%D8%B9%D8%B1%D9%8A%D9%81-%D8%A7%D9%84%D9%82%D8%A7%D8%B9%D8%AF%D8%A9-%D9%84%D8%BA%D8%A9"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    "Referer": BASE,
})

r = session.get(TEST_URL, timeout=20)
print(f"Status: {r.status_code}")
soup = BeautifulSoup(r.text, "html.parser")

# ── 1. عدد كل نوع من العناصر الرئيسية
print("\n── العناصر الرئيسية ──")
for tag in ["article", "section", "main", "div"]:
    print(f"  <{tag}>: {len(soup.find_all(tag))}")

# ── 2. كل div له class - أكثرها احتمالاً للمحتوى
print("\n── div classes (بالترتيب) ──")
from collections import Counter
classes = Counter()
for div in soup.find_all("div", class_=True):
    for c in div.get("class", []):
        classes[c] += 1
for cls, cnt in classes.most_common(30):
    print(f"  .{cls}: {cnt}")

# ── 3. هل توجد articles؟
print("\n── محتوى article tags ──")
for i, art in enumerate(soup.find_all("article")[:3]):
    txt = art.get_text(strip=True)
    print(f"  article[{i}]: {len(txt)} حرف | أول 200: {txt[:200]}")

# ── 4. tab-panes
print("\n── tab-pane divs ──")
for i, pane in enumerate(soup.find_all("div", class_="tab-pane")):
    classes_str = " ".join(pane.get("class", []))
    txt = pane.get_text(strip=True)
    print(f"  pane[{i}] classes='{classes_str}': {len(txt)} حرف | أول 150: {txt[:150]}")

# ── 5. card-body
print("\n── card-body ──")
card = soup.find("div", class_="card-body")
if card:
    txt = card.get_text(strip=True)
    print(f"  {len(txt)} حرف | أول 300: {txt[:300]}")
else:
    print("  لا يوجد card-body")

# ── 6. span classes المتعلقة بالمحتوى
print("\n── span classes ──")
span_classes = Counter()
for span in soup.find_all("span", class_=True):
    for c in span.get("class", []):
        span_classes[c] += 1
for cls, cnt in span_classes.most_common(20):
    print(f"  .{cls}: {cnt}")

# ── 7. روابط التالي/السابق
print("\n── روابط التنقل ──")
nav_re = re.compile(r"^/qfiqhia/")
for a in soup.find_all("a", href=nav_re):
    txt = a.get_text(strip=True)
    if txt:
        print(f"  '{txt}' → {a['href']}")

# ── 8. النص الكامل بعد إزالة nav/header/footer
print("\n── النص الكامل (أول 1000 حرف بعد تنظيف أساسي) ──")
for tag in soup.find_all(["nav","header","footer","script","style"]):
    tag.decompose()
body = soup.find("body")
if body:
    txt = re.sub(r'\s+', ' ', body.get_text()).strip()
    print(txt[:1000])