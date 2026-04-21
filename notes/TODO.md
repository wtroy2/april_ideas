# Critter — TODO / Deferred Features

Living list of things that have been intentionally deferred. Anything in here is
"yes we want it, just not now". Prioritized roughly top-to-bottom.

---

## Audio / music

### Music sources we discussed but skipped
- **Royalty-free library**: pre-loaded ~10 MP3s in `gs://critter-music/{music_vibe}/`, code picks at random by Theme.music_vibe. Easy. License: Epidemic Sound / Mixkit / Pixabay.
- **ElevenLabs Music API**: per-video custom track based on Theme.music_vibe + scenario. ~$0.05–0.10/clip. Good for variety.
- **TikTok / IG trending audio**: scraper that pulls weekly trending sounds for the pet niche; user can pick "use this week's #1 sound". Highest virality upside.
- **BPM detection / auto-sync**: detect track BPM and align video edits / cuts to beat. Premium feature.

### Character-only reference mode (true scene generation around the pet)

Current state: a per-batch toggle `use_photo_background` lets the user pick between
"first-frame mode" (pet exact, background carries through) and "text-only mode"
(fresh background per scenario, pet looks similar via the text description).

Neither is true "character reference" — Veo's image input is fundamentally
first-frame conditioning. Three upgrade paths to get the best of both:

1. **Background-removed first frame**: pre-process the primary photo with Gemini
   2.5 Flash Image to strip the background, then pass the clean PNG (pet on a
   neutral bg) as the first frame. Veo bridges from there to the prompt-driven
   scene. Awkward first ~0.5s but better than nothing. ~$0.02/photo extra.
2. **Runway Gen-4 References**: route any batch with `use_photo_background=False`
   automatically to Runway instead of Veo. Runway has true character-reference
   mode built in. Cost ~5x Veo Lite. Should be a transparent fallback when the
   user toggles off photo background.
3. **Tighter pet description**: Gemini Vision currently produces a one-liner.
   For text-only mode, generate a longer structured description (color, build,
   marking patterns, eye color, fur texture) that's better at carrying identity
   through Veo's text-to-video.

### Specialized Runway models (different workflows, not video gen)

These Runway models exist but don't fit the current "prompt → short clip" pipeline.
Each would be its own feature + UI surface:

- **Gen-4 Aleph** (`gen4_aleph`) — video-to-video editing. Take an existing clip
  and restyle / transform it. Useful for "here's my Veo output, make it look
  more cinematic". Would need an "edit this generation" button on the take card.
- **Gen-4 Image / Gen-4 Image Turbo** — image generation only. Could feed the
  "background-removed first frame" idea above: generate a clean reference image
  of the pet in a desired pose, then pass that to Veo as the seed frame.
- **Act-Two** (`act_two`) — motion capture. Record yourself acting out the
  pet's movement; Act-Two transfers your motion onto the pet. Cool for specific
  action beats but requires a whole new upload + mocap UI.
- **GWM Avatars** (`gwm-avatars`) — real-time interactive. Different API
  surface entirely (WebRTC, not REST). Not a batch-processing fit.

### Audio features beyond the basic mix
- **Live fade preview with Web Audio API**: the audio mix panel live-previews VOLUME only (HTML media element .volume). Fades require Web Audio `GainNode.linearRampToValueAtTime()` tied to `video.currentTime`. Would let the user hear fades before baking. ~30 lines of AudioContext setup.
- **Per-generation audio overrides**: today the audio mix is one-per-batch. Add ability to override on a single generation in the batch detail page (e.g., "regenerate this clip but with different fade-out").
- **Mix history UI**: `AudioMix` rows are saved per-bake in the DB — the UI currently shows only the latest. Could add a "mix history" dropdown to revert to a previous bake without re-baking.
- **Voiceover via ElevenLabs**: text-to-speech of caption / scenario, layered into the mix as a 3rd track. Important for "POV pet adventure" style themes.
- **Sound effects library**: tagged SFX (purr, meow, paws, ASMR chops, vacuum) selectable per generation.
- **Audio waveform preview** on the upload UI — show a wave so the user knows where to set the start offset.
- **Auto-trim silence** at start/end of uploaded music.
- **Loudness normalization** (LUFS target like -14 for IG/TikTok).

---

## Distribution (Phase 4)

- IG / TikTok scheduling via Buffer or Ayrshare API
- Multi-format export: 9:16 (Reels), 1:1 (square), 16:9 (YouTube) from the same source clip
- Watermark / logo overlay (optional per-org)
- Download bundles (zip of all clips in a batch + captions in a CSV)

---

## Monetization (Phase 5)

- Stripe checkout + subscription billing (`billing` app is stubbed; Stripe integration not yet wired)
- Stripe webhooks for `subscription.updated`, `invoice.paid`, etc.
- Plan tier paywalls (Free / Starter / Pro / Agency) — quotas already exist
- Promo / coupon codes

---

## Trends + growth (Phase 5)

- TikTok Creative Center scraper — trending pet hashtags + sounds + formats
- Per-niche dashboard ("what's working in pet content this week")
- Auto-suggest scenarios from trending formats

---

## Production / infra

- **Memorystore Redis** + Serverless VPC connector (`critter-redis-connector`) for the prod worker fleet. Once provisioned: flip `RUN_JOBS_INLINE=False` in prod, then deploy the worker via `deploy_worker.sh`.
- **ClamAV scanning** in prod — currently `ENABLE_CLAMAV_SCANNING=false`. Need to deploy a ClamAV scanner service, set `CLAMAV_SCANNER_URL`, flip to `true`. Pet-photo uploads should be safe in practice but defense-in-depth.
- **SMTP / SendGrid** for real outbound email (currently console backend in dev, no sender configured). Required to flip `REQUIRE_2FA=True` in prod.
- **Frontend deploy**: Firebase Hosting setup, `VITE_API_URL` build variable
- **Custom domain** + Cloud DNS + SSL — point `critter.app` (or whatever final name) at Cloud Run
- **APM / error tracking** — Sentry on backend + frontend

---

## Content safety (when going public)

- ToS + acceptance checkbox at signup
- Pre-flight prompt moderation (Claude classifier before Veo call)
- Output spot-check (Gemini Vision on generated video → keyword denylist for sex/weapon/blood)
- Per-user hourly/daily rate limits (today only monthly quota exists)
- Take-down + report flow on every generated video
- Server-side denylist for celebrity / IP keywords in prompts

---

## Polish / nice-to-have

- Frontend Error Boundaries (React) per route
- Pytest test suite for backend (mirrors RateRail's gap)
- Type hints throughout backend (gradual mypy adoption)
- Pre-commit hooks: ruff for backend, eslint for frontend
- API documentation (OpenAPI / Swagger)
- Sentry / log aggregation
- Subject "lookalike search" — Gemini embedding of reference photos so user can find similar pets across their library
