# Implementation Plan: SilverPilot Derin Kod Denetimi ve Zafiyet Analizi (Audit & Hardening)

Bu plan, yapay zeka desteğiyle geliştirilmiş SilverPilot platformunun tüm kritik modüllerini, veri yollarını, veritabanı transaction güvenlik katmanlarını ve finansal risk yönetim mekanizmalarını parça parça taramak, AI kaynaklı mantıksal hataları ve mimari açıkları tespit edip gidermek amacıyla hazırlanmış **Derin Kod Denetimi ve Sıkılaştırma (Audit & Hardening)** yol haritasıdır.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:** [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Finansal limitler ve risk geçitleri), [docs/DATA_CONTRACTS.md](file:///Users/boe747/SilverPilot/docs/DATA_CONTRACTS.md) (Veri şemaları ve entegrasyon sözleşmeleri).
- **Hedef Tehdit Vektörleri:**
  1. **SQLAlchemy Oturum Sızıntıları:** Kapatılmayan session'lar, transaction havuzunun şişmesi ve `DetachedInstanceError` hataları.
  2. **Finansal Risk Geçidi Açıkları:** Stale data (bayat fiyat verisi) kullanımı, bakiye doğrulama bypass açıkları, hatalı gerçekleşen stop-loss tetikleyicileri.
  3. **Yarış Durumları (Race Conditions):** Eşzamanlı isteklerde (özellikle toplayıcılar ve trade emirleri çalışırken) oluşabilecek veri kilitlenmeleri.
  4. **Hata Yakalama Gaps (Exception Swallowing):** Hataların sessizce yutulması nedeniyle sistemin çöktüğü halde çalışıyor görünmesi.

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Altyapı, Veri Tabanı ve Oturum Güvenliği (Bölge 1)**
  - **Denetlenecek Alanlar:** `apps/api/app/core/`, `apps/api/app/models/`, `apps/api/app/schemas/`
  - [x] **DB Session Lifecycle Audit:** Veritabanı oturumlarının (session) FastAPI dependency injection yapısında (`get_db`) düzgün kapatıldığını doğrulamak.
  - [x] **Transaction Leak Checks:** Kod tabanında `db.commit()` veya `db.rollback()` işlemlerinin asenkron/senkron döngülerde açık bağlantı (connection leak) bırakıp bırakmadığını denetlemek.
  - [x] **Pydantic Validation Gaps:** Pydantic şemalarında (`schemas/`) eksik tip doğrulamaları ve runtime çökmelerine neden olabilecek zayıf veri tiplerini tespit etmek.
  - *Ajanlar:* `backend-architect`, `debugger-agent`
  - *DoD (Tamamlanma Tanımı):* Mevcut yerel testlerin sıfır hata ile geçmesi ve SQLAlchemy bağlantı havuzu (connection pool) sızıntı testinin başarıyla tamamlanması.

- `[x]` **Faz 2: Veri Toplama, Entegrasyonlar ve LLM Katmanı (Bölge 2)**
  - **Denetlenecek Alanlar:** `apps/api/app/collectors/`, `apps/api/app/llm/`
  - [x] **Collector Robustness Audit:** Harici servislerden (TCMB, Yahoo, Kuveyt vb.) veri çeken toplayıcıların ağ kesintilerinde, hatalı JSON/XML yanıtlarında veya timeout durumlarında çökmeden hata loglaması ve kaldığı yerden devam etmesi (graceful degradation).
  - [x] **Duplicate Data Prevention:** Mükerrer fiyat kayıtlarının veritabanına yazılmasını önleyen unique index ve constraint yapılarının doğrulanması.
  - [x] **LLM Gateway Exception Handling:** DeepSeek API kesintilerinde veya bütçe aşımlarında (`DEEPSEEK_DAILY_BUDGET_USD`) sistemin çökmeden nötr kararlarla yoluna devam edebilme mekanizmasının denetimi.
  - *Ajanlar:* `data-engineer`, `security-auditor`
  - *DoD:* Ağ kesinti taklit edilen (mocked network failures) kolektör testlerinin başarıyla geçmesi.

- `[x]` **Faz 3: Karar Algoritmaları, Paper Trading ve Risk Motoru (Bölge 3)**
  - **Denetlenecek Alanlar:** `apps/api/app/services/`, `apps/api/app/paper_trading/`, `apps/api/app/risk/`
  - [x] **Pre-Trade Risk Engine Deep Dive:** Risk motorundaki bayat veri kontrolünün (`evaluate_paper_trade_risk`) milisaniyelik gecikmeleri veya geciken zaman dilimlerini (timezones) doğru yakaladığından emin olunması.
  - [x] **Balance and Equity Guard:** Yetersiz bakiye durumlarında paper trade alımlarının kesinlikle engellenmesi, negatif nakit veya negatif varlık bakiyesi oluşma ihtimallerinin bertaraf edilmesi.
  - [x] **Stop-Loss and Slippage Accuracy:** Stop-loss hesaplamalarının ve komisyon oranlarının (fees, taxes) gerçeğe uygun şekilde uygulandığının ve slipaj (fiyat kayması) durumlarının simüle edilme doğruluğunun denetimi.
  - [x] **Strategy Engine Boundary Checks:** `StrategyRunner` içerisindeki indikatör eşik değerlerinin (RSI sınırları vb.) sınır durumlarında (edge-cases) hatalı karar vermediğinin doğrulanması.
  - *Ajanlar:* `backend-architect`, `data-engineer`, `debugger-agent`
  - *DoD:* Özel olarak hazırlanmış uç sınır durum (edge-case / boundary) paper-trade simülasyon testlerinin yazılması ve başarıyla geçmesi.

- `[x]` **Faz 4: Dış Arayüzler, Ajanlar ve Telegram Entegrasyonu (Bölge 4)**
  - **Denetlenecek Alanlar:** `apps/api/app/api/`, `apps/api/app/agents/` (auditor, news, hermes), Telegram Bot
  - [x] **FastAPI Router Authorization & OWASP:** API uç noktalarında yetkisiz erişim kontrolleri (Zero-Trust denetimi) ve SQL injection / parametre manipülasyonu açıklarının taranması.
  - [x] **Agent Memory Persistence Audits:** `auditor-agent`, `news-agent` ve `hermes-agent` bellek durumlarının (`AgentMemoryEvent`) veritabanında doğru indexlendiğinin ve sorguların şişmeye neden olmadığının doğrulanması.
  - [x] **Telegram Webhook/Polling Connection Stability:** Ağ kopmalarında veya Telegram API sınırlamalarında (rate-limiting) bildirimlerin yutulmaması için kuyruklama mekanizmasının ve hata toleransının denetlenmesi.
  - *Ajanlar:* `security-auditor`, `quality-engineer`
  - *DoD:* API ve Ajan uç noktaları için OWASP güvenlik taramalarının yeşil çıkması.

---

## ❓ Açık Sorular

> [!IMPORTANT]
> 1. **Model Tercihi:** Bu derin denetim ve hata ayıklama operasyonu yüksek muhakeme gerektirdiğinden, kritik inceleme adımlarında **Gemini 3.5 Pro** modeli ile çalışmayı öneriyoruz. Bu model geçiş protokolünü onaylıyor musunuz?
> 2. **Faz-Faz İlerleme:** Denetim sırasında tespit edeceğimiz açıkları anında düzelterek mi ilerleyelim, yoksa her fazın sonunda toplu bir bulgu raporu sunup onayınızı aldıktan sonra mı düzeltmeleri uygulayalım? *(Önerimiz: Tespit edilen zafiyetlerin anında düzeltilip test edilerek faza dahil edilmesidir.)*
