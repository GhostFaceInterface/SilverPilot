# Implementation Plan: Phase 7 - Active Financial Agents Integration (with DeepSeek V4 Modernization)

Bu plan, **Option C: Hybrid Selective Execution & User-Driven Triggers** mimarisi uyarınca, **News Agent**, **Risk Agent** ve **Report Agent**'larının sisteme entegre edilmesi için hazırlanmıştır. Ajanlarımızın tamamı harici API'ler üzerinden çalışacak ve zero-trust güvenlik modelini korumak amacıyla veritabanı işlemlerini FastAPI uç noktaları üzerinden `X-Agent-Token` yetkilendirmesiyle gerçekleştirecektir.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - [docs/ARCHITECTURE.md](file:///Users/boe747/SilverPilot/docs/ARCHITECTURE.md) (Option C: Agents do not trade, hybrid execution rules).
  - [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Zero-trust token authorization, data-privacy).
- **Etkilenen Dosyalar:**
  - `apps/api/app/llm/gateway.py` *(DeepSeek model tanımları, aliaslar ve fiyatlandırma güncellemesi)*
  - `apps/api/app/agents/` *(Yeni oluşturulacak haber, risk ve rapor servisleri için)*
  - `apps/api/app/api/routes.py` *(Yeni ajan uç noktaları)*
  - `apps/api/app/services/strategy.py` *(Strateji sinyal üretimi sonrasında Risk Agent hook tetiklenmesi)*
  - `apps/dashboard/streamlit_app.py` *(Manuel tetikleme ve görselleştirme sekmesi)*
  - `apps/api/app/core/config.py` *(Ajan modelleri ve parametreleri)*

---

## 💡 Model Rol Dağıtımı & Resmi DeepSeek V4 API Geçişi
Yapılan internet araştırması ve resmi DeepSeek API dökümantasyonu doğrultusunda, Temmuz 2026'da kaldırılacak olan eski model isimleri (`deepseek-chat` / `deepseek-reasoner`) yerine resmi modern **DeepSeek V4** modellerine geçiş yapılacaktır:

1. **DeepSeek-V4-Flash (`deepseek-v4-flash`):**
   - **Kullanım Alanı:** Basit, hızlı ve ekonomik işler (News Agent haber özetlemesi, Report Agent günlük bakiye/performans markdown raporu).
   - **API Fiyatlandırması:** Input: $0.14 / 1M tokens ($0.00000014), Output: $0.28 / 1M tokens ($0.00000028).
2. **DeepSeek-V4-Pro (`deepseek-v4-pro`):**
   - **Kullanım Alanı:** Kritik akıl yürütme, agentic mantık ve yüksek finansal değere sahip kararlar (Risk Agent Strateji Critique & Audit).
   - **API Fiyatlandırması:** Input: $0.435 / 1M tokens ($0.000000435), Output: $0.87 / 1M tokens ($0.00000087) (Promosyonlu güncel tarife).

---

## 🛠️ Fazlar ve Görev Listesi

### **Faz 1: DeepSeek Gateway Modernizasyonu ve Ajan Ayarları** [/]
- **Açıklama:** API Gateway'i resmi `deepseek-v4-pro` ve `deepseek-v4-flash` modellerine göre güncelleyecek ve ajanların model ayarlarını tanımlayacağız.
- **Yapılacaklar:**
  - [ ] `apps/api/app/llm/gateway.py` içerisindeki `DEEPSEEK_PRICING` yapısını modern DeepSeek V4 modellerine göre güncelleyin:
    ```python
    DEEPSEEK_PRICING = {
        "deepseek-v4-flash": {
            "input": Decimal("0.00000014"),
            "output": Decimal("0.00000028")
        },
        "deepseek-v4-pro": {
            "input": Decimal("0.000000435"),
            "output": Decimal("0.00000087")
        }
    }
    ```
  - [ ] Gateway içindeki model bazlı parametre istisnalarını (`temperature` vb.) yeni modelleri kapsayacak şekilde güncelleyin.
  - [ ] `apps/api/app/core/config.py` içerisindeki `Settings` sınıfına ajan model tanımlarını ekleyin:
    - `agent_news_model: str = "deepseek-v4-flash"`
    - `agent_report_model: str = "deepseek-v4-flash"`
    - `agent_risk_model: str = "deepseek-v4-pro"`
  - [ ] `apps/api/app/api/routes.py` içerisine yeni ajan POST uç noktalarını `verify_agent_token` korumasıyla ekleyin:
    - `POST /agent/news/trigger` (News Agent)
    - `POST /agent/report/trigger` (Report Agent)
    - `POST /agent/risk/critique` (Risk Agent Critique)
- **DoD (Tamamlanma Tanımı):** `/agent/*` yeni uç noktalarının yetkisiz erişime 401, geçerli token ile 200/201 (boş veya mock veriyle) dönmesi.

### **Faz 2: News Agent Entegrasyonu (Duyarlılık & Haber Analizi)**
- **Açıklama:** `RawNews` tablosundaki son 24 saatlik haberleri okuyup ekonomik `deepseek-v4-flash` modeli ile finansal sentiment (duyarlılık) analizi yapan News Agent'ı kodlayacağız.
- **Yapılacaklar:**
  - [ ] `apps/api/app/agents/news.py` modülünü oluşturun (Ajan: `data-engineer`):
    - `RawNews` tablosundan son haber başlıklarını sorgulayın.
    - DeepSeek gateway (`deepseek-v4-flash`) ile haberlerin gümüş (XAG) ve piyasa üzerindeki etkisini analiz edin.
    - Analiz neticesini `AgentMemoryEvent` tablosuna `event_type="news_sentiment"` ve `key="latest_analysis"` olacak şekilde kaydedin.
  - [ ] `POST /agent/news/trigger` endpoint'ini bu servis ile bağlayın.
- **DoD:** News agent tetiklendiğinde DeepSeek API'ye başarılı bir çağrı yapıp çıktıyı `agent_memory` tablosuna yazması.

### **Faz 3: Risk Agent Entegrasyonu (Signal Critique - On-Demand)**
- **Açıklama:** Strateji motorundan BUY/SELL sinyali üretildiğinde, güçlü `deepseek-v4-pro` modeli ile tetiklenerek bu kararı eleştirmesini (critique) ve audit etmesini sağlayacağız.
- **Yapılacaklar:**
  - [ ] `apps/api/app/agents/risk.py` modülünü oluşturun (Ajan: `backend-architect`):
    - Girdi olarak gelen sinyal detayını, mevcut portföy durumunu ve son `TechnicalIndicator` verilerini alsın.
    - DeepSeek gateway (`deepseek-v4-pro`) ile sinyali eleştirsin (örn: "RSI aşırı satımda ama FOMO riski var mı?", "Spread durumu uygun mu?").
    - Critique çıktısını `agent_memory` tablosuna `event_type="signal_critique"` olarak kaydatsın.
  - [ ] `apps/api/app/services/strategy.py` içinde strateji sinyal üretimi sonrasında Risk Agent critique API hook'unu tetikleyecek mekanizmayı kurun.
- **DoD:** Bir strateji sinyali üretildiğinde, Risk Agent'ın otomatik/elle tetiklenip bu sinyali eleştiren audit logunu `agent_memory` tablosuna yazması.

### **Faz 4: Report Agent Entegrasyonu (Gece Yarısı & Manuel Rapor)**
- **Açıklama:** Günlük bakiye, kâr/zarar ve işlem geçmişini özetleyen Report Agent logic'ini ekonomik `deepseek-v4-flash` ile kodlayacağız.
- **Yapılacaklar:**
  - [ ] `apps/api/app/agents/report.py` modülünü oluşturun (Ajan: `data-engineer` / `backend-architect`):
    - `PortfolioSnapshot` ve `PaperTrade` tablolarını sorgulayarak son 24 saatlik işlem özetini çıkarsın.
    - DeepSeek gateway (`deepseek-v4-flash`) ile performansı yorumlayıp Markdown formatında şık bir günlük rapor üretsin.
    - Rapor çıktısını mevcut `Report` modelini kullanarak veritabanına `report_type="daily"` olacak şekilde kaydatsın.
  - [ ] `POST /agent/report/trigger` endpoint'ini bu servis ile bağlayın.
- **DoD:** `/reports/daily/latest` endpoint'inin Report Agent tarafından üretilen en son markdown raporunu başarıyla dönmesi.

### **Faz 5: Streamlit "🤖 Active Financial Agents" UI Entegrasyonu**
- **Açıklama:** Dashboard üzerinde ajanları izleyeceğimiz, elle tetikleyeceğimiz ve analiz sonuçlarını göreceğimiz premium arayüzü inşa edeceğiz.
- **Yapılacaklar:**
  - [ ] `apps/dashboard/streamlit_app.py` dosyasına yeni bir `"🤖 Active Financial Agents"` sekmesi (tab) ekleyin (Ajan: `frontend-architect`):
    - **Haber Sekmesi:** En son "News Sentiment" analiz raporunu render etsin ve "News Agent Tetikle" butonu koysun.
    - **Risk Sekmesi:** En son üretilen strateji sinyal eleştirilerini (`signal_critique`) listelesin.
    - **Rapor Sekmesi:** En son günlük markdown raporu (`/reports/daily/latest`) şık bir şekilde render etsin ve "Günlük Rapor Üret" butonu koysun.
- **DoD:** Butonlara basıldığında ajanların arka planda tetiklenmesi ve sonuçların anında Streamlit üzerinde görsel olarak WOW etkisi oluşturacak şekilde render edilmesi.

### **Faz 6: Kalite Kontrol, E2E Testler ve Güvenlik Denetimi**
- **Açıklama:** Yazılan tüm ajan logic'lerini ve API entegrasyonlarını test edip VPS ortamına deploy edeceğiz.
- **Yapılacaklar:**
  - [ ] `apps/api/tests/` altında `test_agents.py` dosyasını oluşturun ve uç nokta çağrılarını test edin (Ajan: `quality-engineer`).
  - [ ] `safety-gatekeeper` ile kodların statik güvenlik ve regresyon analizini gerçekleştirin.
  - [ ] `git commit` & `git push` ile kodları uzak sunucuya dağıtıp deploy edin.
- **DoD:** Tüm pytest test süitinin 100% yeşil olması ve VPS üzerinde ajan tetiklemelerinin başarıyla çalışması.

---

## ❓ Açık Sorular ve Kararlar
> [!IMPORTANT]
> - **Gateway Modernizasyonu:** Temmuz 2026'da kaldırılacak olan legacy model alias'ları yerine doğrudan modern resmi `deepseek-v4-pro` ve `deepseek-v4-flash` API kod adlarına geçiş yapılacaktır. Bu mimari karar onayınızda mıdır?
