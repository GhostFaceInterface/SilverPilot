# Implementation Plan: Telegram Bot On-Demand Instant Analysis (`/canli` & `/analiz`)

Bu plan, kullanıcının talebi doğrultusunda Telegram botuna iki yeni komut eklemeyi amaçlar:
1. **/canli:** Canlı veri çekimini tetikleyerek o saniyeye ait en güncel Kuveyt Türk ve küresel gümüş fiyatları üzerinden Yüce Hakem karar analizini metin tabanlı bir rapor olarak anında sunar.
2. **/analiz:** Günü 3 seansa böler (Sabah 00-08, Öğle 08-16, Akşam 16-24) gümüş fiyatının gün içindeki değişimini şık, karanlık mod (dark-mode) tasarımlı ve yumuşak gölgelendirmeli dikey seans dilimlerine sahip bir çizgi grafiği (`matplotlib` ile in-memory) üreterek Telegram'dan görsel olarak gönderir.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - *[.agent/GEMINI.md](file:///.agent/GEMINI.md)*: Dürüst Ortaklık, zero-trust ve Socratic Gate kuralları.
  - *[tech-decisions.md](file:///.agent/memory/tech-decisions.md)*: DeepSeek Budget Guard kuralları ($1.00 olan günlük harcama limitinin aşılmaması için bütçe kontrolünün güncellenmesi).
- **Etkilenen Dosyalar:**
  - `apps/api/app/agents/telegram_bot.py` (Yeni komutlar, asenkron motor ve grafik oluşturma servisi)
  - `apps/api/tests/test_telegram.py` (Yeni komut test senaryolarının entegrasyonu)
  - `apps/api/requirements.txt` (Bağımlılık listesine `matplotlib` eklenmesi)
  - `.env` ve `.env.production` (Günlük DeepSeek bütçe sınırının $3.00 USD'ye yükseltilmesi)

---

## 🛠️ Fazlar ve Görev Listesi

### Faz 1: Altyapı Hazırlığı ve Bütçe Yükseltilmesi
Sistemin donanım/kütüphane bağımlılıklarını kurup yüksek frekanslı yapay zeka harcamaları için Budget Guard bütçesini güncelleyeceğiz.

- [x] **Bağımlılık Tanımı:** `apps/api/requirements.txt` dosyasına `matplotlib>=3.8,<4.0` kütüphanesinin eklenmesi.
- [x] **Bütçe Güncellemesi:** `.env` ve `.env.production` dosyalarında `DEEPSEEK_DAILY_BUDGET_USD` değerinin `3.00` USD'ye çıkarılması.
- [x] **Canlı Analiz Servisi:** `apps/api/app/agents/telegram_bot.py` içerisine asenkron `run_canli_analysis_report(db: Session, settings)` fonksiyonunun eklenmesi (herhangi bir paper-trade tetiklemeden, o saniyeye ait güncel Kuveyt ve Global verileri çekip konsensüs raporunu derler).
- *DoD (Tamamlanma Tanımı):* `run_canli_analysis_report` fonksiyonunun in-memory testlerde başarıyla canlı veri toplayıp rapor hazırlaması.

---

### Faz 2: Şık Günlük Fiyat Grafik Motoru (Matplotlib Dark-Mode Plotter)
Günü 3 seansa bölen ve modern, premium bir grafik üreten görsel motoru inşa edeceğiz.

- [x] **Veri Çekme & Sınıflandırma:** Veritabanındaki `PriceSnapshot` tablosundan son 24 saate ait (veya bugün takvim günündeki) tüm Kuveyt Türk fiyat verilerini çeken ve zaman damgalarını yerel saate (+3) göre düzenleyen SQL sorgusunun yazılması.
- [x] **Grafik Çizim Mantığı (`matplotlib`):**
  - **Arayüz Tasarımı (Premium Dark-Mode):** Grafik arka planını koyu gri (`#121212`), kılavuz çizgilerini belirgin ve çizgi rengini parlayan neon gümüş/mavi tonlarında (`#00e5ff` veya `#c0c0c0`) tasarlayacağız.
  - **Dikey Seans Dilimleri (`axvspan`):**
    - **Sabah Seansı (00:00 - 08:00):** Şeffaf soft mavi gölgeleme.
    - **Öğle-Avrupa Seansı (08:00 - 16:00):** Şeffaf soft altın/sarı gölgeleme.
    - **Akşam-Amerika Seansı (16:00 - 24:00):** Şeffaf soft mor gölgeleme.
  - **Dinamik Etiketler:** Her dilimin üzerine o seansın adı ve saat aralığı şık yazı fontlarıyla yazılacak.
- [x] **Bellek İçi Çıktı Üretimi:** Grafiği fiziksel diske yazıp sunucuyu kirletmek yerine doğrudan `io.BytesIO` bellek tamponuna (PNG formatında ve `.seek(0)` ile sıfırlanmış olarak) çıktı veren modülün tamamlanması.
- *DoD:* Grafik motorunun in-memory test verileriyle başarıyla PNG formatında BytesIO tamponu üretmesi.

---

### Faz 3: Telegram Bot Komut Entegrasyonu (`/canli` ve `/analiz`)
Telegram üzerinden komutları karşılayıp anlık olarak hem metin raporunu hem de şık grafiği bota ileteceğiz.

- [x] **Komut Yakalayıcı:** `telegram_bot.py` içerisindeki `process_telegram_update` fonksiyonuna `/canli` ve `/analiz` komut kontrolünün eklenmesi:
  - **`/canli` komutu:** Kullanıcıya durum bekleme mesajı atıp ardından ham metin konsensüs analizini iletir.
  - **`/analiz` komutu:** Kullanıcıya bekleme mesajı gönderdikten sonra arka planda `generate_daily_price_chart` çağrısı yapar. Grafik üretildiğinde, `bot.send_photo` yöntemi kullanılarak resim olarak gönderilir.
  - **Görsel Altı Detaylı Caption (Açıklama):** Gönderilen resmin altına her 3 seansın en yüksek (High), en düşük (Low) fiyatlarını ve genel günlük eğilimi listeleyen şık bir seans özet tablosu eklenecektir.
- *DoD:* Bot simülatöründe `/analiz` çağrıldığında sistemin bir görsel dosyayı `BytesIO` üzerinden başarıyla gönderebilmesi.

---

### Faz 4: Testler, Doğrulama ve Canlı Deployment
Sistemin tüm aşamalarını test edip remote sunucuda yayına alacağız.

- [x] **Unit Testler:** `apps/api/tests/test_telegram.py` dosyasına `/canli` ve `/analiz` komutlarını mock-up entegrasyonuyla doğrulayan yeni test senaryolarının yazılması.
- [x] **Yerel Test Koşumu:** Tüm yerel test süitinin koşturulması (`pytest apps/api/tests` passing 150/150).
- [/] **VPS Deployment:** `deploy.sh -y` komutu tetiklenerek kodun `main` dala push edilmesi, VPS'e çekilmesi, Docker servislerinin rebuild edilmesi ve `vps_smoke.sh` entegrasyon smoke testlerinin tamamlanması.
- *DoD:* GitHub Actions CI hattının başarıyla tamamlanması ve gerçek Telegram kanalından `/analiz` komutunun çağrılarak şık grafik çıktısının alınması.

---

## ❓ Açık Sorular
> [!IMPORTANT]
> - Günlük DeepSeek limitinin **$3.00 USD** seviyesine yükseltilmesi ve grafik çizimi için `matplotlib` kütüphanesinin projeye dahil edilmesi onaylanmıştır.
> - Matplotlib'in Docker konteyneri içinde font/görsel render motoru (GUI gerektirmeyen `Agg` backend) kullanacak şekilde yapılandırılması sağlanmıştır, bu sayede sunucuda hiçbir pencereleşme/ekran ihtiyacı oluşmadan arka planda görsel üretilebilir.
