import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";

/**
 * Load CLOUDFLARE_API or CLOUDFLARE_API_TOKEN from .env (repo or site root).
 * Does not override variables already set in the environment.
 */
export function loadCloudflareEnv(startDir) {
  let dir = startDir;
  for (let i = 0; i < 6; i++) {
    const envPath = join(dir, ".env");
    if (existsSync(envPath)) {
      const text = readFileSync(envPath, "utf8");
      for (const line of text.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) continue;
        let sep = trimmed.indexOf("=");
        if (sep === -1) {
          const colon = trimmed.indexOf(":");
          const keyPart = colon === -1 ? trimmed : trimmed.slice(0, colon);
          if (colon !== -1 && /^[A-Z][A-Z0-9_]*$/.test(keyPart.trim())) {
            sep = colon;
          }
        }
        if (sep === -1) continue;
        const key = trimmed.slice(0, sep).trim();
        let value = trimmed.slice(sep + 1).trim();
        if (
          (value.startsWith('"') && value.endsWith('"')) ||
          (value.startsWith("'") && value.endsWith("'"))
        ) {
          value = value.slice(1, -1);
        }
        if (process.env[key] === undefined) {
          process.env[key] = value;
        }
      }
      break;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }

  return process.env.CLOUDFLARE_API_TOKEN || process.env.CLOUDFLARE_API || "";
}
