# Implementation Plan: SilverPilot Stres Testi, Veritabanı Sıkılaştırma & VPS Canlı Denetimi

Bu plan, `scout-subagent` tarafından hem yerel kod tabanında hem de **canlı VPS sunucusundaki PostgreSQL veritabanında** gerçekleştirilen derin denetimlerde tespit edilen kritik zafiyetleri gidermeyi, veri tutarsızlıklarını ortadan kaldırmayı ve sistemi aşırı zorlayıcı entegrasyon testleriyle sıkılaştırmayı hedefler.

---

## 🛡️ Canlı VPS Veritabanı Bulguları ve Risk Analizi
Canlı `silverpilot-vps` üzerindeki veritabanı sorgulandığında, **vibe-coding mantığının ve asenkron oturum yönetiminin yarattığı en büyük mimari zafiyet somut olarak kanıtlanmıştır:**

1.  **🔴 Kritik Veri Tutarsızlığı (Cash Balance Write-Back / Stale Overwrite):**
    - `portfolio_snapshots` tablosunda, yapılan alım-satım işlemlerinin bakiyeleri tam olarak olması gerektiği gibi (`0.000002` ve `2424.241339` USD) kaydedilmiştir.
    - Ancak `portfolios` tablosundaki `cash_balance` değeri halen **`2500.000000`** olarak durmaktadır!
    - **Analiz:** `execute_paper_trade` içerisinde `portfolio.cash_balance` güncellenmesine ve snapshot kaydedilmesine rağmen portfolios tablosundaki ana bakiyenin ezilmesi/güncellenmemesi, **asenkron görevlerin (Background Tasks veya Telegram Bot Polling) veritabanı oturumlarını kirletmesi (dirty session leaks)** ve portfolios nesnesini bellekte bayat (stale) tutup veritabanına geri yazarak en son güncel bakiyeyi ezmesinden (`Stale Data Write-back`) kaynaklanmaktadır!
2.  **🔴 Para Birimi Uyuşmazlığı (TRY vs USD):**
    - `XAG_GRAM` alımlarında TRY bazlı fiyatlar hiçbir kur dönüşümü yapılmadan doğrudan USD bazlı portföy bakiyesinden düşülmekte ve bakiye bir anda sıfırlanmaktadır.
3.  **🔴 Row-Level Locking (Satır Kilitleme) Eksikliği:**
    - Eşzamanlı (concurrent) işlemlerde yarış durumunu (race condition) engelleyecek `with_for_update()` mekanizması bulunmamaktadır.

---

## 🛠️ Fazlar ve Görev Listesi (/orchestrate Uyumlu)

- `[ ]` **Faz 1: Döviz Kuru (FX) Entegrasyonu & Para Birimi Uyuşmazlığının Giderilmesi**
  - [ ] `apps/api/app/paper_trading/service.py` içerisine FX dönüştürücü katmanın eklenmesi.
  - [ ] Varlık para birimi portföy base_currency'den farklıysa, son güncel `PriceSnapshot` üzerinden USD/TRY kurunu çekerek alım/satım tutarlarını dönüştürmesi.
  - [ ] `tests/test_paper_trading.py` içerisine cross-currency alım stres testlerinin yazılması.
  - *Ajanlar:* `backend-architect`, `data-engineer`
  - *DoD (Tamamlanma Tanımı):* TRY bazlı alımlarda USD bakiyesinin kur oranında (~33 kat daha az) doğru eksildiğini kanıtlayan testlerin yeşil olması.

- `[ ]` **Faz 2: Satır Düzeyinde Kilitleme (Row-Level Locking) & Asenkron Oturum Sızıntısı Onarımı**
  - [ ] `execute_paper_trade` içerisinde portföy veritabanından çekilirken `with_for_update()` kilidinin uygulanması.
  - [ ] Tüm asenkron background task'lerde ve routers.py altındaki `except` bloklarında, oturum pool'a dönmeden önce **`db.rollback()`** mekanizmasının zorunlu kılınması.
  - [ ] Eşzamanlı 10 paralel isteği simüle eden stress/concurrency entegrasyon testlerinin yazılması.
  - *Ajanlar:* `backend-architect`, `security-auditor`
  - *DoD:* Paralel testlerde bakiyenin eksiye düşmediğinin ve veritabanı portfolios tablosundaki `cash_balance` kolonunun snapshot'lar ile %100 senkronize çalıştığının canlı olarak doğrulanması.

- `[ ]` **Faz 3: FIFO ve Pozisyon Performans Dar Boğazının Giderilmesi**
  - [ ] `calculate_position` ve `_realized_loss_since` fonksiyonlarında, tüm geçmiş trade listesini bellekte loop etmek yerine veritabanı indeksli agregasyon sorgularına (`created_at >= since`) geçilmesi.
  - *Ajanlar:* `backend-architect`, `performance-optimizer`
  - *DoD:* 5.000 adet geçmiş trade kaydı varken bile pozisyon sorgularının 10ms altında yanıt dönmesi.

- `[ ]` **Faz 4: Exception Swallowing Giderilmesi & Log Telemetrisi**
  - [ ] `telegram_bot.py`, `collectors/public_sources.py` ve `risk/service.py` üzerindeki blind `pass`lerin log APM uyarılarıyla değiştirilmesi.
  - *Ajanlar:* `security-auditor`, `quality-engineer`
  - *DoD:* Hata durumlarında loglarda traceback'lerin eksiksiz görünmesi.

- `[ ]` **Faz 5: Aşırı Zorlayıcı E2E Entegrasyon Test Süiti & Canlı VPS Doğrulaması**
  - [ ] `quality-engineer` tarafından tüm bu stres testlerinin ve sınır durum (edge-case) testlerinin koşturulması.
  - [ ] `safety-gatekeeper` (Gemini 3.5 Pro) ile `@logic-lens` ve `@brooks-lint` yardımıyla paranoid kod denetimi.
  - [ ] Başarılı kodların Conventional Commits ile commitlenip push edilmesi ve uzak VPS sunucusunda `deploy.sh` ve `vps_smoke.sh` ile canlı ortam testlerinin yeşillendirilmesi.
  - *Ajanlar:* `safety-gatekeeper`, `quality-engineer`
  - *DoD:* Tüm pytest test süitinin ve VPS smoke testlerinin sıfır hata ile tamamlanması.

---

## ❓ Açık Sorular

> [!IMPORTANT]
> 1. **Döviz Kuru Kaynağı:** Kur dönüştürme için veritabanındaki son `PriceSnapshot` (USD/TRY) kurunu çekmeyi öneriyoruz. Bu dinamik yaklaşımı onaylıyor musunuz?
> 2. **Model Geçiş Protokolü:** Bu kritik finansal ve concurrency zafiyetlerini gidermek, veritabanı kilitlerini yazmak ve `safety-gatekeeper` paranoid kod reviews adımları için modelinizi **Gemini 3.5 Pro** olarak değiştirmeyi onaylıyor musunuz?
