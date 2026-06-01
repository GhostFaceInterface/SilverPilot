# PLAN.md - Telegram `/karzarar` Gelişmiş PNL Entegrasyon Planı

Bu plan, kullanıcının `/cuzdan` (Cüzdan Değişim Özeti) ile `/karzarar` (Açık Pozisyon Kar/Zarar Durumu) komutları arasındaki kavramsal farkı (Açık pozisyon kapalıyken karın $0.00 görünmesi ancak cüzdanda karlı olunması) gidermeyi amaçlar. 

Mevcut `/karzarar` komutu sadece **gerçekleşmemiş (unrealized) açık pozisyon karını** göstermektedir. Bu planla `/karzarar` komutunun kapsamı genişletilerek **Gerçekleşen (Realized) Kar/Zarar** ve **Toplam (Total) Kar/Zarar** kalemleri de rapora eklenecektir.

---

## 🔍 Kavramsal Fark ve Matematiksel Model

Kullanıcı gümüş pozisyonunu tamamen kapattığında (`Açık Pozisyon: 0.0000 XAG_GRAM`):
1.  **Açık Pozisyon (Unrealized) Kar/Zarar:** `silver_qty * (mid_price - avg_buy_cost)` formülü gereği **`$0.00 USD`** olur (Çünkü adet sıfırdır).
2.  **Toplam Kar/Zarar (Total PNL):** Başlangıç bakiyesi ($2500 USD) ile anlık toplam portföy değeri (nakit bakiye + gümüş değeri) arasındaki net farktır:
    $$\text{Toplam PNL} = (\text{Nakit Bakiye} + \text{Gümüş Adedi} \times \text{Anlık Fiyat}) - 2500$$
3.  **Gerçekleşen Kar/Zarar (Realized PNL):** Toplam PNL'den Açık Pozisyon PNL'inin düşülmesiyle elde edilir:
    $$\text{Gerçekleşen PNL} = \text{Toplam PNL} - \text{Açık Pozisyon PNL}$$

Bu entegrasyon sayesinde kullanıcı, pozisyonu sıfır olsa dahi kapattığı işlemlerden elde ettiği **Gerçekleşen Karı** net bir şekilde görebilecektir.

---

## 🛠️ Fazlar ve Görev Listesi (/orchestrate Uyumlu)

### Faz 1: Stratejik Keşif ve Şema Doğrulaması (Scout)
- [x] `apps/api/app/agents/telegram_bot.py` dosyasındaki `get_karzarar_text` ve `get_cuzdan_text` fonksiyon kodları analiz edildi.
- *Ajanlar:* `scout-agent` (Tamamlandı)

### Faz 2: Backend & Telegram Arayüz Entegrasyonu (Backend Dev)
- [ ] `apps/api/app/agents/telegram_bot.py` içerisindeki `get_karzarar_text` fonksiyonunu güncelle.
  - [ ] Portföy değerini (`portfolio_value = cash_balance + silver_value`) hesapla.
  - [ ] Toplam PNL'i hesapla: `total_pnl = portfolio_value - 2500`.
  - [ ] Açık Pozisyon (unrealized) PNL'i hesapla: `silver_qty * (mid_price - avg_buy_cost)` (adet > 0 ise).
  - [ ] Gerçekleşen (realized) PNL'i hesapla: `realized_pnl = total_pnl - unrealized_pnl`.
  - [ ] Çıktı metnini premium emojilerle zenginleştirerek her üç PNL kalemi de listelenecek şekilde formatla:
    * `📊 Açık Pozisyon Kar/Zarar: +$0.00 USD`
    * `💰 Gerçekleşen Kar/Zarar: +$26.58 USD`
    * `🏆 Toplam Net Kar/Zarar: +$26.58 USD`
- *Ajanlar:* `backend-architect`
- *DoD (Tamamlanma Tanımı):* Çıktı formatının başarıyla oluşturulması ve syntax hatasız derlenmesi.

### Faz 3: Kalite Güvencesi & Pytest Entegrasyonu (Quality Dev)
- [ ] `apps/api/tests/test_telegram.py` dosyasını güncelle veya yeni test senaryoları ekle:
  - [ ] **Test Senaryosu 1 (Açık Pozisyonlu Durum):** Gümüş adedi > 0 iken hem unrealized, hem realized hem de total PNL'lerin doğru hesaplanıp metinde yer aldığını doğrula.
  - [ ] **Test Senaryosu 2 (Kapalı Pozisyonlu Durum):** Gümüş adedi = 0 iken unrealized PNL'in 0.00, realized ve total PNL'in ise cüzdan karına eşit olduğunu ve metinde doğru gösterildiğini doğrula.
- *Ajanlar:* `quality-engineer`
- *DoD:* Eklenen `/karzarar` testlerinin lokalde `%100` başarıyla geçmesi.

### Faz 4: Güvenlik Kapısı & Kod Denetimi (Safety Gate)
- [ ] `safety-gatekeeper` (Gemini 3.5 Pro) ile yazılan kodların ve test mocks yapılarının derinlemesine statik analizi.
- [ ] Sıfır soket sızıntısı (sandboxing) ve sıfır mock sapması (mock drift) güvencesi.
- *Ajanlar:* `safety-gatekeeper`
- *DoD:* `safety-gatekeeper` tarafından kodların **APPROVED** (Onaylandı) verilmesi.

### Faz 5: Doğrulama, Git Otomasyonu & Canlı Dağıtım (Deploy)
- [ ] Yerel pytest süitini (`.venv/bin/pytest`) koştur ve regresyonsuz yeşillendiğini doğrula.
- [ ] Başarılı kod değişikliklerini otomatik olarak Conventional Commits (`feat: integrate realized and total pnl calculation to telegram karzarar command`) ile commit et ve `push` yap.
- [ ] `silverpilot-vps` sunucusuna bağlanarak `./scripts/deploy.sh -y` ile canlı sistemi güncelle ve doğrula.
- *Ajanlar:* `quality-engineer`
- *DoD:* VPS smoke testlerinin yeşil tamamlanması ve Telegram botundan `/karzarar` yazıldığında güncel ekranın alınması.

---

## ❓ Kullanıcı Onayı Gerektiren Konular (Socratic Gate)

> [!IMPORTANT]
> 1. **Başlangıç Bakiyesi Varsayımı:** Portföyün realized PNL hesabı için başlangıç bakiyesini `/cuzdan` komutuyla tam uyumlu olması adına sabit **`$2500 USD`** olarak kabul ediyoruz. Bunu onaylıyor musunuz?
> 2. **Model Geçiş Protokolü:** Geliştirme adımları ve `safety-gatekeeper` paranoid kod review aşamalarında en üst düzey mantık doğruluğu sağlamak adına, plan onaylandıktan sonra modeli **Gemini 3.5 Pro** olarak değiştirmeyi onaylıyor musunuz?
