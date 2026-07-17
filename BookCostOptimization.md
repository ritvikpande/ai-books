# Book Cost Optimization — Bringing CAD 3.5–3.8/book Down

**Author:** Claude Fable 5 · **Date:** 2026-07-17 · **Branch:** `feat/face-swap`
**Status:** Strategy only — *no code changed.* Each lever includes a cheap experiment to prove/disprove it and how an agent runs it.
**Decision locked by owner:** generation stays **interactive** (~2-min live wait). Gemini **Batch API (50% off) is rejected** because it needs async "notify when ready" UX. Levers below respect that.

> Companions: [FableSuggestions.md](FableSuggestions.md) (COST/OBS-4 instrumentation, SEC-2 containment) and [NextJSWebDesign.md](NextJSWebDesign.md) (where the character library lives).

---

## 1. The problem & baseline

A 5-page mixed-media storybook with **1 photoreal face-swap character + 1 cartoon character**, all images on Gemini 3 Pro Image, measured:

| | Run 1 | Run 2 (instrumented) |
|---|---|---|
| Total cost | **CAD 3.53** | **CAD 3.83** |
| API calls | — | 8 (0 errors) |
| Pro image requests | — | **7** = 2 references + 5 scenes |
| Flash text requests | — | 1 |
| Pro tokens | — | 5.85K in / 11.65K out |
| Flash tokens | — | 0.63K in / 2.13K out |

**Cost is dominated by Pro image generation, not text.** ~CAD 0.55 per Pro image; references are ~29% of image spend (2 of 7 calls). The Flash text call is negligible.

**The hard constraint (from manual testing):** Gemini **2.5 Flash image quality is not acceptable** for the photoreal/face-swap character — Pro is required *there*. **But** that verdict was measured with Flash doing the **raw face swap from the uploaded photo**. It was **not** tested with Flash rendering a *scene* that already has a clean **Pro-generated reference** attached as context. That specific combination is the untested, decisive question this doc is built around.

---

## 2. Pricing facts (verified) & the 2.8× anomaly ⚠️

Verified against ai.google.dev pricing / image-generation / batch docs (mid-2026):

- **gemini-3-pro-image-preview:** image output bills as a flat per-image token count — **1K and 2K resolution both = 1,120 tokens ≈ $0.134 USD/image**; 4K ≈ $0.24. Text/thinking output $12/1M; input $2/1M; **input images bill a flat ~560 tokens (~$0.0011) regardless of pixel size**. **Default output is already 1K.**
- **gemini-2.5-flash-image:** ≈ **$0.039 USD/image**. (Also check the newer **gemini-3.1-flash-image-preview** — see lever #1.)
- **Thinking on Gemini 3 Pro Image is on by default and can't be disabled**; it can generate interim "thought images" that are billed.
- **Context caching is NOT offered for either image model.**
- **Batch API: 50% off, but async** → rejected by the interactive-only decision (kept on the shelf below).

**Anomaly to resolve first.** 7 Pro images at list ≈ 7 × $0.134 ≈ **$0.94 USD ≈ CAD 1.35** (the UI label in `providers.py:54` even says "~$0.90/book"). Measured is **CAD 3.53–3.83 — ~2.8× list.** The token readout (~1.66K out/image ≈ 1,120 image + ~540 thinking) is consistent with 1K output, so **resolution is not the cause.** Most likely: (1) billed interim **thought images** not reflected in the token line you read, (2) the dashboard undercounts image-modality tokens, or (3) FX + tax stacking.

**Why this matters for lever choice:** if thought-images are ~60% of Pro spend, Flash (no thinking) is ~**10×** cheaper than Pro, not the ~3.4× list ratio — which massively raises the payoff of hybrid routing. **So the first action is free: implement usage logging ([FableSuggestions.md](FableSuggestions.md) COST/OBS-4) and reconcile one run against the billing line items.** Don't place big bets until the 2.8× is explained.

---

## 3. Ranked levers

Each: **Idea · Projected saving on the CAD 3.83 baseline · Quality risk · Experiment to prove it · Agent note.** Savings don't all stack cleanly — see §4.

### Lever #1 — Hybrid model routing 🥇 (highest EV; gated by one ~CAD 1–2 experiment)

- **Idea:** Use Pro **only** for the face-bearing image — the photoreal character's **reference** (the face-synthesis step where quality is proven to matter). Generate the cartoon reference and **all 5 scenes on Flash**, with the clean Pro reference attached as context to anchor identity. Wiring already supports per-call model choice (`providers.generate_image(..., model)`), so routing is a small change in `generate_reference_images` / `generate_all_images`.
- **Projected saving:** ~1×Pro + 6×Flash ≈ `0.55 + 6×0.055 ≈ **CAD 0.88/book (~77% down)**` if quality holds. (If the anomaly is thought-images, Flash's edge is even larger.)
- **Quality risk:** **Real and untested** — does Flash *preserve* the face when the identity is supplied by a Pro reference (as opposed to Flash inventing it from a raw photo, which failed)? Secondary risks: style/texture drift between a Pro reference and Flash scenes; per-page consistency. Mitigation fallback: also render on Pro the 1–2 scenes where the child's face is large/focal (~50% saving instead of 77%).
- **Experiment (do this first, ~CAD 1–2):** Regenerate the *exact* baseline inputs with Pro photoreal-ref → Flash everything else. Owner judges likeness/consistency page-by-page against the all-Pro book. Also run the same book on **gemini-3.1-flash-image-preview** (the "Flash is bad" verdict predates it and may no longer hold — **verify its price first**).
- **Agent note:** An agent can implement a `model_for(step)` routing helper and run the experiment, but a **human judges the output quality** — that gate cannot be automated.

### Lever #2 — Character library / reference reuse 🥈 (~25–29% on repeat characters; near-zero risk)

- **Idea:** Persist each character's generated reference PNG + its fields, keyed by user+character. On a book that reuses a character (same child, new story), attach the **stored** reference bytes instead of regenerating it — `reference_paths` is just a list of paths/bytes (`image_generator.py`), so this is mechanically identical to today and arguably *improves* cross-book consistency.
- **Projected saving:** removes 2 of 7 Pro calls on repeat-character books ≈ **~29%**, plus ~2 calls of wall-clock. **Zero saving on first-ever use** of a character.
- **Quality risk:** Near zero (same bytes). The real cost is **policy**: these are face-derived images of children — requires per-user isolation, explicit consent, and a working delete path.
- **Experiment:** Manually point a second run's `reference_paths` at run 1's `refs/` and confirm identical quality at 2 fewer Pro calls.
- **Home:** the Next.js-era DB + object storage — see [NextJSWebDesign.md](NextJSWebDesign.md) "Character library." Don't build a bespoke store in the Flask app; it lands with the migration.
- **Agent note:** **Mechanical** to prototype (reuse existing paths); the persistence layer is migration-scoped.

### Lever #3 — Draft-on-Flash → approve → Pro final (business lever; interactive-compatible)

- **Idea:** Show a cheap **all-Flash draft** of the book instantly; the user tweaks/approves; only then spend Pro on the final render. Absorbs iteration and abandonment on the cheap tier and gates Pro spend behind intent.
- **Projected saving:** For a book that *is* finalized, this *adds* ~CAD 0.3–0.4. It pays off by (a) making rejected/iterated books cost pennies and (b) ensuring Pro is spent only on keepers. If users iterate ~once per finished book on average, effective **~40–50% per finished book.**
- **Quality risk:** None to the final (Pro renders it); the draft just looks cheaper — set expectations in copy.
- **Experiment:** Measure your real iteration/abandon rate; the lever only helps if it's meaningfully above zero.
- **Agent note:** Pairs with #1 (the draft *is* the Flash path). Needs a two-step UX — build during the Next.js work.

### Lever #4 — Instrumentation + pin image config (prerequisite, ~0% direct)

- **Idea:** Log `usage_metadata` per call and pin `image_size`/`aspect_ratio` in the generation config. (= [FableSuggestions.md](FableSuggestions.md) COST/OBS-4.)
- **Projected saving:** ~0% directly (output is already 1K; 1K/2K cost the same), **but it is the prerequisite for measuring #1–#3 and it resolves the 2.8× anomaly** — which may itself reveal the real saving (e.g. a way to reduce thought-image billing, or confirmation that Flash's advantage is 10× not 3×). Pinning aspect ratio also gives deterministic book-page layout.
- **Quality risk:** None.
- **Experiment:** One instrumented run; reconcile the logged tokens/cost against the Gemini billing line items.
- **Agent note:** **Mechanical, cheap-model-safe. Do this first — it's free and unblocks everything.**

### Lever #5 — Spend containment (biggest expected-dollar protection)

- **Idea:** Auth + per-user quota + GCP budget alerts + API-key quota cap. (= [FableSuggestions.md](FableSuggestions.md) SEC-2; landed properly in [NextJSWebDesign.md](NextJSWebDesign.md).)
- **Projected saving:** Not a unit-cost saving, but it bounds worst-case spend. Today an anonymous caller (or a bot) can run your budget to zero on a public endpoint; that dwarfs per-book optimization in expected dollars.
- **Quality risk:** None.
- **Agent note:** Interim mitigations are ops/config; the durable version is migration-scoped.

### Lever #6 — Regenerate-one-scene + idempotency (cap failure/iteration cost)

- **Idea:** Let the user regenerate a single disliked page (pay 1 image, not 7), and guard the double-submit of a CAD-3.83 action (client submit-lock + optional server idempotency key). Pairs with CORR-5's retry so a scene-5 flake doesn't discard the whole book.
- **Projected saving:** Situational — turns a full re-run (7 images) into 1, and prevents accidental double books.
- **Quality risk:** None.
- **Agent note:** Regenerate-one-scene is a small pipeline+UX addition (migration-friendly); the idempotency guard is a tiny frontend/back-end change (cheap-model-safe).

### Rejected / not worth it

| Lever | Why rejected |
|---|---|
| **Batch API (50% off)** | Requires async "notify when ready" UX — **owner chose interactive-only.** *Revisit only if a "queued/cheaper" tier is ever added; it would need the job model from the migration anyway.* |
| **Context caching of reference bytes** | **Not supported** for either image model. |
| **Downscaling context images** | Input is only ~5.85K tokens (~$0.012), and input images bill a flat ~560 tokens regardless of size — negligible. |
| **Programmatic compositing** (Pro character over Flash background) | Same ceiling as hybrid but **reintroduces the white cutout-border look that was just fixed**, plus lighting/perspective mismatch and no character–scene interaction. Last resort only. |
| **Fewer pages** | Linear ~14%/page but degrades the product; prefer regenerate-one-scene (#6). |

---

## 4. Recommended sequence & outcome scenarios

1. **Lever #4 (instrumentation)** — free, resolves the 2.8× anomaly, unblocks measurement.
2. **Lever #1 experiment** — the single highest-EV test (~CAD 1–2). Also test 3.1-Flash. Human judges quality.
3. If #1 passes → ship hybrid routing. If it partially passes → Pro only on face-focal scenes.
4. **Lever #2 (character library)** + **#5 (containment)** land with the Next.js migration.
5. **Lever #6** as UX polish.

**Scenarios (from the CAD 3.83 baseline):**

| Outcome | Result |
|---|---|
| Hybrid passes + character reuse | **~CAD 0.3–0.5/book (~90% down)** |
| Hybrid partially passes (face-focal scenes on Pro) | ~CAD 1.5–2.0/book (~50% down) |
| Hybrid fails, reuse + containment only | ~CAD 2.7/book on repeat characters; first-use unchanged — cost stays a product-pricing problem |

**Bottom line:** the whole program hinges on one cheap, human-judged experiment (Lever #1). Instrument first (free), then run it. Everything else is either a modest stack-on saving or spend protection. **The open problem is cost, not quality** — the goal is to find the *minimum* Pro usage that keeps the face quality the owner already validated.
