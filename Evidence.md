# EVIDENCE.md

Proof pasted the moment each checklist item passes — not backfilled.
Status legend: ✅ done with proof below · ⏳ in progress · ⬜ not started

---

## ✅ Image variants correct
Instagram 1080×1080, X 1600×900, test asserts dimensions.

```
python manage.py test content_pipeline
Ran 7 tests in 1.249s
OK
```
Also re-proven inside the full pipeline test (`campaigns` app):
```
python manage.py test campaigns
Ran 4 tests in 1.333s
OK
```
(`test_create_campaign_generates_assets_and_schedules_both_platforms`
asserts both variant dimensions after a real API call.)

---

## ✅ Captions are platform-aware
Composed from shared + platform-specific fragments, no duplicated
near-identical prompts.

```
python manage.py test content_pipeline
Ran 7 tests in 1.249s
OK
```

---

## ✅ One SocialPublisher interface, ≥2 adapters
`publishing/base.py` defines the ABC; `FakeInstagramPublisher` and
`FakeXPublisher` in `publishing/adapters.py` are the only two concrete
implementations, both accessed only via `get_publisher(platform)` (a
string-keyed factory) from `scheduling/tasks.py` — no file outside
`publishing/adapters.py` imports either concrete class directly.

```
python manage.py test publishing
Ran 9 tests in 0.266s
OK
```

---

## ✅ OAuth tokens encrypted at rest
Random IV/nonce per encryption, never logged. (Same `publishing` test
run above — 5 of the 9 tests cover encryption specifically: round-trip,
ciphertext doesn't contain plaintext, nonce unique per call, same
plaintext produces different ciphertext across calls, wrong nonce fails
decryption.)

---

## ✅ Idempotent publishing
Same (post, platform) published twice or retried after timeout → exactly
one post.

```
python manage.py test scheduling
Ran 10 tests in 0.456s
OK
```
Specifically: `IdempotencyHammerIntegrationTests` hits the REAL
`fake_platform` publish view (no mocking) twice, then 10 times, with the
same `Idempotency-Key`, and asserts exactly one `FakePost` row exists
each time, and the webhook only dispatches once. `AtomicClaimTests`
proves the claim mechanism itself is race-safe (a second claim attempt
on an already-claimed row affects zero DB rows).

---

## ✅ Rate limits respected
On 429, worker honors `Retry-After`, backs off, retries safely.

```
python manage.py test publishing   # adapter parses 429 -> retry_after_seconds
python manage.py test scheduling   # scheduler sets next_retry_at from that value
Both: OK
```
`test_429_sets_next_retry_at_from_retry_after` in `scheduling/tests.py`
proves the scheduler sets `next_retry_at` using the exact `Retry-After`
value from the platform, not a guessed backoff.

**Still worth doing before demo:** a live run showing this happen
end-to-end against `fake_platform`'s real `?force_429=1` flag, not just
mocked. Planned as part of the live full-stack demo run.

---

## ✅ Scheduling is durable
Survives crash mid-batch, restarted worker doesn't double-post.

```
python manage.py test scheduling
Ran 12 tests in 0.477s
OK
```
`StaleClaimReclaimTests` simulates a worker that claimed a row then
crashed (status stuck at "claimed", claimed_at 5 minutes in the past) and
proves the poller reclaims it (log line:
`poll_due_scheduled_posts: reclaimed 1 stale claim(s)`) and re-dispatches
it for publishing -- not left stuck forever. `AtomicClaimTests` proves
the claim itself is race-safe. Combined with the idempotency hammer
tests, this covers both halves of durability: survives the crash AND
never double-posts on recovery.

This gap was found by reasoning through the crash scenario before
writing the test, not by the test failing first: the original poller only
queried status="queued", so a row stuck at "claimed" was invisible to it
-- no duplicate, but also never published. Fixed by adding stale-claim
reclaim to the same poller task.

**Live proof** (via `python manage.py simulate_crash` + `runstack`, 15 Aug 2026):
```
(venv) D:\Flyrank-Capstone-Social-Studio>python manage.py simulate_crash
Simulated a crashed worker: ScheduledPost cac308d2-6725-440a-a8f7-e569eeb3e457
(campaign f0e8341d-6fb5-4eda-8dd3-a8a2d4636716, platform=x) is now
status='claimed', claimed_at=5 min ago.

--- runstack terminal, next poll cycle ---
[2026-08-15 22:23:12,736: WARNING/MainProcess] poll_due_scheduled_posts: reclaimed 1 stale claim(s)
[2026-08-15 22:23:12,788: INFO/MainProcess] poll_due_scheduled_posts: claimed 1 of 1 due rows
[2026-08-15 22:23:12,888: INFO/MainProcess] Task scheduling.tasks.publish_scheduled_post[0dd5859d-5bb8-4594-804b-aaf3788418a8] received
[15/Aug/2026 22:23:15] "POST /fake/x/publish/ HTTP/1.1" 202 82
[2026-08-15 22:23:15,222: INFO/MainProcess] Task scheduling.tasks.publish_scheduled_post[0dd5859d-5bb8-4594-804b-aaf3788418a8] succeeded in 2.343s
```
The simulated-crashed row went from stuck at `claimed` to actually
published within one 15s poll cycle, with no duplicate `FakePost` created
(same idempotency key as before the "crash").

---

## ✅ Delivery webhooks are signature-verified
Forged/modified → 400.

```
python manage.py test webhooks
Ran 4 tests in 0.180s
OK
```
Plus manual end-to-end proof via curl + Celery worker logs showing
publish → 202 → webhook task succeeded → receiver 200 (see prior commit
for full terminal transcript).

---

## ✅ Campaign status updates only after a verified webhook
Same `webhooks` test suite: forged webhook leaves `ScheduledPost.status`
at `"queued"`; valid signed webhook moves it to `"published"`.

---

## ✅ Automated tests cover: image dimensions, duplicate-publish
## prevention, forged-webhook rejection, rate-limit behavior
All four now have real automated coverage:
- Image dimensions — `content_pipeline`, `campaigns`
- Duplicate-publish prevention — `scheduling` (idempotency hammer)
- Forged-webhook rejection — `webhooks`
- Rate-limit behavior — `publishing` (parsing) + `scheduling` (backoff)

---

## ⬜ README + architecture diagram + setup instructions + § 11 files
`DESIGN.md`, `FAKE_PLATFORM_CONTRACT.md`, `BUILDLOG.md`, `EVIDENCE.md`
exist. Still needed: `README.md` setup instructions, architecture
diagram, `capstone.yaml`, final `.env.example` review. Planned for demo
prep phase.