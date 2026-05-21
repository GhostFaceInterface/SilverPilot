---
description: Standardized project planning, task decomposition, and user approval protocol. Standardizes phase division, Socratic Gate validation, and token economy.
---

# /plan - Project Planning & Task Decomposition

$ARGUMENTS

---

## 1. Purpose
Bu iş akışı (workflow), SilverPilot projesinde yeni bir özellik ekleme, hata ayıklama veya refactoring işlemlerinde izlenecek adımları, fazlandırma kurallarını ve kullanıcı onay mekanizmalarını standartlaştırmak amacıyla tanımlanmıştır. `project-planner` ajanı bu iş akışının ana yürütücüsüdür.

---

## 2. Rules & Steps (Adım Adım Planlama Süreci)

### Adım 1: Keşif ve Etki Alanı Tespiti (Scouting)
- **Mükerrer Keşif Yasağı (No Redundant Scouting):** Eğer kullanıcı görev açıklamasında veya konuşma bağlamında gerekli keşif sonuçlarını, dosya yollarını ve arka planı zaten sağlamışsa, bağımsız bir keşif ajanı (`scout-agent`) tetiklemeyin ve sıfırdan arama yapmayın. Doğrudan kullanıcının sağladığı bağlam üzerinden planlama adımına geçin. Güçlü modelle (Pro) çalışırken gereksiz arama yapmak büyük oranda token israfına yol açar.
- Eğer kullanıcının vermediği, doğrulanması zorunlu kritik bir dosya varsa, sadece o dosyayı hedefleyerek okuyun (Adım 3'teki RTK kurallarına uyun).
- Değişiklik yapılacak alanların finansal risk boyutunu ölçmek için **[docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md)** ve veri bütünlüğü için **[docs/DATA_CONTRACTS.md](file:///Users/boe747/SilverPilot/docs/DATA_CONTRACTS.md)** dosyalarını inceleyin.

### Adım 2: Zorunlu Fazlandırma ve PLAN.md Hazırlığı
- Büyük veya çok dosyalı işleri, ucuz modellerin (Gemini 3.5 Flash gibi) hata payını sıfıra indirmek için olabildiğince küçük, bağımsız ve ardışık **Fazlara (Phases)** bölün.
- Proje kök dizininde bir **`PLAN.md`** dosyası oluşturun (veya mevcut olanı güncelleyin). Plan taslağını aşağıdaki şablon standartlarına uygun şekilde hazırlayın.

### Adım 3: Socratic Gate (Kullanıcı Onayı Kapısı)
- **Kritik Kural:** Planı hazırladıktan sonra **TEK BİR SATIR BİLE KOD YAZMAYIN VEYA DEĞİŞTİRMEYİN.**
- Hazırlanan planı sohbette kullanıcıya sunun. Varsa açık soruları, mimari ikilemleri veya riskleri GitHub Alert (`> [!IMPORTANT]`) formatında vurgulayın.
- Kullanıcıdan açıkça yazılı **"onaylıyorum"** veya benzeri bir onay gelene kadar bekleyin.

### Adım 4: Canlı İlerleme Takibi (Living Checklist)
- Kullanıcı onayından sonra uygulama aşamasına geçin.
- Aktif olarak üzerinde çalışmaya başladığınız fazı `PLAN.md` dosyasında `[/]` (devam ediyor) olarak işaretleyin.
- Tamamlanan adımları `[x]` (tamamlandı) olarak işaretleyin.
- Bir fazın doğrulama testleri başarıyla geçmeden asla bir sonraki faza geçmeyin.

### Adım 5: Kapanış, Test ve Otomatik Git İşlemleri
- Tüm fazlar bittiğinde `quality-engineer` testlerini çalıştırın.
- `safety-gatekeeper` ajanı ile son pre-execution static analiz incelemesini yapın.
- Her şey yeşil (green) ise, `PLAN.md` dosyasını silin veya "Tamamlandı" durumuna getirip değişiklikleri otomatik git commit ve git push politikasına (orchestrate.md) göre uzak sunucuya gönderin.

---

## 3. Token Economy & RTK (Read Target Keylines) Protocol (Token Tasarrufu ve RTK Protokolü)
Güçlü modellerin (Gemini 3.5 Pro) planlama veya analiz aşamalarında gereksiz yere yüksek miktarda token tüketmesini önlemek için şu kurallara uymak zorunludur:

- **RTK (Read Target Keylines - Hedef Satır Aralığı Okuma):** Bir kod dosyasını kontrol etmeniz veya incelemeniz gerektiğinde, dosyayı asla tamamen okumayın (`view_file` aracında satır sınırı belirtmeden çağırmak büyük token kaybına sebep olur). Her zaman `StartLine` ve `EndLine` belirterek sadece ilgili satır aralığını/fonksiyonları okuyun.
- **Alt Ajan Bağlam Ayrımı (Subagent Context Isolation):** Büyük arama veya tarama işlemleri kaçınılmaz ise, bu işlemleri ana konuşmanın bağlam limitini doldurmamak için izole `scout-subagent` ile çalıştırıp sadece neticelerini ana konuşmaya aktarın.
- **Gereksiz Dosya Okuma Yasağı:** Yalnızca plan kapsamına giren ve etki alanında olan dosyaları okuyun. Projenin bağımsız kısımlarını okumaktan kaçının.

---

## 4. PLAN.md Standart Şablonu (Template)

Plan oluştururken her zaman aşağıdaki markdown şablonunu kullanın:

```markdown
# Implementation Plan: [Özellik/Görev Adı]

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:** [docs/RISK_POLICY.md içindeki ilgili kurallar]
- **Etkilenen Şemalar:** [models/ veya veri tabanı tabloları]

## 🛠️ Fazlar ve Görev Listesi

- `[ ]` **Faz 1: [Altyapı / Veri Tabanı / Şema Hazırlığı]**
  - [ ] `models/` veya `schemas/` üzerinde değişiklik yapılması (Ajan: `backend-architect`)
  - [ ] Alembic migrasyonunun oluşturulması ve test edilmesi
  - *DoD (Tamamlanma Tanımı):* `pytest tests/test_models.py` komutunun hatasız çalışması.

- `[ ]` **Faz 2: [Çekirdek İş Mantığı / Servis Katmanı]**
  - [ ] Servis fonksiyonlarının yazılması / güncellenmesi (Ajan: `backend-architect` / `data-engineer`)
  - *DoD:* Servis unit testlerinin yeşil olması.

- `[ ]` **Faz 3: [API / Router ve Entegrasyon Katmanı]**
  - [ ] FastAPI router uç noktalarının yazılması
  - *DoD:* `GET /risk/status` veya ilgili uç noktanın 200 OK dönmesi.

- `[ ]` **Faz 4: [Kalite Kontrol ve Doğrulama]**
  - [ ] Uçtan uca (E2E) entegrasyon testlerinin yazılması (Ajan: `quality-engineer`)
  - [ ] `safety-gatekeeper` statik analizi ve onayı
  - *DoD:* Tüm pytest test süitinin başarıyla tamamlanması.

## ❓ Açık Sorular (Varsa)
> [!IMPORTANT]
> - Sorulan kritik mimari soru veya parametre detayı?
```

---

## 5. Anti-Patterns (Kaçınılması Gereken Hatalar)
- **Onay Almadan Kodlama:** Kullanıcı onay vermeden gizlice backend kodu yazmaya veya dosya değiştirmeye başlamak.
- **Devasa Fazlar:** Tek bir faza 5 farklı dosyanın değiştirilmesi, test edilmesi ve entegrasyonu gibi büyük işler yığmak. Fazları her zaman atomik tutun.
- **DoD (Tamamlanma Tanımı) Eksikliği:** Bir fazın bittiğini kanıtlayacak somut bir test komutunun veya çıktının plana yazılmaması.
- **Whole-File Bleeding:** `view_file` aracını kullanırken hedef satır aralıkları belirlemek yerine, tüm dosyayı okuyarak bağlamı (context) lüzumsuz doldurmak.
