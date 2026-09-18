import os
import json
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OSYM_URL = "https://www.osym.gov.tr/"
KARIYER_URL = "https://kariyerkapisi.gov.tr/isealim"
STATE_FILE = "seen.json"

# Profil filtreleri
PROFILE_KEYWORDS = [
    "bilişim", "bilgisayar", "yazılım", "veri hazırlama",
    "veri hazırlama ve kontrol işletmeni", "vhki",
    "bilgisayar işletmeni", "programcı", "tekniker", "memur"
]
EDUCATION_KEYWORDS = ["lisans", "4 yıllık", "dört yıllık"]
KPSS_KEYWORDS = ["kpss", "p3", "2024 kpss", "2026 kpss"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def normalize(s):
    return re.sub(r"\s+", " ", s or "").strip()

def fingerprint(title, url, text=""):
    raw = f"{title}|{url}|{text[:500]}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]

def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen(seen):
    values = list(seen)[-3000:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(values, f, ensure_ascii=False, indent=2)

def is_relevant(title, text):
    blob = normalize(f"{title} {text}").lower()
    has_profile = any(k in blob for k in PROFILE_KEYWORDS)
    has_education_or_kpss = any(k in blob for k in EDUCATION_KEYWORDS + KPSS_KEYWORDS)
    return has_profile and has_education_or_kpss

def scrape_osym():
    html = get(OSYM_URL)
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for a in soup.find_all("a", href=True):
        title = normalize(a.get_text(" ", strip=True))
        href = urljoin(OSYM_URL, a["href"])
        if not title or len(title) < 10:
            continue
        low = title.lower()
        if any(x in low for x in ["kpss", "personel", "yerleştirme", "atama", "kamu"]):
            parent = a.parent.get_text(" ", strip=True) if a.parent else ""
            text = normalize(parent)
            items.append({"title": title, "url": href, "text": text, "source": "ÖSYM"})
    return dedupe(items)

def scrape_kariyer():
    html = get(KARIYER_URL)
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for a in soup.find_all("a", href=True):
        title = normalize(a.get_text(" ", strip=True))
        href = urljoin(KARIYER_URL, a["href"])
        if not title or len(title) < 8:
            continue
        if "ilandetay" in href.lower() or "ilan" in title.lower():
            parent = a.parent.get_text(" ", strip=True) if a.parent else ""
            items.append({
                "title": title,
                "url": href,
                "text": normalize(parent),
                "source": "Kariyer Kapısı"
            })
    return dedupe(items)

def dedupe(items):
    out, seen = [], set()
    for x in items:
        key = (x["title"], x["url"])
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out

def telegram_send(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID GitHub Secrets olarak ayarlanmalı.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    r = requests.post(url, data=payload, timeout=30)
    r.raise_for_status()

def format_message(item):
    title = item['title'].replace("<", "&lt;").replace(">", "&gt;")
    text = item['text'][:800].replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<b>🔔 YENİ KAMU İLANI</b>\n\n"
        f"<b>Kaynak:</b> {item['source']}\n"
        f"<b>📌 Başlık:</b> {title}\n\n"
        f"{text}\n\n"
        f"🔗 <a href='{item['url']}'>İlana Gitmek İçin Tıklayın</a>"
    )

def main():
    seen = load_seen()
    all_items = []

    for scraper in (scrape_osym, scrape_kariyer):
        try:
            all_items.extend(scraper())
        except Exception as exc:
            print(f"Kaynak okunamadı: {scraper.__name__}: {exc}")

    new_relevant = []
    for item in all_items:
        fid = fingerprint(item["title"], item["url"], item["text"])
        if fid in seen:
            continue

        seen.add(fid)
        if is_relevant(item["title"], item["text"]):
            new_relevant.append(item)

    # İlan Bildirimleri
    if new_relevant:
        for item in new_relevant:
            try:
                telegram_send(format_message(item))
                print("Bildirildi:", item["title"])
            except Exception as exc:
                print("Telegram bildirimi başarısız:", exc)
    else:
        # Uygun ilan bulunamadığında da doğrulama amaçlı bilgi mesajı gönder
        now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        info_msg = (
            f"<b>ℹ️ Kamu İlan Takip Botu Çalıştı</b>\n"
            f"<b>Tarih:</b> {now_str}\n"
            f"<b>Taranan Toplam İlan:</b> {len(all_items)}\n"
            f"<b>Yeni Uygun İlan:</b> 0\n\n"
            f"<i>Sistem sorunsuz çalışıyor, kriterlerinize uyan yeni ilan bulunduğunda haber verilecektir.</i>"
        )
        try:
            telegram_send(info_msg)
            print("Bilgi mesajı Telegram'a gönderildi.")
        except Exception as exc:
            print("Bilgi mesajı gönderilemedi:", exc)

    save_seen(seen)
    print(f"Toplam taranan: {len(all_items)}, yeni uygun ilan: {len(new_relevant)}")

if __name__ == "__main__":
    main()