import os
import json
import hashlib
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ============================================================
# KAMU İLAN TAKİP BOTU
# ============================================================

OSYM_URL = "https://www.osym.gov.tr/"
KARIYER_URL = "https://kariyerkapisi.gov.tr/isealim"
RESMI_GAZETE_URL = "https://www.resmigazete.gov.tr/cesitli-ilanlar"
ILANGOV_URL = "https://www.ilan.gov.tr/ilan/kategori/20/personel-alimi-ve-akademik-kadro-ilanlari"

STATE_FILE = "seen.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    )
}

# ============================================================
# SENİN İÇİN TAKİP EDİLECEK UNVANLAR
# ============================================================

TARGET_TITLES = [
    "memur",
    "vhki",
    "veri hazırlama",
    "veri hazırlama ve kontrol işletmeni",
    "bilgisayar işletmeni",
    "programcı",
    "bilgisayar",
    "bilişim",
    "yazılım",
    "sistem uzmanı",
    "sistem analisti",
    "çözümleyici",
    "büro personeli",
    "tekniker",
    "teknisyen",
    "zabıta",
    "zabıta memuru",
    "itfaiye",
    "itfaiye eri",
    "idari personel",
]

# ÖSYM lisans genel/bilişim kadrolarında kontrol edilecek kodlar.
# Bunlar "kesin başvuru hakkı" anlamına gelmez;
# ilan şartlarının tamamı ayrıca kontrol edilmelidir.
TARGET_CODES = [
    "4001",
    "4531",
    "4532",
    "4533",
    "4535",
    "4537",
    "4539",
    "6225",
]

EDUCATION_WORDS = [
    "lisans",
    "lisans mezunu",
    "4 yıllık",
    "dört yıllık",
    "fakülte",
]

KPSS_WORDS = [
    "kpss",
    "p3",
    "2024 kpss",
    "2026 kpss",
]

# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def get(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    return response.text


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def fingerprint(title, url, text=""):
    raw = f"{title}|{url}|{text[:1000]}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    values = list(seen)[-5000:]

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            values,
            f,
            ensure_ascii=False,
            indent=2
        )


def contains_any(text, words):
    text = text.lower()
    return [word for word in words if word.lower() in text]


# ============================================================
# İLAN UYGUNLUK ANALİZİ
# ============================================================

def analyze_item(item):

    title = normalize(item["title"])
    text = normalize(item["text"])

    blob = f"{title} {text}".lower()

    found_titles = contains_any(blob, TARGET_TITLES)
    found_codes = contains_any(blob, TARGET_CODES)
    found_education = contains_any(blob, EDUCATION_WORDS)
    found_kpss = contains_any(blob, KPSS_WORDS)

    # En azından hedef unvan veya nitelik kodu bulunmalı.
    has_target = bool(found_titles or found_codes)

    # Genel kamu ilanı mı?
    has_public_context = any(
        word in blob
        for word in [
            "personel",
            "memur",
            "kamu",
            "atama",
            "alımı",
            "sözleşmeli",
            "yerleştirme",
            "kpss"
        ]
    )

    relevant = has_target and has_public_context

    # Telegram'da göstereceğimiz durum.
    if found_codes and found_education and found_kpss:
        status = "🟢 Güçlü eşleşme"
    elif found_codes or (found_titles and found_kpss):
        status = "🟡 İncelenmeli"
    else:
        status = "⚠️ Şartları kontrol et"

    return {
        "relevant": relevant,
        "status": status,
        "titles": found_titles,
        "codes": found_codes,
        "education": found_education,
        "kpss": found_kpss,
    }


# ============================================================
# ÖSYM
# ============================================================

def scrape_osym():

    html = get(OSYM_URL)
    soup = BeautifulSoup(html, "html.parser")

    items = []

    for a in soup.find_all("a", href=True):

        title = normalize(a.get_text(" ", strip=True))
        href = urljoin(OSYM_URL, a["href"])

        if len(title) < 8:
            continue

        low = title.lower()

        if any(
            word in low
            for word in [
                "kpss",
                "personel",
                "yerleştirme",
                "atama",
                "tercih",
                "kamu"
            ]
        ):

            parent = a.parent.get_text(
                " ",
                strip=True
            ) if a.parent else ""

            items.append({
                "title": title,
                "url": href,
                "text": normalize(parent),
                "source": "ÖSYM"
            })

    return dedupe(items)


# ============================================================
# KARİYER KAPISI
# ============================================================

def scrape_kariyer():

    html = get(KARIYER_URL)
    soup = BeautifulSoup(html, "html.parser")

    items = []

    for a in soup.find_all("a", href=True):

        title = normalize(a.get_text(" ", strip=True))
        href = urljoin(KARIYER_URL, a["href"])

        if len(title) < 6:
            continue

        low = title.lower()

        if (
            "ilandetay" in href.lower()
            or any(
                word in low
                for word in [
                    "ilan",
                    "alımı",
                    "personel",
                    "memur",
                    "zabıta"
                ]
            )
        ):

            parent = a.parent.get_text(
                " ",
                strip=True
            ) if a.parent else ""

            items.append({
                "title": title,
                "url": href,
                "text": normalize(parent),
                "source": "Kariyer Kapısı"
            })

    return dedupe(items)


# ============================================================
# RESMİ GAZETE
# ============================================================

def scrape_resmi_gazete():

    try:

        html = get(RESMI_GAZETE_URL)
        soup = BeautifulSoup(html, "html.parser")

        items = []

        for a in soup.find_all("a", href=True):

            title = normalize(a.get_text(" ", strip=True))
            href = urljoin(
                RESMI_GAZETE_URL,
                a["href"]
            )

            if len(title) < 8:
                continue

            low = title.lower()

            if any(
                word in low
                for word in [
                    "personel",
                    "memur",
                    "zabıta",
                    "alımı",
                    "belediye",
                    "rektörlük"
                ]
            ):

                items.append({
                    "title": title,
                    "url": href,
                    "text": title,
                    "source": "Resmî Gazete"
                })

        return dedupe(items)

    except Exception as e:

        print(
            f"Resmî Gazete taranamadı: {e}"
        )

        return []


# ============================================================
# İLAN.GOV.TR
# ============================================================

def scrape_ilan_gov():

    try:

        html = get(ILANGOV_URL)
        soup = BeautifulSoup(html, "html.parser")

        items = []

        for a in soup.find_all("a", href=True):

            title = normalize(a.get_text(" ", strip=True))
            href = urljoin(
                ILANGOV_URL,
                a["href"]
            )

            if len(title) < 10:
                continue

            low = title.lower()

            if any(
                word in low
                for word in [
                    "alımı",
                    "memur",
                    "zabıta",
                    "personel",
                    "sözleşmeli",
                    "itfaiye"
                ]
            ):

                parent = a.parent.get_text(
                    " ",
                    strip=True
                ) if a.parent else ""

                items.append({
                    "title": title,
                    "url": href,
                    "text": normalize(parent),
                    "source": "İlan.gov.tr"
                })

        return dedupe(items)

    except Exception as e:

        print(
            f"İlan.gov.tr taranamadı: {e}"
        )

        return []


# ============================================================
# TEKRARLARI TEMİZLE
# ============================================================

def dedupe(items):

    output = []
    seen = set()

    for item in items:

        key = (
            item["title"],
            item["url"]
        )

        if key not in seen:

            seen.add(key)
            output.append(item)

    return output


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message, url=None):

    token = os.environ.get(
        "TELEGRAM_BOT_TOKEN"
    )

    chat_id = os.environ.get(
        "TELEGRAM_CHAT_ID"
    )

    if not token or not chat_id:

        raise RuntimeError(
            "Telegram Secrets eksik."
        )

    api_url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    if url:

        payload["reply_markup"] = json.dumps({
            "inline_keyboard": [
                [
                    {
                        "text": "🔗 İLANI AÇ",
                        "url": url
                    }
                ]
            ]
        })

    response = requests.post(
        api_url,
        data=payload,
        timeout=30
    )

    response.raise_for_status()


# ============================================================
# TELEGRAM MESAJI
# ============================================================

def escape_html(text):

    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_message(item, analysis):

    title = escape_html(
        item["title"]
    )

    source = escape_html(
        item["source"]
    )

    details = escape_html(
        item["text"][:900]
    )

    codes = (
        ", ".join(analysis["codes"])
        if analysis["codes"]
        else "Bulunamadı"
    )

    titles = (
        ", ".join(analysis["titles"])
        if analysis["titles"]
        else "Bulunamadı"
    )

    education = (
        ", ".join(analysis["education"])
        if analysis["education"]
        else "Belirtilmemiş"
    )

    kpss = (
        ", ".join(analysis["kpss"])
        if analysis["kpss"]
        else "Belirtilmemiş"
    )

    return (
        "<b>🚨 YENİ KAMU İLANI</b>\n\n"

        f"<b>📊 Durum:</b> "
        f"{analysis['status']}\n\n"

        f"<b>🏛 Kaynak:</b> {source}\n"

        f"<b>📌 İlan:</b>\n"
        f"{title}\n\n"

        f"<b>🎯 Eşleşen unvan:</b>\n"
        f"{escape_html(titles)}\n\n"

        f"<b>🔢 Bulunan nitelik kodu:</b>\n"
        f"{escape_html(codes)}\n\n"

        f"<b>🎓 Öğrenim:</b> "
        f"{escape_html(education)}\n"

        f"<b>📊 KPSS:</b> "
        f"{escape_html(kpss)}\n\n"

        f"<b>📋 İlan detayı:</b>\n"
        f"{details}\n\n"

        "⚠️ Başvurmadan önce resmi ilandaki "
        "tüm özel şartları ve nitelik kodlarını kontrol et."
    )


# ============================================================
# ANA PROGRAM
# ============================================================

def main():

    seen = load_seen()

    all_items = []

    scrapers = [
        scrape_osym,
        scrape_kariyer,
        scrape_resmi_gazete,
        scrape_ilan_gov
    ]

    for scraper in scrapers:

        try:

            result = scraper()

            all_items.extend(result)

            print(
                f"{scraper.__name__}: "
                f"{len(result)} kayıt"
            )

        except Exception as exc:

            print(
                f"{scraper.__name__} hata: "
                f"{exc}"
            )

    all_items = dedupe(all_items)

    new_relevant = []

    for item in all_items:

        fid = fingerprint(
            item["title"],
            item["url"],
            item["text"]
        )

        if fid in seen:
            continue

        # Yeni ilanı hafızaya al.
        seen.add(fid)

        analysis = analyze_item(item)

        if analysis["relevant"]:

            item["analysis"] = analysis

            new_relevant.append(item)

    print(
        f"Toplam taranan: {len(all_items)}"
    )

    print(
        f"Yeni uygun ilan: "
        f"{len(new_relevant)}"
    )

    # SADECE YENİ İLAN VARSA TELEGRAM
    for item in new_relevant:

        try:

            message = format_message(
                item,
                item["analysis"]
            )

            telegram_send(
                message,
                item["url"]
            )

            print(
                "Telegram bildirildi:",
                item["title"]
            )

        except Exception as exc:

            print(
                "Telegram hatası:",
                exc
            )

    save_seen(seen)


if __name__ == "__main__":
    main()