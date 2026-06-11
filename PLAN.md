# SilverPilot Sağlamlaştırma ve Teşhis Planı

  ## Özet

  - Canlı kanıt: signals=1040; baskın sorunlar HOLD/BLENDED_NEUTRAL=658 ve HOLD/DAILY_TREND_MISSING=249. Son 100 sinyal çoğunlukla DAILY_TREND_MISSING.
  - Ana kök neden: 1d indicator input_bar_count canlı DB’de 7-8 seviyesinde, kod ise 50 bar istiyor. Sistem trade fırsatı kaçırmaktan çok “günlük trend datası hazır değil”
    durumunda takılıyor.

  - İlk tercih edilen duruş: diagnostik mod, strategy_v2 default registry, backfill + strict gate. Paper BUY/SELL geçici olarak durur; karar/audit çalışır, tekrarlı HOLD
    Telegram bastırılır.

  ## Key Changes

  - auto_trader akışı DecisionEnvelope üretmeli: requested_strategy, resolved_strategy, candidate_action, final_action, reason_code, readiness, risk_preflight, agent_inputs,
    notification_policy, trade_id.

  - Yeni ayarlar:
      - AUTO_TRADING_MODE=diagnostic|paper, ilk değer diagnostic.
      - NOTIFICATION_POLICY_V2=true.
      - HOLD_NOTIFICATION_COOLDOWN_MINUTES=360.
      - DECISION_ENVELOPE_SHADOW=false çünkü envelope doğrudan ana audit formatı olacak.

  - Diagnostik modda BUY/SELL trade intent üretmez; yalnızca sinyal/audit yazar. HOLD Telegram sadece reason değişirse veya cooldown dolarsa gider.
  - Strategy registry eklenecek: strategy_v2 default, eski rsi/sma_cross/bollinger/blended live’da ancak açık registry seçimiyle kullanılacak. Bilinmeyen strategy
    BLOCKED_CONFIG_INVALID üretir.

  - 1d indicator problemi eşik düşürülerek çözülmeyecek. İdempotent backfill komutu üretilecek; raw/snapshot veriden 1d market bars ve indicators tamamlanacak, 50 bar kuralı
    korunacak.

  ## DB ve Veri Sözleşmesi

  - İlk DB değişiklikleri expand-only olacak: kolon/tablo ekle, veri silme/drop yok.
  - decision_audits veya mevcut signals.details_json içinde standard envelope saklanacak; kısa vadede tablo eklemek zorunlu değilse signals ile başlanacak.
  - Unit contract netleştirilecek: XAG ve XAG_GRAM dönüşümü tek conversion policy üzerinden yapılacak; 31.1035 collector içinde hardcoded kalmayacak.
  - close_usd_oz hemen rename edilmeyecek; uyumluluk için close_price, price_unit, quote_currency schema/property alanları eklenecek.
  - Canlı DB için mutasyon öncesi read-only doğrulama zorunlu: alembic head, latest indicator counts, stale source counts, failed collector error summary.

  ## Uygulama Sırası

  1. Diagnostik mod ve notification policy: HOLD spam durur, BUY/SELL execution kapanır, audit devam eder.
  2. Decision envelope: her kararın nedeni ve hangi gate’te takıldığı görünür olur.
  3. Indicator backfill: 1d bar/indicator geçmişi tamamlanır; DAILY_TREND_MISSING çözülür.
  4. Strategy registry: config gerçekten canlı kararı belirler, strategy_v2 default kalır.
  5. Risk preflight: trade olmasa bile stale data, ML veto, spread, source ve market-closed nedenleri audit edilir.
  6. Unit/provider refactor: conversion policy ve source/provider normalization başlar.
  7. SaaS hazırlığı: providers, strategy configs, notification preferences; users/accounts daha sonraki faz.

  ## Test Planı

  - test_notification_policy_hold_dedupes
  - test_diagnostic_mode_does_not_execute_buy_or_sell
  - test_decision_envelope_records_readiness_reason
  - test_live_strategy_uses_v2_registry_default
  - test_unknown_strategy_blocks_without_trade
  - test_indicator_backfill_creates_1d_minimum_history
  - test_daily_trend_missing_resolves_after_backfill
  - test_xag_to_gram_conversion_uses_policy
  - Targeted run: cd apps/api && python -m pytest tests/test_auto_trader.py tests/test_indicator_readiness.py tests/test_indicators.py tests/test_trade_intents.py

  ## Acceptance Criteria

  - Aynı HOLD reason’ı cooldown içinde Telegram mesajı üretmez.
  - Diagnostik modda paper_trades artmaz; signals/audit artar.
  - Backfill sonrası latest 1d indicator input_bar_count >= 50.
  - DAILY_TREND_MISSING yeni sinyallerde baskın reason olmaktan çıkar.
  - BUY/SELL sadece AUTO_TRADING_MODE=paper ve gerçek risk allow sonucuyla trade üretir.
  - Hiçbir LLM/agent HOLD’u BUY’a yükseltmez; yalnızca veto/advisory etkisi vardır.
  - Production DB migration/deploy öncesi ayrıca açık onay gerekir.