# AI Coding Agent Framework (AGENTS.md)

Bu dosya, SilverPilot projesinde kod geliştirme ve planlama aşamalarında kullanılan **AI Coding Agent Framework** yapısının ana index noktasıdır.

> [!WARNING]
> **Kritik Mimari Ayrımı:** 
> Bu dizin yapısı, projenin kendi runtime (çalışma zamanı) finansal/veri ajanları ile (`agents/` klasörü altındaki `news-agent.md`, `risk-agent.md` vb.) **kesinlikle karıştırılmamalıdır.** 
> Bu yapı, yalnızca geliştiriciye (AI kodlama asistanına) güvenli, planlı ve yüksek standartlarda kod yazması için kılavuzluk eder.

---

## 📂 Framework Yapısı

### 1. Global Davranış Kuralları (Governance)
- **[.agent/GEMINI.md](file:///Users/boe747/SilverPilot/.agent/GEMINI.md)**
  - AI asistanının projedeki temel TIER 0 anayasasıdır. Kod yazmaya başlamadan önce aşılması gereken **Socratic Gate** (Anlamadan kod yazmama), araç kullanımı ve değişiklik güvenliği kurallarını belirler.

### 2. Uzman Kodlama Ajanları (Coding Agents)
Yeni bir kodlama görevinde asistan önce uygun ajan kimliğini yüklemelidir:
- **[project-planner.md](file:///Users/boe747/SilverPilot/.agent/agents/project-planner.md):** Kod yazmaz. Görevleri zorunlu olarak küçük, uygulanabilir Fazlara (Phases) böler.
- **[scout-agent.md](file:///Users/boe747/SilverPilot/.agent/agents/scout-agent.md):** Okuma-amaçlı keşif ajanı. Kod tabanını tarar ve etki alanı/bağımlılık haritası çıkarır.
- **[backend-architect.md](file:///Users/boe747/SilverPilot/.agent/agents/backend-architect.md):** Python, FastAPI, SQLAlchemy ve database tasarımı uzmanıdır.
- **[data-engineer.md](file:///Users/boe747/SilverPilot/.agent/agents/data-engineer.md):** Veri toplayıcılar (collectors), pipeline akışları ve risk simülasyon hesaplamaları uzmanıdır.
- **[debugger-agent.md](file:///Users/boe747/SilverPilot/.agent/agents/debugger-agent.md):** Sistematik hata ayıklayıcı. 5 Neden analizi yaparak kök neden tespiti yapar.
- **[security-auditor.md](file:///Users/boe747/SilverPilot/.agent/agents/security-auditor.md):** OWASP 2025 güvenlik denetçisi. Sızıntı testi ve API güvenlik uzmanı.
- **[archaeologist-agent.md](file:///Users/boe747/SilverPilot/.agent/agents/archaeologist-agent.md):** Refactor uzmanı. Kodu bozmadan "Strangler Fig" ile eski yapıları yeniler.
- **[frontend-architect.md](file:///Users/boe747/SilverPilot/.agent/agents/frontend-architect.md):** Streamlit ve Python tabanlı modern dashboard / UI/UX mimarıdır.
- **[quality-engineer.md](file:///Users/boe747/SilverPilot/.agent/agents/quality-engineer.md):** Pytest testleri, Docker Compose ve CI/CD doğrulaması uzmanıdır.
- **[safety-gatekeeper.md](file:///Users/boe747/SilverPilot/.agent/agents/safety-gatekeeper.md):** Güvenlik geçidi ve regresyon koruyucu. Kodlar çalıştırılmadan önce derin statik analiz ve test gerçekçiliği denetimi yapar.


### 3. Teknik Beceriler & Standartlar (Skills)
Ajanların uymak zorunda olduğu teknik kurallar:
- **[general-coding.md](file:///Users/boe747/SilverPilot/.agent/skills/general-coding.md):** Python clean code, SOLID, DRY ve sır güvenliği.
- **[fastapi.md](file:///Users/boe747/SilverPilot/.agent/skills/fastapi.md):** FastAPI router yapısı, DI, Pydantic şemaları.
- **[sqlalchemy-alembic.md](file:///Users/boe747/SilverPilot/.agent/skills/sqlalchemy-alembic.md):** N+1 sorgu engelleme, index tasarımı ve Alembic kuralları.
- **[security-rules.md](file:///Users/boe747/SilverPilot/.agent/skills/security-rules.md):** API güvenliği, yetkilendirme, OWASP 2025 ve zero-trust.

### 4. İş Akışları & Orkestrasyon (Workflows)
- **[orchestrate.md](file:///Users/boe747/SilverPilot/.agent/workflows/orchestrate.md)**
  - Büyük ve çok dosyalı iş geliştirme adımlarında ajanların sequential (sıralı) olarak nasıl orkestre edileceğini tanımlar.
- **[plan.md](file:///Users/boe747/SilverPilot/.agent/workflows/plan.md)**
  - Görev fazlandırma, PLAN.md şablonu, kullanıcı onayı (Socratic Gate) ve faz takibi süreçlerini standartlaştıran planlama anayasasıdır.
- **[brainstorm.md](file:///Users/boe747/SilverPilot/.agent/workflows/brainstorm.md)**
  - Yeni bir özelliğin geliştirilmesi veya mimari kararlar öncesinde farklı çözüm yollarını (en az 3 seçenek) yapılandırılmış şekilde beyin fırtınası yaparak değerlendirir.
- **[remember.md](file:///Users/boe747/SilverPilot/.agent/workflows/remember.md)**
  - Kritik eşikler aşıldığında veya önemli kararlar alındığında öğrenimlerin ve bilgilerin kalıcı belleğe (.agent/memory/) kaydedilmesini sağlar.

---

## 🚀 Yeni Görev Protokolü
Yeni bir geliştirme talebi geldiğinde AI asistanı:
1. Talebin kapsamını analiz eder ve [GEMINI.md](file:///Users/boe747/SilverPilot/.agent/GEMINI.md) kuralını yükler.
2. Göreve en uygun uzman ajanları belirler ve yönlendirme yapar.
3. Planlama gerekiyorsa `project-planner` ile `PLAN.md` çıkarıp kullanıcı onayı almadan kod yazmaya başlamaz.
