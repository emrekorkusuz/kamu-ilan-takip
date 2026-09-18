# 🇹🇷 Kamu İlan Takip Botu

ÖSYM ve Kariyer Kapısı üzerindeki yeni kamu personel ilanlarını kontrol eder,
profil filtrelerine uyan yeni ilanları Telegram'a gönderir.

## 1. Telegram botu oluştur

Telegram'da `@BotFather` hesabını aç.

`/newbot` komutunu gönder ve botu oluştur.

BotFather sana bir **BOT TOKEN** verecek.

Sonra kendi botuna `/start` gönder.

Chat ID'yi öğrenmek için:
`https://api.telegram.org/botBOT_TOKEN/getUpdates`

Buradaki `BOT_TOKEN` kısmını kendi token'ınla değiştir.
Gelen JSON içinde `"chat":{"id": ...}` değerini bul.

## 2. GitHub Secrets

GitHub reposunda:

Settings → Secrets and variables → Actions → New repository secret

şunları ekle:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## 3. GitHub Actions

Actions sekmesine gir.

`Kamu İlan Takip` workflow'unu seç.

`Run workflow` ile ilk testi manuel çalıştır.

Sonrasında workflow yaklaşık 15 dakikada bir çalışır.
GitHub zamanlaması yoğunluğa göre gecikebilir.

## Filtreler

Başlangıçta şu tür kelimeler izleniyor:

- Bilişim
- Bilgisayar
- Yazılım
- VHKİ
- Veri Hazırlama ve Kontrol İşletmeni
- Bilgisayar İşletmeni
- Programcı
- Memur
- KPSS / P3
- Lisans

Filtreleri `main.py` içindeki `PROFILE_KEYWORDS` listesinden değiştirebilirsin.

## Önemli

Bu ilk sürüm ilan metnini kelime bazında filtreleyen bir MVP'dir.
Bir ilanın gerçekten başvurulabilir olup olmadığını otomatik olarak kesinleştirmez.
Başvurmadan önce resmi ilan metnindeki öğrenim, nitelik kodu, KPSS yılı/puan türü,
özel şartlar ve başvuru tarihleri mutlaka kontrol edilmelidir.

Bir sonraki sürümde ÖSYM nitelik kodlarını ve senin mezuniyet bölümünü daha
ayrıntılı eşleştirebiliriz.
