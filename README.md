# FlyRank Capstone — Social Campaign Publisher

Takes one blog post and turns it into a scheduled, multi-platform social
campaign (Instagram 1:1 + X 16:9), published against a self-built fake
social platform (never a real account). The graded difficulty isn't
calling an API — it's a publishing system that survives duplicate
requests, network failures, rate limits, and crashed workers, with
webhook-verified status tracking.

## What it actually does

1. `POST /api/campaigns/` a blog post (title, body, url, source image).
2. The system composes a shared caption core, then a platform-specific
   caption for Instagram and for X (different length/tone/link
   behavior), and generates a correctly-sized image variant for each
   (1080×1080, 1600×900) via a center-crop pipeline.
3. Both platform posts get scheduled with a deterministic idempotency
   key. A Celery Beat poller claims due posts atomically every 15s and
   dispatches them for publishing.
4. Publishing goes through a `SocialPublisher` interface — the app never
   knows which concrete platform it's talking to. Every publish call
   honors 429/`Retry-After`, retries transient failures with backoff, and
   is safe to call twice with the same idempotency key.
5. The fake platform accepts the post, then asynchronously fires a
   signature-verified webhook back. Campaign status only moves to
   `published` after that signature is verified — a forged webhook is
   rejected with 400 and never touches state.
6. A worker that crashes mid-publish doesn't lose the post or duplicate
   it — a stale-claim reclaim mechanism picks it back up on the next poll.

## Architecture

```
                         POST /api/campaigns/
                                 |
                                 v
                        +-----------------+
                        |    campaigns    |  DRF API surface, BlogPost + Campaign
                        +-----------------+
                                 |
                 +---------------+---------------+
                 v                                v
        +-----------------+              +-------------------+
        | content_pipeline |              |     scheduling     |
        | caption composer |              | ScheduledPost model |
        | image variants   |              | Beat poller + tasks |
        +-----------------+              +-------------------+
                                                    |
                                     atomic claim + idempotency key
                                                    v
                                          +-------------------+
                                          |     publishing     |
                                          | SocialPublisher ABC |
                                          | FakeInstagramPublisher
                                          | FakeXPublisher      |
                                          | PlatformToken (AESGCM)
                                          +-------------------+
                                                    |
                                        real HTTP, never a function call
                                                    v
                                          +-------------------+
                                          |   fake_platform    |
                                          | OAuth / publish /   |
                                          | simulated 429/timeout|
                                          | async signed webhook |
                                          +-------------------+
                                                    |
                                     signed X-Hub-Signature-256
                                                    v
                                          +-------------------+
                                          |      webhooks       |
                                          | HMAC verification    |
                                          | updates ScheduledPost |
                                          | only if signature OK |
                                          +-------------------+
```

Six Django apps, each owning one layer. `publishing/adapters.py` is the
only code in the project that knows `fake_platform`'s HTTP contract
(documented in `FAKE_PLATFORM_CONTRACT.md`) — everything upstream depends
only on the `SocialPublisher` interface.

See `DESIGN.md` for the full data model and the reasoning behind key
decisions (why `Campaign.status` is derived, why claiming uses an atomic
`UPDATE` instead of `SELECT FOR UPDATE`, etc).

## Setup (clean machine)

```bash
git clone <this repo>
cd flyrank-capstone-social-studio
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Generate real values for `.env` (copy `.env.example`, fill in real values):
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
python -c "import secrets; print(secrets.token_hex(32))"
python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; import base64; print(base64.b64encode(AESGCM.generate_key(bit_length=256)).decode())"
```

```bash
python manage.py migrate
python manage.py seed_demo      # creates one full demo campaign
python manage.py runstack       # starts server + worker + beat together
```

`runstack` is a dev-convenience management command (Python `subprocess`,
not Docker) — see Known Limitations. If it doesn't work cleanly on your
machine, run the three processes manually in separate terminals instead:
```bash
python manage.py runserver
celery -A config worker -l info
celery -A config beat -l info
```

Within 15 seconds of seeding, the demo campaign publishes itself to both
platforms automatically — check with:
```bash
curl http://localhost:8000/api/campaigns/<id-from-seed_demo-output>/
```

## Tests

```bash
python manage.py test
```

Runs the full suite across all apps (image dimensions, caption
platform-awareness, encryption, adapter HTTP handling, idempotency
hammer against the real fake_platform view, forged-webhook rejection,
scheduling durability). See `EVIDENCE.md` for a per-checklist-item
breakdown with pasted output.

## Known limitations

Documented on purpose, not hidden:

- **No Docker yet.** Local dev runs SQLite + a filesystem-based Celery
  broker (no Redis required) by explicit project constraint. Docker
  Compose with Postgres + Redis is planned before final submission —
  `CELERY_BROKER_URL` is read only from settings, so this is a
  configuration change, not a code change.
- **Filesystem Celery broker supports one worker process reliably.**
  Fine for dev and demo; not for production, which is exactly why `prod.py`
  will use Redis.
- **`runstack` is a subprocess-based convenience wrapper**, not a real
  process supervisor — no automatic restart on crash, no log separation.
  Stand-in for `docker compose up` until Docker Compose exists.
- **Own fake platform, not the provided starter.** The
  `starters/challenge-5-social/` link in the brief was unreachable, so
  `fake_platform` is a self-built equivalent app in this same project,
  with its contract documented in `FAKE_PLATFORM_CONTRACT.md`. Both sides
  of the contract are ours, which means we could shape it to be honest
  about failure modes (429, timeout) rather than matching an unknown spec.
- **Image variant pipeline uses simple center-crop**, assuming the
  subject is roughly centered in the source image. A real "safe zone"
  implementation (subject detection or a manual focal point) is a
  documented v2, not silently skipped.
- **`fake_platform`'s organic random 429** (~1-in-8 publish requests) is
  controllable via `FAKE_PLATFORM_SIMULATE_RANDOM_429` in settings —
  deterministic tests turn it off; left on by default for a more honest
  demo of the retry path actually firing under normal conditions.

## AI usage

This project was built with AI (Claude) assistance throughout, logged
transparently in `BUILDLOG.md` — including two real Celery configuration
bugs Claude's first pass got wrong (missing `load_dotenv()` in
`celery.py`, and a filesystem-broker folder misconfiguration), both found
by actually running the code, not by review.