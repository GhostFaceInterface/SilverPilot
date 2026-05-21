# [COMPLETED] Implementation Plan: Phase 3.9 Yahoo Finance Daily Backfill & Timeframe Isolation

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Veri kalitesi, test standartları, toplayıcı kararlılığı)
  - [docs/DATA_CONTRACTS.md](file:///Users/boe747/SilverPilot/docs/DATA_CONTRACTS.md) (PriceSnapshot, RawGlobalPrice ve TechnicalIndicator şema ve kısıt kural bütünlüğü)
- **Etkilenen Şemalar:**
  - `PriceSnapshot`, `RawGlobalPrice` ve `TechnicalIndicator` tablolarında yeni veri girişi yapılmıştır.
- **Kritik Risk (Mixed Timeframe Bug):**
  - Tarihsel günlük backfill verileri ile real-time 5-dakikalık veriler veritabanında aynı `source` ismi (`yahoo-si-f`) ile saklanırsa, real-time gösterge motoru (`service.py`) son 200 barı çekip teknik gösterge hesaplarken bu iki timeframe verisini karıştıracaktır. Bu durum teknik göstergeleri (RSI, MACD, SMA200 vb.) tamamen kullanılmaz hale getirecektir.
  - **Çözüm (Option A):** Günlük backfill verileri veritabanına `source="yahoo-si-f-1d"` olarak kaydedilmiştir. Gerçek zamanlı 5m verileri ise `source="yahoo-si-f"` olarak devam etmektedir. Bu sayede iki timeframe tamamen izole edilmiştir.

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Tarihsel Backfill Scriptinin Güncellenmesi (Ajan: `data-engineer`)**
  - `scripts/backfill_history.py` dosyasındaki `source` değerlerinin tamamının `"yahoo-si-f-1d"` olarak güncellenmesi (duplicate kontrolü ve veri ekleme kısımlarında).
  - Phase 3.8 veri hardening kurallarına tam uyum için `RawGlobalPrice` ve `PriceSnapshot` insert satırlarına `resolved_source="yahoo_si_f"` ve `is_degraded=False` alanlarının entegre edilmesi.
  - *DoD (Tamamlanma Tanımı):* Güncellenen `scripts/backfill_history.py` kodunun gözden geçirilerek hata/uyarı içermemesi.

- `[x]` **Faz 2: Tarihsel Verinin Çekilmesi ve Veri Tabanına Aktarılması (Ajan: `data-engineer`)**
  - Güncellenen backfill scriptinin çalıştırılması: `python scripts/backfill_history.py`
  - Veri tabanında XAG asset id'sine sahip `yahoo-si-f-1d` PriceSnapshot, RawGlobalPrice ve TechnicalIndicator (timeframe="1d") kayıtlarının başarıyla oluştuğunun doğrulanması.
  - *DoD:* SQL veya ORM sorgularıyla veritabanına 2 yıllık günlük verilerin (~500+ bar) ve bunlara ait teknik göstergelerin başarıyla eklendiğinin kanıtlanması.

- `[x]` **Faz 3: Entegrasyon ve Regresyon Doğrulaması (Ajan: `quality-engineer`)**
  - Mevcut real-time collector ve gösterge hesaplama mekanizmalarının bu backfill verilerinden etkilenmediğinin (timeframe contamination yaşanmadığının) doğrulanması.
  - *DoD:* `pytest` komutu çalıştırılarak tüm 76 testin sıfır regresyonla başarıyla tamamlanması.

- `[x]` **Faz 4: Güvenlik Geçidi ve Otomatik Git Commit/Push (Ajan: `safety-gatekeeper` & `quality-engineer`)**
  - `safety-gatekeeper` tarafından pre-execution review ile kodun son kez onaylanması.
  - Testlerin yeşil olması durumunda yapılan değişikliklerin `git add scripts/backfill_history.py` ile stage edilip, Conventional Commits formatında (`feat: implement Phase 3.9 historical daily backfill script`) otomatik olarak commit edilmesi ve `git push` ile uzak repoya gönderilmesi.
  - *DoD:* Git commit ve push işleminin başarıyla tamamlandığının gösterilmesi.

---

## ❓ Açık Sorular
> [!NOTE]
> Herhangi bir açık soru veya belirsizlik bulunmamaktadır. Mixed Timeframe Bug'ı çözecek olan Option A (Kaynak ismi izolasyonu) seçilmiştir ve Phase 3.8 veri standartları tam olarak korunmuştur.
