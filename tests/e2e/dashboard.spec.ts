import { test, expect } from "@playwright/test";

/**
 * E2E tests for the F1 Telemetry Oracle dashboard.
 *
 * Prerequisites:
 *   - Full stack running (docker compose up)
 *   - Oracle seeded with fixture data
 *
 * Tests verify all 6 dashboard panels render correctly with real data,
 * AI chat produces streaming responses, and lap comparison works.
 */

const API_BASE = "http://localhost:8100";

test.describe("Dashboard -- Panel Rendering", () => {
  test.beforeEach(async ({ page }) => {
    // Verify API is healthy before testing UI
    const healthResp = await page.request.get(`${API_BASE}/health`);
    expect(healthResp.ok()).toBeTruthy();

    await page.goto("/");
    // Wait for the dashboard layout to be visible
    await page.waitForSelector('[data-testid="dashboard-grid"]', {
      timeout: 15_000,
    });
  });

  test("all 6 dashboard panels are visible", async ({ page }) => {
    const panels = [
      "live-telemetry-panel",
      "race-engineer-chat-panel",
      "track-map-panel",
      "sim-vs-real-panel",
      "strategy-advisor-panel",
      "historical-explorer-panel",
    ];

    for (const panelId of panels) {
      const panel = page.getByTestId(panelId);
      await expect(panel).toBeVisible({ timeout: 10_000 });
    }
  });

  test("live telemetry panel shows speed gauge", async ({ page }) => {
    const telemetryPanel = page.getByTestId("live-telemetry-panel");
    await expect(telemetryPanel).toBeVisible();

    // Speed gauge or speed value should be rendered
    const speedElement = telemetryPanel
      .getByTestId("speed-value")
      .or(telemetryPanel.locator("text=/\\d+.*km\\/h/i"));
    await expect(speedElement).toBeVisible({ timeout: 10_000 });
  });

  test("strategy advisor shows tire compound", async ({ page }) => {
    const strategyPanel = page.getByTestId("strategy-advisor-panel");
    await expect(strategyPanel).toBeVisible();

    // Should show at least one tire compound label
    const tireLabel = strategyPanel.locator(
      "text=/SOFT|MEDIUM|HARD|INTERMEDIATE|WET/i"
    );
    await expect(tireLabel.first()).toBeVisible({ timeout: 10_000 });
  });

  test("track map panel renders canvas/WebGL", async ({ page }) => {
    const trackPanel = page.getByTestId("track-map-panel");
    await expect(trackPanel).toBeVisible();

    // react-three-fiber renders into a canvas element
    const canvas = trackPanel.locator("canvas");
    await expect(canvas).toBeVisible({ timeout: 10_000 });
  });

  test("historical explorer panel has search input", async ({ page }) => {
    const histPanel = page.getByTestId("historical-explorer-panel");
    await expect(histPanel).toBeVisible();

    const searchInput = histPanel.locator(
      'input[placeholder*="search" i], input[placeholder*="ask" i], input[type="text"]'
    );
    await expect(searchInput.first()).toBeVisible();
  });
});

test.describe("AI Race Engineer Chat", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector('[data-testid="dashboard-grid"]', {
      timeout: 15_000,
    });
  });

  test("typing a question shows streaming response", async ({ page }) => {
    const chatPanel = page.getByTestId("race-engineer-chat-panel");
    await expect(chatPanel).toBeVisible();

    // Find the chat input
    const chatInput = chatPanel
      .locator('input[type="text"], textarea')
      .first();
    await expect(chatInput).toBeVisible();

    // Type a question
    await chatInput.fill("What was Verstappen's best lap at Monza?");
    await chatInput.press("Enter");

    // Wait for a response to start appearing (streaming)
    const responseArea = chatPanel
      .locator(
        '[data-testid="chat-response"], [data-testid="ai-response"], .chat-message'
      )
      .first();
    await expect(responseArea).toBeVisible({ timeout: 30_000 });

    // Response should contain some text (not empty)
    await expect(responseArea).not.toBeEmpty({ timeout: 30_000 });
  });

  test("quick-ask buttons send predefined questions", async ({ page }) => {
    const chatPanel = page.getByTestId("race-engineer-chat-panel");

    // Click a quick-ask button if present
    const quickButton = chatPanel
      .locator(
        'button:has-text("tire"), button:has-text("strategy"), button:has-text("lap")'
      )
      .first();

    if (await quickButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await quickButton.click();

      // Should trigger a response
      const responseArea = chatPanel
        .locator(
          '[data-testid="chat-response"], [data-testid="ai-response"], .chat-message'
        )
        .first();
      await expect(responseArea).toBeVisible({ timeout: 30_000 });
    }
  });
});

test.describe("Lap Comparison", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector('[data-testid="dashboard-grid"]', {
      timeout: 15_000,
    });
  });

  test("sim-vs-real panel renders comparison view", async ({ page }) => {
    const simVsRealPanel = page.getByTestId("sim-vs-real-panel");
    await expect(simVsRealPanel).toBeVisible();

    // The panel should have lap selectors or auto-load the comparison
    // Look for chart/trace elements (Recharts renders SVG)
    const chartElement = simVsRealPanel
      .locator(
        'svg.recharts-surface, [data-testid="comparison-chart"], canvas'
      )
      .first();

    // If lap selectors exist, use them
    const lapSelector = simVsRealPanel
      .locator('select, [data-testid="lap-selector"]')
      .first();
    if (await lapSelector.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const selectors = simVsRealPanel.locator("select");
      if ((await selectors.count()) >= 2) {
        await selectors.nth(0).selectOption({ index: 1 });
        await selectors.nth(1).selectOption({ index: 2 });
      }
    }

    // Verify chart traces render
    await expect(chartElement).toBeVisible({ timeout: 15_000 });
  });

  test("comparison shows sector delta indicators", async ({ page }) => {
    const simVsRealPanel = page.getByTestId("sim-vs-real-panel");
    await expect(simVsRealPanel).toBeVisible();

    // Look for delta indicators (positive/negative time differences)
    const deltaElement = simVsRealPanel
      .locator('text=/[+-]\\d+\\.\\d+/i, [data-testid*="delta"]')
      .first();

    // Delta might not appear until data loads
    await expect(deltaElement).toBeVisible({ timeout: 15_000 });
  });
});
