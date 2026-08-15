# DEMO_SCRIPT.md — 6-minute walkthrough

Matches § 13 of the brief exactly. Every command here has already been
run for real and is backed by proof in `EVIDENCE.md` — this isn't a
hopeful script, it's a rehearsed one.

**Before starting:** `python manage.py runstack` running in one terminal
(server + worker + beat together). Second terminal free for commands.
Browser tab open to `http://localhost:8000/admin/`, logged in.

---

## 1. Create campaign (~45s)

```bash
curl -X POST http://localhost:8000/api/campaigns/ ^
  -F "title=Demo Post" ^
  -F "body=This is the real first sentence for the demo. More text follows." ^
  -F "url=https://example.com/demo-post" ^
  -F "source_image=@C:\path\to\image.jpg"
```

Say while it returns: *"One call — this creates the BlogPost, composes
both captions, generates both image variants, and schedules both
platforms. Nothing else has to happen manually from here."*

Note the returned `id` — used in the next step.

## 2. Show variants + captions (~45s)

```bash
curl http://localhost:8000/api/campaigns/<id>/
```

Point out in the JSON: two `platform_assets`, different `caption` text
(Instagram longer + no link, X shorter + has the link), different image
paths. Optionally open both image files from `media/platform_variants/`
side by side to show 1080×1080 vs 1600×900.

Say: *"Same shared core message, different platform fragment — not two
copy-pasted templates."*

## 3. Schedule + advance time (~45s)

Switch to the `runstack` terminal — within 15 seconds of step 1, you'll
already see the Beat poller claim these rows and the worker publish them
automatically. Point at the log lines live:
```
poll_due_scheduled_posts: claimed 2 of 2 due rows
Task scheduling.tasks.publish_scheduled_post[...] received
POST /fake/instagram/publish/ HTTP/1.1 202
```

Say: *"No cron job, no manual trigger — the scheduler found this on its
own next poll cycle."*

## 4. Idempotency hammer (~60s)

```bash
python manage.py test scheduling.tests.IdempotencyHammerIntegrationTests -v 2
```

This hits the real `fake_platform` endpoint 12 times total (2 tests, one
sending 2 duplicate requests, one sending 10) with the same
`Idempotency-Key` each time and asserts exactly one `FakePost` row exists
either way.

Say: *"This isn't mocked — it's hitting the actual publish view. Ten
duplicate requests, same key, one post."*

## 5. Forced 429 (~45s)

```bash
curl -i -X POST "http://localhost:8000/fake/instagram/publish/?force_429=1" ^
  -H "Authorization: Bearer fake-instagram-demo" ^
  -H "Idempotency-Key: demo-429-key" ^
  -F "caption=test" ^
  -F "image=@C:\path\to\image.jpg"
```

Point at the response headers: `429`, `Retry-After: 5`. If you want to
show the scheduler honoring it end-to-end rather than just the raw
response, create a real `ScheduledPost` for this and watch `runstack`
log `rate-limited, retrying in 5s` followed by an actual retry — this
already happened for real, unprompted, during the `runstack` test run on
15 Aug (organic 429, see `EVIDENCE.md`), worth mentioning that it's not
just a forced flag, it fires under normal random conditions too.

## 6. Forged then valid webhook (~60s)

**Forged first:**
```bash
curl -i -X POST http://localhost:8000/api/webhook/social-delivery/ ^
  -H "Content-Type: application/json" ^
  -H "X-Hub-Signature-256: sha256=0000000000000000000000000000000000000000000000000000000000000000" ^
  -d "{\"idempotency_key\": \"fake-key\", \"event\": \"published\"}"
```
Point at: `400`.

**Then a real one** — easiest to demonstrate by letting an actual
scheduled post's webhook arrive naturally (already happens automatically
via `runstack`), or by generating a valid signature with Python:
```bash
python -c "import hmac,hashlib,json; body=json.dumps({'idempotency_key':'fake-key','event':'published'}).encode(); print(hmac.new(b'YOUR_WEBHOOK_SHARED_SECRET', body, hashlib.sha256).hexdigest())"
```
(use your real `.env` value for the secret, and the exact same `body`
bytes in the curl `-d`)

## 7. Dashboard (~45s)

Switch to the browser, `http://localhost:8000/admin/`:
- **Scheduling → Scheduled posts** — show live status transitions
  (`published`, `attempt_count`, `next_retry_at` on any that hit a 429)
- **Publishing → Platform tokens** — click into one, show `encrypted_token`
  is raw ciphertext bytes, never plaintext
- **Webhooks → Webhook events** — show both a `signature_valid=True` row
  and the forged `signature_valid=False` row from step 6, side by side

Close with: *"Everything on this screen is real state, updated only
through the actual pipeline — nothing here was set by hand."*

---

## Timing budget
~45+45+45+60+45+60+45 = ~5m45s, leaves buffer for questions.

## If something doesn't work live
Fall back to `EVIDENCE.md` — every beat above has a corresponding pasted
terminal output from an earlier real run. Say so directly rather than
awkwardly debugging in front of an evaluator: *"Here's the same result
from an earlier run, logged in EVIDENCE.md"* is a fine thing to say.