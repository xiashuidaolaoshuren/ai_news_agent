# Implementation plans: Follow-ups and settings

**Specs:** `docs/superpowers/specs/2026-10-20-targeted-followups-design.md`, `docs/superpowers/specs/2026-10-20-settings-and-credentials-design.md`
**Created:** 2026-10-30
**Goal scope:** This file is the index. The work is two pieces.

The follow-ups spec and the settings, keys, and sign-in spec ship as one backend piece and one frontend piece. The frontend piece follows the current OpenDesign prototype (`research-chat-prototype.html` in "AI News Research Agent").

| Piece | Plan |
|---|---|
| Backend | `docs/superpowers/plans/2026-10-20-followups-settings-backend-plan.md` (B1–B12) |
| Frontend | `docs/superpowers/plans/2026-10-20-followups-settings-frontend-plan.md` (U1–U6) |

Backend **B1** is the entry resolver the research plan consumes. Settings owns schema 4. Research records are schema 5 in the research plan.

OpenRouter as a digest source stays in `docs/superpowers/specs/2026-10-20-openrouter-and-source-visibility-design.md`. The Settings panel still edits the OpenRouter profile, because the settings spec defines it.

## Plan changelog

| Date | Change | Kind |
|---|---|---|
| 2026-10-30 | Initial combined follow-ups plan (F1–F7) | — |
| 2026-10-30 | Replaced by the backend and frontend pieces. Settings, keys, and sign-in are included. Old F1–F4 are B1–B4. Old F5–F6 are U1–U2. | material |
