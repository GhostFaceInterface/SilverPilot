# PLAN.md - Modüler Piyasa Takvimi & Yedekli RSS Haber Toplayıcı Entegrasyon Planı

Bu plan, SilverPilot sistemindeki iki kritik eksikliği ve hatalı tetiklenmeyi gidermeyi amaçlar:
1.  **Zamanlama ve Takvim Uyumsuzluğu:** Salı geceleri (New York saatiyle Pazartesi 17:00'deki günlük 1 saatlik bakım penceresinde) Telegram'a hatalı giden "Hafta Sonu Nöbetçi Raporu" sorununu çözmek için piyasa takvim kontrolünü modüler hale getirmek.
2.  **Haber Akışı Eksikliği:** Sistemde tanımlı olan ancak toplayıcısı (collector) yazılmamış olan `"kitco-rss"`, `"bloomberght-rss"`, `"fxstreet-rss"`, ve `"investing-rss"` gibi zengin kaynaklar için modüler RSS kazıyıcılar yazmak. Aynı zamanda background lag durumunda analizcinin doğrudan canlı RSS çekimi yapmasını sağlayan **Demir Kalkan (Iron-Clad) Yedeklilik** mekanizmasını entegre etmek.

---

## 👥 Görev Alacak Uzman Ajanlar

Multi-Agent Orkestrasyonu kapsamında şu uzman ajanlar sequential olarak görev alacaktır:
*   **`project-planner`:** Görevi fazlandırır, hedefleri belirler (bu plan).
*   **`backend-architect`:** Modüler takvim fonksiyonlarını ve esnek RSS toplayıcı yapısını kodlar.
*   **`quality-engineer`:** AAA standartlarında mock testlerini yazar ve pytest doğrulamalarını yapar.
*   **`safety-gatekeeper`:** Statik kod denetimi ve secrets/sızıntı taraması gerçekleştirir.

---

## 🛠️ Fazlar ve Görev Listesi (/orchestrate Uyumlu)

### Faz 1: Modüler Piyasa Takvimi Bölümlemesi (Backend Dev)
*   **Ajan:** `backend-architect`
*   `apps/api/app/risk/service.py` dosyasındaki takvim kontrolünü böl:
    *   `is_comex_weekend(dt) -> bool`: Sadece gerçek hafta sonlarını (Cuma 17:00 ET - Pazar 18:00 ET) kapsar.
    *   `is_comex_maintenance(dt) -> bool`: Hafta içi günlük 1 saatlik bakım penceresini (Pzt-Per 17:00 - 18:00 ET) kapsar.
    *   `is_comex_market_closed(dt) -> bool`: Bu iki fonksiyonun birleşimidir (`weekend or maintenance`).
*   `apps/api/app/agents/hermes.py` dosyasında Telegram bildirim koşulunu güncelle:
    *   Rapor gönderimini `is_comex_market_closed` yerine sadece `is_comex_weekend` koşuluna bağla. Hafta içi bakım saatlerinde hafta sonu nöbetçi raporu gönderilmesini engelle.

### Faz 2: Modüler RSS Haber Kazıyıcıların Tasarımı (Backend Dev)
*   **Ajan:** `backend-architect`
*   `apps/api/app/collectors/public_sources.py` içerisine genel amaçlı, esnek RSS toplayıcısını ekle:
    *   `RSS_FEEDS` haritasını oluştur (Kitco, Bloomberg HT, FXStreet, Investing RSS linkleri).
    *   `collect_rss_news(db, *, source: str, url: str)` fonksiyonunu yaz. rate-limit korumalı `_fetch_text` kullanarak XML çeken, title/link/pubDate parsing yapan ve duplicate engelleyen yapı.
    *   Bağlantı hatası durumunda alternatif (yedek) RSS beslemelerine geçebilen **Yedekli URL Hataları Yönetimi**.
*   `apps/api/app/collectors/runner.py` dosyasındaki `JOB_CHOICES`'a yeni toplayıcıları ekle ve `run_once` akışına bağla.

### Faz 3: Demir Kalkan (Iron-Clad) Canlı RSS Çekim Yedekliliği
*   **Ajan:** `backend-architect` & `data-engineer`
*   `apps/api/app/agents/hermes.py` ve `news.py` içindeki analiz akışını güncelle:
    *   Eğer son 24 saat içinde veri tabanına taze haber düşmemişse, doğrudan tarihi Fed tutanaklarına dönmek yerine, **analiz sırasında canlı ve inline olarak RSS kanallarından haber çekilmesini sağlayan** on-demand kurtarıcı tetikle. Bu sayede background servis gecikse dahi analiz daima taze haberler üzerinden çalışır.

### Faz 4: Şiddetli Test Aşaması (Quality Dev)
*   **Ajan:** `quality-engineer`
*   **Test Senaryoları:**
    *   *Takvim Testi:* Hafta sonu, hafta içi açık saat ve hafta içi bakım saatleri için `is_comex_weekend` ve `is_comex_maintenance` çıktılarını doğrula.
    *   *RSS Parser Testi:* Başarılı XML akışları, hatalı/bozuk XML şemaları, eksik alanlar ve mükerrer (duplicate) URL durumları için izole mock testleri yazar.
    *   *Yedekleme Testi:* Birincil RSS adresi çöktüğünde sistemin yedek URL üzerinden başarıyla veri topladığını mock'lar üzerinden test eder.
*   **DoD (Tamamlanma Tanımı):** Tüm testlerin lokalde `%100` başarıyla yeşillenmesi.

### Faz 5: Statik Güvenlik Kapısı (Safety Gate)
*   **Ajan:** `safety-gatekeeper`
*   Yazılan kodların statik analizi, ağ sandboxing izolasyonu ve mock kalitesinin Gemini 3.5 Pro ile static audit edilmesi.

---

## ❓ Kullanıcı Onayı Gerektiren Konular (Socratic Gate)

> [!IMPORTANT]
> 1. **Model Geçiş Onayı:** Geliştirme, canlı kurtarma ve `safety-gatekeeper` statik analiz aşamalarında en üst düzey mantık doğruluğu sağlamak adına, plan onaylandıktan sonra modeli **Gemini 3.5 Pro** olarak değiştirmeyi onaylıyor musunuz?
> 2. **RSS Haber Kaynakları:** Listelediğimiz 4 ana haber kaynağının (Kitco, Bloomberg HT, FXStreet, Investing) standart RSS şablonları üzerinden toplanmasını ve veri tabanında tekilleştirilmesini onaylıyor musunuz?
