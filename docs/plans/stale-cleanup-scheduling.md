# Stale Claim Cleanup — Scheduling (Pending)

## What

`backend/scripts/abandon_stale.py` marks `in_progress` claims as `abandoned` when they
haven't been updated in `DEJASHIP_ABANDONMENT_DAYS` days (default: 7). It works correctly
but must be run externally — nothing schedules it yet.

## Options

### Option A — GitHub Actions cron (recommended)

Add a scheduled workflow that SSHs into the host and runs the script via docker exec.
Simple, no new infrastructure, visible in the CI dashboard.

```yaml
# .github/workflows/stale-cleanup.yml
on:
  schedule:
    - cron: "0 3 * * *"   # 03:00 UTC daily
jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - name: Run abandon_stale
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_KEY }}
          script: |
            docker exec dejaship-backend-1 \
              uv run python scripts/abandon_stale.py
```

Requires: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY` GitHub secrets.

### Option B — Host crontab

On the Docker host, add to crontab:

```
0 3 * * * docker exec dejaship-backend-1 uv run python scripts/abandon_stale.py >> /var/log/dejaship-stale.log 2>&1
```

No GitHub secrets needed. Harder to observe/audit.

### Option C — Sidecar container with supercronic

Add a `scheduler` service to `docker-compose.yml` using
[`supercronic`](https://github.com/aptible/supercronic) that shares the backend image and
runs the script on a schedule. Most self-contained, no external dependencies.

## Recommendation

**Option A** (GitHub Actions cron) — keeps scheduling visible alongside CI, uses existing
infrastructure, easy to manually trigger for testing (`workflow_dispatch`).

## Impact of Not Scheduling

Without scheduling, stale claims accumulate. They:
- inflate `in_progress` density counts (false crowding signal for agents)
- are not automatically resolved even if `ABANDONMENT_DAYS` is set

The impact grows slowly — only affects density reads, not claim/update correctness.
Safe to defer briefly but should be in place before significant agent adoption.
