# Implementation Plan: Phase 14 - Automated Paper-Trading Runner & Telegram Alerts

Bu plan, SilverPilot projesinde **Phase 14: Automated Paper-Trading Runner & Telegram Alerts** entegrasyonunun tasarım, güvenlik, test ve canlıya alma adımlarını detaylandırmaktadır. Bu entegrasyon sayesinde, fiyat toplayıcı (collector) yeni bir gümüş spot fiyatı çektiğinde otomatik olarak teknik indikatörleri analiz edecek, aktif stratejiye (RSI/SMA) göre sinyaller üretecek, risk süzgecinden geçirip simüle alım/satım (paper-trade) işlemlerini otomatik gerçekleştirecek ve anında Telegram üzerinden bildirim gönderecektir.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - *Deterministic Risk Authority:* Tüm otomatik işlemler `evaluate_paper_trade_risk` süzgecinden geçecektir. Risk kurallarını aşan işlemler engellenerek `blocked` olarak kaydedilecek ve kullanıcıya risk uyarısı gönderilecektir.
  - *Port Isolation:* Otomatik işlem döngüsü FastAPI veritabanı oturum katmanı (`SessionLocal()`) üzerinden yürütülecektir. Sızıntıları önlemek için context manager kullanılacaktır.
  - *Zero-Trust Access Control:* Otomatik işlem bildirimleri yalnızca yapılandırılmış `TELEGRAM_CHAT_ID` değerine gönderilecektir.
- **Etkilenen Şemalar:**
  - `signals` (Yeni üretilen strateji sinyalleri kaydedilecek)
  - `paper_trades` (Gerçekleşen veya engellenen otomatik simüle işlemler yazılacak)
  - `portfolios` / `portfolio_snapshots` (Nakit bakiyesi ve gümüş miktarı güncellenecek)

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Konfigürasyon Güncellemesi**
  - `[x]` `apps/api/app/core/config.py` içerisine `strategy_name: str = "rsi"` (kullanılacak varsayılan strateji) ve otomatik işlem bildirimlerini açıp kapatmak için `auto_trading_enabled: bool = True` parametrelerinin eklenmesi.
  - *DoD (Tamamlanma Tanımı):* `get_settings()` çağrıldığında yeni parametrelerin varsayılan değerleriyle hatasız okunması.

- `[x]` **Faz 2: Otomatik Ticaret Servisi (Auto Trader Service)**
  - `[x]` `apps/api/app/services/auto_trader.py` *[NEW]* dosyasının oluşturulması. Bu dosya:
    - `run_auto_trading(db: Session)` fonksiyonunu içerir.
    - `default-paper` portföyünü ve `XAG` gümüş varlığını çeker.
    - `yahoo-si-f` kaynağından en son iki `TechnicalIndicator` kaydını sorgular.
    - `StrategyRunner.evaluate_all_strategies` fonksiyonu ile sinyal (BUY/SELL/HOLD) üretir.
    - Sinyal `BUY` ise ve pozisyon yoksa, cüzdandaki tüm nakitle (`cash_balance`) simüle alım yapar.
    - Sinyal `SELL` ise ve açık gümüş pozisyonu varsa, tüm gümüşü simüle satar.
    - İşlem gerçekleştiğinde veya risk engeline takıldığında Telegram (`TELEGRAM_CHAT_ID`) üzerinden anlık bildirim atar.
  - *DoD:* Servis fonksiyonunun bağımsız Python çağrısıyla (mock verilerle) hatasız çalışması ve sinyal üretebilmesi.

- `[x]` **Faz 3: Collector Döngüsü Entegrasyonu**
  - `[x]` `apps/api/app/collectors/runner.py` içindeki `run_once` fonksiyonunda `global-xag-usd` işi bittiğinde `auto_trader.py`'nin tetiklenmesi:
    ```python
    if selected_job == "global-xag-usd":
        # ... global fiyat toplama ...
        if settings.auto_trading_enabled:
            import asyncio
            from app.services.auto_trader import run_auto_trading
            asyncio.run(run_auto_trading(db))
    ```
  - *DoD:* Fiyat toplama döngüsü çalıştığında arka planda otomatik strateji analizi ve işlem motorunun sorunsuz tetiklenmesi.

- `[x]` **Faz 4: Kalite Kontrol, Doğrulama ve Canlı Testler**
  - `[x]` Birim test dosyası `apps/api/tests/test_auto_trader.py` *[NEW]* oluşturulması. Strateji sinyallerinin (oversold/overbought) otomatik alım/satım işlemlerini ve veritabanı kayıtlarını doğru tetiklediğinin mock veritabanı ile test edilmesi.
  - `[x]` `pytest tests/test_auto_trader.py` komutunun tamamen yeşil geçmesi.
  - `[x]` Değişikliklerin test edildikten sonra otomatik olarak git commit ve git push işlemlerinin yapılması.
  - *DoD:* Bütün pytest test süitinin (143+ test) sıfır hata ile yeşil geçmesi.

---

## ❓ Açık Sorular & Kullanıcı Görüşü
> [!IMPORTANT]
> 1. **Strateji Seçimi:** Otomatik alım-satım için varsayılan olarak **RSI** stratejisini (`RSI < 30` oversold iken BUY, `RSI > 70` overbought iken SELL) kullanacağız. Dilerseniz bunu `sma_cross` veya `bollinger` olarak da ayarlayabilirsiniz.
> 2. **Telegram Bildirim Formatı:** Otomatik işlemler gerçekleştiğinde botunuzdan size gelecek bildirim mesajının Markdown formatında şık bir tasarımı olacaktır. Bu tasarımı onaylıyor musunuz?
