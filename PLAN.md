# Implementation Plan: Merciless System-Wide Testing & Telegram Bot HTML Resiliency Audit

Bu eylem planı, SilverPilot sisteminin tüm kritik katmanlarında (Telegram arayüzü, tarihsel veri backfill mekanizması, veri toplayıcı veri bütünlüğü ve auto-trader strateji motoru) acımasız ve uçtan uca (E2E) testler uygulamayı, Telegram `/canli` çökme sorununu HTML göçü ile kökten gidermeyi ve her bir bileşenin davranışlarını doğrulamayı hedefler.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:** [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Portföy riski, pozisyon limitleri ve BSMV kambiyo vergileri), [docs/DATA_CONTRACTS.md](file:///Users/boe747/SilverPilot/docs/DATA_CONTRACTS.md) (Veri şemaları ve entegrasyon yapıları).
- **Etkilenen Dosyalar:**
  - `apps/api/app/agents/telegram_bot.py` (Telegram formatlarının Markdown'dan güvenli HTML'e taşınması)
  - `apps/api/tests/test_telegram.py` (Yeni HTML tag doğrulama ve komut güvenliği testleri)
  - `scripts/backfill_history.py` (Veri kaynağının `yahoo-si-f` olarak düzeltilmesi ve `XAG_GRAM` tarihsel verilerinin indikatörleri beslemek üzere otomatik çoğaltılması)
  - `apps/api/app/collectors/service.py` (Düşük veri seanslarında indikatör koruması ve fallback testleri)

---

## 🛠️ Fazlar ve Görev Listesi

- `[ ]` **Faz 1: Telegram Bot Formatting & HTML Migration Audit (Ajan: frontend-architect / security-auditor)**
  - [ ] Telegram bot mesaj şablonlarını `/canli`, `/durum`, `/karzarar`, `/cuzdan` ve `/ajanlar` için tamamen robust **HTML parsing moduna** (`parse_mode="HTML"`) taşımak.
  - [ ] Markdown V1'in iç içe geçmiş asteriks/underscore karakterlerindeki ve `XAG_GRAM` alt çizgilerindeki parsing çökmelerini (Offset 64 hatası) `html.escape` kullanarak kalıcı olarak engellemek.
  - [ ] `sanitize_markdown` yerine HTML etiketlerini koruyan ve LLM çıktılarındaki tehlikeli HTML karakterlerini temizleyen `escape_html_response` yardımcı fonksiyonunu yazmak.
  - *DoD (Tamamlanma Tanımı):* `tests/test_telegram.py` içerisine tüm komutların (/canli, /durum, /karzarar, /cuzdan, /ajanlar, /help) HTML etiket bütünlüğünü, boş/dolu portföy senaryolarını ve hata durumlarını acımasızca sınayan unit testlerin eklenmesi ve tamamının hatasız geçmesi.

- `[ ]` **Faz 2: Tarihsel Veri & İndikatör Seeding Düzeltmesi (Ajan: data-engineer)**
  - [ ] `scripts/backfill_history.py` dosyasını, Yahoo Finance'den çekilen tarihsel verileri hem `XAG` (Ounce) hem de `XAG_GRAM` (Gram Silver, 31.1035'e bölünmüş) olarak veri tabanına kaydedecek şekilde güncellemek.
  - [ ] Tarihsel veri kaynağını `"yahoo-si-f-1d"` yerine doğrudan `/canli` ve auto-trader'ın kullandığı ana `"yahoo-si-f"` global kaynağı olarak kaydetmek.
  - [ ] Local ve VPS veritabanlarında `python scripts/backfill_history.py` çalıştırarak en az 200 barlık günlük teknik indikatör geçmişini (`TechnicalIndicator` ve `PriceSnapshot`) `XAG_GRAM` için eksiksiz üretmek.
  - *DoD:* `pytest tests/test_collectors.py` veya backfill script'inin yerelde sorunsuz çalışması ve DB'de `XAG_GRAM` indikatörlerinin varlığının doğrulanması.

- `[ ]` **Faz 3: Uçtan Uca Collector & Degraded Network Dayanıklılık Testleri (Ajan: data-engineer / quality-engineer)**
  - [ ] FRED, TCMB, RSS ve Gold API toplayıcılarının (collectors) sıfır veri veya bağlantı kopukluğu anlarındaki hata yakalama ve "graceful degradation" (kısmi hizmet durdurma) davranışlarını simüle etmek.
  - [ ] Hafta sonu / piyasa dışı saatler simülasyonu altında `kuveyt-silver` ve `global-xag-usd` toplayıcılarının soft-fail davranışlarını ve veri tutarlılığını test eden acımasız senaryolar işletmek.
  - *DoD:* Tüm testlerin `pytest` ile test edilip yeşil yanması ve `verify_execution_pipeline.py` script'inin başarılı olması.

- `[ ]` **Faz 4: Strateji Sinyalleri & BSMV Vergi Mantığı Simülasyonu (Ajan: backend-architect / quality-engineer)**
  - [ ] `StrategyRunner` oylamalarında RSI, Bollinger ve SMA kesişimlerinin `None`/eksik indikatör durumundaki mukavemetini test etmek.
  - [ ] Paper-trading işlemlerinde %0.2 BSMV (kambiyo vergisi), spread ve slippage (kayma) hesaplamalarının doğruluğunu matematiksel sınamalarla denetlemek.
  - *DoD:* Yerel testlerin `pytest tests/test_auto_trader.py` komutuyla 100% başarılı olması.

- `[ ]` **Faz 5: VPS Deployment & Smoke Validation (Ajan: safety-gatekeeper / quality-engineer)**
  - [ ] `deploy.sh -y` kullanarak güncellenmiş kodları ve backfill script'ini VPS'e göndermek.
  - [ ] VPS üzerinde `vps_smoke.sh` duman testini tetiklemek ve Telegram botundan `/canli`, `/durum`, `/karzarar` komutlarını göndererek sunucu çıktılarının loglarını doğrulamak.
  - *DoD:* VPS smoke testlerinin sıfır hata ile yeşile dönmesi ve Telegram botunun hiçbir parse hatası vermeden canlı analiz raporunu başarıyla iletmesi.

---

## ❓ Açık Sorular
> [!IMPORTANT]
> 1. **Telegram Webhook Modu:** VPS üzerinde Telegram botunun webhook modunda çalıştığından emin olmak için `vps_smoke.sh` sonrasında port 8000'deki webhook uç noktasını test edecek mini bir duman testi ekleyelim mi?
> 2. **Tarihsel Backfill:** VPS'teki PostgreSQL veritabanını temizlemeden, sadece eksik olan `XAG_GRAM` tarihsel verilerini eklemek için `backfill_history.py` içindeki tekilleştirme mekanizması (observed_at membership check) yeterli olacaktır. Onaylıyor musunuz?
