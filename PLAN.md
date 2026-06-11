# Implementation Plan: SilverPilot Sağlamlaştırma, OOP Modülerlik ve SaaS Mimari Geçişi

> [!WARNING]
> This file is an archive of the active stabilization effort. It is not a
> canonical source for current SilverPilot phase status, implementation order,
> or execution authority.
>
> Refer to `docs/PHASE_PLAN.md` for the live baseline.

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:** [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Makas, Staleness, Volatilite, Kayıp Limitleri, Komisyon/Vergi Hesapları)
- **Etkilenen Şemalar:** `signals`, `agent_memory_events`, `technical_indicators`, `raw_bank_prices`, `raw_news`, `paper_trades`
- **Ana Hedef:** Projedeki anlık spam ve strateji eşleşme hatalarını çözmek, haber sentiment algoritmasındaki seyreltme hatasını gidermek, projenin tamamını genişletilebilir OOP (Abstract Base Classes) yapısına kavuşturmak ve hem indikatörlerde hem de stratejilerde finansal bilgisi olmayan kullanıcılar için "AUTO" (Piyasa Rejimine Göre Dinamik Karar Verici) modunu inşa etmek.

---

## 🛠️ Fazlar ve Görev Listesi

### **Faz 1: Çekirdek Hata Giderme, Test ve Dökümantasyon Stabilizasyonu**
- [x] [PLAN.md](file:///Users/boe747/SilverPilot/PLAN.md) dosyasına docs tutarlılık kontrolü testini (`test_docs_consistency.py`) geçmesi için gerekli canonical warning bloğunu eklemek. (Ajan: `project-planner`)
- [x] [auto_trader.py](file:///Users/boe747/SilverPilot/apps/api/app/services/auto_trader.py) içerisindeki `settings.strategy_name` değerini dinamik olarak okuyup ilgili strateji metoduna yönlendiren router yapısını kurmak (sabit `strategy_v2` hardcode bağımlılığını sonlandırmak).
- [x] `send_telegram_notification` fonksiyonundaki `HOLD` sessiz mesaj gönderme mantığını; cooldown (6 saatte bir) veya sadece neden kodu (`reason_code`) değiştiğinde mesaj atacak şekilde revize etmek.
- [x] **COMEX Zaman Aşımı / Staleness Bypass Düzeltmesi:** Hafta sonu ve bakım saatlerinde `indicator_readiness.py`'nin ürettiği `stale` bayrağının strateji motorunu (`StrategyRunner`) kitlemesini engellemek için, COMEX kapalıyken freshness kontrolünü strateji seviyesinde de bypass edecek kuralı eklemek.
- [x] `test_blended_trader.py` içerisindeki blended consensus testlerinin strategy router düzeltildikten sonra başarıyla geçmesini sağlamak.
- *DoD (Tamamlanma Tanımı):* `pytest tests/test_auto_trader.py tests/test_blended_trader.py tests/test_docs_consistency.py` komutlarının sıfır hata ile yeşil yanması.

---

### **Faz 2: Haber Sentiment Matematiksel Düzeltmesi ve Çok Boyutlu Etki Analizi**
- [x] LLM (Hermes) promptuna haberin gümüş üzerindeki ilgililik derecesi (`relevance`) ile birlikte haberin şiddetini/büyüklüğünü belirten `impact_severity` (0.0 - 1.0) parametre analizini eklemek.
- [x] [hermes.py](file:///Users/boe747/SilverPilot/apps/api/app/agents/hermes.py) içerisindeki ağırlıklı sentiment formülünü, ilgisiz veya spekülatif haberlerin seyreltme yapmasını önleyecek şekilde "Ağırlıklı İlgi ve Şiddet Ortalaması" olarak güncellemek:
  $$\text{final\_score} = \frac{\sum (\text{sentiment\_numeric} \times (1 - \text{speculation}) \times \text{relevance} \times \text{impact\_severity} \times \text{source\_weight})}{\sum (\text{relevance} \times \text{impact\_severity} \times \text{source\_weight})}$$
- [x] LLM (Hermes) promptunda gümüşü dolaylı etkileyen tüm faktörlerin (DXY, Altın/Emtia korelasyonları, faiz kararları, enflasyon verileri vb.) korelasyon ilişkisini tanımlayarak LLM'in doğru `relevance` ve `impact_severity` üretmesini sağlamak.
- [x] `test_hermes_agent.py` test suite'ini güncel formüle ve etki kurallarına göre revize etmek.
- *DoD:* `pytest tests/test_hermes_agent.py` test suite'inin yeşil olması.

---

### **Faz 3: OOP Modülerlik ve Fiyat/Haber/Komisyon Sağlayıcı Katmanı (OOP / Architecture Refactor)**
- [x] Fiyat sağlayıcıları için soyut bir interface olan `BasePriceScraper` (Abstract Base Class - ABC) oluşturmak ve `fetch_price(db, asset) -> PriceSnapshot` kontratını tanımlamak. (Ajan: `backend-architect`)
- [x] Haber sağlayıcıları ve metin tabanlı veriler için soyut bir interface olan `BaseNewsCollector` (ABC) oluşturmak ve `collect(db) -> list[RawNews]` kontratını tanımlamak.
- [x] **Banka Komisyon ve Vergi Modeli (`BaseCostModel`):** Her bankanın/sağlayıcının makas (spread), vergi (BSMV %0.2) ve komisyon oranlarını hesaplayan soyut `BaseCostModel` (ABC) tanımlamak. `KuveytTurkCostModel` ve `ZiraatCostModel` sınıflarını buradan türetmek.
- [x] **Modüler Risk Kuralları (`BaseRiskGuard`):** Risk filtrelerini (Spread, Staleness, Volatilite vb.) modüler hale getirmek için `BaseRiskGuard` (ABC) tanımlamak ve mevcut kuralları birer kural sınıfı olarak soyutlamak.
- [x] **Modüler İndikatör Hesaplayıcılar (`BaseIndicator`):** İndikatör hesaplama fonksiyonlarını `BaseIndicator` (ABC) yapısına geçirmek.
- [x] Stratejiler için `BaseStrategy` soyut sınıfı oluşturmak ve `evaluate(db, context) -> StrategyDecision` kontratını zorunlu kılmak.
- *DoD:* Refaktör sonrasında tüm ingestion ve trade execution testlerinin (`pytest tests/test_collectors.py tests/test_auto_trader.py`) hatasız geçmesi.

---

### **Faz 4: AUTO Strateji ve AUTO İndikatör Motoru**
- [x] Piyasa rejimini (`get_market_regime`) 1 saatlik bar aralıklarıyla sorgulayarak dominant stratejiyi seçen `AutoRegimeStrategy` sınıfını (`BaseStrategy` türevi) yazmak.
  - `ADX < 20` veya BB Bandwidth dar ise: Mean-reversion stratejilerini (RSI, Bollinger) çalıştırır.
  - `ADX >= 25` ise: Trend-following stratejisini (SMA Cross, MACD) çalıştırır.
- [x] İndikatör hesaplamalarında, kullanıcının seçmediği durumda en doğru indikatör setini otomatik ağırlıklandıran "AUTO İndikatör Seçim Mantığı"nı karar mekanizmasına dahil etmek.
- [x] `test_auto_strategy.py` adında yeni bir test dosyası oluşturarak auto modunun test senaryolarını yazmak.
- *DoD:* `pytest tests/test_auto_strategy.py` testlerinin başarıyla tamamlanması.

---

### **Faz 5: SaaS Veri Tabanı ve Çoklu Tenant Altyapısı**
- [ ] Veri tabanında `providers` (banka sağlayıcıları ayarları), `tenant_portfolios` (kullanıcı hesapları ve banka eşleşmeleri) ve `strategy_parameters` (kullanıcının seçtiği indikatör parametreleri) tablolarını oluşturacak Alembic migrasyonunu yazmak.
- [ ] `collectors/service.py` içinde hardcode olarak duran `31.1035` birim dönüşüm katsayısını dynamic veri tabanı conversion tablosuna taşımak.
- *DoD:* Canlı PostgreSQL üzerinde Alembic migration'ın sorunsuz uygulanması ve `verify_execution_pipeline.py` smoke testinin başarılı olması.

---

## 📌 Netleşen Kararlar (Socratic Gate)
- **AUTO Strateji Karar Sıklığı:** 1 saatlik bar aralıklarıyla rejim analizi yapılmasına karar verildi (Aşırı makas kaybını engellemek amacıyla günlük yerine saatlik barlar seçildi).
- **Haber Korelasyon Ağırlıklandırması:** Altın, DXY ve faiz gibi makro haberlerin gümüş üzerindeki etki gücü, LLM promptuna eklenen `relevance` (ilgililik) ve `impact_severity` (şiddet) parametreleri üzerinden dinamik olarak ölçeklenecektir.
- **Haber Modülerliği:** Metin tabanlı haber kaynakları `BaseNewsCollector` (ABC) soyut sınıfı altında toplanarak OOP mimarisine entegre edilecektir.
- **Banka Kesintileri, Makas ve Vergiler:** Banka bazlı değişken komisyon ve vergileri yönetebilmek için soyut `BaseCostModel` mimarisi kurulacaktır.
- **Risk ve İndikatör Modülerliği:** Gelecekte sisteme kolayca yeni risk kuralları ve indikatör tipleri eklenebilmesi amacıyla `BaseRiskGuard` ve `BaseIndicator` soyut sınıfları tanımlanacaktır.
- **Bypass Çelişkisi Düzeltmesi:** Hafta sonları ve tatil günlerinde indikatör freshness kilitlerinin işlem yapmayı tamamen bloke etme hatası Faz 1'de çözülecektir.