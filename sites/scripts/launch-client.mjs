#!/usr/bin/env node
/**
 * Scaffold a ParlayVU client site from sites/_template.
 *
 * Usage:
 *   node sites/scripts/launch-client.mjs <client-slug> \
 *     --domain example.com \
 *     --to hello@example.com \
 *     --from contact@example.com \
 *     [--from-name "Example Site"] \
 *     [--brand "Example Co"] \
 *     [--pages-project example-site] \
 *     [--zone-id ZONE_ID] \
 *     [--account-id ACCOUNT_ID] \
 *     [--deploy]
 */
import { cpSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const sitesDir = dirname(__dirname);
const templateDir = join(sitesDir, "_template");
const repoRoot = dirname(sitesDir);

const DEFAULT_ACCOUNT = "e19918245a483360e7f4b4303c02afdf";

function parseArgs(argv) {
  const slug = argv[0];
  if (!slug || slug.startsWith("-")) {
    printHelp();
    process.exit(1);
  }
  const opts = {
    slug,
    domain: null,
    to: null,
    from: null,
    fromName: null,
    brand: null,
    logoLetters: null,
    tagline: null,
    description: null,
    pagesProject: null,
    zoneId: null,
    accountId: DEFAULT_ACCOUNT,
    deploy: false,
  };
  for (let i = 1; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--domain") opts.domain = next();
    else if (a === "--to") opts.to = next();
    else if (a === "--from") opts.from = next();
    else if (a === "--from-name") opts.fromName = next();
    else if (a === "--brand") opts.brand = next();
    else if (a === "--logo") opts.logoLetters = next();
    else if (a === "--tagline") opts.tagline = next();
    else if (a === "--description") opts.description = next();
    else if (a === "--pages-project") opts.pagesProject = next();
    else if (a === "--zone-id") opts.zoneId = next();
    else if (a === "--account-id") opts.accountId = next();
    else if (a === "--deploy") opts.deploy = true;
    else if (a === "--help" || a === "-h") {
      printHelp();
      process.exit(0);
    }
  }
  if (!opts.domain || !opts.to || !opts.from) {
    console.error("Required: --domain, --to, --from");
    process.exit(1);
  }
  if (!opts.pagesProject) {
    opts.pagesProject = opts.slug.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") + "-site";
  }
  if (!opts.fromName) {
    opts.fromName = `${opts.brand ?? opts.domain} Website`;
  }
  if (!opts.brand) {
    opts.brand = opts.domain.split(".")[0].replace(/-/g, " ");
    opts.brand = opts.brand.charAt(0).toUpperCase() + opts.brand.slice(1);
  }
  if (!opts.logoLetters) {
    opts.logoLetters = opts.brand
      .split(/\s+/)
      .map((w) => w[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
  }
  if (!opts.tagline) opts.tagline = "Welcome";
  if (!opts.description) opts.description = "We help you grow.";
  return opts;
}

function printHelp() {
  console.log(`Usage: node sites/scripts/launch-client.mjs <client-slug> --domain DOMAIN --to EMAIL --from EMAIL [options]

Options:
  --from-name "Name"     Sender display name (default: brand Website)
  --brand "Brand"        Brand name in nav/hero
  --logo "AB"            Logo letters (default: initials)
  --tagline "..."        Hero eyebrow
  --description "..."    Hero paragraph
  --pages-project NAME   Cloudflare Pages project (default: <slug>-site)
  --zone-id ID           Cloudflare zone ID (optional)
  --account-id ID        Cloudflare account (default: BSG)
  --deploy               Run npm ci && npm run pages:deploy after scaffold
`);
}

function slugify(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

const opts = parseArgs(process.argv.slice(2));
const clientDir = join(sitesDir, slugify(opts.slug));

if (existsSync(clientDir)) {
  console.error(`Already exists: ${clientDir}`);
  process.exit(1);
}

cpSync(templateDir, clientDir, { recursive: true });

const siteContact = {
  client: slugify(opts.slug),
  domain: opts.domain,
  cloudflareAccountId: opts.accountId,
  zoneId: opts.zoneId ?? "ZONE_ID",
  pagesProject: opts.pagesProject,
  brand: {
    name: opts.brand,
    logoLetters: opts.logoLetters,
    tagline: opts.tagline,
    description: opts.description,
  },
  contact: {
    to: opts.to,
    from: opts.from,
    fromName: opts.fromName,
  },
  successMessage: `Someone from ${opts.brand} will get back to you soon at the email you provided.`,
};

writeFileSync(join(clientDir, "site.contact.json"), JSON.stringify(siteContact, null, 2) + "\n");

const wrangler = `name = "${opts.pagesProject}"
pages_build_output_dir = "./dist"
compatibility_date = "2024-06-01"

[vars]
CONTACT_TO_EMAIL = "${opts.to}"
CONTACT_FROM_EMAIL = "${opts.from}"
CONTACT_FROM_NAME = "${opts.fromName}"
`;
writeFileSync(join(clientDir, "wrangler.toml"), wrangler);

let pkg = readFileSync(join(clientDir, "package.json"), "utf8");
pkg = pkg.replace(/CLIENT_SLUG/g, slugify(opts.slug)).replace(/PROJECT_NAME/g, opts.pagesProject);
writeFileSync(join(clientDir, "package.json"), pkg);

const deployMd = `# ${opts.domain}

ParlayVU client site. See \`../PARLAYVU_CLIENT_SITES.md\` and \`../RESEND_SETUP.md\`.

\`\`\`bash
cd sites/${slugify(opts.slug)}
npm run dev
npm run pages:deploy
\`\`\`

## Checklist

- [ ] Resend: verify **${opts.domain}**
- [ ] Pages **${opts.pagesProject}**: \`RESEND_API_KEY\` secret
- [ ] Custom domain + DNS CNAME → \`${opts.pagesProject}.pages.dev\`
`;
writeFileSync(join(clientDir, "DEPLOY.md"), deployMd);

console.log(`\nCreated: sites/${slugify(opts.slug)}/`);
console.log(`  domain: ${opts.domain}`);
console.log(`  pages:  ${opts.pagesProject}`);
console.log(`  contact: ${opts.from} → ${opts.to}`);

console.log(`
Next (human or agent):
  1. Resend → add domain ${opts.domain} → Auto configure Cloudflare (if applicable)
  2. Pages → ${opts.pagesProject} → RESEND_API_KEY (secret)
  3. Attach custom domain; CNAME @ and www to ${opts.pagesProject}.pages.dev
  4. cd sites/${slugify(opts.slug)} && npm run pages:deploy
  5. curl -X POST https://${opts.domain}/api/contact -F name=Test -F email=t@t.com -F message=Hi -F website=
`);

if (opts.deploy) {
  console.log("Running deploy…");
  const npm = spawnSync("npm", ["install"], { cwd: clientDir, shell: true, stdio: "inherit" });
  if (npm.status !== 0) process.exit(npm.status ?? 1);
  const deploy = spawnSync("npm", ["run", "pages:deploy"], { cwd: clientDir, shell: true, stdio: "inherit" });
  process.exit(deploy.status ?? 0);
}
