"""
تشخيص مرحلة 2 — إيجاد الحاوي الفعلي للمحتوى
"""

import requests
from bs4 import BeautifulSoup
import re

BASE     = "https://dorar.net"
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
soup = BeautifulSoup(r.text, "html.parser")

# ── 1. تتبع سلسلة الآباء لكل span محتوى
print("── سلسلة آباء .aaya و .tip و .title-2 ──")
for cls in ["aaya", "tip", "title-2", "title-1"]:
    spans = soup.find_all("span", class_=cls)
    if not spans:
        print(f"\n  .{cls}: لا يوجد")
        continue
    print(f"\n  .{cls} ({len(spans)} عنصر) — أول واحد:")
    span = spans[0]
    print(f"    النص: {span.get_text(strip=True)[:100]}")
    # اطبع سلسلة الآباء
    chain = []
    for parent in span.parents:
        if parent.name in [None, "[document]", "html", "body"]:
            break
        cls_str = " ".join(parent.get("class", []))
        pid     = parent.get("id", "")
        chain.append(f"<{parent.name} id='{pid}' class='{cls_str}'>")
    print("    الآباء: " + " → ".join(chain[:6]))

# ── 2. أكبر div ليس modal ولا nav ولا header
print("\n── أكبر 10 divs بالنص (بعد استثناء modal/nav/header) ──")
candidates = []
for div in soup.find_all("div"):
    classes = " ".join(div.get("class", []))
    if re.search(r"\bmodal\b|\bnav\b|\bheader\b|\bfooter\b|\bcollapse\b", classes):
        continue
    txt = div.get_text(strip=True)
    if len(txt) > 300:
        candidates.append((len(txt), classes[:60], div.get("id",""), txt[:200]))

candidates.sort(reverse=True)
for length, cls, did, preview in candidates[:10]:
    print(f"\n  [{length} حرف] id='{did}' class='{cls}'")
    print(f"  → {preview}")

# ── 3. طباعة HTML الخام حول أول .tip
print("\n── HTML الخام حول أول .tip ──")
tip = soup.find("span", class_="tip")
if tip:
    # اطبع الـ grandparent
    gp = tip.parent.parent if tip.parent else tip
    print(str(gp)[:2000])
else:
    print("  لا يوجد .tip")

# ── 4. هل يوجد div بـ id يحتوي "content" أو "main" أو "text"
print("\n── divs بـ id يحتوي content/main/text/body ──")
for div in soup.find_all("div", id=True):
    did = div.get("id","").lower()
    if any(x in did for x in ["content","main","text","body","article","post"]):
        txt = div.get_text(strip=True)
        print(f"  id='{did}': {len(txt)} حرف | {txt[:150]}")