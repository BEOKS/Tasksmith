const puppeteer = require("puppeteer");
const path = require("path");
const fs = require("fs");

const FRAME_DIR = path.join(__dirname, "frames");
const HTML_PATH = `file://${path.join(__dirname, "tasksmith-animation.html")}`;
const FPS = 20;
const FRAME_INTERVAL = 1000 / FPS;
const DURATION_SEC = 22; // total animation duration ~20s + buffer
const TOTAL_FRAMES = DURATION_SEC * FPS;

(async () => {
  // Clean/create frames dir
  if (fs.existsSync(FRAME_DIR)) fs.rmSync(FRAME_DIR, { recursive: true });
  fs.mkdirSync(FRAME_DIR);

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 800, height: 500, deviceScaleFactor: 2 });
  await page.goto(HTML_PATH, { waitUntil: "networkidle0" });

  console.log(`Capturing ${TOTAL_FRAMES} frames at ${FPS}fps...`);

  for (let i = 0; i < TOTAL_FRAMES; i++) {
    const framePath = path.join(FRAME_DIR, `frame_${String(i).padStart(4, "0")}.png`);
    await page.screenshot({ path: framePath });

    // Advance GSAP time
    await page.evaluate((ms) => {
      if (window.gsap) gsap.globalTimeline.time(ms / 1000);
    }, i * FRAME_INTERVAL);

    if (i % 20 === 0) console.log(`  frame ${i}/${TOTAL_FRAMES}`);
  }

  await browser.close();
  console.log(`Done. ${TOTAL_FRAMES} frames saved to ${FRAME_DIR}/`);
})();
