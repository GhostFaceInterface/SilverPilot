# Implementation Plan: VPS-Only Migration & Secure Production Environment Transition

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - *[.agent/GEMINI.md](file:///.agent/GEMINI.md)*: Dürüst Ortaklık, zero-trust ve Socratic Gate kuralları.
- **Etkilenen Dosyalar:**
  - `docker-compose.yml` (Veritabanı port ve şifre yapılandırması)
  - `.env` (Yerel makine ayarları - temizlenecek)

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Güvenli Veri Koruma & Yerel Konteyner Temizliği**
  - [x] **Veri Güvenliği (Kritik):** Yereldeki gruptan verilerin kaybolmaması için `pg_dump` ile yerel veritabanının `data/local_backup.sql` dosyasına yedeklenmesi.
  - [x] Yerel Docker konteynerlerinin, verilerin silinmesini önlemek adına `-v` parametresi **kullanılmadan** durdurulması (`docker compose down`). Bu sayede verileriniz güvenli bir şekilde diskte saklanır ancak sistem kaynakları tamamen serbest kalır.
  - [x] Yerel makinedeki `.env` dosyasındaki şifrenin güvenlik amacıyla production ile uyumlu (`bTv999wbFVYP6yBErdGiIdrtRkcOv6hZSygJ6xvfM2tNM8NW7Q`) olacak şekilde güncellenmesi.
  - *DoD (Tamamlanma Tanımı):* `data/local_backup.sql` yedek dosyasının oluşması ve yerelde `docker ps` çıktısının boş olması.

- `[x]` **Faz 2: VPS Database Zero-Trust Güvenlik Teşhisi**
  - [x] `docker-compose.yml` içindeki `postgres` servisinin port eşlemesinin dış dünyaya kapalı, sadece localhost (`127.0.0.1:5433:5432`) ile sınırlandırıldığının doğrulanması.
  - [x] VPS üzerindeki `.env.production` şifresinin güvenli halinin sorunsuz çalıştığının ve dışarıdan doğrudan sızıntılara (zero-trust) geçit vermediğinin teyit edilmesi.
  - *DoD:* VPS üzerinde `docker exec silverpilot-api` veritabanı bağlantı testinin `1` sonucunu vermesi.

- `[/]` **Faz 3: Test Stratejisinin Güçlendirilmesi (CI/CD Entegrasyonu)**
  - [ ] Her kod değişikliğinde (örneğin gümüş fiyatı düzeltmesinde) birim testlerin (`tests/test_collectors.py`) güncellenmesi ve yazılması.
  - [ ] **Hibrit Test Yaklaşımı:** CI (GitHub Actions) üzerinde hızlı ve izole doğrulama için in-memory SQLite/Mock testlerinin koşturulması; dağıtım sonrasında ise VPS üzerinde gerçek canlı veritabanıyla E2E (`verify_execution_pipeline.py`) testlerinin tetiklenmesi.
  - [ ] `scripts/deploy.sh` betiğinin yerel makineden tetiklenerek kodun VPS'e aktarılması ve uzaktan testlerin koşturulması.
  - *DoD:* `deploy.sh` entegrasyon akışının ve E2E testlerinin sıfır hatayla başarıyla tamamlanması.

## ❓ Açık Sorular (Varsa)
> [!NOTE]
> - Yerel veritabanının yedeğini alıp konteynerleri durdurduktan sonra, yerel geliştirme ortamında kod testlerini in-memory SQLite/Mock ile çok hızlı şekilde koşturacağız. Canlı/Gerçek veritabanı testleri ise tamamen VPS üzerinde entegre CI/CD hattında (`verify_execution_pipeline.py`) gerçekleşecektir. Bu modern yazılım mühendisliği yaklaşımını onaylıyor musunuz?
