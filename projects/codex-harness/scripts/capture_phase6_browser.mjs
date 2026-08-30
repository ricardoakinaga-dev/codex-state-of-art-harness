#!/usr/bin/env node

import fs from "node:fs/promises";
import crypto from "node:crypto";
import path from "node:path";
import process from "node:process";

const playwrightModule = process.env.PLAYWRIGHT_MODULE || "playwright";
const importedPlaywright = await import(playwrightModule);
const { chromium } = importedPlaywright.default || importedPlaywright;

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1]);
}

const url = args.get("--url");
const outputDirArg = args.get("--output-dir");
const sourceHtml = args.get("--source-html");
const projectRootArg = args.get("--project-root") || process.cwd();
const taskId = args.get("--task-id");
const runId = args.get("--run-id");
const criteriaDigest = args.get("--criteria-digest");
const artifactId = args.get("--artifact-id");
const artifactVersion = args.get("--artifact-version") || "artifact_v1";
if (!url || !outputDirArg || !sourceHtml || !taskId || !runId || !criteriaDigest || !artifactId) {
  throw new Error(
    "usage: capture_phase6_browser.mjs --url URL --project-root DIR --output-dir DIR " +
      "--source-html FILE --task-id ID --run-id ID --criteria-digest DIGEST --artifact-id ID",
  );
}

const projectRoot = path.resolve(projectRootArg);
const projectRootReal = await fs.realpath(projectRoot);
const assertInside = (root, candidate, label) => {
  const relative = path.relative(root, candidate);
  if (relative.startsWith(".." + path.sep) || relative === ".." || path.isAbsolute(relative)) {
    throw new Error(label + " must remain inside project root");
  }
};
const sourceCandidate = path.resolve(sourceHtml);
assertInside(projectRoot, sourceCandidate, "source HTML");
const sourcePath = await fs.realpath(sourceCandidate);
assertInside(projectRootReal, sourcePath, "source HTML");
const sourceMetadata = await fs.lstat(sourcePath);
if (!sourceMetadata.isFile()) {
  throw new Error("source HTML must be a regular file");
}
const outputCandidate = path.resolve(outputDirArg);
assertInside(projectRoot, outputCandidate, "output directory");
await fs.mkdir(outputCandidate, { recursive: true });
const outputDir = await fs.realpath(outputCandidate);
assertInside(projectRootReal, outputDir, "output directory");

const targetUrl = new URL(url);
const loopbackHosts = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);
if (
  !["http:", "https:"].includes(targetUrl.protocol) ||
  !loopbackHosts.has(targetUrl.hostname) ||
  !targetUrl.port ||
  targetUrl.username ||
  targetUrl.password
) {
  throw new Error("browser capture URL must target an unauthenticated loopback origin");
}
const sourceBytes = await fs.readFile(sourcePath);
const sourceDigest = "sha256:" + crypto.createHash("sha256").update(sourceBytes).digest("hex");
const sourceStat = await fs.stat(sourcePath);
const captureStartedAt = new Date().toISOString();

const viewports = [
  { id: "desktop", width: 1440, height: 900 },
  { id: "mobile", width: 390, height: 844 },
];
await fs.mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
  args: ["--no-sandbox"],
});
const observations = [];
const consoleMessages = [];
const failedRequests = [];
let servedSource = null;
const browserInfo = {
  engine: "chromium",
  version: browser.version(),
  executable_path: process.env.CHROME_PATH || "/usr/bin/google-chrome",
  capture_method: "playwright_local_fallback",
  url,
  task_id: taskId,
  run_id: runId,
  criteria_digest: criteriaDigest,
  artifact_id: artifactId,
  artifact_version: artifactVersion,
  source_html: sourcePath,
  source_html_digest: sourceDigest,
  source_html_bytes: sourceStat.size,
  capture_started_at: captureStartedAt,
};

for (const viewport of viewports) {
  const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
  const page = await context.newPage();
  await page.route("**/favicon.ico", (route) => route.fulfill({ status: 204, body: "" }));
  page.on("console", (message) => {
    consoleMessages.push({ viewport: viewport.id, type: message.type(), text: message.text() });
  });
  page.on("pageerror", (error) => {
    consoleMessages.push({ viewport: viewport.id, type: "pageerror", text: String(error) });
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({ viewport: viewport.id, url: request.url(), failure: request.failure()?.errorText || "unknown" });
  });
  const response = await page.goto(url, { waitUntil: "networkidle" });
  if (!response || !response.ok()) {
    throw new Error(`browser capture received an invalid HTTP response: ${response?.status() ?? "missing"}`);
  }
  const finalUrl = new URL(page.url());
  if (finalUrl.origin !== targetUrl.origin || !loopbackHosts.has(finalUrl.hostname)) {
    throw new Error("browser capture navigation escaped the loopback origin");
  }
  const servedBytes = await response.body();
  const servedDigest = "sha256:" + crypto.createHash("sha256").update(servedBytes).digest("hex");
  if (servedDigest !== sourceDigest || servedBytes.length !== sourceBytes.length) {
    throw new Error("served page does not match declared source HTML");
  }
  if (servedSource === null) {
    servedSource = { bytes: servedBytes.length, digest: servedDigest };
  } else if (servedSource.bytes !== servedBytes.length || servedSource.digest !== servedDigest) {
    throw new Error("served page differs between viewport captures");
  }
  const metrics = await page.evaluate(() => {
    const focusable = document.querySelectorAll(
      'a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])',
    );
    const externalResources = performance
      .getEntriesByType("resource")
      .map((entry) => entry.name)
      .filter((resource) => {
        try {
          return new URL(resource).origin !== window.location.origin;
        } catch {
          return true;
        }
      });
    return {
      viewport: { width: window.innerWidth, height: window.innerHeight },
      document_width: document.documentElement.scrollWidth,
      viewport_width: window.innerWidth,
      body_height: document.body.scrollHeight,
      h1_count: document.querySelectorAll("h1").length,
      focusable_count: focusable.length,
      landmarks: ["header", "main", "footer"].map((tag) => ({ tag, count: document.querySelectorAll(tag).length })),
      external_resources: externalResources,
      title: document.title,
    };
  });
  if (metrics.external_resources.length > 0) {
    throw new Error("browser capture encountered an external resource");
  }
  const screenshot = path.join(outputDir, `${viewport.id}-${viewport.width}x${viewport.height}.png`);
  await page.screenshot({ path: screenshot, fullPage: false, scale: "css" });
  const compactScreenshot = path.join(outputDir, `${viewport.id}-${viewport.width}x${viewport.height}.jpg`);
  await page.screenshot({ path: compactScreenshot, fullPage: false, scale: "css", type: "jpeg", quality: 82 });
  await fs.writeFile(
    path.join(outputDir, `${viewport.id}-snapshot.txt`),
    await page.locator("body").innerText(),
    "utf8",
  );
  observations.push({
    ...metrics,
    id: viewport.id,
    screenshot,
    compact_screenshot: compactScreenshot,
    artifact_id: artifactId,
    artifact_version: artifactVersion,
    source_html_digest: sourceDigest,
  });
  await context.close();
}

await browser.close();
const digestFile = async (filePath) => {
  const bytes = await fs.readFile(filePath);
  return {
    path: filePath,
    bytes: bytes.length,
    digest: `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`,
  };
};
const captureFiles = [
  ...(await Promise.all(observations.flatMap((item) => [item.screenshot, item.compact_screenshot].map(digestFile)))),
];
await fs.writeFile(path.join(outputDir, "browser-info.json"), `${JSON.stringify(browserInfo, null, 2)}\n`, "utf8");
await fs.writeFile(path.join(outputDir, "browser-observations.json"), `${JSON.stringify(observations, null, 2)}\n`, "utf8");
await fs.writeFile(path.join(outputDir, "console-messages.json"), `${JSON.stringify(consoleMessages, null, 2)}\n`, "utf8");
await fs.writeFile(path.join(outputDir, "network-failures.json"), `${JSON.stringify(failedRequests, null, 2)}\n`, "utf8");
const consoleEvidence = await digestFile(path.join(outputDir, "console-messages.json"));
const networkEvidence = await digestFile(path.join(outputDir, "network-failures.json"));
const captureManifest = {
  schema_version: "P6-BROWSER-CAPTURE-1",
  task_id: taskId,
  run_id: runId,
  criteria_digest: criteriaDigest,
  artifact_id: artifactId,
  artifact_version: artifactVersion,
  url,
  source: {
    path: sourcePath,
    bytes: sourceStat.size,
    digest: sourceDigest,
    served_bytes: servedSource?.bytes,
    served_digest: servedSource?.digest,
    served_matches_declared: true,
  },
  browser: browserInfo,
  captures: captureFiles,
  observations_path: path.join(outputDir, "browser-observations.json"),
  console_evidence: consoleEvidence,
  network_evidence: networkEvidence,
  captured_at: new Date().toISOString(),
};
await fs.writeFile(
  path.join(outputDir, "browser-capture-manifest.json"),
  `${JSON.stringify(captureManifest, null, 2)}\n`,
  "utf8",
);
console.log(JSON.stringify({ browser: browserInfo, observations, console_messages: consoleMessages, network_failures: failedRequests }, null, 2));
