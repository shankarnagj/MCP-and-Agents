// Frontend ↔ backend integration smoke test driving the real UI in Chromium.
// Requires: backend on :8000 (seeded), `vite preview` on :4173.
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";

const BASE = process.env.TESSERA_UI ?? "http://127.0.0.1:4173";
const OUT = process.env.TESSERA_SHOTS ?? "../docs/screenshots";
const PASSWORD = process.env.TESSERA_DEMO_PASSWORD ?? "Demo-Passw0rd!";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM ?? "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
const step = async (name, fn) => {
  const t = Date.now();
  await fn();
  console.log(`PASS ${name} (${Date.now() - t} ms)`);
};

try {
  await step("login", async () => {
    await page.goto(BASE);
    await page.fill("#u", "investigator");
    await page.fill("#p", PASSWORD);
    await page.click("button[type=submit]");
    await page.waitForSelector("[aria-label='Global search']");
  });
  await step("search entity", async () => {
    await page.fill("[aria-label='Global search']", "device:DV-7F3A-SHARED");
    await page.keyboard.press("Enter");
    await page.waitForSelector("text=1 match(es)");
    await page.keyboard.press("Enter");
    await page.waitForSelector("[data-testid=entity-label]");
  });
  await step("expand graph", async () => {
    await page.click("text=Expand 1-hop");
    await page.waitForFunction(() => document.querySelector("[data-testid=graph-canvas]") && /[1-9]\d* nodes/i.test(document.body.innerText));
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/01-graph.png` });
  });
  await step("open signal (explainability)", async () => {
    await page.click("text=shared_device");
    await page.waitForSelector("[data-testid=signal-card]");
    await page.waitForSelector("text=Alternative explanations");
    await page.screenshot({ path: `${OUT}/02-signal.png` });
  });
  await step("filter relationships", async () => {
    await page.click("text=Filters");
    await page.waitForSelector("text=Relationship types");
    await page.click("text=Entities");
  });
  await step("timeline", async () => {
    await page.click("button:has-text('Timeline')");
    await page.waitForSelector("[data-testid=timeline-chart] canvas");
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT}/03-timeline.png` });
  });
  await step("map", async () => {
    await page.click("button:has-text('Map')");
    await page.waitForSelector("[data-testid=map] canvas");
    await page.click("text=Fit to data");
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${OUT}/04-map.png` });
  });
  await step("provenance of a relationship", async () => {
    await page.click("button:has-text('Table')");
    await page.click("text=Relationships (");
    await page.locator("tbody tr").first().click();
    await page.waitForSelector("text=Why does this relationship exist?");
    await page.waitForSelector("text=Source records");
    await page.screenshot({ path: `${OUT}/05-provenance.png` });
  });
  await step("investigation + hypothesis", async () => {
    await page.click("button:has-text('Investigation')");
    await page.fill("input[placeholder=Name]", `E2E investigation ${Date.now()}`);
    await page.fill("textarea[placeholder='Question / scope']", "Relationships between accounts, devices, transactions and locations (synthetic).");
    await page.click("button:has-text('Create')");
    await page.waitForSelector("[data-testid=investigation-name]");
    await page.click("text=Pin workspace entities");
    await page.waitForFunction(() => /entities \([1-9]/i.test(document.body.innerText));
    // select an entity for hypothesis subject
    await page.locator(".grid .cursor-pointer").first().click();
    await page.fill("textarea[placeholder^='Entity A may be']", "Accounts using device DV-7F3A-SHARED may be operated by the same party.");
    await page.click("button:has-text('Create hypothesis')");
    await page.waitForSelector("text=ANALYST ASSERTION — HYPOTHESIS");
    await page.screenshot({ path: `${OUT}/06-investigation.png` });
  });
  await step("query builder", async () => {
    await page.click("button:has-text('Query')");
    await page.click("button:has-text('Run query')");
    await page.waitForSelector("text=Plan");
    await page.screenshot({ path: `${OUT}/07-query.png` });
  });
  await step("report download", async () => {
    await page.click("button:has-text('Investigation')");
    const [dl] = await Promise.all([page.waitForEvent("download"), page.click("button:has-text('Report PDF')")]);
    const path = `${OUT}/report.pdf`;
    await dl.saveAs(path);
  });
  const fatal = errors.filter((e) => !/favicon|WebGL|Failed to load resource/.test(e));
  if (fatal.length) {
    console.log("Console errors:\n" + fatal.join("\n"));
    process.exitCode = 1;
  } else console.log("E2E SMOKE: PASS");
} catch (e) {
  console.error("E2E FAIL:", e.message);
  await page.screenshot({ path: `${OUT}/failure.png` });
  process.exitCode = 1;
} finally {
  await browser.close();
}
