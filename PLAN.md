# Implementation Plan: VPS Port Isolation & Agent Token Security Hardening

Bu plan, **Phase 6** sonrasında tespit edilen dış ağ güvenlik açıklarını kapatmak ve sistemi tamamen zırhlandırmak amacıyla hazırlanmıştır. **Phase 7 (İlk Aktif Ajanlar)** aşamasına geçmeden önce, ajanlarımızın hassas bellek ve telemetri verilerinin tam güvenliği garanti altına alınacaktır.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - [docs/ARCHITECTURE.md](file:///Users/boe747/SilverPilot/docs/ARCHITECTURE.md) (Port Isolation, Option C Rules).
  - [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Veri gizliliği ve zero-trust ilkeleri).
- **Etkilenen Dosyalar & Ağ Yapısı:**
  - `docker-compose.yml` (Sunucu dış arayüz port bağlamaları).
  - `apps/api/app/api/routes.py` (FastAPI router yetkilendirmesi).
  - `apps/dashboard/streamlit_app.py` (Dashboard'un yetkili istek göndermesi).
  - `apps/api/tests/test_agent_routes.py` (Uç nokta testleri).

---

## 🛠️ Fazlar ve Görev Listesi

### **Faz 1: Docker Compose Port Sıkılaştırması (Local Loopback Binding)**
- **Açıklama:** Veritabanı ve FastAPI API portlarını tüm ağ arayüzlerine (0.0.0.0) açmak yerine yalnızca yerel localhost'a (127.0.0.1) bağlayarak internetten gelen tüm ham ağ taramalarını bloke edeceğiz.
- **Yapılacaklar:**
  - [ ] `docker-compose.yml` dosyasında `api` servisinin port haritalamasını `127.0.0.1:8000:8000` olarak güncelleyin.
  - [ ] `docker-compose.yml` dosyasında `postgres` servisinin port haritalamasını `127.0.0.1:5433:5432` olarak güncelleyin.
- **DoD (Tamamlanma Tanımı):** Docker konteynerleri yeniden başlatıldığında, sunucunun dış IP adresine dışarıdan yapılan port taramalarının engellenmesi.

### **Faz 2: Zero-Trust Ajan Yetkilendirmesi (FastAPI Dependency)**
- **Açıklama:** Ajan bellek ve izleme API uç noktalarını (`/agent/*`) şifresiz ve yetkisiz erişime kapatmak için `AGENT_API_TOKEN` tabanlı bir başlık (header) kontrol katmanı ekleyeceğiz.
- **Yapılacaklar:**
  - [ ] `apps/api/app/core/config.py` içerisindeki `Settings` sınıfına `agent_api_token: str = ""` alanını ekleyin (Ajan: `backend-architect`).
  - [ ] `.env.example` dosyasına `AGENT_API_TOKEN=your-secure-agent-token-here` satırını ekleyin.
  - [ ] `apps/api/app/api/routes.py` içerisinde `verify_agent_token` bağımlılık (Dependency) fonksiyonunu yazın. Gelen `X-Agent-Token` başlığını `Settings.agent_api_token` ile karşılaştırsın.
  - [ ] `/agent/trace`, `/agent/traces`, `/agent/traces/stats` ve `/agent/memory` uç noktalarına `Depends(verify_agent_token)` korumasını uygulayın.
- **DoD:** Yetkisiz isteklerin HTTP 401 Unauthorized hatası alması.

### **Faz 3: Dashboard ve Test Entegrasyon Güncellemeleri**
- **Açıklama:** Güvenlik katmanının Dashboard'u veya testleri kırmasını engellemek için gerekli başlık iletim sistemini entegre edeceğiz.
- **Yapılacaklar:**
  - [ ] `docker-compose.yml` dosyasında `dashboard` servisi ortam değişkenlerine `AGENT_API_TOKEN: ${AGENT_API_TOKEN:-}` ekleyin.
  - [ ] `apps/dashboard/streamlit_app.py` içindeki `fetch_json` fonksiyonunu güncelleyin. Eğer ortam değişkenlerinde `AGENT_API_TOKEN` tanımlı ise istek başlığına `X-Agent-Token` değerini eklesin.
  - [ ] `apps/api/tests/test_agent_routes.py` dosyasındaki tüm test istemcisi isteklerine `headers={"X-Agent-Token": "test_token"}` ekleyin ve test ayarlarında mock token tanımlayın.
- **DoD:** `pytest apps/api/tests/test_agent_routes.py` testlerinin tamamen yeşil olması.

### **Faz 4: Canlı Dağıtım ve Dış Ağ Doğrulaması**
- **Açıklama:** Yapılan tüm sıkılaştırmaları canlandırıp uzak sunucu (VPS) üzerinde E2E ağ doğrulamasını gerçekleştireceğiz.
- **Yapılacaklar:**
  - [ ] Testler başarıyla geçtikten sonra değişiklikleri otomatik git commit ve push ile uzak sunucuya deploy edin (`scripts/deploy.sh`).
  - [ ] VPS sunucusunun dış IP adresi üzerinden port tarama ve unauthenticated HTTP erişim denemesi yaparak dışarıya tamamen kapandığını doğrulayın.
- **DoD:** `deploy.sh` betiğinin sorunsuz tamamlanması ve sunucu dışından veritabanına ve API'ye hiçbir şekilde erişilemediğinin (bağlantı reddi) kanıtlanması.

---

## ❓ Açık Sorular
> [!NOTE]
> *   **Token Gücü:** Lokalde ve sunucuda `.env` dosyalarına yazılacak `AGENT_API_TOKEN` değerini en az 32 karakterlik güvenli bir rastgele dizi (örnekin UUID veya secure hex) olarak seçmenizi öneririm.
