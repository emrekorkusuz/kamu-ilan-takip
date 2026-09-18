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
RESMI_GAZETE_URL = "https://www.resmigazete.gov.tr/cesitli-ilanlar"
ILANGOV_URL = "https://www.ilan.gov.tr/ilan/kategori/20/personel-alimi-ve-akademik-kadro-ilanlari"
STATE_FILE = "seen.json"

# Bilişim Sistemleri ve Teknolojileri (Lisans) + Zabıta / Genel Alım Filtreleri
PROFILE_KEYWORDS = [
    # Bilişim / Teknik Unvanlar
    "bilişim", "bilgisayar", "yazılım", "veri hazırlama",
    "veri hazırlama ve kontrol işletmeni", "vhki",
    "bilgisayar işletmeni", "programcı", "tekniker", "teknisyen",
    "sistem analisti", "ağ yöneticisi", "sistem uzmanı", "çözümleyici",

    # Genel Alımlar / Zabıta / Büro / Düz Memurluk
    "zabıta", "zabıta memuru", "itfaiye", "itfaiye eri",
    "büro personeli", "memur", "icra müdür", "gümrük", 
    "koruma ve güvenlik", "idari personel",

    # ÖSYM Nitelik Kodları (Lisans Bilişim Sistemleri & Genel)
    "4539", "4531", "4532", "4533", "4535",
    "4001"
]

EDUCATION_KEYWORDS = ["lisans", "4 yıllık", "dört yıllık", "fakülte", "üniversite"]
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
    return has_profile or (has_profile and has_education_or_kpss)

# --- SCRAPER FONKSİYONLARI ---

def scrape_osym():
    html = get(OSYM_URL)
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        title = normalize(a.get_text(" ", strip=True))
        href = urljoin(OSYM_URL, a["href"])
        if not title or len(title) < 8:
            continue
        low = title.lower()
        if any(x in low for x in ["kpss", "personel", "yerleştirme", "atama", "kamu", "tercih", "duyuru"]):
            parent = a.parent.get_text(" ", strip=True) if a.parent else ""
            items.append({"title": title, "url": href, "text": normalize(parent), "source": "ÖSYM"})
    return dedupe(items)

def scrape_kariyer():
    html = get(KARIYER_URL)
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        title = normalize(a.get_text(" ", strip=True))
        href = urljoin(KARIYER_URL, a["href"])
        if not title or len(title) < 6:
            continue
        if "ilandetay" in href.lower() or any(x in title.lower() for x in ["ilan", "alımı", "personel", "zabıta", "memur"]):
            parent = a.parent.get_text(" ", strip=True) if a.parent else ""
            items.append({"title": title, "url": href, "text": normalize(parent), "source": "Kariyer Kapısı"})
    return dedupe(items)

def scrape_resmi_gazete():
    try:
        html = get(RESMI_GAZETE_URL)
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for a in soup.find_all("a", href=True):
            title = normalize(a.get_text(" ", strip=True))
            href = urljoin(RESMI_GAZETE_URL, a["href"])
            if not title or len(title) < 8:
                continue
            low = title.lower()
            if any(x in low for x in ["alımı", "zabıta", "memur", "personel", "rektörlük", "belediye"]):
                items.append({"title": title, "url": href, "text": title, "source": "Resmî Gazete"})
        return dedupe(items)
    except Exception as e:
        print(f"Resmi Gazete taranamadı: {e}")
        return []

def scrape_ilan_gov():
    try:
        html = get(ILANGOV_URL)
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for a in soup.find_all("a", href=True):
            title = normalize(a.get_text(" ", strip=True))
            href = urljoin(ILANGOV_URL, a["href"])
            if not title or len(title) < 10:
                continue
            low = title.lower()
            if any(x in low for x in ["alımı", "memur", "zabıta", "personel", "sözleşmeli", "itfaiye"]):
                parent = a.parent.get_text(" ", strip=True) if a.parent else ""
                items.append({"title": title, "url": href, "text": normalize(parent), "source": "İlan.gov.tr"})
        return dedupe(items)
    except Exception as e:
        print(f"İlan.gov.tr taranamadı: {e}")
        return []

def dedupe(items):
    out, seen = [], set()
    for x in items:
        key = (x["title"], x["url"])
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out

# --- TELEGRAM GÖNDERİM ---

def telegram_send(message, url=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID GitHub Secrets olarak ayarlanmalı.")

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    # Buton ekleme (Varsa ilana yönlendiren buton basar)
    if url:
        payload["reply_markup"] = json.dumps({
            "inline_keyboard": [[{"text": "🔗 İlana Git", "url": url}]]
        })

    r = requests.post(api_url, data=payload, timeout=30)
    r.raise_for_status()

def format_message(item):
    title = item['title'].replace("<", "&lt;").replace(">", "&gt;")
    text = item['text'][:600].replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<b>📢 YENİ KAMU İLANI</b>\n\n"
        f"<b>🏛️ Kaynak:</b> {item['source']}\n"
        f"<b>📌 Başlık:</b> {title}\n\n"
        f"<b>📋 Detay:</b>\n{text}\n"
    )

def main():
    seen = load_seen()
    all_items = []

    # 4 Kaynağı da tara
    for scraper in (scrape_osym, scrape_kariyer, scrape_resmi_gazete, scrape_ilan_gov):
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

    # İlan varsa gönder
    if new_relevant:
        for item in new_relevant:
            try:
                telegram_send(format_message(item), url=item['url'])
                print("Bildirildi:", item["title"])
            except Exception as exc:
                print("Telegram bildirimi başarısız:", exc)
    else:
        # Bildirim kirliliğini önlemek için bilgilendirme mesajını sadece akşam 18:00 - 20:00 UTC arasında atar
        current_hour = datetime.now(timezone.utc).hour
        if current_hour == 18:
            now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
            info_msg = (
                f"<b>ℹ️ Günlük Rapor ({now_str})</b>\n\n"
                f"Sistem bugün aktif çalıştı. Taranan kaynaklarda şartlarınıza uyan yeni bir ilan henüz yayınlanmadı."
            )
            try:
                telegram_send(info_msg)
            except Exception as exc:
                print("Bilgi mesajı gönderilemedi:", exc)

    save_seen(seen)
    print(f"Toplam taranan: {len(all_items)}, yeni uygun ilan: {len(new_relevant)}")

if __name__ == "__main__":
    # Test amaçlı anlık mesaj gönderimi (Doğrulama için):
    try:
        telegram_send("🚀 Test Bildirimi: Botunuz ve 4 kaynaklı tarama sistemi sorunsuz çalışıyor!")
        print("Test mesajı yollandı.")
    except Exception as e:
        print("Test mesajı hatası:", e)

    main()