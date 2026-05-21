# Implementation Plan: Phase 3.9.1 backfill_history.py Robustness & Performance Hardening

Bu plan, `safety-gatekeeper` ajanı tarafından yapılan denetim sonucunda ortaya konan risk ve iyileştirme önerilerini (Risk A, B, C) `backfill_history.py` betiğinde hayata geçirmeyi hedefler.

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - [docs/DATA_CONTRACTS.md](file:///Users/boe747/SilverPilot/docs/DATA_CONTRACTS.md) (Toplayıcı kalitesi, veri tekilliği, hata durumlarının veritabanına izlenebilir şekilde yansıtılması)
  - [docs/ARCHITECTURE.md](file:///Users/boe747/SilverPilot/docs/ARCHITECTURE.md) (Veritabanı transaction güvenliği, toplayıcı çalışma durumları)
- **Etkilenen Dosyalar:**
  - [scripts/backfill_history.py](file:///Users/boe747/SilverPilot/scripts/backfill_history.py) (Tarihsel verileri dolduran betik)

---

## 🛠️ Fazlar ve Görev Listesi

### `[x]` Faz 1: Collector Run Crash Safety (Hata Durumu Kayıt Güvenliği)
- **Yapılacaklar:**
  - [scripts/backfill_history.py](file:///Users/boe747/SilverPilot/scripts/backfill_history.py) betiğindeki genel `try-except` bloğunun güncellenmesi.
  - Hata oluşması durumunda aktif transaction rollback edildikten sonra yeni bir DB oturumu/alt transaction açılarak `CollectorRun.status` değerinin `"failed"` olarak işaretlenmesi ve `error_message` alanına yakalanan hatanın eklenerek veritabanına kaydedilmesi.
- **DoD (Tamamlanma Tanımı):**
  - Yapay olarak tetiklenen bir bağlantı hatası durumunda veritabanında `CollectorRun.status == "failed"` ve `error_message` alanının dolu olması.

### `[x]` Faz 2: Single-Query O(1) Mükerrerlik Denetimi Optimizasyonu (Performans)
- **Yapılacaklar:**
  - Döngü içinde her kayıt için veritabanına 504 kez ayrı ayrı SELECT sorgusu atılması yerine, betiğin başında `PriceSnapshot` ve `RawGlobalPrice` tablolarından mevcut `"yahoo-si-f-1d"` kayıtlarının `observed_at` zaman damgalarının tek bir sorguyla çekilmesi.
  - Çekilen verilerin Python `set` yapısında tutulması ve döngü içindeki mükerrerlik kontrolünün bu set üzerinden O(1) sürede yapılması.
- **DoD:**
  - Betik çalıştırıldığında veritabanına giden tekil SELECT sorgusu sayısının 500+'den 1'e düşmesi ve verilerin başarıyla eklenmesi.

### `[x]` Faz 3: İki Yönlü Tekillik Kısıt Denetimi (Çift Yazım Koruyucu)
- **Yapılacaklar:**
  - Tekillik denetiminin sadece `PriceSnapshot` tablosu üzerinde değil, aynı zamanda `RawGlobalPrice` tablosunun `observed_at` zaman damgaları üzerinde de yapılması.
  - Eğer o tarihe ait bir raw fiyat veya snapshot mevcutsa kaydın atlanarak veritabanının `UniqueConstraint` ihlaliyle çökmesinin %100 engellenmesi.
- **DoD:**
  - DB'de manuel olarak sadece `RawGlobalPrice` kaydı oluşturulduğunda dahi betiğin IntegrityError fırlatmadan bu kaydı atlayabilmesi.

### `[x]` Faz 4: Entegrasyon ve Regresyon Testleri
- **Yapılacaklar:**
  - Değişiklikler yapıldıktan sonra tüm pytest entegrasyon testlerinin yürütülmesi.
  - Yapılan değişikliklerin git reposuna commit & push edilmesi.
- **DoD:**
  - `pytest` komutu çalıştırılarak tüm 77 entegrasyon testinin (yeni yazılan backfill testi dahil) yeşil olması.

---

## ❓ Açık Sorular
> [!NOTE]
> Herhangi bir açık soru veya mimari belirsizlik bulunmamaktadır. Yapılacak tüm güncellemeler tek bir betik (`backfill_history.py`) üzerinde izole ve güvenlidir.
