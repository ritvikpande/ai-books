# Execution Checkpoint — Face-Swap Photo Upload for Photoreal Characters

**Plan:** `docs/superpowers/plans/2026-06-16-face-swap-photo-upload.md` (approved 2026-06-16)
**Prior feature plan:** `~/.claude/plans/fizzy-splashing-truffle.md` ([spec](../specs/2026-06-15-character-reference-images-design.md))
**Branch:** `feat/face-swap`
**Last updated:** 2026-06-17 (after Task 7 manual E2E + border fix + cost recording)

## Prior feature (character reference images + structured multi-character UI) — built, E2E not confirmed in this checkpoint

Tasks 1–9 built, reviewed, committed (`287fcfb`..`a33dc2b`). Findings recorded in git history / design specs. Task 10 (full E2E of the reference-image pipeline) was not separately confirmed before face-swap work began.

## Done (this feature — all 6 build tasks + E2E + follow-ups)

- **Task 1: Data model** — `CHARACTER_FIELDS` gains `photo_path`. Commit `b9723b9`. ✅
- **Task 2: Reference prompt** — `assemble_reference_prompt` gains `has_photo`; face-preservation variant. Commit `896f776`. ✅
- **Task 3: Reference generation** — `generate_reference_images` reads `photo_path`, passes photo bytes as context, copies original to `refs/<kind>_<n>_upload.png`, records `from_photo`. Commit `72671b3`. ✅
- **Task 4: Upload endpoint** — `POST /upload_photo` (validate, Pillow normalize, UUID filename, 8MB cap). Commits `f8d22fc`, `62e858e`. ✅
- **Task 5: Frontend** — photoreal cards gain file input + thumbnail + hidden `field-photo-path`; upload-on-select; Generate disabled while uploads in flight. Commits `850f1d8`, `68317d1`. ✅
- **Task 6: Docs** — spec status updated. Commit `a2ad0b0`. ✅
- Final full-implementation code review: **Ready to merge: Yes** (one Important note: TOCTOU in `_load_context_bytes` is a pre-production concern only — acceptable for POC with no `_uploads/` cleanup). Test-coverage nit fixed in `28d752f`.

## Manual E2E results (Task 7 — USER ran, 2026-06-17, Gemini 3 Pro Image)

- ✅ **Face-swap quality: excellent.** Photorealistic character with a real human face swapped in looked fantastic. Upload UX, refs/ folder (generated + original side by side), and the no-photo character all worked.
- ⚠️ **White sticker/cutout border around characters** (both photoreal and cartoon, intermittently). **FIXED** in commit `7b7b65f`: removed the "collage" wording (root cause) from `STYLE_PHRASES` closers and the mixed-media opener, added an explicit "blend seamlessly / no white border/outline/frame/cut-out edge" instruction, and added the same no-border rule to the classic `SYSTEM_PROMPT`. Suite: 98 passed. **Needs a re-run to confirm the border is gone in actual output.**
- 💸 **Cost: CAD 3.53 for a 5-page book** — over the $3 POC ceiling and ~4× the original ~$0.90 estimate. Driver: one Pro reference per character + 5 Pro scene images (~7–8 Pro image calls/book). **Does not scale at this per-book cost.** Recorded in `.claude/CLAUDE.md` (Cost Estimate + Risks) and both design specs. Cost reduction (cheaper model for non-face steps, fewer/reused reference calls, fewer scene images) is the main open problem before scaling — quality is not the issue.

## Next

- **Re-run E2E** to confirm the border fix removed the white edges in actual Gemini output (the fix is prompt-level; only a real run confirms it).
- finishing-a-development-branch: push `feat/face-swap` to origin, open PR to main (not yet pushed).

## Pending / open (not blocking the branch)

- Cost reduction strategy before any scale-up (see above).
- Pre-production hardening: TOCTOU guard in `_load_context_bytes`; `_uploads/` lifecycle/cleanup; portable paths in `story.json`.
- Optional: update stale `TECHNICAL_OVERVIEW.md` (still describes the Streamlit version).
