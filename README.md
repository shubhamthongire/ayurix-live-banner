# Ayurix banner bot — sub progress bar (N / goal) on the YouTube banner

## STATUS (for any AI continuing this)
DONE and tested locally: render.py (banner renderer), prepare_track.py (built assets/track.png), update_banner.py (poll + upload), get_refresh_token.py, workflow.
LIVE and working end to end (channel banner updates when the sub count changes).

## How it works
1. Every 5 min GitHub Actions runs update_banner.py.
2. It reads statistics.subscriberCount (exact below 1,000 subs). If equal to count.txt -> exit.
3. render.py: bar PNG space (2171x724) -> empty track + gradient fill CROPPED to count/goal (not stretched)
   + ragged pixel edge + number (Press Start 2P, blue/magenta chromatic edge) + additive multi-blur glow (Deep Glow look-alike)
   -> scaled 0.3325, placed at (71,612) on assets/bg.png at 88% opacity (matches the AE layer) -> banner.jpg (JPEG, <6 MB).
4. channelBanners.insert uploads it -> URL; channels.update(brandingSettings) sets image.bannerExternalUrl,
   re-sending the existing brandingSettings so nothing else is wiped.
5. count.txt is written only after success and committed by the workflow.

## Files
assets/bg.png banner without the bar | assets/track.png empty bar (made by prepare_track.py from bar_original.png)
| assets/vtks_noise.ttf VTKS Noise font used for subscriber count
assets/fill.png user's full noisy gradient | assets/PressStart2P-Regular.ttf (SIL OFL)
render.py constants at top: SCALE, OFFSET, FILL_BOX, NUM_XY, NUM_SIZE, glow strengths, GOALS

## YOUR SETUP (one time)
1. console.cloud.google.com -> new project -> enable "YouTube Data API v3".
2. OAuth consent screen: External. Add yourself as a test user, then PUBLISH the app ("In production").
   If it stays in "Testing", the refresh token dies after 7 days and the bot silently stops.
3. Credentials -> Create OAuth client ID -> type "Desktop app" -> download as client_secret.json into this folder.
4. pip install -r requirements.txt ; python get_refresh_token.py -> log in with the CHANNEL's Google account
   (click through the "unverified app" warning) -> copy the 3 printed values.
5. GitHub: create a PUBLIC repo (see warning below), push this folder, then Settings -> Secrets -> Actions:
   CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN.
6. Actions tab -> update-banner -> Run workflow once to test.

## Local tests
DRY_RUN=1 FAKE_COUNT=54 python update_banner.py   # renders banner.jpg only, no API calls
python render.py 73                                # quick preview

## Known limits (be realistic)
- Not instant: GitHub cron is delayed 5-20 min, and YouTube's count and banner caching add more.
- Private repo + 5-min cron burns the free 2,000 Actions minutes/month. Use a public repo, or change cron to */15.
- GitHub disables scheduled workflows after 60 days without repo activity; commits of count.txt keep it alive while subs change.
- At count >= goal the goal auto-advances (100 -> 250 -> 500 -> 1000...) per GOALS in render.py. 4-digit numbers are wider; check the look.
- Quota: poll = 1 unit, banner update ~100 units; default 10,000/day is plenty.
- If the sub count is hidden in Studio, the API returns no number and the script exits with a message.
- Glow is an approximation of After Effects Deep Glow, not identical.

## LOOK TUNING (top of render.py) — v3, tested against the user's AE export
Bar: OPACITY, SOFTEN, TINT/DESAT/GAIN, BAR_SHADOW (soft drop shadow), DG_THRESHOLD=80 + DG_RADII (Deep Glow look-alike), DG_WARM.
Number: NUM_COLOR (muted indigo so it reads on bright areas), NUM_SHADOW, NUM_GLOW (light halo, weaker than the bar's glow).
assets/track.png is built by prepare_track.py: spike removed, dark track turned into a pale glassy strip, dark blurry fringe faded out.
Known gap vs AE: the AE version has a stronger pink haze and orange heart rim. Raise DG_RADII exposures / DG_WARM to push closer.

## v7 (current look) — render.py
Wave: NEW random shape every render (WAVE_SEED=None; seed printed as "wave seed: N", set an int to freeze one). Drawn once per render in _new_wave(), shared by track, fill, number baseline and heart (position + tilt).
Same strength along the whole bar (WAVE_FLOOR=1.0). Knobs: WAVE_AMP (44), WAVE_SIZE (wavelength multiplier, >1 = broader), WAVE_TURB (0.10, fine turbulence on the track), WAVE_X0/X1, HEART_TILT. Base wavelengths are set in _new_wave.
Scattered stars (banner px): random layout every render (STAR_SEED=None; set an int to freeze). Tapered sparkles, thin crosses, dots; sparser (STAR_MIN0/STAR_MINK) and dimmer (STAR_FADE) farther from the bar. STAR_KEEPOUT is taller (60,664,835,810) because of the bigger wave. Stars do NOT follow the wave; the sparkles baked into track.png DO.
Number: NUM_X/NUM_Y/NUM_H/NUM_CW/NUM_GAP, NUM_COLOR, NUM_SHADOW (dark, bottom-right), NUM_LIGHT (white, top-left), NUM_GLOW. Shadows are applied after the glow.
Needs scipy (requirements.txt). Test: python render.py 54

## v8 (heart only, no progress bar)
Bar/track/fill are no longer drawn (the "N / goal" number is the progress). assets/heart.png = heart isolated from track.png (no bar, no stars). Heart sits after the number on the same line and rides the shared wave (position + tilt).
Knobs: HEART_H, HEART_SIZE (random range, seeded by the sub count so size changes whenever the count changes), HEART_GAP, HEART_DY, NUM_X/NUM_Y. WAVE_TURB and the bar functions (_bar_layer/_fill_layer/_displace) are now unused.

## Live deployment
Runs on GitHub Actions in a friend's account (github.com/shubhamthongire/ayurix-live-banner, public); secrets CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN are set there. Run `git pull` before pushing (the bot commits count.txt).
Banner only re-uploads when the sub count changes; force it by setting count.txt to -1 (or FORCE=1).
YouTube's API rounds counts to 3 significant digits from 1,000 subs. Past 10,000 add bigger GOALS and check that 4-5 digit numbers fit.

## CONTINUATION PROMPT (paste into another AI together with this folder)
"I have a Python project (banner-bot) that renders my YouTube banner with a subscriber progress bar (render.py) and uploads it via YouTube Data API v3 (update_banner.py) from a GitHub Actions cron. Read README.md first. Rendering is done and visually tuned; the live upload is untested. Help me: (1) finish Google Cloud OAuth setup and get the refresh token, (2) push to a public GitHub repo with the 3 secrets and run the workflow once, (3) fix any API errors I paste, (4) optionally tune the look in render.py (constants at top). Do not rewrite the renderer from scratch. Keep answers short."
