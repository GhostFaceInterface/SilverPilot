# Systematic Debugging Skill

## 1. Purpose
Establishes the absolute playbook for investigating, reproducing, and fixing bugs, test failures, or unexpected behaviors in the SilverPilot project. Prevents random guess-and-check fixing and protects code quality.

## 2. Rules
- **The Iron Law:** Never attempt any code fix or modification before establishing the exact root cause of the error. Symptom-level patching is strictly forbidden.
- **Isolate First:** For multi-component failures (e.g., FastAPI calling DB, docker orchestration, external API parser), isolate the failing layer first using diagnostic instrumentation before proposing fixes.
- **Zero Secrets:** Never print, log, or leak environment secrets, password parameters, or production API keys during debugging.

## 3. Recommended Patterns
1. **Read Stack Traces Fully:** Examine every line of tracebacks, starting from the source error at the bottom and tracing up to the API/app layer. Note line numbers and variable states.
2. **Consistent Reproduction:** Define a minimal reproduction command (e.g., a single pytest command or specific API curl) that triggers the failure 100% of the time.
3. **The 5 Whys Trace:**
   - *Why 1:* The endpoint returned a 500 status.
   - *Why 2:* Because the service attempted to divide cash by total silver value, which was zero.
   - *Why 3:* Because the latest price snapshot had a null close value.
   - *Why 4:* Because the Stooq API returned a null close due to weekend maintenance.
   - *Why 5 (Root Cause):* The price parser lacked a null-value filter to skip incomplete price feeds.
4. **Log boundaries:** Print incoming arguments and outgoing results when tracing calls across boundaries.

## 4. Anti-Patterns
- **Guess-and-Check Fixing:** Making random changes to lines of code in the hope that a test might pass.
- **Ignoring Warnings:** Glossing over deprecation notices or database driver warnings that often predict immediate runtime errors.
- **Swallowing Exceptions:** Catching broad `Exception` scopes without logging traceback context or re-raising the failure.

## 5. Checklist
- [ ] Has the exact line of code causing the crash been identified?
- [ ] Can the bug be reproduced consistently with a single command?
- [ ] Did you trace the 5 Whys back to the fundamental root cause?
- [ ] Is the proposed fix minimal, target-specific, and safe from side-effects?
- [ ] Is there an automated test defined to prevent future regression?

## 6. Example Guidance
When a test like `test_create_paper_trade` fails with a `NotNullViolation` database error:
1. **Analyze error:** The traceback shows `models/paper_trade.py:L45` attempting to insert a row where `risk_decision_id` is null, violating database constraints.
2. **Trace data flow:** Check the incoming payload schema and default factory values.
3. **Run 5 Whys:**
   - Why 1: Database threw a not-null constraint error on `risk_decision_id`.
   - Why 2: Because the mock data did not populate the risk decision parameter.
   - Why 3: Because the test fixture was written before Phase 4.1 rules required a risk decision row for every trade.
   - Why 4 (Root Cause): Legacy test fixtures were not updated to match the new DB model integrity requirements.
4. **Fix:** Update legacy test fixtures to include a dummy risk decision relationship, avoiding any modifications to production database models.
