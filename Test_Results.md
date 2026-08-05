# Test Results — AI Storybook Generator

A running log of manual end-to-end test runs, their parameters, measured metrics, and
analysis notes. Append a new dated section per run.

---

## Run — 2026-06-17 · Mixed media + face swap (instrumented)

**Branch:** `feat/face-swap` · **Tester:** Ritvik (manual E2E)

### Configuration / parameters

| Parameter | Value |
|---|---|
| Mode | Mixed media (photoreal characters in a cartoon world) |
| Pages / scenes | 5 |
| Photoreal characters | 1 (with **face swap** — real uploaded photo) |
| Cartoon characters | 1 |
| Image model | Nano Banana Pro — Gemini 3 Pro Image |
| Text model | Gemini 3 Flash |
| Provider | Gemini |
| Art style | _not recorded — fill in (e.g. 2D flat vector / watercolor)_ |
| Keywords / interests | _not recorded_ |
| Setting | _not recorded_ |
| Story type | _not recorded_ |
| Character details (name, traits, description) | _not recorded_ |
| Sliding-window size | 2 previous pages (+ reference images on every scene) |

> The "not recorded" rows weren't captured at run time. Fill them in from memory if
> known, or capture them on the next run — the app does not currently log the input
> form values into `story.json` beyond the assembled prompts.

### Measured metrics (as reported by the tester)

| Metric | Value |
|---|---|
| Total API calls | 8 |
| Total API errors | 0 |
| Requests — Nano Banana Pro (Gemini 3 Pro) | 7 |
| Requests — Gemini 3 Flash | 1 |
| Input tokens — Gemini 3 Pro | 5.85K |
| Output tokens — Gemini 3 Pro | 11.65K |
| Input tokens — Gemini 3 Flash | 0.63K |
| Output tokens — Gemini 3 Flash | 2.13K |
| **Total cost** | **CAD 3.83** |

### Derived analysis (for later)

- **Request breakdown:** the 7 Pro image requests = **2 reference images** (1 face-swap
  photoreal + 1 cartoon) **+ 5 scene images**. The 1 Flash request = the story-text
  generation. Total = 8 calls, matching the reported count.
- **Pro token totals:** 5.85K in + 11.65K out = **17.5K tokens** across 7 image calls
  (~2.5K tokens/image avg). Flash: 0.63K in + 2.13K out = **2.76K tokens** for 1 call.
- **Cost per Pro image (approx):** CAD 3.83 ÷ 7 ≈ **~CAD 0.55 / Pro image** (Flash text
  cost is negligible by comparison). This is ~3× the early planning assumption of
  ~$0.18/image.
- **Reference overhead:** 2 of 7 Pro image calls (~29% of image spend) went to
  reference images rather than visible pages. With more characters this overhead grows
  (one reference per character), bounded by `MAX_CHARACTERS = 6`.
- **Cost per visible page (approx):** CAD 3.83 ÷ 5 pages ≈ **~CAD 0.77 / page** all-in
  (references included).

### Qualitative findings

- ✅ **Face-swap quality: excellent.** The photorealistic character with a real human
  face swapped in looked fantastic on Gemini 3 Pro. Identity was well preserved.
- ✅ **Pipeline reliability:** 8/8 calls succeeded, 0 errors.
- ⚠️ **White sticker/cutout border** appeared around characters (both photoreal and
  cartoon) in some images. **Fixed** (commit `7b7b65f`) by removing the "collage"
  prompt wording and adding an explicit "blend seamlessly / no border/outline/frame/
  cut-out edge" instruction across mixed-media and classic prompts. **Needs a re-run to
  confirm** the border is gone in actual output (prompt-level fix, not unit-testable).
- ✅ **Reference images now viewable in the UI** (commit `e25ebc9`) — generated
  references plus the original uploaded photo render side-by-side after generation, for
  easier visual QA on future runs.

### Cost / scaling implications

- A 5-page mixed-media face-swap book costs **~CAD 3.5–3.8** (two runs: CAD 3.53 and
  this CAD 3.83) — **over the $3 POC ceiling** and ~4× the original ~$0.90 estimate.
- **Does not scale at this per-book cost.** Cost is dominated by Pro image generation,
  not text. Levers to reduce it before scaling:
  - Use a cheaper model (e.g. Flash image) for non-face steps — cartoon references and
    backgrounds — reserving Pro for the face-swapped photoreal characters.
  - Reduce or reuse reference calls (cache a character's reference across books).
  - Reduce the number of scene images.
- **The open problem is cost, not quality.**

---

## Run — 2026-06-17 · Mixed media + face swap (first run)

| Parameter | Value |
|---|---|
| Mode | Mixed media + face swap |
| Pages | 5 |
| Image model | Gemini 3 Pro Image |
| **Total cost** | **CAD 3.53** |

Detailed per-model metrics were not captured for this run (only total cost). Treated as
a second cost data point alongside the instrumented run above (→ ~CAD 3.5–3.8 / book).

---

## Template for future runs

```
## Run — YYYY-MM-DD · <short description>

### Configuration / parameters
| Parameter | Value |
|---|---|
| Mode | classic / mixed media |
| Pages | 5 |
| Photoreal characters | N (face swap? y/n) |
| Cartoon characters | N |
| Image model | |
| Text model | |
| Art style | |
| Keywords | |
| Setting | |
| Story type | |

### Measured metrics
| Metric | Value |
|---|---|
| Total API calls | |
| Total API errors | |
| Requests per model | |
| Input / output tokens per model | |
| Total cost (CAD) | |

### Findings / analysis
- quality:
- issues:
- cost / scaling notes:
```
