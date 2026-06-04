# Release Gates

## Commit gate
- Git diff reviewed.
- Secrets and generated artifacts checked.
- Applicable validation levels complete.
- User approves commit command.

## Push gate
- Branch/upstream state understood.
- Working tree clean after commit.
- Local verification complete.
- CI expectations known.
- User approves push command.

## Deploy gate
- Target environment identified.
- Docker/config/migration/model/data assumptions verified.
- Rollback plan exists.
- Security review complete.
- User approves deployment command.

## Release gate
- Validation levels required by change are satisfied.
- CI is green or failures are explained and accepted.
- Post-deploy verification plan exists.
- Known risks documented.
- Final reviewer approves.
