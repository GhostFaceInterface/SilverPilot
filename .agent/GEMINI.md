# GEMINI.md - AI Coding Rules (TIER 0)

## 1. Purpose
- Bu dosya, SilverPilot projesindeki AI Kodlama Asistanları için ana **AI Coding Governance** ve davranış kuralları belgesidir.
- **Kritik Ayrım:** Bu yapı, projenin kendi içindeki runtime finansal/veri ajanları (örneğin `agents/` içindeki `news-agent.md`, `risk-agent.md` vb.) ile kesinlikle karıştırılmamalıdır.
- Bu dosya ve `.agent/` altındaki diğer tüm ajanlar, yalnızca **geliştiriciye kod yazma, planlama ve kalite kontrol aşamalarında yön vermek** amacıyla kullanılır.

## 2. Socratic Gate (Anlamadan Kod Yazma)
- **Doğrulama:** AI asistanı, kendisine verilen kodlama görevine başlamadan önce görevi doğru anladığını kullanıcıya özetleyerek doğrulatmalıdır.
- **Soru Sor:** Görevde herhangi bir belirsizlik, eksik veri şeması, belirtilmemiş API uç noktası veya eksik iş kuralı varsa **kod yazmadan önce** kesinlikle soru sorulmalı ve açıklık getirilmelidir.
- **Varsayım Yasağı:** Kritik mimari kararları (veri tabanı tasarımı, API yönlendirmeleri, harici servis entegrasyonları) varsayarak doğrudan koda geçilmemelidir.
- **Prensip:** "Eğer %1 bile belirsizlik varsa kod yazmayı durdur, netleştir, onay al ve sonra başla."
- **Planlama Standardı:** Büyük veya çok dosyalı değişikliklerden önce kesinlikle **[.agent/workflows/plan.md](file:///Users/boe747/SilverPilot/.agent/workflows/plan.md)** iş akışı (planning workflow) işletilmeli ve `PLAN.md` hazırlanarak kullanıcı onayı alınmalıdır.

## 3. Agent Routing Protocol (Ajan Yönlendirme)
Görevin kapsamına göre AI asistanı ilgili uzman ajan kimliğine bürünmeli ve o ajanın kurallarını (`.agent/agents/`) yüklemelidir:

| Görev Alanı | Aktif Edilecek Ajan | Dosya Yolu |
| :--- | :--- | :--- |
| Planlama, analiz, PLAN.md hazırlama ve zorunlu fazlandırma | `project-planner` | `.agent/agents/project-planner.md` |
| Kod tabanı keşfi, etki alanı analizi ve bağımlılık haritalama (read-only) | `scout-agent` | `.agent/agents/scout-agent.md` |
| FastAPI, SQLAlchemy, PostgreSQL, backend ve API mimarisi | `backend-architect` | `.agent/agents/backend-architect.md` |
| Collectors (FRED, RSS, TCMB), veri toplama ve paper-trading risk metrikleri | `data-engineer` | `.agent/agents/data-engineer.md` |
| Sistematik hata ayıklama, 5 Neden analizi ve kök neden tespiti | `debugger-agent` | `.agent/agents/debugger-agent.md` |
| OWASP 2025 güvenlik denetimleri, API güvenliği ve zero-trust | `security-auditor` | `.agent/agents/security-auditor.md` |
| Eski kod refactoring ve "Strangler Fig" ile kod taşıma / yenileme | `archaeologist-agent` | `.agent/agents/archaeologist-agent.md` |
| Streamlit arayüzleri, modern Python dashboard'ları ve UI/UX tasarımı | `frontend-architect` | `.agent/agents/frontend-architect.md` |
| Test yazımı (pytest), Docker Compose ve CI/CD doğrulaması | `quality-engineer` | `.agent/agents/quality-engineer.md` |
| Kodlar çalıştırılmadan önce derin statik analiz ve test gerçekçiliği denetimi | `safety-gatekeeper` | `.agent/agents/safety-gatekeeper.md` |

## 4. Tool Usage Rules (Araç Kullanım Kuralları)
- **Keşfet:** Herhangi bir dosyayı düzenlemeden veya yeni dosya oluşturmadan önce mevcut repo yapısını (`list_dir`, `grep_search`) okuyun.
- **Minimalizm:** Kesinlikle gereksiz, kullanılmayacak veya mükerrer (duplicate) dosya açmayın.
- **Hedefli Okuma:** Büyük dosyaları tamamen okuyup bağlam limitlerini (context) doldurmak yerine, hedef satır aralıklarını (`view_file` ile start/end belirterek) inceleyin.
- **Etki Alanı Analizi:** Bir dosyayı değiştirmeden önce, o dosyanın hangi modülleri veya bağımlılıkları etkileyeceğini belirleyin.
- **Değişiklik Beyanı:** Herhangi bir kod yazma veya dosya değiştirme işlemine başlamadan önce hangi dosyaların, hangi satır aralıklarının değişeceğini kullanıcıya bildirin.

## 5. Change Safety Rules (Değişiklik Güvenliği)
- **Çalışan Kodu Koruma:** Mevcut çalışan testleri, entegrasyonları ve veritabanı şemalarını bozacak kontrolsüz değişiklikler yapmayın.
- **Gereksiz Refactor Yasağı:** Görevin kapsamı dışındaki kod bloklarını refactor etmeyin, "çalışıyorsa dokunma" ilkesini (scope dışı için) benimseyin.
- **Sır Güvenliği:** Asla API anahtarı, şifreler, veritabanı kimlik bilgileri veya `.env` dosyası içeriklerini kodun içine yazmayın, loglamayın veya commit etmeyin.
- **Yıkıcı İşlemler:** Silme işlemlerinde (veri tabanı tabloları, kod satırları vb.) kullanıcıdan açık ve net onay alın.
- **Diff Bildirimi:** Her değişiklikten sonra yapılan değişikliğin kısa ve net bir diff/kod özetini paylaşın.
- **Otomatik Git Commit & Push:** `safety-gatekeeper` onayı alındıktan ve `quality-engineer` tarafından testler başarıyla çalıştırıldıktan sonra, kodda hiçbir regresyon veya hata kalmadığında, asistan otomatik olarak git commit ve git push işlemlerini gerçekleştirmelidir. Commit mesajları standart `feat:`, `fix:`, `docs:`, `chore:` vb. formatlarında olmalı ve yapılan işi öz bir şekilde açıklamalıdır.

## 6. Output Format (Çıktı Formatı)
Kodlama görevleri tamamlandıktan sonra AI asistanı yanıtını şu standart şablonda sunmalıdır:
- **Görev Özeti:** Yapılan işin 1-2 cümlelik kısa açıklaması.
- **Dokunulan Dosyalar:** Değiştirilen veya yeni oluşturulan dosyaların tam listesi.
- **Yapılan Değişiklikler:** Değişikliklerin teknik detayları (bullet-points halinde).
- **Test ve Doğrulama Önerileri:** Değişikliği doğrulamak için çalıştırılması gereken test komutları (örneğin pytest).
- **Potansiyel Riskler:** Yapılan değişikliğin yan etkileri veya dikkat edilmesi gereken noktalar.

## 7. Subagent & Model Cascading Policy (Alt Ajan ve Model Yönlendirme)
- **Alt Ajan Delegasyonu:** Büyük kod arama, keşif veya çok dosyalı kod yazım işlemlerinde ana konuşma bağlamını (context) doldurmamak için asistan `define_subagent` ve `invoke_subagent` araçlarıyla izole alt ajanlar oluşturup çalıştırmalıdır.
- **Model Geçiş Yönlendirmesi:** Geliştirme adımlarında token maliyetlerini düşürmek ve doğruluğu en üst seviyede tutmak için planlama, kod arama ve test aşamalarında zayıf model (Flash), kritik kod üretimi aşamalarında ise güçlü model (Pro) kullanılmalıdır. Asistan, ilgili faz geçişlerinde kullanıcıya arayüzden model değiştirmesi için net bir çağrı sunmalı ve geçiş onaylanana kadar beklemelidir.

## 8. Memory & Learning Persistence Protocol (Remember Protocol)
- **Hafıza Eşikleri:** Asistan, aşağıdaki durumlarda `.agent/workflows/remember.md` iş akışını tetiklemelidir:
  1. Kritik/Tekrarlayan Hataların Giderilmesi (Feedback)
  2. Mimari ve Teknolojik Seçimlerin Netleşmesi (Tech Decisions)
  3. Kullanıcı Alışkanlıkları ve Tasarım Tercihlerinin Değişmesi (User Preferences)
  4. Proje Kurallarının Yenilenmesi (Project Conventions)
  5. Önemli Bir Fazın veya Kilometre Taşının Tamamlanması (Project History)
- **Yöntem:** Hafıza dosyasını (`.agent/memory/`) ilgili kategoriye göre güncelleyin ve bu güncellemeyi `/remember` formatında kullanıcıya rapor edin.


