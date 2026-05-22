# Implementation Plan: Phase 12 - Advanced Multi-Agent Analysis

Bu plan, SilverPilot projesinde **Phase 12: Advanced Multi-Agent Analysis** (Gelişmiş Çoklu Ajan Analizi) aşamasının tasarım, geliştirme ve entegrasyon süreçlerini detaylandırmaktadır. 5 yeni uzman ajan ve merkezi bir orkestratör eklenirken, **Port Isolation** (FastAPI HTTP sınırı) ve **Deterministic Risk Authority** (Ajanların işlem yetkisinin olmaması) kurallarına tam uyum sağlanacaktır.

Bu plan, en son **DeepSeek V4 Model Ailesi** esas alınarak güncellenmiş; en güçlü model olan **`deepseek-v4-pro`** kritik denetim ve audit işlerine, **`deepseek-v4-flash`** ise standart veri ve sentiment işlerine tahsis edilmiştir.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar (docs/RISK_POLICY.md):** 
  - *Deterministic Risk Authority:* Ajan kararları tamamen tavsiye, denetleme ve açıklama (advisory) amaçlıdır. Hiçbir ajan deterministic risk motoru kurallarını bypass edemez, gerçek alım-satım tetikleyemez veya banka entegrasyonlarına erişemez.
  - *Port Isolation:* Yeni eklenecek ajanlar ve orkestratör katmanı PostgreSQL veri tabanına doğrudan TCP portları üzerinden bağlanamaz. Tüm veri okuma/yazma ve hafıza işlemleri FastAPI HTTP endpoint'leri (token korumalı) aracılığıyla gerçekleştirilmelidir.
  - *Token Economy & Model Cascading (DeepSeek V4):* 
    - Standart/hafif görevler (`news-agent`, `market-research`, `report-agent`, `source-reliability`) hızlı ve son derece ucuz olan **`deepseek-v4-flash`** (Input $0.14/1M, Output $0.28/1M) ile çalışacaktır.
    - Kritik, mantıksal derinlik ve denetim gerektiren önemli görevler (`auditor-agent`, `postmortem-agent`, `risk-agent` uyuşmazlık incelemeleri, `ml-analyst`) projenin en güçlü modeli olan **`deepseek-v4-pro`** (Promosyonlu: Input $0.435/1M, Output $0.87/1M) ile çalışacaktır.
    - Günlük $1.00 USD olan LLM bütçe sınırının aşılmaması için `deepseek-v4-pro` kullanımı sadece kritik durumlar ve orkestratörün uyuşmazlık çözümleriyle sınırlandırılacaktır.
- **Etkilenen Dosyalar ve Klasörler:**
  - `apps/api/app/agents/` (Yeni ajanların ve orkestratörün ekleneceği yer)
  - `apps/api/app/api/routes.py` (FastAPI orkestrasyon rotasının ekleneceği yer)
  - `apps/dashboard/streamlit_app.py` (Arayüzde görselleştirme ve manuel tetikleme sekmesi)
  - `apps/api/tests/` (Unit ve entegrasyon testlerinin ekleneceği yer)

---

## 🛠️ Fazlar ve Görev Listesi

### 🟩 Faz 1: Yeni Ajanların Tasarımı ve Oluşturulması (Ajan: `backend-architect` / `data-engineer`)
Bu fazda, her biri belirli bir analiz sorumluluğuna sahip 5 yeni Python modülü `apps/api/app/agents/` altında oluşturulacaktır. Ajanlar `DeepSeekGateway` ve `AgentMemoryEvent` yapılarını kullanacaktır.

- [ ] **Agent Market Research** (`apps/api/app/agents/market_research.py`) *[NEW]*:
  - Teknik indikatörler, fiyat geçmişi ve TCMB/FRED makro verilerini analiz ederek piyasa eğilim raporu ve sentiment skoru üretir.
  - *Model:* `deepseek-v4-flash`
- [ ] **Agent ML Analyst** (`apps/api/app/agents/ml_analyst.py`) *[NEW]*:
  - Aktif ML model tahminlerini, metriklerini ve son inference sonuçlarını inceleyerek sinyal kalitesini denetler.
  - *Model (Kritik):* `deepseek-v4-pro`
- [ ] **Agent Source Reliability Analyst** (`apps/api/app/agents/source_reliability.py`) *[NEW]*:
  - Son collector çalıştırma günlüklerini (`CollectorRun` ve `PriceSnapshot.is_degraded`) tarayarak her veri kaynağı için güvenilirlik skoru ve sağlık raporu hesaplar.
  - *Model:* `deepseek-v4-flash`
- [ ] **Agent Postmortem** (`apps/api/app/agents/postmortem.py`) *[NEW]*:
  - Bloke edilmiş paper-trade kayıtları (`PaperTrade.status = blocked` veya risk ihlalleri) için otomatik postmortem hata analizi hazırlar.
  - *Model (Kritik):* `deepseek-v4-pro`
- [ ] **Agent Auditor** (`apps/api/app/agents/auditor.py`) *[NEW]*:
  - Ajanlar arası uyuşmazlıkları (`disagreement`) denetler, LLM bütçe tüketimini izler ve genel sistem audit raporunu sunar.
  - *Model (Kritik):* `deepseek-v4-pro`
- *DoD (Tamamlanma Tanımı):* 5 ajanın da yerel mock verilerle sorunsuz şekilde çalışabilmesi ve syntax hatalarının olmaması.

---

### 🟩 Faz 2: Ajan Orkestratörünün ve Anlaşmazlık Algoritmasının Geliştirilmesi (Ajan: `backend-architect`)
Tüm ajanları tek bir akışta yöneten merkezi orkestratör modülü kurulacaktır.

- [ ] **Orchestrator Modülü** (`apps/api/app/agents/orchestrator.py`) *[NEW]*:
  - Tek bir tetikleme ile (`run_multi_agent_analysis`) tüm analiz süreçlerini ardışık olarak çalıştırır.
  - **Uyuşmazlık Algılama (Disagreement Detection):** Ajanların kararları (örneğin News sentiment BULLISH iken ML Analyst veto öneriyorsa) arasındaki tezatları algılar ve `agent_disagreement` anahtarıyla `AgentMemoryEvent` tablosuna kaydeder.
  - **Model Cascading:** Normal analizlerde `deepseek-v4-flash` kullanırken, bir uyuşmazlık veya denetim durumunda muhakeme ve son karar yetkisi için **`deepseek-v4-pro`** modelini tetikler.
- *DoD:* Orkestratör modülünün tüm ajanları ardışık çalıştırıp uyuşmazlıkları başarıyla veri tabanına loglayabilmesi.

---

### 🟩 Faz 3: FastAPI Rotaları ve API Güvenliği (Ajan: `backend-architect` / `security-auditor`)
Orkestrasörün port isolation kuralları altında dışarıdan tetiklenebilmesi için secure endpoint açılacaktır.

- [ ] **Orkestrasyon Endpoint'i** (`apps/api/app/api/routes.py`):
  - `POST /agent/orchestrate/run` rotasını eklemek.
  - Rota, `verify_agent_token` dependency'si ile korunarak zero-trust API standartlarına uyumlu hale getirilecektir.
  - Background task olarak çalışarak sistemin yanıt süresini tıkamayacaktır.
- *DoD:* `POST /agent/orchestrate/run` endpoint'inin geçerli token ile çağrıldığında 200 OK veya 202 Accepted dönmesi, geçersiz token ile 401 Unauthorized dönmesi.

---

### 🟩 Faz 4: Streamlit Dashboard Görselleştirme (Ajan: `frontend-architect`)
Streamlit arayüzünde ajan analizlerinin, uyuşmazlıkların ve kaynak güvenilirliklerinin görsel olarak izlenebilmesi sağlanacaktır.

- [ ] **Dashboard Güncellemesi** (`apps/dashboard/streamlit_app.py`):
  - "Advanced Multi-Agent Analysis" sekmesi eklemek.
  - Ajan analiz raporlarını, kaynak güvenilirlik skorlarını ve postmortem çıktılarını render etmek.
  - "Run Multi-Agent Analysis" butonu ekleyerek token korumalı API tetikleyicisi eklemek.
  - Ajan uyuşmazlıklarını ve audit geçmişini interaktif grafikler ve uyarı kartları ile sunmak.
- *DoD:* Streamlit uygulamasının yerelde çalıştırılması ve yeni sekmenin görsel olarak hatasız render edilmesi.

---

### 🟩 Faz 5: Kalite Kontrol, Doğrulama ve Canlı Dağıtım (Ajan: `quality-engineer` / `safety-gatekeeper`)
Tüm entegrasyon ve birim testlerinin yazılarak sistemin VPS'e güvenle dağıtılması sağlanacaktır.

- [x] **Birim ve Entegrasyon Testleri**:
  - `apps/api/tests/test_agent_routes.py` ve `apps/api/tests/test_agents.py` test suite'leri oluşturularak 100% test başarısı sağlandı.
- [x] **Safety Gatekeeper Analizi**:
  - `safety-gatekeeper` ile kod statik analizi yapıldı, regresyon kontrolü sağlandı.
- [/] **Otomatik Dağıtım**:
  - Testler başarıyla geçtikten sonra değişikliklerin Git'e commit & push edilerek VPS'e taşınması (Çalışıyor...).
- *DoD:* pytest suite'lerinin tamamının (139 test) yeşil geçmesi ve VPS'te `/health` endpoint'inin sorunsuz çalışması.

---

## ❓ Açık Sorular & Kararlar
> [!NOTE]
> 1. **Model Tercihleri:** legacy `deepseek-chat` ve `deepseek-reasoner` modelleri yerine, resmi DeepSeek V4 ailesine (`deepseek-v4-flash` ve `deepseek-v4-pro`) tam geçiş yapılmıştır.
> 2. **Hafıza Saklama Formatı:** Ajan çıktıları ve audit verileri için yeni bir PostgreSQL tablosu eklemek yerine esnek ve compact `AgentMemoryEvent` tablosunun JSON formatını kullanacağız. Bu karar kullanıcı tarafından **onaylanmıştır**.
