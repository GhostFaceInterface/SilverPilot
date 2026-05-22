# Implementation Plan: Phase 13 - Telegram Portfolio & Diagnostics Bot

Bu plan, SilverPilot projesinde **Phase 13: Telegram Portfolio & Diagnostics Bot** entegrasyonunun tasarım, güvenlik, test ve canlıya alma adımlarını detaylandırmaktadır. 

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - *Deterministic Risk Authority:* Telegram botu kesinlikle herhangi bir AL/SAT işlemi tetikleyemez, sadece salt okunur (read-only) durum raporlaması yapar.
  - *Port Isolation:* Telegram botu veri tabanına doğrudan TCP portları üzerinden bağlanamaz. Tüm sorgulamalar local FastAPI endpoints veya FastAPI servis katmanı üzerinden yürütülecektir.
  - *Zero-Trust Access Control (Sadece Size Özel):* Bot, dışarıdan gelebilecek güvenlik ihlallerini önlemek için yalnızca yapılandırılmış tek bir `TELEGRAM_CHAT_ID` üzerinden gelen komutlara yanıt verecektir. Farklı kişilerden gelen komutlar anında bloklanacak ve loglanacaktır.

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Konfigürasyon ve Çevre Değişkenleri**
  - `[x]` `.env` ve `apps/api/app/core/config.py` içerisine `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_BOT_MODE`, `TELEGRAM_WEBHOOK_URL` parametrelerinin eklenmesi (Ajan: `backend-architect` / `security-auditor`)
  - *DoD (Tamamlanma Tanımı):* FastAPI başladığında yeni konfigürasyon değerlerinin hatasız okunabilmesi.

- `[x]` **Faz 2: Secure Webhook API Rotaları ve Güvenlik Filtresi**
  - `[x]` FastAPI Webhook Rotası (`apps/api/app/api/routes.py`) `POST /agent/telegram/webhook` rotasını açmak.
  - `[x]` Telegram İmza/Token Doğrulaması ve Chat ID Filtrelemesi eklemek.
  - `[x]` Background Task entegrasyonu ile milisaniyeler içinde 200 OK dönmek.
  - *DoD:* Gelen webhook isteklerine API'nin anında 200 OK dönmesi.

- `[x]` **Faz 3: Bot Komut İşleyicisi ve Port-Isolated Servis Tasarımı**
  - `[x]` Command Parser & Formatters (`apps/api/app/agents/telegram_bot.py` *[NEW]*) oluşturmak.
  - `[x]` `/durum`, `/cuzdan`, `/karzarar` ve `/ajanlar` komutlarını şık Markdown formatında yanıtlayacak fonksiyonların yazılması (Ajan: `backend-architect` / `data-engineer`).
  - *DoD:* Servis fonksiyonlarının yerel mock veritabanı sorgularıyla hatasız markdown çıktısı üretmesi.

- `[x]` **Faz 4: Lifespan Webhook Kaydı & Local Polling Geliştirici Modu**
  - `[x]` FastAPI Lifespan Entegrasyonu (`apps/api/app/main.py`) webhook set/delete işlemlerinin eklenmesi (Ajan: `backend-architect`).
  - `[x]` `asyncio.create_task` ile arka planda bağımsız bir polling döngüsü (long-polling loop) başlatılması.
  - *DoD:* FastAPI yerelde polling moduyla başlatıldığında Telegram botunun ngrok olmadan çalışması, webhook modunda ise webhook kaydını başarıyla yapması.

- `[x]` **Faz 5: Kalite Kontrol ve Doğrulama Suite**
  - `[x]` Birim ve Entegrasyon Testleri (`apps/api/tests/test_telegram.py` *[NEW]*) ile webhook rotasını test etmek (Ajan: `quality-engineer`).
  - `[x]` Pytest Regresyon Testi: Tüm test suite'inin (142 passed) sıfır hata ile yeşil geçmesini doğrulamak.
  - `[x]` Otomatik Git Commit & Push: Değişiklikleri uzak depoya otomatik push etmek.
  - *DoD:* `pytest` suite'indeki tüm testlerin (142 test) sıfır hata ile yeşil geçmesi.

---

## ❓ Açık Sorular & Kullanıcı Görüşü
> [!IMPORTANT]
> 1. **Telegram Token ve Chat ID:** Bu aşamada testleri yerelde mock veriyle yürüteceğimiz için gerçek Telegram token değerini `.env` içine yazmanız yeterlidir. Chat ID'nizi öğrenmek için Telegram'da `@userinfobot` botuna herhangi bir mesaj göndererek `Id:` kısmını alıp `.env` dosyasına `TELEGRAM_CHAT_ID=xxxxxx` olarak tanımlamanız gerekecektir.
> 2. **Telegram Kütüphanesi:** Projeye hafiflik kazandırmak adına asenkron HTTP tabanlı `httpx` üzerinden minimal sarmalayıcı mı kullanalım, yoksa `python-telegram-bot` kütüphanesini `apps/api/requirements.txt` dosyasına ekleyelim mi? (Hafiflik ve sürdürülebilirlik açısından `python-telegram-bot` kütüphanesini kullanmak komut parse etme ve buton ekleme işlerimizi çok kolaylaştıracaktır).
