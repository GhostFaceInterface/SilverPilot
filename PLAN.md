# Implementation Plan: Phase 8 - Agent-Assisted Strategy Backtesting & Refinement (Option A: Offline-First Pre-cached LLM)

Bu plan, **Option A: Offline-First Pre-cached LLM (Tarihsel Önbellek & Geriye Dönük Walk-Forward Simülasyonu)** mimarisi uyarınca, News Agent ve Risk Agent kararlarının geriye dönük walk-forward strateji simülasyonlarına entegre edilmesi için hazırlanmıştır. 

Tarihsel simülasyonlar sırasında binlerce bar için canlı LLM (DeepSeek) çağrısı yapmak aşırı API gecikmelerine, zaman aşımlarına ve devasa finansal maliyetlere yol açacaktır. Bu sorunu aşmak için, gümüş fiyatlarının tarihsel periyotlarına karşılık gelen haber sentimentlerini ve risk critique kararlarını veritabanında pre-cache (tarihsel önbellek) olarak saklayacağız. Backtest motorumuz, simülasyon sırasında canlı LLM'e gitmek yerine bu yerel önbellekten sorgulama yapacaktır.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - [docs/ARCHITECTURE.md](file:///Users/boe747/SilverPilot/docs/ARCHITECTURE.md) (Deterministic accounting rules, agent signal critique boundary).
  - [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (No real-money operations, local budget guard rules).
- **Etkilenen Dosyalar:**
  - `apps/api/app/models/entities.py` *(Yeni `HistoricalAgentCache` tablosunun tanımlanması)*
  - `apps/api/app/services/strategy.py` *(Strateji değerlendirmesine Ajan filtrelerinin entegre edilmesi)*
  - `scripts/backtest_engine.py` *(Simülasyon döngüsünün ajan verilerini okuyacak şekilde güncellenmesi ve karşılaştırma raporu)*
  - `scripts/seed_agent_cache.py` *[NEW]* *(Tarihsel fiyat barlarına denk gelen ajan kararlarının ve sentimentlerinin tohumlanması / seeder)*
  - `apps/api/tests/test_backtest.py` *(Yeni ajanlı backtest senaryolarının test edilmesi)*

---

## 🛠️ Fazlar ve Görev Listesi

### **Faz 1: Veritabanı Modeli ve Alembic Migrasyonu**
- **Açıklama:** Geriye dönük ajan kararlarını saklayacağımız `historical_agent_caches` tablosunu tanımlayacak ve Alembic migrasyonu ile veritabanına uygulayacağız.
- **Yapılacaklar:**
  - [ ] `apps/api/app/models/entities.py` dosyasına `HistoricalAgentCache` tablosunu ekleyin (Ajan: `backend-architect`):
    ```python
    class HistoricalAgentCache(Base):
        __tablename__ = "historical_agent_caches"

        id: Mapped[int] = mapped_column(primary_key=True)
        agent_name: Mapped[str] = mapped_column(String(128), index=True)      # news-agent, risk-agent
        event_type: Mapped[str] = mapped_column(String(64), index=True)       # news_sentiment, signal_critique
        timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True) # Eşleşen bar zamanı
        value_json: Mapped[dict] = mapped_column(JSON, default=dict)          # Sentiment/Critique JSON payload
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ```
  - [ ] Alembic migrasyonu oluşturun: `docker-compose exec api alembic revision --autogenerate -m "add historical agent cache"`
  - [ ] Migrasyonu test edin ve veritabanına uygulayın: `docker-compose exec api alembic upgrade head`
- **DoD (Tamamlanma Tanımı):** `historical_agent_caches` tablosunun veritabanında başarıyla şemaya eklenmesi.

### **Faz 2: Tarihsel Ajan Kararı Tohumlama Scripti (Seeder)**
- **Açıklama:** Backtest simülasyonunun testi ve çalışması için geriye dönük fiyat snapshot barlarına karşılık gelen gerçekçi Ajan kararlarını (News Sentiment: BULLISH/BEARISH/NEUTRAL, Risk Critique: APPROVED/REJECTED/CAUTION) veritabanına tohumlayacak scripti yazacağız.
- **Yapılacaklar:**
  - [ ] `scripts/seed_agent_cache.py` seeder scriptini oluşturun (Ajan: `data-engineer`):
    - Gümüş fiyatlarının `observed_at` tarihsel barlarını listelesin.
    - Her bara karşılık gelecek şekilde gerçekçi ve tutarlı (fiyat yükselirken BULLISH/APPROVED, düşerken BEARISH/REJECTED) veya stokastik ajan sentimentleri/kararları üreterek `HistoricalAgentCache` tablosuna yazsın.
    - Script doğrudan terminalden çalıştırılabilmelidir.
- **DoD:** `python scripts/seed_agent_cache.py` çalıştırıldığında barlar için önbelleğin başarıyla dolması.

### **Faz 3: Strategy Runner ve Ajan Filtre Entegrasyonu**
- **Açıklama:** Mevcut deterministik stratejilerimizin (RSI, SMA Cross, Bollinger) ürettiği BUY/SELL sinyallerini, Ajan önbelleğinden çekilecek sentiment ve kritik kararlarına göre veto edebilecek veya onaylayacak logic yapısını kuracağız.
- **Yapılacaklar:**
  - [ ] `apps/api/app/services/strategy.py` içerisindeki `StrategyRunner` sınıfına ajan filtresi mantığını ekleyin (Ajan: `backend-architect`):
    - `apply_agent_filters(action: str, news_sentiment: str | None, risk_decision: str | None) -> tuple[str, str]` metodunu ekleyin.
    - Eğer deterministik karar `BUY` ise ve en son `news_sentiment` değeri `BEARISH` ise veya `risk_decision` değeri `REJECTED` ise, işlemi engellesin (`action = "HOLD"`, `reason = "AGENT_VETO_BEARISH_NEWS"` veya `AGENT_VETO_RISK_REJECTED`).
    - Eğer karar `SELL` ise ve ajan kararları tehlikeli bir durum gösteriyorsa (örneğin aşırı riskli bir piyasa haberi veya trend dönüşü tespiti), satışı hızlandıracak veya destekleyecek veto kuralları tasarlayın.
- **DoD:** Ajan kararlarına göre deterministik sinyallerin başarıyla veto edilip "HOLD" durumuna çekilmesi.

### **Faz 4: Backtest Engine Güncellemesi ve Karşılaştırma Raporu**
- **Açıklama:** `scripts/backtest_engine.py` simülasyon döngüsünü, barların zaman damgasına en yakın tarihsel ajan kararlarını sorgulayacak, ajanlı strateji varyantlarını destekleyecek ve premium karşılaştırma raporu sunacak şekilde güncelleyeceğiz.
- **Yapılacaklar:**
  - [ ] `scripts/backtest_engine.py` simülasyon motorunu güncelleyin (Ajan: `backend-architect`):
    - Her simülasyon barında, o barın `observed_at` tarihine ait (veya son 24 saat içindeki en taze) `HistoricalAgentCache` kayıtlarını çeksin.
    - Yeni ajan destekli strateji tiplerini desteklesin: `rsi_with_agents`, `sma_cross_with_agents`, `bollinger_with_agents`.
    - Ajan veto kararlarını ve override nedenlerini trading loguna ve ekrana yazdırsın.
    - Simülasyon sonunda, **Baseline Deterministik Strateji** ile **Ajan Destekli Strateji** ve **Buy & Hold Benchmark'ını** yan yana koyup Net Alpha, Max Drawdown, Kazanma Oranı ve İşlem Maliyeti (Cost Drag) farklarını gösteren premium renkli bir karşılaştırma raporu bassın.
- **DoD:** Simülatörün ajan destekli stratejileri sıfır canlı LLM çağrısıyla, tamamen veritabanı önbelleğinden beslenerek saniyeler içinde çalıştırıp karşılaştırma raporunu basması.

### **Faz 5: Kalite Kontrol, E2E Testler ve Doğrulama**
- **Açıklama:** Ajanlı backtest mantığını tamamen test edecek kapsamlı pytest testlerini yazacağız ve tüm test süitinin hatasız çalıştığını doğrulayacağız.
- **Yapılacaklar:**
  - [ ] `apps/api/tests/test_backtest.py` dosyasına yeni test senaryoları ekleyin (Ajan: `quality-engineer`):
    - Ajan verisi tohumlanmış SQLite in-memory ortamında backtestin çalıştırılması.
    - `BEARISH` haber sentimentinin veya `REJECTED` risk kararının BUY işlemini başarıyla bloke ettiğini (veto ettiğini) doğrulayan iddialar (assertions).
    - Önbellekte ajan verisi olmadığında stratejinin deterministik kurallarla çökmeden (graceful fallback) devam ettiğinin doğrulanması.
  - [ ] Tüm test süitini `.venv/bin/pytest` ile koşturarak regresyon olmadığını doğrulayın.
- **DoD:** Tüm pytest test süitinin 100% yeşil olması ve ajan vetolarının testler altında doğrulanması.

---

## ❓ Açık Sorular ve Kararlar
> [!IMPORTANT]
> - **Zaman Pencereleri:** Tarihsel ajan cache verisini sorgularken, tam zaman damgası eşleşmesi yerine (çünkü haberler ve fiyat barları saniye saniye denk gelmeyebilir), fiyattan önceki **son 24 saatlik en taze kararı** baz alan bir `observed_at` penceresi kullanmayı planlıyoruz. Bu tolerans aralığı tasarımı onayınızda mıdır?
