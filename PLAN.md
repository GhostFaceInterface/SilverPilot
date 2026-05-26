# Implementation Plan: Resilient Global XAG/USD Data Provider Fallback & Technical Indicators Recovery

Bu plan, Yahoo Finance'in VPS IP'lerini engellemesinden kaynaklanan veri toplayıcı başarısızlıklarını ve buna bağlı olarak teknik indikatörlerin/Telegram işlemlerinin durması sorununu kökünden çözmeyi amaçlar. Ücretsiz, anahtarsız ve VPS dostu yeni bir servis olan **GoldApiSilverProvider** entegre edilecek ve sistemin indikatör/auto-trader katmanı tek bir kaynağa (`yahoo-si-f`) bağımlı olmaktan çıkarılarak tam bir yedeklilik (resilience) kazandırılacaktır.

---

## 🛡️ Risk ve Bağlam Analizi
- **Tek Noktadan Başarısızlık (SPOF):** Mevcut auto-trader ve Telegram indikatör sorguları sert şekilde `yahoo-si-f` kaynağına bağımlıdır. Yahoo Finance VPS IP'sini engellediğinde veri toplama 200 OK HTML (cookie consent/CAPTCHA) döndüğü için `PARSE_ERROR` ile çökmekte, indikatörler hesaplanamamakta ve tüm auto-trading motoru durmaktadır.
- **Yedekli İndikatör Hesaplama Güvencesi:** Gold API veya gelecekteki herhangi bir global sağlayıcıdan veri çekildiğinde de indikatörlerin otomatik hesaplanması ve veri tabanına yazılması gerekmektedir.
- **Etkilenen Dosyalar:**
  - `apps/api/app/core/config.py` (Yeni Gold API ayarlarının eklenmesi ve varsayılan öncelik listesinin güncellenmesi)
  - `apps/api/app/collectors/public_sources.py` (Yeni `GoldApiSilverProvider` sınıfı ve parser işlevinin yazılması)
  - `apps/api/app/collectors/service.py` (`_INDICATOR_GLOBAL_SOURCES` kümesine yeni kaynağın eklenmesi)
  - `apps/api/app/services/auto_trader.py` (Sadece `yahoo-si-f` yerine tüm aktif global kaynaklardan indikatör sorgulayacak dinamik yapıya geçiş)
  - `apps/api/app/agents/telegram_bot.py` (İndikatör ve fiyat seansı analizlerini yedekli kaynaklardan çekecek esnek kurgunun entegrasyonu)
  - `apps/api/tests/test_collectors.py` (Yeni sağlayıcı için unit ve entegrasyon testlerinin yazılması)

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Konfigürasyon & Yeni Gold API Sağlayıcı Altyapısı**
  - [x] **Config Güncellemesi:** `apps/api/app/core/config.py` dosyasına `gold_api_xag_usd_enabled`, `gold_api_xag_usd_url` ve `gold_api_xag_usd_timeout_seconds` alanlarının eklenmesi.
  - [x] **Öncelik Güncellemesi:** `global_xag_source_priority` varsayılan değerinin `"yahoo-si-f,gold-api-xag-usd,metals-dev"` olarak güncellenmesi.
  - [x] **Sağlayıcı Sınıfı:** `apps/api/app/collectors/public_sources.py` içerisine `GoldApiSilverProvider` sınıfının ve `parse_gold_api_silver_spot_json` parser işlevinin yazılması.
  - [x] **Sağlayıcı Tescili:** `_global_xag_providers` fonksiyonuna yeni sağlayıcının tescil edilmesi.
  - *DoD (Tamamlanma Tanımı):* Gold API sağlayıcısının yerelde sahte payload ile başarıyla parse edilebilmesi.

- `[x]` **Faz 2: İndikatör Hesaplama & Auto-Trader / Telegram Yedeklilik Entegrasyonu**
  - [x] **İndikatör Tetikleyici Güncellemesi:** `apps/api/app/collectors/service.py` içerisindeki `_INDICATOR_GLOBAL_SOURCES` kümesine `"gold-api-xag-usd"` ve `"metals-dev-silver-spot"` değerlerinin eklenmesi.
  - [x] **Auto-Trader Sorgu Esnekliği:** `apps/api/app/services/auto_trader.py` içerisindeki indikatör ve snapshot sorgularının tek bir sert kaynak yerine en son başarıyla güncellenen herhangi bir global kaynağı (`"yahoo-si-f"`, `"gold-api-xag-usd"`, `"metals-dev-silver-spot"`) getirecek şekilde esnetilmesi.
  - [x] **Telegram Bot Sorgu Esnekliği:** `apps/api/app/agents/telegram_bot.py` içindeki `/canli` (indikatör), seans analizleri ve chart sorgularının en son aktif global kaynağı dinamik olarak algılamasının sağlanması.
  - *DoD:* Auto-trader ve Telegram modüllerinin `yahoo-si-f` yerine `gold-api-xag-usd` indikatörleri bulunduğunda da hatasız çalışması.

- `[x]` **Faz 3: Testler & Yerel Doğrulama**
  - [x] **Unit Testler:** `apps/api/tests/test_collectors.py` içerisine `GoldApiSilverProvider`'ın başarılı akış, timeout ve parse hatası senaryolarını test eden kapsamlı unit testlerin yazılması.
  - [x] **Entegrasyon Testi:** Fallback zincirinde Yahoo Finance başarısız olduğunda sistemin otomatik olarak Gold API'ye geçiş yaptığını ve `PriceSnapshot` ile `TechnicalIndicator` kayıtlarını oluşturduğunu doğrulayan entegrasyon testinin yazılması.
  - *DoD:* Tüm pytest yerel test süitinin (150+ test) sıfır hata ile tamamlanması.

- `[x]` **Faz 4: Canlı Dağıtım & VPS Smoke Doğrulaması**
  - [x] **Git Commit & Push:** Kod değişikliklerinin `main` dalına otomatik commit ve push edilmesi.
  - [x] **VPS Deploy & Smoke:** VPS sunucusunda `vps_smoke.sh` duman testlerinin çalıştırılması ve yeşil yanmasının teyit edilmesi.
  - *DoD:* `vps_smoke.sh` testinin tüm sağlayıcılar için (özellikle Yahoo başarısız olsa dahi Gold API yedeğiyle) 100% başarıyla tamamlanması.

---

## ❓ Açık Sorular
> [!NOTE]
> - Gold API (`api.gold-api.com`) tamamen ücretsiz, anahtarsız ve VPS IP'lerine karşı son derece hoşgörülüdür. Bu sağlayıcıyı öncelik sırasında Yahoo Finance'in hemen ardına koyarak Yahoo'nun çöktüğü tüm anlarda otomatik ve kusursuz bir yedeklilik sağlamayı hedefliyoruz.
> - İndikatörlerin her iki global kaynaktan da gelebileceğini varsayarak, auto-trader ve Telegram botunun veri tabanındaki en taze global indikatör kaydını çekmesi mimari açıdan en doğru ve sağlam yaklaşımdır.
