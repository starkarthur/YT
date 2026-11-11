// Rendert l001_test.html Bild für Bild mit Headless Chrome (puppeteer-core) nach $GK_ARBEIT/frames/%05d.jpg.
// Aufruf: node render.mjs   (Umgebung: GK_ARBEIT, CHROME = Pfad zu Chrome)
import { mkdirSync, readFileSync, writeFileSync, createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { join, resolve, dirname, normalize, extname } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const HIER = dirname(fileURLToPath(import.meta.url));
const ARBEIT = resolve(process.env.GK_ARBEIT || "arbeit");
const FPS = 30;
const zeiten = JSON.parse(readFileSync(join(ARBEIT, "zeiten.json"), "utf8"));
const clipInfo = JSON.parse(readFileSync(join(ARBEIT, "clips.json"), "utf8"));
// Kleiner Server nur auf 127.0.0.1 (gleicher Ursprung, damit Canvas/WebGL die Bilder lesen dürfen)
const WURZELN = { seite: HIER, arbeit: ARBEIT };
const TYP = { ".html": "text/html", ".png": "image/png", ".jpg": "image/jpeg", ".mjs": "text/javascript" };
const server = createServer((req, res) => {
  const [, wurzel, ...rest] = decodeURIComponent(req.url.split("?")[0]).split("/");
  const basis = WURZELN[wurzel], pfad = basis && normalize(join(basis, ...rest));
  if (!pfad || !pfad.startsWith(basis) || !existsSync(pfad) || !statSync(pfad).isFile()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "Content-Type": TYP[extname(pfad)] || "application/octet-stream" });
  createReadStream(pfad).pipe(res);
}).listen(0, "127.0.0.1");
await new Promise(r => server.once("listening", r));
const BASIS = `http://127.0.0.1:${server.address().port}`;
const konf = { render: true, zeiten, clipInfo, bilder: `${BASIS}/arbeit/bilder/`, clips: `${BASIS}/arbeit/clips/` };
const ausgabe = join(ARBEIT, "frames");
mkdirSync(ausgabe, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/usr/bin/google-chrome",
  headless: true,
  // --no-sandbox: Ubuntu 24.04 auf GitHub erlaubt Chromes Sandbox nicht; geladen wird nur unsere eigene lokale Seite.
  args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--window-size=1920,1080", "--hide-scrollbars", "--mute-audio"],
  defaultViewport: { width: 1920, height: 1080 },
});
const page = await browser.newPage();
page.on("console", m => { if (m.type() === "error") console.log("Seite:", m.text()); });
page.on("pageerror", e => { console.log("Seitenfehler:", e.message); process.exitCode = 1; });
await page.evaluateOnNewDocument(k => { window.KONF = k; }, konf);
await page.goto(`${BASIS}/seite/l001_test.html`, { waitUntil: "load" });
await page.waitForFunction("window.bereit === true", { timeout: 120000 });

const ende = zeiten[zeiten.length - 1], n = Math.round(ende * FPS), start = Date.now();
for (let i = 0; i < n; i++) {
  const url = await page.evaluate(async t => { await window.zeige(t); return document.getElementById("c").toDataURL("image/jpeg", 0.92); }, i / FPS);
  writeFileSync(join(ausgabe, String(i + 1).padStart(5, "0") + ".jpg"), Buffer.from(url.split(",")[1], "base64"));
  if (i % 150 === 0) console.log(`Bild ${i + 1}/${n} (${((Date.now() - start) / 1000).toFixed(0)} s)`);
}
await browser.close();
server.close();
console.log(`fertig: ${n} Bilder in ${((Date.now() - start) / 1000).toFixed(0)} s`);
