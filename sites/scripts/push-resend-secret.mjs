#!/usr/bin/env node
/**
 * Pushes Resend API key from repo .env to Cloudflare Pages (Production).
 * Reads RESEND_API or RESEND_API_KEY from .env — stores as Pages secret RESEND_API_KEY.
 *
 * Usage: node sites/scripts/push-resend-secret.mjs bakerstrategy-site
 */
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { loadCloudflareEnv } from "./load-cloudflare-env.mjs";

const projectName = process.argv[2];
if (!projectName) {
  console.error("Usage: node sites/scripts/push-resend-secret.mjs <pages-project-name>");
  process.exit(1);
}

const sitesDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = dirname(sitesDir);
loadCloudflareEnv(repoRoot);

const apiKey = process.env.RESEND_API_KEY || process.env.RESEND_API;
if (!apiKey) {
  console.error("Add RESEND_API or RESEND_API_KEY to repo .env (gitignored).");
  process.exit(1);
}

const siteDir = join(sitesDir, "..", "baker-strategy");
const result = spawnSync(
  "npx",
  ["wrangler", "pages", "secret", "put", "RESEND_API_KEY", "--project-name", projectName],
  {
    cwd: siteDir,
    input: apiKey,
    encoding: "utf8",
    shell: true,
    stdio: ["pipe", "inherit", "inherit"],
  },
);

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}

console.log(`OK: RESEND_API_KEY set on Pages project "${projectName}" (from .env).`);
