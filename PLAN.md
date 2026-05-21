# Implementation Plan: Phase 5.5 VPS Integration & Phase 6 LLM Gateway, Premium Custom Observability & Best-in-Class Paid Models

Bu plan, localde başarıyla tamamlanan **Phase 5.5 (Deterministic Signal & Backtest Engine)** modüllerinin VPS ortamına entegrasyonunu ve bir sonraki aşama olan **Phase 6 (LLM Gateway, Custom Observability, and Agent Foundation)** mimarisini içerir. 

Kullanıcı geri bildirimleri doğrultusunda **Özel Gözlemleme Sistemi (kendi yazacağımız sıfır VPS RAM yüklü modül)** ve **En Üst Seviye Ücretli Finansal Muhakeme Modelleri (Claude 3.5 Sonnet, DeepSeek-R1, Gemini 2.5 Pro)** kullanımı plana dahil edilmiştir.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Veri bütünlüğü, işlem limitleri, gerçek para yasağı).
  - [docs/ARCHITECTURE.md](file:///Users/boe747/SilverPilot/docs/ARCHITECTURE.md) (LLM bütçe sınırları, Özel Tracing, Port İzolasyon kuralı).
- **Etkilenen Şemalar & Yapılar:**
  - `signals` veritabanı tablosu (Alembic migrasyonunun VPS üzerinde canlıya alınması).
  - `llm_call_traces` (Sıfırdan yazacağımız hafif ve yerel izleme tablosu).
  - `apps/api/app/llm/` ve `apps/api/app/agents/` (Yeni modüller).

---

## 🚀 Mimari Kararlar (Kararlaştırılan Yapı)

1. **Özel Gözlemleme Sistemi (Custom Light-Logger - Biz Yazıyoruz):**
   - VPS kaynaklarını (RAM) yormamak ve verileri tamamen kendi bünyemizde tutmak için herhangi bir harici kütüphane (Langfuse vb.) **kurmuyoruz**.
   - Veritabanımızda hafif bir `llm_call_traces` tablosu oluşturuyoruz.
   - Backend tarafında yazacağımız `@trace_llm` dekoratörü ile tüm API çağrılarının yanıt süresini, token kullanımını ve maliyetini anlık ölçüp bu tabloya yazıyoruz.
   - Streamlit dashboard arayüzümüze **"LLM Observability"** adında şık bir sekme ekleyerek, harcanan toplam dolar miktarını, ortalama yanıt sürelerini ve prompt loglarını görsel grafiklerle panelde sunuyoruz.

2. **Premium Finansal Muhakeme Modelleri (Direct DeepSeek V4 Pro Entegrasyonu):**
   - Finansal doğruluk ve maliyet/performans liderliğini garantilemek adına harici servisleri bypass ederek **doğrudan resmi DeepSeek API** altyapısını kullanıyoruz:
     - **Tüm Ajanlar İçin (Risk, News, Report):** En yeni nesil **DeepSeek-V4-Pro** modelini kullanıyoruz.
     - **Risk Agent (Risk Analizörü):** `deepseek-reasoner` (DeepSeek-V4-Pro'nun derinlemesine düşünme "Think" modunu tetikleyerek üstün kurumsal muhakeme ve matematiksel doğrulama).
     - **News & Report Agents (Haber & Raporlama):** `deepseek-chat` (DeepSeek-V4-Pro'nun ultra hızlı, yüksek bağlamlı ve ekonomik standart modunu kullanarak hızlı haber tarama ve Türkçe raporlama).
   - Bu modellerin tamamına doğrudan resmi **DeepSeek API Key** (`DEEPSEEK_API_KEY`) ile bağlanıyoruz.

3. **Option C Güvenlik Sınırları:**
   - **Port İzolasyonu:** VPS'teki ajanlar PostgreSQL'e doğrudan bağlanamaz. Tracing logları dahil tüm okuma/yazma işlemlerini FastAPI HTTP uç noktaları üzerinden yapacaktır.
   - **Bellek Önceliği:** Faz 7 ajanları doğmadan önce Faz 6.5 bellek tabloları (`agent_memory_events`) hazır olacaktır.

---

## 🛠️ Fazlar ve Görev Listesi

### `[ ]` **Faz 1: Phase 5.5 VPS Entegrasyonu ve Canlı Doğrulama**
- **Açıklama:** Localde testi geçen strategy, backtest ve signals migrasyonlarının VPS ortamına deploy edilmesi ve E2E doğrulama betiğinin canlıda çalıştırılması.
- **Yapılacaklar:**
  - [ ] Local değişikliklerin git commit & push ile gönderilmesi (Ajan: `safety-gatekeeper`).
  - [ ] `scripts/deploy.sh` betiğinin çalıştırılarak VPS üzerinde:
    - Koda güncellemelerin çekilmesi (`git pull`).
    - Docker container yapılarının yeniden kurulması (`docker compose up -d --build`).
    - Veritabanı Alembic migrasyonlarının (`62456308964b_refactor_signals_table`) uygulanması.
    - E2E doğrulama betiğinin (`scripts/verify_execution_pipeline.py`) PostgreSQL üzerinde izole bir transaction açarak dry-run çalıştırılması ve rollback ile temizlenmesi.
- *DoD (Tamamlanma Tanımı):* `deploy.sh` betiğinin sıfır hata koduyla tamamlanması ve remote VPS smoke-testlerin başarıyla geçmesi.

### `[ ]` **Faz 2: Phase 6.1 - LLM Gateway Config & Direct DeepSeek Entegrasyonu**
- **Açıklama:** Doğrudan DeepSeek API bağlantısı, model bazlı (`deepseek-chat` ve `deepseek-reasoner`) fiyatlandırma haritası ve budget-guard bütçe sigortasının yazılması.
- **Yapılacaklar:**
  - [ ] `app/core/config.py` içerisine `DEEPSEEK_API_KEY` ve resmi DeepSeek base URL (`https://api.deepseek.com/v1`) tanımlarının eklenmesi (Ajan: `backend-architect`).
  - [ ] `app/llm/gateway.py` asenkron `httpx` istemcisinin ve model fiyatlandırma tablosunun (input/output token başına cent cinsinden) eklenmesi.
  - [ ] `app/llm/budget_guard.py` modülünün yazılması. Belirlenen günlük limit (örn: $1.00 USD) aşıldığında LLM çağrılarını keserek faturanın şişmesini engelleyen koruma mekanizması.
- *DoD:* `pytest tests/test_llm_gateway.py` ile gateway çağrılarının ve bütçe sınırlarının mock olarak test edilmesi.

### `[ ]` **Faz 3: Phase 6.2 - Kendi Gözlemleme Sistemimizin (Custom Light-Logger) İnşası**
- **Açıklama:** Harici ağır uygulamalar yerine veritabanımızda tutulacak hafif ve yerel LLM tracing veritabanı şemasının, backend servislerinin ve Streamlit arayüzünün yazılması.
- **Yapılacaklar:**
  - [ ] `llm_call_traces` tablosunun veritabanı modelinin tasarlanması ve Alembic migrasyonunun oluşturulması:
    - `id`: Serial Primary Key.
    - `agent_name`: Hangi ajanın çağırdığı (Risk, News, Report vb.).
    - `model_name`: Çağrılan model (`deepseek-chat`, `deepseek-reasoner` vb.).
    - `prompt_tokens`, `completion_tokens`, `total_cost_usd`: Harcanan kaynaklar.
    - `latency_ms`: Milisaniye cinsinden yanıt süresi.
    - `status`: `'SUCCESS'` veya `'FAILED'`.
    - `prompt_raw`, `response_raw`, `error_message`: Log detayları.
    - `created_at`: DateTime (UTC).
  - [ ] Backend tarafında `@trace_llm` dekoratörünün yazılması. Gateway çağrılarını sarmalayarak süre ve maliyet ölçümü yapması.
  - [ ] Ajanların loglama yapabilmesi için FastAPI HTTP `/agent/trace` endpoints'lerinin yazılması (Port İzolasyon Kuralı).
- *DoD:* `@trace_llm` dekoratörünün başarıyla veritabanına log attığının entegrasyon testleriyle kanıtlanması.

### `[ ]` **Faz 4: Phase 6.3 - Streamlit Dashboard LLM İzleme Paneli**
- **Açıklama:** Yazdığımız Custom Logger verilerinin Streamlit arayüzünde şık grafiklerle gösterilmesi.
- **Yapılacaklar:**
  - [ ] Streamlit dashboard uygulamamıza `LLM Analytics & Observability` adında yeni bir tab eklenmesi (Ajan: `frontend-architect`).
  - [ ] Bu sekmede:
    - Toplam LLM Harcaması (USD).
    - Ajan başına çağrı sayısı ve maliyet dağılımı grafiği.
    - Ortalama yanıt süreleri.
    - Son 50 LLM çağrısının prompt ve response loglarının okunabilir şık bir tablo halinde listelenmesi.
- *DoD:* Streamlit arayüzünde LLM Observability sekmesinin sorunsuz yüklenmesi ve verileri PostgreSQL'den FastAPI HTTP endpoints aracılığıyla canlı okuması.

### `[ ]` **Faz 5: Phase 6.4 - Structured Output Validation (Instructor / Schema Guard)**
- **Açıklama:** Ajanların ürettiği Türkçe veya mantıksal finans kararlarının Pydantic şemalarına tam uymasını sağlayan doğrulama katmanı.
- **Yapılacaklar:**
  - [ ] `Instructor` kütüphanesi entegrasyonunun asenkron gateway'e bağlanması (Ajan: `backend-architect`).
  - [ ] Şema hatası durumunda 2 kez otomatik retry ve prompt düzeltme (self-healing) mekanizmasının kurulması.
- *DoD:* pytest ile şemaya uymayan mock LLM çıktılarının başarıyla reddedildiğinin ve düzeltildiğinin test edilmesi.

### `[ ]` **Faz 6: Phase 6.5 - PostgreSQL Bellek Katmanı (Prerequisite)**
- **Açıklama:** Ajanların geçmiş kararları hatırlaması için `agent_memory_events` tablolarının ve FastAPI endpoint'lerinin oluşturulması.
- **Yapılacaklar:**
  - [ ] `agent_memory_events` SQLAlchemy model ve migrasyonlarının tamamlanması (Ajan: `backend-architect`).
  - [ ] `GET /agent/memory` ve `POST /agent/memory` endpoints entegrasyonu.
- *DoD:* Bellek API uç noktalarının yeşil olması.

---

## ❓ Açık Sorular (Tamamlandı)
- **Langfuse:** Kullanılmayacak, yerine **kendi yazacağımız sıfır RAM footprint'li Özel Gözlemleme Sistemi** kullanılacaktır.
- **Modeller:** Doğrudan resmi **DeepSeek API Key** üzerinden **DeepSeek-V4-Pro** (`deepseek-chat` ve `deepseek-reasoner` modları) kullanılacaktır.
- **Instructor:** requirements.txt dosyasına eklenerek güvenli şema doğrulaması sağlanacaktır.

