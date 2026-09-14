# Race control desk

## Capture notes

Actual Next.js browser captures. `telemetry.jpg` uses synthetic WebSocket frames; `desktop.jpg` is the waiting state. Circuit geometry falls back to an explicitly labeled illustrative track; sector markers are approximate. The strategy panel retains its existing heuristic fallback. No real driver, lap, or model prediction is represented.

Web captures use Chromium at 1440 × 1080 (desktop) and 390 × 1080 (mobile), with reduced motion enabled. Screenshots are real rendered interfaces, not image-generated UI mockups. Raster renderer examples retain their native dimensions.

## Verification — 2026-09-14

`cd frontend && npm run build` passed, including type checking. Offline browser checks cover five widths, telemetry connection/disconnection, the labeled fallback map, and initial scroll position. Native HTML sector labels remove the map's runtime font-CDN requirement. Oracle, OpenF1, game UDP, and live inference were not tested.

Only the existing visual surfaces were changed. The screenshots are not evidence of end-to-end service availability, accessibility certification, or production performance.
