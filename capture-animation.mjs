import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const htmlPath = path.join(__dirname, 'tasksmith-animation.html');
const videoDir = path.join(__dirname, 'capture-output');

async function capture() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 960, height: 540 },
    recordVideo: {
      dir: videoDir,
      size: { width: 960, height: 540 }
    }
  });

  const page = await context.newPage();
  await page.goto(`file://${htmlPath}`, { waitUntil: 'networkidle' });

  // Wait for full animation cycle + buffer (20s animation + 1.5s repeatDelay + 1s buffer)
  console.log('Recording animation for 22 seconds...');
  await page.waitForTimeout(22000);

  await context.close();
  await browser.close();

  console.log(`Video saved to ${videoDir}/`);
}

capture().catch(console.error);
