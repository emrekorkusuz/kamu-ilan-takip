import os
import json
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ==========================================
# TEST MODU AYARI
# Test etmek için True yapın. Normal kullanımda False yapın.
TEST_MODE = False  
# ==========================================

OSYM_URL = "https://www.osym.gov.tr/"
KARIYER_URL = "https://kariyerkapisi.gov.tr/isealim"
RESMI_GAZETE_URL = "https://www.resmigazete.gov.tr/cesitli-ilanlar"
ILANGOV_URL = "https://www.ilan.gov.tr/ilan/kategori/20/personel-alimi-ve-akademik-kadro-ilanlari"
STATE_FILE = "seen.json"

# --- FİLTRE VE KOD TANIMLARI ---

# Bilişim/Yazılım Lisans Nitelik Kodları
TECH_QUALIFICATION_CODES = ["4539", "4531", "4532", "4533", "4535", "4537"]
# Genel Lisans Kodları
GENERAL_QUALIFICATION_CODES = ["4001", "6225"]

PRIMARY_TITLES = [
    "bilişim", "bilgisayar", "yazılım", "veri hazırlama", 
    "vhki", "programcı", "tekniker", "sistem analisti", 
    "ağ yöneticisi", "sistem uzmanı", "çözümleyici"
]

SECONDARY_TITLES = [
    "zabıta", "itfaiye", "büro personeli", "memur", 
    "icra müdür", "gümrük", "koruma ve güvenlik", "idari personel"
]

EDUCATION_KEYWORDS = ["lisans", "4 yıllık", "dört yıllık", "fakülte", "üniversite"]
KPSS_KEYWORDS = ["kpss", "p3", "kpssp3"]

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

def extract_meta_info(text):
    """Metin içerisinden tarih, KPSS ve nitelik kodlarını ayıklar."""
    found_codes = list(set(re.findall(r"\b(4\d{3}|6225)\b", text)))
    dates = re.findall(r"\b\d{1,2}[\.\/]\d{1,2}[\.\/]\d{4}\b", text)
    deadline = dates[-1] if dates else "Belirtilmedi"
    kpss_found = "KPSS P3" if "p3" in text.lower() else ("KPSS Var" if "kpss" in text.lower() else "Belirtilmedi")
    
    return {
        "codes": found_codes,
        "deadline": deadline,
        "kpss": kpss_found
    }

def analyze_relevance(title, text):
    """
    1. Kesin Uygunluk (MATCH)
    2. Geniş Takip (REVIEW)
    3. Uygun Değil (NONE)
    """
    blob = normalize(f"{title} {text}").lower()
    
    has_tech_title = any(k in blob for k in PRIMARY_TITLES)
    has_sec_title = any(k in blob for k in SECONDARY_TITLES)
    has_education = any(k in blob for k in EDUCATION_KEYWORDS)
    has_kpss = any(k in blob for k in KPSS_KEYWORDS)
    
    meta = extract_meta_info(text)
    has_tech_code = any(code in meta["codes"] for code in TECH_QUALIFICATION_CODES)
    has_gen_code = any(code in meta["codes"] for code in GENERAL_QUALIFICATION_CODES)

    if (has_tech_title or has_tech_code) and (has_education or has_kpss or has_gen_code):
        return "MATCH", meta

    if has_sec_title or has_gen_code:
        return "REVIEW", meta

    return "NONE", meta

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

# --- TELEGRAM VE BİLDİRİM ---

def telegram_send(message, url=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID GitHub Secrets (veya Environment Variable) olarak tanımlanmamış!")

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    if url:
        payload["reply_markup"] = json.dumps({
            "inline_keyboard": [[{"text": "🔗 İlana Git", "url": url}]]
        })

    r = requests.post(api_url, data=payload, timeout=30)
    r.raise_for_status()

def format_message(item, status, meta):
    title = item['title'].replace("<", "&lt;").replace(">", "&gt;")
    codes_str = ", ".join(meta["codes"]) if meta["codes"] else "Metinde Kod Saptanmadı"
    
    if status == "MATCH":
        header = "🚨 <b>SANA UYGUN YENİ KAMU İLANI</b>"
    else:
        header = "⚠️ <b>KONTROL ET: GENEL / ALTERNATİF İLAN</b>"

    return (
        f"{header}\n\n"
        f"🏛️ <b>Kurum/Kaynak:</b> {item['source']}\n"
        f"📌 <b>Kadro/Başlık:</b> {title}\n"
        f"🎓 <b>Öğrenim:</b> Lisans\n"
        f"📊 <b>KPSS:</b> {meta['kpss']}\n"
        f"🔢 <b>Nitelik Kodları:</b> {codes_str}\n"
        f"📅 <b>Son Başvuru (Tahmini):</b> {meta['deadline']}\n"
    )

def run_test():
    """Telegram API ve Bot Entegrasyonu Test Fonksiyonu"""
    print("🧪 TEST MODU AKTİF: Test mesajı gönderiliyor...")
    test_item = {
        "title": "Çevre ve Şehircilik Bakanlığı - Programcı ve VHKİ Alım İlanı (TEST MESAJI)",
        "source": "ÖSYM (Test)",
        "url": "https://www.osym.gov.tr"
    }
    test_meta = {
        "codes": ["4539", "4001", "6225"],
        "deadline": "31.12.2026",
        "kpss": "KPSS P3"
    }
    
    msg = format_message(test_item, "MATCH", test_meta)
    msg = "🧪 <b>[TEST SİSTEMİ BİLDİRİMİ]</b>\nBot bağlantınız ve bildirim şablonunuz başarıyla çalışıyor!\n\n" + msg
    
    try:
        telegram_send(msg, url=test_item['url'])
        print("✅ TEST BAŞARILI: Telegram'a test bildirim mesajı gönderildi.")
    except Exception as exc:
        print(f"❌ TEST BAŞARISIZ: Telegram mesajı gönderilemedi! Hata: {exc}")

def main():
    # Test Modu Kontrolü
    if TEST_MODE:
        run_test()

    seen = load_seen()
    all_items = []

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
        status, meta = analyze_relevance(item["title"], item["text"])
        
        if status in ("MATCH", "REVIEW"):
            new_relevant.append((item, status, meta))

    if new_relevant:
        for item, status, meta in new_relevant:
            try:
                telegram_send(format_message(item, status, meta), url=item['url'])
                print("Bildirildi:", item["title"])
            except Exception as exc:
                print("Telegram bildirimi başarısız:", exc)
    else:
        current_hour = datetime.now(timezone.utc).hour
        if current_hour == 18 and not TEST_MODE:
            now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
            info_msg = (
                f"<b>ℹ️ Günlük Rapor ({now_str})</b>\n\n"
                f"Sistem bugün aktif çalıştı. Taranan kaynaklarda kriterlerinize uyan yeni bir ilan bulunamadı."
            )
            try:
                telegram_send(info_msg)
            except Exception as exc:
                print("Bilgi mesajı gönderilemedi:", exc)

    save_seen(seen)
    print(f"Toplam taranan: {len(all_items)}, yeni bildirim: {len(new_relevant)}")

if __name__ == "__main__":
    main()
