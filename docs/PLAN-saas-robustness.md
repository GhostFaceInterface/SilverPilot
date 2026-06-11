# PLAN-saas-robustness.md - SilverPilot Robustness & SaaS OOP Migration Plan

> [!WARNING]
> This file is a roadmap and design document for the SaaS and OOP transition. Refer to `docs/PHASE_PLAN.md` for the live canonical baseline of execution status.

## 1. Goal Description
Bu plan, SilverPilot projesindeki mevcut test başarısızlıklarını gidermeyi, haber sentiment seyreltme hatasını düzeltmeyi, finansal korelasyonları (Altın-Gümüş ilişkisi) modele doğru entegre etmeyi ve projenin OOP prensiplerine göre baştan sona modüler bir SaaS altyapısına taşınmasını hedefler.

---

## 2. User Review Required

> [!IMPORTANT]
> **Finansal Korelasyon Kararı:** Altın ve makro haberler gümüş fiyatlarını doğrudan etkilemektedir (%80+ korelasyon). Bu nedenle Altın haberleri spekülasyon değil, yüksek derecede ilgili haberler olarak değerlendirilmeli ve sentiment hesaplamasında doğru ağırlıklandırılmalıdır.

> [!IMPORTANT]
> **OOP Soyutlama Katmanları:** Tüm banka toplayıcıları, stratejiler ve indikatörler abstract Python class'ları arkasına alınacaktır. Gelecekte yeni bir banka veya indikatör eklendiğinde ana motor kodlarında sıfır değişiklik yapılacaktır.

---

## 3. Proposed Changes

### Component 1: Core Stabilization (Faz 1)
Mevcut testlerin geçmesini sağlamak ve Telegram spamini susturmak.

#### [MODIFY] [auto_trader.py](file:///Users/boe747/SilverPilot/apps/api/app/services/auto_trader.py)
- `settings.strategy_name` değerine göre stratejiyi dinamik seçen router mekanizması eklenecek. Hardcoded `strategy_v2` çağrısı yerine dinamik çağrı yapılacak.
- Telegram `HOLD` mesajlarının gönderimi cooldown tabanlı veya tamamen sessiz (dispatch iptali) olacak şekilde güncellenecek.
- Stale indicator weekend bypass kuralı, indikatörün readiness gate'inden önce değerlendirilerek hafta sonu takılmaları önlenecek.

#### [MODIFY] [PLAN.md](file:///Users/boe747/SilverPilot/PLAN.md)
- `test_docs_consistency.py` testinin geçmesi için canonical plan uyarısı ve docs/PHASE_PLAN.md referansı geri yüklenecek.

---

### Component 2: Sentiment & News Engine (Faz 2)
Altın-Gümüş korelasyonunu entegre etmek ve seyreltme hatasını gidermek.

#### [MODIFY] [hermes.py](file:///Users/boe747/SilverPilot/apps/api/app/agents/hermes.py)
- Ağırlıklı sentiment payda hesabı güncellenecek: `total_source_weight += source_weight * relevance`.
- LLM promptu güncellenecek: Altın haberleri için `relevance = 0.8`, makro haberler için `relevance = 0.7` verilmesi kural haline getirilecek.

---

### Component 3: OOP Abstraction Layers (Faz 3)
OOP kurallarını sonuna kadar uygulayarak projeyi modüler hale getirmek.

#### [NEW] [base.py](file:///Users/boe747/SilverPilot/apps/api/app/services/base.py)
- `BasePriceProvider` (scrapers için)
- `BaseStrategy` (RSI, SMA, Blended vb. için)
- `BaseIndicator` (indikatör hesapları için)
soyut sınıfları tanımlanacak.

#### [MODIFY] [collectors/service.py](file:///Users/boe747/SilverPilot/apps/api/app/collectors/service.py)
- Kuveyt Türk ve Yahoo scrapers, `BasePriceProvider` sınıflarından türetilecek.

#### [MODIFY] [strategy.py](file:///Users/boe747/SilverPilot/apps/api/app/services/strategy.py)
- RSI, SMA ve Blended stratejileri `BaseStrategy` sınıfından türetilen bağımsız strateji sınıfları haline getirilecek.

---

### Component 4: SaaS Auto Engine & DB Integration (Faz 4)
Otomatik modlar ve çoklu kullanıcı yönetimi.

#### [NEW] [auto_regime.py](file:///Users/boe747/SilverPilot/apps/api/app/services/auto_regime.py)
- `RegimeAdaptiveAutoStrategy` (Piyasa rejimine göre en iyi stratejiyi dinamik seçen Auto mod).
- `AutoIndicatorSelector` (Otomatik indikatör ağırlıklandırıcı).

#### [NEW] Migration (Alembic)
- Çoklu sağlayıcılar (`providers`), strateji şablonları (`strategy_definitions`) ve kullanıcı bazlı strateji parametreleri tabloları eklenecek.
- Birim dönüşüm politikaları tablosu eklenerek `31.1035` veri tabanından okunacak.

---

## 4. Verification Plan

### Automated Tests
- `pytest tests/test_auto_trader.py tests/test_blended_trader.py`
- `pytest tests/test_docs_consistency.py`
- `pytest tests/test_indicators.py`
- `pytest tests/test_hermes_agent.py`

### Manual Verification
- Streamlit arayüzünden strateji geçişlerinin testi.
- Telegram üzerinden `/canli` konsensüs çıktılarının doğrulanması.
