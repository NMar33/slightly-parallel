// Render a deterministic intro page (window.__render(t), window.__duration) to JPEG frames, then a VP8 webm
// with Playwright's bundled ffmpeg (the only encoder it ships). Run from the frontend folder so playwright resolves.
// usage: node render.mjs page.html out/dir [fps]
import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import { mkdirSync, readdirSync, readFileSync, writeFileSync, appendFileSync, unlinkSync, existsSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { homedir } from 'node:os';
const [,, page, out, fpsArg] = process.argv;
const fps = Number(fpsArg || 30);
const dir = resolve(out); mkdirSync(join(dir, 'frames'), { recursive: true });
const ffDir = readdirSync(join(homedir(), '.cache/ms-playwright')).find(d => d.startsWith('ffmpeg'));
const ffmpeg = join(homedir(), '.cache/ms-playwright', ffDir, 'ffmpeg-linux');
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const p = await ctx.newPage();
await p.goto('file://' + resolve(page) + '#capture');
await p.waitForFunction(() => window.__ready === true, null, { timeout: 20000 });
const duration = await p.evaluate(() => window.__duration);
const n = Math.round(duration * fps);
const all = join(dir, 'all.mjpeg'); if (existsSync(all)) unlinkSync(all); writeFileSync(all, '');
for (let i = 0; i < n; i++) {
  await p.evaluate(t => window.__render(t), i / fps);
  const buf = await p.screenshot({ type: 'jpeg', quality: 94 });
  appendFileSync(all, buf);
  if (i === Math.round(n * 0.9)) await p.screenshot({ path: join(dir, 'poster.png') });
}
await browser.close();
const r = spawnSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', all,
  '-c:v', 'libvpx', '-b:v', '8M', '-deadline', 'good', '-cpu-used', '2', '-pix_fmt', 'yuv420p', join(dir, 'intro.webm')], { stdio: 'inherit' });
console.log(r.status === 0 ? `${n} frames → ${join(dir, 'intro.webm')}` : 'encode failed');
