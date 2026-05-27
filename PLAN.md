# Implementation Plan: DeepSeek-Based Hermes Agent & Advanced News Sentiment Analysis (REVISED v4)

Bu revize edilmiş plan, SilverPilot sistemine küresel ve yerel düzeyde **sadece kurumsal, profesyonel ve prestijli** ekonomi/finans kaynaklarından gelen verileri tarayan, spekülasyon ve alaka filtreleri uygulayan, ağırlıklı bir konsensüs skoru üreten ve bu skoru otomatik veto mekanizmasına ("Yüce Hakem") aktaran DeepSeek tabanlı **Hermes Agent** yapısının entegrasyonunu hedefler.

Kullanıcı yönlendirmesi ve saptamaları doğrultusunda, **tüm bireysel yatırımcı yorumları, forumlar, investing.com tartışmaları ve crowd-sourced (halk tabanlı) spekülatif kaynaklar mimariden ve plandan TAMAMEN ÇIKARILMIŞTIR.** Sistemin profesyonel yapısına uygun olarak, sadece dünya çapında ve Türkiye'de saygınlığı tartışmasız olan, verileri stabil RSS veya API kanallarından sorunsuz alınabilen **kurumsal referans kaynakları** entegre edilecektir.

---

## 🔍 Nihai Kurumsal & Profesyonel Haber Kaynakları
Veri toplama skili (Python Ingestion Skill) tarafından taranacak ve IP engeli vb. sorunlar yaratmayan, dünya çapında/yerel düzeyde saygın kaynaklar şunlardır:

### 1. Küresel Kurumsal Referanslar (Global Institutional Sources)
- **Kitco Metals (kitco.com) [Küresel Kıymetli Madenler Otoritesi]:** Dünya kıymetli madenler piyasasının haber teknik analiz merkezidir. Profesyonel analist makaleleri ve gümüş haberleri RSS beslemesiyle çekilir.
- **Bloomberg & Reuters (Yahoo Finance API/RSS kanalları üzerinden):** Küresel emtia fiyatlamaları, merkez bankası politikaları ve makroekonomik kararlar için mutlak kurumsal referanstır.
- **LBMA (London Bullion Market Association) & Silver Institute:** Gümüş arz-talep dengesi ve kurumsal fiyatlama verileri için resmi referans raporları.

### 2. Türkiye Yerel Kurumsal Referanslar (Turkish Corporate Sources)
- **Bloomberg HT (bloomberght.com) [Türkiye Ekonomi Referansı]:** Türkiye'deki en prestijli, resmi ve profesyonel ekonomi haberciliği platformudur. Sadece makro analizler ve resmi veriler çekilir (hiçbir bireysel yorum içermez).
- **GCM Yatırım (Günlük Gümüş Raporları) [Yerel Kurumsal Analiz]:** Profesyonel araştırma departmanı tarafından hazırlanan günlük resmi teknik ve temel gümüş analiz bültenleri (spekülasyondan arınmış kurumsal veri).

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:** [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Duyarlılık tabanlı veto kuralları ve risk limitleri), [docs/DATA_CONTRACTS.md](file:///Users/boe747/SilverPilot/docs/DATA_CONTRACTS.md) (Veri bütünlüğü ve yeni haber metadata şemaları).
- **Etkilenen Dosyalar/Bileşenler:**
  - `.env` ve `.env.example` [MODIFY] -> `HERMES_VETO_THRESHOLD` ve kaynak bazlı ağırlık katsayılarının (`WEIGHT_GLOBAL_CORP=0.6` [Bloomberg/Reuters/Kitco], `WEIGHT_LOCAL_CORP=0.4` [Bloomberg HT/GCM]) eklenmesi.
  - `apps/api/app/collectors/public_sources.py` [MODIFY] -> Sadece bu kurumsal kaynakların RSS/API beslemelerini toplayan ve veritabanına kaydeden Python toplayıcıları.
  - `apps/api/app/agents/hermes.py` [NEW] -> Tek bir LLM çağrısıyla (DeepSeek v4-pro) kurumsal haber paketlerini analiz eden ve ağırlıklı sentiment skorunu hesaplayan Hermes Agent motoru.
  - `apps/api/app/services/strategy.py` [MODIFY] -> `StrategyRunner.apply_agent_filters` metodunun `.env` üzerinden okunan veto eşiğine göre güncellenmesi.

---

## 🛠️ Fazlar ve Görev Listesi

- `[ ]` **Faz 1: Python Tabanlı Kurumsal Haber Toplama Skili (Ajan: data-engineer)**
  - [ ] Gümüş için Yahoo Finance RSS (`SI=F`), Kitco Metals RSS, Bloomberg HT Ekonomi RSS ve GCM Yatırım bülten toplayıcılarını yazmak.
  - [ ] Python seviyesinde **Ön Filtreleme & Temizleme:**
    - RSS'ten gelen haberler arasından sadece gümüş ("silver", "gümüş", "xag") ve kritik makro olayları ("fed rate", "faiz", "enflasyon", "inflation") içeren girdileri kabul etmek.
    - LLM'e sadece bu temizlenmiş ve doğrudan hedefe odaklı kurumsal haber/analiz başlıklarını ve özetlerini sunmak (böylece gereksiz token tüketimi sıfırlanır).
  - *DoD (Tamamlanma Tanımı):* `pytest tests/test_collectors.py` ile kurumsal toplayıcıların Türkiye ve küresel kaynaklardan verileri hatasız çekmesi, filtrelemesi ve veritabanına kaydetmesi.

- `[ ]` **Faz 2: DeepSeek-Hermes Agent Tasarımı & Kurumsal Analiz Motoru (Ajan: backend-architect)**
  - [ ] `apps/api/app/agents/hermes.py` dosyasını oluşturmak. Bu modülde DeepSeek LLM (`deepseek-v4-pro` veya `deepseek-r1`) kullanılarak derlenmiş kurumsal paketler analiz edilecektir.
  - [ ] LLM, her haber girdisi için şu analizleri yapacaktır:
    - **Sentiment:** BULLISH (+1), BEARISH (-1), NEUTRAL (0).
    - **Relevance (0.0 - 1.0):** Gümüş piyasası ile doğrudan alaka düzeyi.
    - **Speculation (0.0 - 1.0):** clickbait, sansasyonellik veya kanıtsız iddia puanı.
  - [ ] Ağırlıklı nihai sentiment skoru formülünü kodlamak:
    $$\text{Duyarlılık Skoru} = \text{Sentiment}_{küresel\_kurumsal} \times W_{glob\_corp} + \text{Sentiment}_{yerel\_kurumsal} \times W_{local\_corp}$$
    *(Not: Her bileşen kendi içinde Spekülasyon ve Alaka filtreleriyle ağırlıklandırılacaktır.)*
  - [ ] Skoru `AgentMemoryEvent` tablosuna `hermes-agent` adıyla kaydetmek.
  - *DoD:* Hermes Agent'ın tek tek haberleri analiz ederek ağırlıklı skoru başarıyla hesaplaması.

- `[ ]` **Faz 3: Yüce Hakem Veto Entegrasyonu & .env Konfigürasyonu (Ajan: backend-architect)**
  - [ ] `.env` ve `.env.example` dosyalarına `HERMES_VETO_THRESHOLD` (Varsayılan: `-0.45`) parametresini eklemek.
  - [ ] `apps/api/app/services/strategy.py` içindeki `StrategyRunner.apply_agent_filters` metodunu güncellemek. Statik veto yerine, veritabanındaki son `hermes-agent` skorunu okup bu değer `HERMES_VETO_THRESHOLD` değerinden küçükse `BUY` sinyalini veto edip `HOLD` yapmak.
  - [ ] Sistem denetim ajanı olan `apps/api/app/agents/auditor.py` içerisindeki agent listesine `hermes-agent`'ı dahil etmek.
  - *DoD:* Strateji motorunun .env üzerinden okunan eşik değerine göre veto filtresini başarıyla uygulaması.

- `[ ]` **Faz 4: Kalite Kontrol & Simülasyon Testleri (Ajan: quality-engineer)**
  - [ ] Hermes Agent için mock kurumsal haber paketleri ile pytest test senaryoları yazmak.
  - [ ] Ağırlıklı formülün ve filtreleme mantığının matematiksel olarak doğru çalıştığını doğrulamak.
  - *DoD:* `pytest tests/test_hermes_agent.py` test süitinin %100 başarıyla tamamlanması.

---

## ❓ Açık Sorular

> [!IMPORTANT]
> 1. **Küresel / Yerel Ağırlık Dağılımı:** Varsayılan katsayıları `Küresel Kurumsal Haberler (Bloomberg/Reuters/Kitco) = %60` (`WEIGHT_GLOBAL_CORP`) ve `Yerel Kurumsal Haberler (Bloomberg HT/GCM) = %40` (`WEIGHT_LOCAL_CORP`) olarak belirledim. Bu dağılım sizin için uygun mudur?
> 2. **Varsayılan Veto Eşiği (-0.45):** Eşik değeri `.env` parametresi üzerinden dinamik olacaktır. Başlangıç eşiği olarak `-0.45` değerini onaylıyor musunuz?
