# SilverPilot Codex Agent Framework

Bu dosya, SilverPilot icinde Codex ile yapilan gelistirme, inceleme, test,
commit hazirligi, push hazirligi, deploy hazirligi ve rollback planlama
islerinde kullanilacak ana Codex index dosyasidir.

> [!IMPORTANT]
> Codex icin proje kapsamli tek kaynak `.codex/` dizinidir. Codex isleri
> baslarken `.agent/` altindaki Antigravity/Gemini belgeleri otomatik olarak
> yuklenmez ve karar kaynagi yapilmaz. `.agent/` yalnizca kullanici acikca
> Antigravity framework'unu denetlemeyi veya guncellemeyi isterse okunur.

> [!WARNING]
> Bu framework, projenin runtime finansal/veri ajanlariyla (`/agents`) da
> karistirilmamalidir. `.codex/agents` kodlama ve denetim subagent'laridir;
> `/agents` ise uygulamanin calisma zamani ajan tanimlari icindir.

---

## Codex Source Of Truth

- [`.codex/README.md`](file:///Users/boe747/SilverPilot/.codex/README.md):
  Codex framework sinirlari, model routing, validation, commit/push/deploy
  onay kurallari ve dizin yapisi.
- [`.codex/workflows/codex-orchestration.md`](file:///Users/boe747/SilverPilot/.codex/workflows/codex-orchestration.md):
  Codex'e ozel agent routing, subagent kullanim karar agaci, RTK token
  tasarrufu protokolu ve model/sandbox matrisi.
- [`.codex/config.toml`](file:///Users/boe747/SilverPilot/.codex/config.toml):
  Proje kapsamli Codex ayarlari. Secret, provider auth veya uretim
  credential'i icermez.

## Codex Agents

Yeni bir Codex gorevinde uygun ajan `.codex/agents/*.toml` altindan secilir:

| Gorev alani | Codex agent | Model |
| --- | --- | --- |
| Kod tabani kesfi ve etki haritasi | `scout` | `gpt-5.4-mini` |
| Mimari sinir ve tasarim denetimi | `architect` | `gpt-5.5-pro` |
| Minimal onayli implementasyon | `implementation_worker` | `gpt-5.5` |
| Hata ayiklama ve kok neden | `troubleshooter` | `gpt-5.5` |
| DB, SQLAlchemy, Alembic inceleme | `db_investigator` | `gpt-5.4-mini` |
| Test stratejisi | `test_strategist` | `gpt-5.5` |
| Test ve smoke dogrulama | `test_verifier` | `gpt-5.4-mini` |
| Git scope, secret ve commit/push guvenligi | `git_guardian` | `gpt-5.4-mini` |
| CI/CD hata inceleme | `ci_investigator` | `gpt-5.5` |
| Deploy hazirlik denetimi | `deploy_guardian` | `gpt-5.5` |
| Deploy sonrasi izleme | `post_deploy_monitor` | `gpt-5.4-mini` |
| Rollback planlama | `rollback_planner` | `gpt-5.5` |
| Guvenlik denetimi | `security_reviewer` | `gpt-5.5-pro` |
| Final release denetimi | `final_reviewer` | `gpt-5.5-pro` |

Model bulunamazsa ayni roldeki en yakin model kullanilir: okuma ve
dogrulama icin mini, implementasyon ve planlama icin standard, guvenlik ve
final review icin en guclu mevcut model.

## Codex Skills

Teknik kurallar `.codex/skills/<skill-name>/SKILL.md` altindadir. En sik
kullanilan paketler:

- `.codex/skills/fastapi-sqlalchemy/SKILL.md`
- `.codex/skills/alembic-migrations/SKILL.md`
- `.codex/skills/pytest-fastapi/SKILL.md`
- `.codex/skills/integration-testing/SKILL.md`
- `.codex/skills/docker-compose-ops/SKILL.md`
- `.codex/skills/deployment-safety/SKILL.md`
- `.codex/skills/git-safe-operations/SKILL.md`
- `.codex/skills/github-actions-monitoring/SKILL.md`
- `.codex/skills/financial-agent-runtime/SKILL.md`
- `.codex/skills/financial-risk-regression/SKILL.md`
- `.codex/skills/streamlit-dashboard/SKILL.md`

## Installed Plugin Layer

SilverPilot, yerel `.codex` framework'unun uzerine kurulu onayli bir plugin
katmani da kullanir. Bu katman su anda `claude-code-workflows` marketplace
uzerinden yuklenmis su pluginlerle sinirlidir:

- `developer-essentials`
- `backend-development`
- `agent-orchestration`
- `comprehensive-review`
- `database-migrations`
- `deployment-validation`
- `security-scanning`
- `unit-testing`
- `debugging-toolkit`
- `context-management`

Bu pluginler karar otoritesi degil, hizlandirici katmandir:

- Repo policy, approval gate ve risk sinirlari icin `.codex/` kanoniktir.
- Tekrarlayan coding akislari icin once uygun plugin komutu tercih edilir.
- Plugin onerisi `.codex` kurallariyla celisirse `.codex` kazanir.

Baslangic mapping:

- Backend feature veya servis degisikligi: `backend-development`
- Hata ayiklama ve belirsiz regression: `debugging-toolkit`
- Test uretimi veya kapsam artisi: `unit-testing`
- Cok yonlu review: `comprehensive-review`
- Migration ve schema isi: `database-migrations`
- Deploy oncesi kontrol: `deployment-validation`
- Guvenlik taramasi: `security-scanning`
- Orkestrasyon tuning ve task decomposition: `agent-orchestration`

## Codex Workflows

- `.codex/workflows/codex-orchestration.md`: ana Codex orkestrasyon ve RTK
  protokolu.
- `.codex/workflows/aggressive-validation.md`: lokal dogrulama seviyeleri.
- `.codex/workflows/commit-readiness.md`: commit oncesi kapsam ve secret gate.
- `.codex/workflows/push-readiness.md`: push oncesi branch/upstream/CI gate.
- `.codex/workflows/deploy-readiness.md`: deploy oncesi Docker, env, DB,
  model/data ve rollback gate.
- `.codex/workflows/post-deploy-verification.md`: deploy sonrasi PASS/FAIL/UNKNOWN
  dogrulama.
- `.codex/workflows/ci-cd-failure-investigation.md`: GitHub Actions hata
  inceleme.
- `.codex/workflows/rollback-response.md`: rollback onerisi ve onay gerektiren
  komutlar.
- `.codex/workflows/release-gate.md`: release kapanis denetimi.

## RTK Token Economy

Codex, token tasarrufu icin RTK protokolunu uygular:

1. Once `rg` veya `rg --files` ile hedef dosya ve sembol bulunur.
2. Buyuk dosya komple okunmaz; `sed -n 'start,endp'` veya esdeger hedefli
   satir okuma kullanilir.
3. Genis arama veya cok dosyali haritalama gerekiyorsa `scout` gibi read-only
   subagent kullanilir ve ana konusmaya yalnizca bulgu ozeti tasinir.
4. Ayni dosya tekrar tekrar okunmaz; onceki bulgular yeniden kullanilir.

## Markdown Butcesi

- Yeni markdown dosyasi olusturmak istisnadir.
- Var olan kanonik belge guncellenebiliyorsa yeni belge acilmaz.
- Ayni gercegi birden fazla markdown dosyasina dagitmak yasaktir.

## Yeni Gorev Protokolu

1. Talebin kapsamini belirle.
2. `.codex/workflows/codex-orchestration.md` uzerinden gorev tipi, ajan,
   model, sandbox ve dogrulama seviyesini sec.
   Uygun installed plugin varsa ayni adimda once onu tercih et.
3. Gorev dogrudan riskli degilse varsayilan recipe uygula:
   kucuk islerde ana context veya `implementation_worker`, belirsiz veya
   cok dosyali islerde once `scout`, hata ayiklamada `troubleshooter`,
   tasarim/refactor kararlarinda `architect`.
4. Spawn karari verirken minimum uzman sayisini kullan:
   normal gorevde en fazla 2 paralel specialist, toplamda en fazla 4 rol.
   Kucuk islerde 0-1 specialist tercih edilir.
5. Tek bir write owner tut:
   ayni anda yalnizca ana context, `implementation_worker`, veya
   `troubleshooter` yazma sahibi olabilir.
6. `scout` kesif icin, `db_investigator` schema/migration icin,
   `test_strategist` genis test tasarimi icin, `test_verifier`
   dogrulama icin, `security_reviewer` auth/secret/CI riskleri icin
   spawn edilir.
7. Kullanici commit/push/deploy/release istemedikce gate ajanlari
   (`git_guardian`, `deploy_guardian`, `final_reviewer`, `rollback_planner`)
   otomatik acilmaz.
8. Gerekli `.codex/skills/*/SKILL.md` paketlerini yukle.
   Plugin komutu kullanildiysa, buna ek olarak SilverPilot skill paketleriyle
   yerel kural ve verification gate'lerini tamamla.
9. Kod degisikligi yapmadan once hedef dosyalari ve beklenen etki alanini
   bildir.
10. Implementasyonu kucuk, geri alinabilir ve testlenebilir tut.
11. Degisiklikten sonra ilgili `.codex/scripts/verify-*.sh` veya hedefli test
   komutlariyla kanit uret.
12. Oturumda acik release onayi varsa dogrulama gectikten sonra commit, push ve
   deploy zincirini duraksamadan tamamla.
13. `git add`, `git commit`, `git push`, deploy, rollback ve production/staging
   erisimleri icin acik kullanici onayi olmadan islem yapma.

## Legacy Boundary

`.agent/` dizini bu Codex framework'unun kaynagi degildir. Eski
Antigravity/Gemini talimatlariyla `.codex` talimatlari celisirse, Codex ile
yurutulen islerde `.codex` kurallari gecerlidir.
