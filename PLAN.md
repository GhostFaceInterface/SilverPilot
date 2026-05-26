# Implementation Plan: Modüler Kıymetli Metal Dönüşüm Matrisi & Gram Gümüş Entegrasyonu (Option C)

Bu plan, ons tabanlı paper-trade hesabını tamamen kaldırarak yerine $2500 USD başlangıç bakiyesine sahip Gram/Dolar (`XAG_GRAM`) hesabını koymayı ve tüm sistemi gelecekte altın, platin gibi farklı maden ve birimlerin eklenmesini sıfır kod değişimiyle destekleyecek jenerik **Option C** mimarisine kavuşturmayı amaçlar.

---

## 🛡️ Risk ve Bağlam Analizi
- **Kritik Veritabanı Kısıt Riski:** `TechnicalIndicator` benzersizlik kısıtı `UniqueConstraint("bar_timestamp", "timeframe")` olarak tanımlıdır ve varlık ayırt etmemektedir. Çoklu varlık uyumluluğu için bu kısıt esnetilmelidir.
- **CI/CD Duman Testi Regresyonu:** `verify_execution_pipeline.py` E2E doğrulama betiği ons varlığı `XAG` bağımlıdır ve `XAG_GRAM` ile uyumlu güncellenmelidir.
- **Kuveyt BSMV Vergi Gerçekçiliği:** `paper_buy` işlemlerinde yasal %0.2 oranında yasal Kambiyo/BSMV vergisinin otomatik işlenmesi gerekmektedir.
- **Etkilenen Dosyalar:**
  - `apps/api/app/models/entities.py` (Kısıt tanımları)
  - `apps/api/app/services/seed.py` (Tohumlama)
  - `apps/api/app/collectors/service.py` (Dönüşüm ve replikasyon matrisi)
  - `apps/api/app/services/auto_trader.py` (Auto trader emir jenerikleştirilmesi)
  - `apps/api/app/agents/telegram_bot.py` (Bot komutları ve durum raporu)
  - `scripts/verify_execution_pipeline.py` (E2E duman testi)

---

## 🛠️ Fazlar ve Görev Listesi

- `[ ]` **Faz 1: DB Modülerlik Hazırlığı & Şema Tohumlama (Seeding)**
  - [ ] **Modüler Kısıt Güncellemesi:** `apps/api/app/models/entities.py` içerisindeki `TechnicalIndicator` benzersizlik kısıtının (UniqueConstraint) `price_snapshot_id` ve `timeframe` parametrelerini içerecek şekilde modüler hale getirilmesi.
  - [ ] **Seed Revizyonu:** `apps/api/app/services/seed.py` dosyasından ons portföyünün silinmesi; yerine `initial_cash = Decimal("2500.00")` ile `"gram-paper"` portföyünün ve `"XAG_GRAM"` asset kaydının eklenmesi.
  - [ ] **Alembic Migration:** Değişen model kısıtı için yeni bir Alembic migrasyonunun oluşturulması ve lokal test veri tabanında başarıyla uygulanması.
  - *DoD (Tamamlanma Tanımı):* `pytest` model testlerinin hatasız geçmesi ve veri tabanında `gram-paper` portföyü ile `XAG_GRAM` varlığının başarıyla tohumlanması.

- `[ ]` **Faz 2: Modüler Dönüşüm & Replikasyon Matris Servisi**
  - [ ] **Dönüşüm Matrisi Entegrasyonu:** `apps/api/app/collectors/service.py` içerisine jenerik dönüşüm matrisi (`AssetConversionManager`) ve `replicate_prices_for_gram(db, ounce_snapshot)` kurgusunun eklenmesi.
  - [ ] **Otomatik Tetikleyici:** Ons gümüş fiyatı sisteme girdiğinde anında gram birim fiyatını (Ons Fiyatı ÷ 31.1035) hesaplayıp `PriceSnapshot` ve scaled `TechnicalIndicator` kayıtlarını `XAG_GRAM` varlık kimliği ile otomatik oluşturan yapının entegre edilmesi.
  - *DoD:* Yeni ons fiyat toplayıcı çalıştırıldığında veri tabanında anında scaled Gram snapshot'larının ve teknik göstergelerinin hatasız oluşması.

- `[ ]` **Faz 3: Jenerik Auto-Trader ve E2E Duman Testi Revizyonu**
  - [ ] **AutoTrader Jenerikleşmesi:** `apps/api/app/services/auto_trader.py` içerisindeki auto-trading emir tetikleyicisinin tamamen `gram-paper` portföyü ve `XAG_GRAM` gram fiyat/miktar oranlarıyla çalışacak şekilde güncellenmesi.
  - [ ] **Kuveyt BSMV Vergi Mantığı:** `execute_paper_trade` çağrısında, eğer işlem yapılan varlık Gram ise `paper_buy` emirlerine %0.2 yasal verginin otomatik giydirilmesi.
  - [ ] **Duman Testi Güncellemesi:** `scripts/verify_execution_pipeline.py` betiğinin ons `XAG` yerine tamamen modüler `XAG_GRAM` varlığını simüle edecek şekilde revize edilmesi.
  - *DoD:* `python scripts/verify_execution_pipeline.py` duman testinin yerelde sıfır hata ve temiz rollback ile tamamlanması.

- `[ ]` **Faz 4: Telegram Botu Arayüzü ve Durum Raporlama Revizyonu**
  - [ ] **Telegram Komut Güncellemeleri:** `/durum`, `/cuzdan`, `/karzarar` ve `/ajanlar` komutlarının, ons hesabını tamamen dışarıda bırakıp yeni $2500 USD'lik gram hesabı değerlerini, gram/dolar fiyatlarını ve gram bazlı konsensüs raporlarını gösterecek şekilde güncellenmesi.
  - *DoD:* Telegram botunda `/durum` çağrıldığında gram hesabının bakiye, gümüş miktarı ve PNL durumunun kusursuz listelenmesi.

- `[ ]` **Faz 5: Derinlemesine Kalite Kontrol, Entegrasyon Testleri ve Canlı Dağıtım**
  - [ ] **Unit & Entegrasyon Testleri:** `test_paper_trading.py`, `test_telegram.py`, `test_auto_trader.py` dosyalarındaki ons bağımlı testlerin yeni gram kurgusuna göre adapte edilmesi.
  - [ ] **Safety Gatekeeper Analizi:** Statik analiz ve regresyon koruması kontrollerinin çalıştırılması.
  - [ ] **Canlı VPS Deploy:** Kodların `main` dala gönderilerek VPS sunucusuna `deploy.sh -y` ile kurulması ve `vps_smoke.sh` testlerinden tam başarı alınması.
  - *DoD:* Tüm pytest yerel test süitinin (150+ test) ve uzak sunucu smoke testlerinin yeşil (green) çıkması.

---

## ❓ Açık Sorular
- Alım işlemlerinde devlet adına kesilen %0.2 BSMV/Kambiyo vergisini otomatik hesaplamak üzere `execute_paper_trade` içerisinde `taxes = amount * Decimal("0.002")` formülünü uygulamak sizin için uygun mudur? [ONAYLANDI]
- Model kısıtının (UniqueConstraint) Alembic migrasyonu ile esnetilerek gelecekteki Altın (XAU) ve Platin (XPT) çoklu gösterge yapısına bugünden hazırlanması sizin için uygun mudur? [ONAYLANDI]
