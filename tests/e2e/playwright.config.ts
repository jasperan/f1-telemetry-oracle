import { defineConfig, devices } from "@playwright/test";

/**
 * E2E test config for F1 Telemetry Oracle.
 *
 * Expects the full stack to be running via docker compose before tests run.
 * Frontend on :3100, API on :8100, Oracle on :1525.
 */
export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.ts",
  fullyParallel: false, // tests share seeded state
  retries: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: "http://localhost:3100",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  /* Start full stack before tests if not already running */
  webServer: {
    command:
      "docker compose -f ../../docker-compose.yml up --wait --build 2>&1",
    url: "http://localhost:3100",
    timeout: 180_000, // Oracle container can be slow to start
    reuseExistingServer: true,
    stdout: "pipe",
    stderr: "pipe",
  },
});
