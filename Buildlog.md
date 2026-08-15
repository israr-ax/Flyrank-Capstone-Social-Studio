# BUILDLOG.md

Running log of where AI (Claude) helped, what it got wrong, and what I
changed or decided myself. Updated as I go, not backfilled at the end.

---

## Phase 1 — Design & scaffolding

**DESIGN.md** — AI drafted the data model, API surface, layer sketch, and
`SocialPublisher` interface signature. Several details were marked as
`⚠️ ASSUMPTION` pending the real `starters/challenge-5-social/` contract.

**Deviation from the brief:** could not access the `starters/challenge-5-social/`
link referenced in the PDF. Built an equivalent fake platform as our own
`fake_platform` Django app instead. This means WE define the contract
both sides talk to, rather than matching an existing spec.

**fake_platform contract decisions:** AI proposed the shape (Idempotency-Key
as an HTTP header vs. body field; HMAC-SHA256 with either a custom
`X-Signature` or GitHub-style `X-Hub-Signature-256` header). I chose:
header-based idempotency key, `X-Hub-Signature-256` signing.

**Settings split (`config/settings/{base,dev,prod}.py`):** AI's first pass
of `base.py` only had the custom additions (INSTALLED_APPS, secret keys)
and was missing `MIDDLEWARE`, `TEMPLATES`, `ROOT_URLCONF` — caused
`admin.E403/E408/E409/E410` errors on `migrate`. Fixed by pasting the
complete file with Django's standard defaults included.

**Models across 6 apps** (`campaigns`, `content_pipeline`, `publishing`,
`scheduling`, `webhooks`, `fake_platform`): AI drafted all six. Two design
decisions I need to be able to explain at demo, not just accept:
1. `Campaign.status` is a `@property`, not a stored column — derived from
   `ScheduledPost` rows to avoid a second source of truth that could drift.
2. `FakePost` has its own `idempotency_key` uniqueness, independent of
   `ScheduledPost`'s — two independent dedup layers (ours + the simulated
   external platform's), matching how a real platform's API would behave.

**File placement bug (my error, not AI's):** downloaded model files got
saved as e.g. `campaigns_models.py` sitting next to where `models.py`
should be, instead of overwriting it. `makemigrations` silently reported
"No changes detected" because it was still reading the original empty
`models.py`. Fixed by renaming/moving each file into its app folder.

---

## Phase 2 — Content generation

**Caption composer (`content_pipeline/captions.py`):** shared "core"
message computed once per blog post, combined with a per-platform spec
dict (max length, hashtag count, whether a link is included, CTA text) —
not two near-identical hand-written templates. X gets the link + short
limit; Instagram gets more room and no link ("link in bio" convention).

**Image variant pipeline (`content_pipeline/images.py`):** Pillow
center-crop to each platform's target aspect ratio, then resize to exact
pixel dimensions. Chose simple center-crop for v1 (assumes subject is
roughly centered) — documented as a known limitation, not a hidden gap.

**Evidence:** `python manage.py test content_pipeline` → 7/7 passing,
covers both image dimensions and caption platform-awareness.

---

## Phase 3 — Publishing system

**Celery + filesystem broker setup — real debugging, not copy-paste.**
Two genuine bugs surfaced by actually running the code:
1. `config/celery.py` didn't call `load_dotenv()`. Without it, required
   env vars in `base.py` raised `KeyError` during Django's lazy settings
   resolution, which somehow surfaced as a misleading
   `AttributeError: 'Settings' object has no attribute 'worker_pool'`
   (different attribute name each retry). Found by web-searching the
   exact error and matching it to a known Celery/Django settings-resolution
   issue, not a Celery/Click version bug as it first appeared.
2. `CELERY_BROKER_TRANSPORT_OPTIONS` had `data_folder_in` and
   `data_folder_out` pointing at different folders. Kombu's filesystem
   transport requires these to be the SAME folder when producer and
   consumer are the same app (our case) — otherwise the worker polls a
   folder the producer never writes to. Confirmed against Kombu's docs.
   Also needed `pywin32` for file locking on Windows (undocumented in
   Celery's own quick-start).

**Known limitation, documented on purpose:** filesystem broker only
reliably supports a single worker process. Fine for local dev and the
demo; `prod.py` switches to Redis via Docker Compose at the end, and
because the broker is only ever referenced through settings, that's a
one-line change.

**Token encryption (`publishing/encryption.py`):** AESGCM with a fresh
random 12-byte nonce per call. 5/5 tests passing, including a check that
reusing the same plaintext twice produces different ciphertext (proves
the nonce is doing its job).

**`fake_platform` endpoints:** OAuth stub, publish endpoint with
server-side idempotency dedup, simulated 429/timeout via query params,
async signed webhook dispatch via Celery. Manually verified end-to-end
with curl + watching the worker logs: publish → 202 accepted → webhook
task fires on a delay → (before `webhooks` existed) 3 retries then a
clean failure with a 404 traceback — correct behavior, not a bug.

**`webhooks` receiver:** HMAC-SHA256 verification using
`hmac.compare_digest` (constant-time, not `==`, to avoid a timing side
channel). Forged/missing signatures return 400 and are logged but never
touch `ScheduledPost` state. 4/4 tests passing. Re-ran the fake_platform
loop after this existed — worker showed `succeeded` instead of `retry`,
receiver logged `200`.

**`SocialPublisher` interface + adapters
(`publishing/base.py`, `adapters.py`, `token_store.py`):** ABC interface
with `publish()` and `get_access_token()`; `FakeInstagramPublisher`/
`FakeXPublisher` are the only code that knows fake_platform's HTTP
contract, both calling it over real HTTP via `requests`, not a direct
function call (to preserve the actual network boundary the reliability
exercise depends on). 9/9 tests passing (mocked HTTP), covering 202
acceptance, 429 → `retry_after_seconds`, timeout handling, and that the
idempotency key is actually sent as the `Idempotency-Key` header.

**Still pending (Step 6, in progress):** `scheduling` app — `ScheduledPost`
creation from a campaign, the durable Celery Beat poller, and the actual
retry-with-backoff behavior honoring `Retry-After`. This is where
idempotent-publishing and durable-scheduling get their real proof, not
just the adapter reading the header.

Dry-running the demo script surfaced a real infinite-loop bug: simulate_crash reset an already-published row back to 'claimed', and since fake_platform's idempotency dedup only fires a webhook on first creation, the republished row got 202-accepted every cycle but never received a fresh webhook — looped every ~2 minutes indefinitely. Root cause diagnosed by reading the repeating log pattern (reclaimed → 202 → succeeded → repeat) and tracing it to the dedup branch in fake_platform/views.py never calling send_delivery_webhook. Fixed two places: (1) scheduling/tasks.py now separately times out accepted-but-webhook-never-arrived rows to 'failed' instead of endlessly re-publishing them, (2) simulate_crash now refuses to run against an already-terminal row. This is exactly the kind of bug a rehearsal catches and a rushed demo doesn't — glad we dry-ran it first.