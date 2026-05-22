# Implementation Plan: Phase 15 - Harmanlanmış Ajan Rejim ve Konsensüs Motoru (Updated with Live Loop & Heartbeat Repair)

Bu plan, **Phase 15: Harmanlanmış Ajan Rejim ve Konsensüs Motoru** (Blended Agentic Regime & Consensus Engine) entegrasyonunun tasarım, güvenlik, test ve canlıya alma adımlarını detaylandırmaktadır. 

Ayrıca, kullanıcının geri bildirimi doğrultusunda **canlı döngüdeki görünmezlik ve bildirim sessizliği** sorunlarını kökten çözecek **Faz 0: Canlı Döngü ve Bildirim Observability & Heartbeat Tamiri** plana entegre edilmiştir.

---

## 🐛 Bug Teşhis ve Analiz Raporu (5 Neden Analizi)

*   **Semptom:** VPS üzerinde otomatik alım-satım botu çalışıyor görünmesine rağmen hiç işlem yapmıyor ve Telegram kanalına hiçbir otomatik bildirim gelmiyor. Ancak `/durum` ve `/karzarar` komutları elle yazıldığında bot anında cevap veriyor.
*   **1. Neden:** Sistem kurulduğundan beri `strategy_name` parametresi `"rsi"` olarak ayarlı ve RSI stratejisi sadece RSI < 30 (Aşırı Satım - AL) veya RSI > 70 (Aşırı Alım - SAT) durumlarında işlem tetikliyor. Son dönemde gümüş yatay seyrettiği için tüm sinyaller `HOLD (RSI_NEUTRAL)` olarak üretildi.
*   **2. Neden:** Sinyal `HOLD` olduğunda veritabanında sadece `signals` kaydı oluşturuluyor, herhangi bir `PaperTrade` (alım-satım veya bloke) kaydı oluşmuyor.
*   **3. Neden:** Mevcut `auto_trader.py` kodundaki Telegram bildirim tetikleyicisi sadece bir `PaperTrade` işlemi gerçekleştiğinde veya risk motoru tarafından engellendiğinde (`trade.action in ("paper_buy", "paper_sell", "blocked")`) çalışıyor. `HOLD` durumlarında hiçbir bildirim gönderilmiyor.
*   **4. Neden:** Collector konteyneri arka planda çalışırken `app/collectors/runner.py` doğrudan tetikleniyor. Ancak bu dosya içerisinde standard Python `logging.basicConfig` yapılandırması çağrılmadığı için, `auto_trader.py` içerisindeki `logger.info` veya `logger.error` çıktıları docker loglarına yazılmıyor ve sessiz kalıyor.
*   **Kök Neden (5. Neden):** Sistemde bir "kalp atışı" (heartbeat) veya sinyal değişim takip mekanizması bulunmadığı için, botun sağlıklı şekilde `HOLD` kararı vererek beklediği anlar ile botun tamamen çökmüş olduğu anlar kullanıcı gözünde tamamen aynı (sessiz) görünmektedir.

---

## 🛡️ Risk ve Bağlam Analizi
*   **Etkilenen Politikalar:**
    *   *docs/RISK_POLICY.md:* Ajanlar arası kararlar harmanlansa dahi, deterministik risk süzgeci (`evaluate_paper_trade_risk`) ve bakiye kontrolleri asla devre dışı bırakılamaz.
    *   *docs/DATA_CONTRACTS.md:* `signals` ve `paper_trades` tablolarına eklenecek yeni alanlar veri kontratlarına tam uygun olmalıdır.
*   **Etkilenen Şemalar:**
    *   `signals` (`details_json` kolonunda o anki piyasa rejimi ve her stratejinin oyu saklanacak).
    *   `agent_memory_events` (Yüce Hakem'in harmanlama mantığı ve gerekçesi kaydedilecek).

---

## 🛠️ Fazlar ve Görev Listesi

### ⚙️ Faz 0: Canlı Döngü ve Bildirim Observability & Heartbeat Tamiri
*   **[MODIFY] [runner.py](file:///Users/boe747/SilverPilot/apps/api/app/collectors/runner.py)** (Ajan: `debugger-agent`):
    *   Dosyanın en başına `logging.basicConfig(level=logging.INFO)` eklenerek collector docker loglarının (`docker compose logs -f collector`) görünürlüğü sağlanacak.
*   **[MODIFY] [auto_trader.py](file:///Users/boe747/SilverPilot/apps/api/app/services/auto_trader.py)** (Ajan: `backend-architect`):
    *   Telegram bildirim mantığı geliştirilecek:
        *   Eğer işlem `BUY`, `SELL` veya `BLOCKED` ise Telegram üzerinden **sesli/titreşimli bildirim** (varsayılan) gönderilmeye devam edecek.
        *   Eğer işlem `HOLD` ise, botun yaşadığını ve analiz yaptığını göstermek için **sessiz bildirim** (`disable_notification=True`) gönderilecek. Böylece kullanıcının telefonu titremeyecek ancak Telegram sohbetine girdiğinde botun 15 dakikada bir yaptığı analizlerin güncel akışını (anlık fiyat, RSI değeri, rejim kararı vb.) görebilecek.
*   **DoD (Tamamlanma Tanımı):** Collector manuel koşturulduğunda docker loglarında `run_auto_trading` çıktılarının görünmesi ve Telegram'a ilk sessiz `HOLD` durum bildiriminin başarıyla ulaşması.

### 📊 Faz 1: Otonom Rejim Tespit Servisi (Regime Classifier)
*   **[NEW] [regime.py](file:///Users/boe747/SilverPilot/apps/api/app/services/regime.py)** (Ajan: `data-engineer`):
    *   Son fiyat snapshot'larını ve indikatör verilerini (SMA_20, SMA_50, BB_Upper, BB_Lower) alarak **ADX, Volatilite ve Bant Genişliği (Bandwidth)** hesaplamaları yapacak matematiksel motor kurulacak.
    *   Piyasa durumunu otonom olarak 3 sınıfa ayıracak:
        *   `TRENDING_UP` (Güçlü yükseliş trendi - Trend takip eden stratejiler öncelikli)
        *   `TRENDING_DOWN` (Güçlü düşüş trendi - Defansif kalma / nakitte bekleme öncelikli)
        *   `SIDEWAYS` (Yatay/sakin piyasa - RSI ve Bollinger gibi salınım stratejileri öncelikli)
*   **DoD:** Birim testlerinde farklı fiyat dalgalanmalarına göre doğru rejim etiketinin (`TRENDING_UP`, `TRENDING_DOWN`, `SIDEWAYS`) hatasız döndürülmesi.

### 🔄 Faz 2: Çoklu Strateji Sinyal Oylayıcı (Blended Strategy Evaluator)
*   **[MODIFY] [strategy.py](file:///Users/boe747/SilverPilot/apps/api/app/services/strategy.py)** (Ajan: `backend-architect`):
    *   RSI, Bollinger ve SMA Cross stratejilerini aynı anda çalıştıran ve oylarını toplayan `evaluate_blended_strategies` fonksiyonu eklenecek.
    *   Fonksiyon, stratejilerin oylarını (`RSI: BUY`, `Bollinger: HOLD`, `SMA: HOLD` vb.) bir sözlük olarak geriye dönecek.
*   **DoD:** Birim testlerinde 3 farklı indikatörün aynı fiyat barı için ürettiği oyların tek bir sözlük altında doğru şekilde toplanması.

### 👑 Faz 3: Yüce Hakem (Supreme Arbiter) Harmanlama Entegrasyonu
*   **[MODIFY] [orchestrator.py](file:///Users/boe747/SilverPilot/apps/api/app/agents/orchestrator.py)** (Ajan: `backend-architect`):
    *   Supreme Arbiter (deepseek-v4-pro) promptu güncellenecek.
    *   Girdi olarak LLM'e o anki **Piyasa Rejimi** ve **Çoklu Strateji Sinyal Dağılımı** beslenecek.
    *   Yüce Hakem, rejim bilgisine göre stratejilerin oylarını ağırlıklandırarak (örneğin yatay piyasada RSI oylarına %70 ağırlık verirken, trend piyasasında SMA Cross oylarına öncelik vererek) nihai `resolved_stance` kararını verecek ve gerekçesini `agent_memory_events` tablosuna yazacak.
*   **DoD:** Yüce Hakem LLM çağrısının rejim ve strateji oyları girdiğinde kurallara uygun, uyuşmazlıkları çözen ve kararlı bir JSON çıktı üretmesi.

### 🤖 Faz 4: Otomatik Ticaret Döngüsü & Premium Telegram Entegrasyonu
*   **[MODIFY] [auto_trader.py](file:///Users/boe747/SilverPilot/apps/api/app/services/auto_trader.py)** (Ajan: `backend-architect`):
    *   Default strateji `"blended"` olarak set edilecek.
    *   `strategy_name == "blended"` olduğunda, sistem önce piyasa rejimini hesaplayacak, ardından tüm indikatörlerin oylarını alacak, sonrasında Yüce Hakem'i çağıracak.
    *   Karara göre işlem (BUY/SELL) yapılacak ve Telegram bildirimi aşağıdaki **şık ve premium görsel şablonla** güncellenecek:
        ```markdown
        📊 *SilverPilot Canlı Analiz Raporu*
        
        🥈 *Gümüş (XAG):* 75.3510 USD/oz
        📈 *Piyasa Rejimi:* Yatay Sakin Piyasa (SIDEWAYS)
        
        🗳️ *Strateji Oylaması:*
        • RSI (14): 🟢 AL (Aşırı Satım)
        • Bollinger Bands: ⚪️ BEKLE
        • SMA Cross (20/50): ⚪️ BEKLE
        
        👑 *Yüce Hakem Kararı:* 🟢 AL (Onaylandı)
        📝 *Gerekçe:* Yatay piyasada RSI aşırı satım bölgesinde ve Bollinger alt bandına yakın. Risk limitleri uygun, alım onaylandı.
        ```
*   **DoD:** Canlı collector tetiklendiğinde tüm harmanlanmış döngünün sızıntı olmadan baştan sona çalışması ve Telegram'a premium şablonla bildirim atması.

### 🧪 Faz 5: Kalite Kontrol ve E2E Doğrulama
*   **[NEW] [test_blended_trader.py](file:///Users/boe747/SilverPilot/tests/test_blended_trader.py)** (Ajan: `quality-engineer`):
    *   Mock rejim verileri, strateji oyları ve LLM çıktılarıyla Yüce Hakem harmanlama mantığının uçtan uca test edilmesi.
*   **[MODIFY] [.env.production](file:///Users/boe747/SilverPilot/.env.production)** (Ajan: `backend-architect`):
    *   `strategy_name` varsayılan olarak `blended` değerine güncellenecek.
*   **DoD:** Bütün testlerin sıfır hata ile yeşil geçmesi.

---

## 🧪 Doğrulama Planı

### Otomatik Testler
- Yazılacak yeni testler ve mevcut testler yerel ortamda koşturulacak:
  ```bash
  .venv/bin/pytest apps/api/tests/test_auto_trader.py
  .venv/bin/pytest apps/api/tests/test_blended_trader.py
  ```

### Manuel Doğrulama
- Geliştirmeler bittikten sonra kodlar VPS'e aktarılacak (`scripts/deploy.sh` ile).
- VPS üzerinde collector manuel tetiklenerek sessiz ve sesli Telegram bildirimlerinin premium formatta düştüğü doğrulanacak:
  ```bash
  docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job global-xag-usd
  ```
