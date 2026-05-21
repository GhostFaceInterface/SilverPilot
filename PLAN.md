# Implementation Plan: Phase 5.5 - Deterministic Signal & Backtest Engine

Bu plan, SilverPilot projesinde **Option B (Backtest-First)** ve **Option C (Deterministic Signal Engine)** yaklaşımlarını birleştiren **Phase 5.5** aşamasının adım adım, düşük riskli ve son derece modüler bir şekilde hayata geçirilmesini amaçlar.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Gereken verilerin eksikliği durumunda bloklama, kağıt üzerinde işlem kuralları, gerçek para/banka entegrasyonu yasağı, işlem limitleri).
  - [docs/DATA_CONTRACTS.md](file:///Users/boe747/SilverPilot/docs/DATA_CONTRACTS.md) (Zaman damgası tekilliği, UTC uyumluluğu, deterministik ve izole indikatör/sinyal verileri).
- **Etkilenen Dosyalar (Create / Modify):**
  - **Modify:** `apps/api/app/models/entities.py` (Database model güncellemesi)
  - **Create:** `apps/api/app/schemas/signal.py` (Pydantic doğrulama şemaları)
  - **Create:** `apps/api/app/services/strategy.py` (Deterministik Strateji Koşucusu)
  - **Create:** `scripts/backtest_engine.py` (Yerel/Çevrimdışı Tarihsel Simülasyon Motoru)
  - **Create:** `scripts/verify_execution_pipeline.py` (Dry-run Entegrasyon ve Doğrulama Betiği)
  - **Create/Modify:** `apps/api/tests/` altındaki pytest test dosyaları

---

## 🛠️ Fazlar ve Görev Listesi

### `[x]` Faz 1: Database Migration & Schema Design (signals tablosu)
- **Açıklama:** Mevcut `Signal` modelinin Phase 5.5 gereksinimlerine göre yeniden yapılandırılması ve veritabanı migrasyonunun tamamlanması.
- **Yapılacaklar:**
  - [x] `apps/api/app/models/entities.py` içindeki `Signal` modelinin güncellenmesi (Ajan: `backend-architect`):
    - `id`: Serial Primary Key.
    - `observed_at`: DateTime(timezone=True) (UTC, index-enabled, nullable=False).
    - `price_snapshot_id`: Integer, ForeignKey referencing `price_snapshots.id` (nullable=False).
    - `indicator_id`: Integer, ForeignKey referencing `technical_indicators.id` (nullable=True - indikatörsüz stratejiler için).
    - `action`: String(16) (Values: `'BUY'`, `'SELL'`, `'HOLD'`, nullable=False).
    - `reason_code`: String(64) (e.g., `'RSI_OVERSOLD'`, `'RSI_OVERBOUGHT'`, `'SMA_GOLDEN_CROSS'`, nullable=False).
    - `price_usd_oz`: Numeric(18, 6) (nullable=False).
    - `details_json`: JSON (nullable=False, default=dict).
    - `created_at`: DateTime(timezone=True) (server_default=func.now()).
  - [x] `apps/api/app/schemas/signal.py` şema dosyasının sıfırdan oluşturulması (Pydantic tabanlı doğrulama).
  - [x] Alembic migrasyonunun oluşturulması:
    ```bash
    cd apps/api
    poetry run alembic revision --autogenerate -m "refactor_signals_table"
    ```
  - [x] Migrasyonun local PostgreSQL üzerinde test edilmesi (`poetry run alembic upgrade head`).
- **DoD (Tamamlanma Tanımı):**
  - PostgreSQL veritabanında `signals` tablosunun belirtilen kolonlarla başarıyla oluşturulması.
  - `pytest` entegrasyon testlerinin migrasyon veya model uyuşmazlığı olmadan sıfır hata ile çalışması.

### `[x]` Faz 2: Deterministic Strategy Runner (app/services/strategy.py)
- **Açıklama:** Teknik indikatörleri okuyarak deterministik alım-satım kararları alan saf/matematiksel motorun yazılması.
- **Yapılacaklar:**
  - [x] `apps/api/app/services/strategy.py` dosyasının oluşturulması (Ajan: `backend-architect`).
  - [x] **Purity of Calculations:** İndikatör değerlendirme ve sinyal üretim mantığının veritabanı veya harici durum yan etkisi (side-effect) olmadan, tamamen deterministik matematiksel fonksiyonlar şeklinde tasarlanması.
  - [x] **Inventory/State Constraints (Envanter Kısıtları):** Üst üste binen (overlapping) sinyallerin engellenmesi. Eğer halihazırda açık bir sanal pozisyon varsa yeni bir `BUY` sinyali üretilmemelidir.
  - [x] **Signal Expiration:** Sinyallerin sadece belirli bir bar penceresi (active window of N bars) için geçerli olmasının sağlanması.
  - [x] **Temel Stratejilerin İmplementasyonu:**
    - **RSI (14):** RSI < 30 ise `BUY` (Oversold), RSI > 70 ise `SELL` (Overbought).
    - **SMA Cross (20/50/200):** Altın Kesişim (SMA20 > SMA50) durumunda `BUY`, Ölüm Kesişimi durumunda `SELL`.
    - **Bollinger Bands (20, 2):** Alt banda dokunulduğunda `BUY`, üst banda dokunulduğunda `SELL`.
- **DoD (Tamamlanma Tanımı):**
  - `apps/api/tests/test_strategy.py` altında strateji kurallarını test eden pytest test süitinin tamamlanması ve %100 başarılı olması.
  - Testlerin edge-case (sıfır veri, NaN indikatör değerleri, aşırı oynak fiyatlar) durumlarında hata fırlatmadan güvenli bir şekilde `HOLD` kararı ürettiğinin doğrulanması.

### `[x]` Faz 3: Offline Backtest Engine (scripts/backtest_engine.py)
- **Açıklama:** Geçmişe dönük 2 yıllık günlük `"yahoo-si-f-1d"` ve 5m intraday verileri üzerinden simülasyon yapan çevrimdışı motorun kurulması.
- **Yapılacaklar:**
  - [x] `scripts/backtest_engine.py` scriptinin sıfırdan oluşturulması (Ajan: `data-engineer`).
  - [x] **Simülasyon Döngüsü (Execution Loop):** Tarihsel `price_snapshots` ve `technical_indicators` verilerinin kronolojik olarak çekilerek sırayla Strategy Runner'a aktarılması.
  - [x] **İşlem Maliyeti & Gerçekçi Sürtünme Modeli (Transaction Cost Reality):**
    - **Spread:** Kuveyt Türk tarihsel spread farklarının (örneğin %2 ile %4 arası) veya yapılandırılabilir sabit bir spread oranının uygulanması.
    - **Metals Tax (Vergi):** Türkiye Cumhuriyeti banka altın/gümüş satış işlemlerinde uygulanan %0.2 BSMV/vergi kesintisinin net hasılattan düşülmesi.
    - **Banka Ücretleri (Fees):** İşlem başına sabit $0.05 USD ücret uygulanması.
    - **Kayma (Slippage):** İletim ve işlem gecikmesi kaynaklı olarak fiyatta %0.05 oranında negatif kayma etkisi yansıtılması.
  - [x] **Muhasebe Motoru (Accounting Engine):**
    - Başlangıç portföy bakiyesinin $600 USD olarak set edilmesi.
    - Her adımda gerçekleşen (realized) ve gerçekleşmeyen (unrealized) PnL hesabının yapılması.
    - Her adımın bakiye durumunu tutan bir Equity Curve dizisi oluşturulması.
  - [x] **Metrik ve Performans Analizörleri:**
    - Net PnL (USD & % getiri).
    - Maksimum Çekilme (Max Drawdown - MDD) hesabı.
    - Win Rate (%) ve Profit Factor (Gross Profits / Gross Losses).
    - Maliyet Yükü (Cost Drag % = Toplam maliyetler / Bitiş bakiyesi).
  - [x] **Buy & Hold Benchmark Karşılaştırması:**
    - İlk snapshot anında tüm bakiye ile ($600 USD) gümüş alıp, son snapshot anında satma (Buy and Hold) simülasyonunun aynı tarih aralığı için çalıştırılması.
    - Strateji performansı ile Buy & Hold performansının yan yana terminale yazdırılması.
- **DoD (Tamamlanma Tanımı):**
  - `python scripts/backtest_engine.py --strategy rsi --timeframe 1d` komutunun terminalde hatasız çalışması ve karşılaştırmalı performans raporunu basması.
  - `pytest apps/api/tests/test_backtest.py` testlerinin yazılması; drawdown ve vergi hesaplamalarının matematiksel olarak doğrulanması.

### `[x]` Faz 4: E2E Verification & Automated Tests
- **Açıklama:** Sistemin uçtan uca çalışabilirliğini, paper-trading veritabanı kısıtlarını ve deterministik entegrasyonu doğrulayan mekanizmaların kurulması.
- **Yapılacaklar:**
  - [x] `scripts/verify_execution_pipeline.py` doğrulama betiğinin sıfırdan yazılması (Ajan: `quality-engineer`).
  - [x] Betiğin; indikatörleri okuması, strateji değerlendirmesi yapması, mock veritabanı oturumları ve rollback desteğiyle `signals` ve `paper_trades` tablolarına deneme kayıtları atarak risk engine kurallarını test etmesi.
  - [x] **No-LLM Dependency:** Tüm doğrulama ve backtest süreçlerinin hiçbir harici API key (OpenRouter vb.) veya LLM çağrısı gerektirmeden tamamen local/offline çalışmasının garanti edilmesi.
  - [x] **Safety-Gatekeeper Statik İncelemesi:** Kodların deploy edilmeden önce statik analiz kurallarına göre taranması.
- **DoD (Tamamlanma Tanımı):**
  - `python scripts/verify_execution_pipeline.py` betiğinin dry-run modunda sıfır hata kodu (exit code 0) ile tamamlanması.
  - Projedeki tüm test süitinin (`pytest`) başarıyla yeşile dönmesi.

---

## ❓ Açık Sorular & Riskler
> [!IMPORTANT]
> 1. **Geriye Dönük Sinyal Uyumsuzluğu:** Mevcut `Signal` tablosundaki kayıtların yeni kolon yapısına (`observed_at`, `price_snapshot_id`, vb.) dönüştürülmesi gerekiyor mu, yoksa eski veriler temizlenebilir mi? (Paper-trading aşamasında olduğumuz için eski signals verilerinin silinmesinde veya tablonun sıfırdan oluşturulmasında bir sakınca bulunmamaktadır.)
> 2. **İndikatör Çözünürlüğü:** Backtest simülasyonunda 1 günlük `"yahoo-si-f-1d"` ile 5m intraday verilerinin her ikisi için de teknik göstergeler eksiksiz hesaplanabiliyor mu? (Evet, Phase 3.9 kapsamında backfill yapıları tamamlandığı için veriler hazırdır.)
