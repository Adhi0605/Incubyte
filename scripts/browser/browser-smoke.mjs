#!/usr/bin/env node
/**
 * Actual Chrome QA, isolated from developer databases and running servers.
 * Reproduce from the repository root:
 *   npm ci --prefix scripts/browser --ignore-scripts
 *   npm test --prefix scripts/browser
 * Requires the backend .venv, frontend dependencies, and /usr/bin/google-chrome.
 * Always builds React, snapshots dist, and starts its own FastAPI on a free port.
 * Screenshots/report/logs survive under /tmp; owned processes and DB are removed.
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import { access, cp, mkdtemp, open, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const CHROME = '/usr/bin/google-chrome';
const artifacts = await mkdtemp(path.join(os.tmpdir(), 'forecourt-browser-qa-'));
const temporary = await mkdtemp(path.join(os.tmpdir(), 'forecourt-browser-data-'));
const children = new Set();
const pages = [];
const expectedFailures = new Set();
const report = {
  status: 'running', startedAt: new Date().toISOString(), browserExecutable: CHROME,
  artifacts, checks: [], screenshots: [], pageErrors: [], consoleErrors: [],
  httpErrors: [], failedRequests: [], overflowChecks: [], cleanup: {},
};
let browser;
let cleanupPromise;
let currentStep = 'initialization';
let base;

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(label, check, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await check()) return;
    await delay(100);
  }
  throw new Error(`Timed out: ${label}`);
}
async function step(label, run) {
  currentStep = label;
  const start = Date.now();
  const details = await run();
  report.checks.push({ name: label, status: 'passed', milliseconds: Date.now() - start, details });
  console.log(`PASS ${label}`);
}
function launch(command, args, options) {
  const child = spawn(command, args, { detached: true, ...options });
  children.add(child);
  child.once('exit', () => children.delete(child));
  return child;
}
async function terminate(child) {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((resolve) => child.once('exit', resolve));
  try { process.kill(-child.pid, 'SIGTERM'); } catch (error) {
    if (error.code !== 'ESRCH') throw error;
  }
  await Promise.race([exited, delay(3000)]);
  if (child.exitCode === null && child.signalCode === null) {
    try { process.kill(-child.pid, 'SIGKILL'); } catch (error) {
      if (error.code !== 'ESRCH') throw error;
    }
    await exited;
  }
}
async function cleanup() {
  if (!cleanupPromise) cleanupPromise = (async () => {
    try { await browser?.close(); } finally {
      await Promise.all([...children].map(terminate));
      report.cleanup.ownedProcessesStopped = children.size === 0;
      await rm(temporary, { recursive: true, force: true });
      report.cleanup.temporaryDataRemoved = true;
    }
  })();
  return cleanupPromise;
}
async function saveReport() {
  report.finishedAt = new Date().toISOString();
  await writeFile(path.join(artifacts, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
}
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, async () => {
    report.status = 'interrupted';
    report.failure = { step: currentStep, message: signal };
    try { await cleanup(); } finally { await saveReport(); process.exit(signal === 'SIGINT' ? 130 : 143); }
  });
}

async function frontendHash() {
  const hash = createHash('sha256');
  async function visit(relative) {
    const full = path.join(ROOT, 'frontend', relative);
    const entries = await readdir(full, { withFileTypes: true });
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const name = path.join(relative, entry.name);
      if (entry.isDirectory()) await visit(name);
      else { hash.update(name); hash.update(await readFile(path.join(ROOT, 'frontend', name))); }
    }
  }
  await visit('src');
  await visit('public');
  for (const name of ['package.json', 'package-lock.json', 'index.html', 'vite.config.js']) {
    hash.update(name); hash.update(await readFile(path.join(ROOT, 'frontend', name)));
  }
  return hash.digest('hex');
}
async function buildFrontend() {
  const log = await open(path.join(artifacts, 'build.log'), 'w');
  try {
    for (let attempt = 1; attempt <= 3; attempt++) {
      const before = await frontendHash();
      const child = launch('npm', ['run', 'build', '--prefix', 'frontend'], {
        cwd: ROOT, stdio: ['ignore', log.fd, log.fd],
      });
      const code = await new Promise((resolve, reject) => {
        child.once('error', reject); child.once('exit', resolve);
      });
      assert.equal(code, 0, `Frontend build failed; see ${path.join(artifacts, 'build.log')}`);
      const after = await frontendHash();
      if (before === after) {
        await cp(path.join(ROOT, 'frontend/dist'), path.join(temporary, 'dist'), { recursive: true });
        assert.equal(after, await frontendHash(), 'Frontend changed while copying its build; retry after edits settle');
        return { sourceHash: after, attempts: attempt };
      }
      console.log('Frontend changed during build; rebuilding the latest source.');
    }
    throw new Error('Frontend changed during three builds; rerun when source is stable');
  } finally { await log.close(); }
}
async function freePort() {
  const listener = net.createServer();
  await new Promise((resolve, reject) => { listener.once('error', reject); listener.listen(0, '127.0.0.1', resolve); });
  const port = listener.address().port;
  await new Promise((resolve, reject) => listener.close((error) => error ? reject(error) : resolve()));
  return port;
}
async function startServer() {
  const port = await freePort();
  const env = {
    ...process.env, DATABASE_PATH: path.join(temporary, 'inventory.sqlite3'),
    JWT_SECRET: randomBytes(48).toString('hex'), FRONTEND_DIST: path.join(temporary, 'dist'),
    PYTHONDONTWRITEBYTECODE: '1', PYTHONUNBUFFERED: '1',
  };
  delete env.DATABASE_URL;
  delete env.ADMIN_EMAIL;
  delete env.ADMIN_PASSWORD;
  const log = await open(path.join(artifacts, 'server.log'), 'w');
  let server;
  try {
    server = launch(path.join(ROOT, '.venv/bin/python'), [
      '-m', 'uvicorn', 'app.main:production_app', '--factory', '--host', '127.0.0.1', '--port', String(port),
    ], { cwd: path.join(ROOT, 'backend'), env, stdio: ['ignore', log.fd, log.fd] });
  } finally { await log.close(); }
  let spawnError;
  server.once('error', (error) => { spawnError = error; });
  base = `http://127.0.0.1:${port}`;
  await until('isolated API readiness', async () => {
    if (spawnError) throw spawnError;
    assert.equal(server.exitCode, null, `Owned FastAPI exited; see ${path.join(artifacts, 'server.log')}`);
    assert.equal(server.signalCode, null, 'Owned FastAPI was terminated before readiness');
    try {
      const response = await fetch(`${base}/api/health`, { signal: AbortSignal.timeout(1000) });
      return response.ok && (await response.json()).status === 'ok';
    } catch { return false; }
  }, 30000);
  const spa = await fetch(base);
  assert.equal(spa.status, 200);
  assert.match(await spa.text(), /id="root"/);
  report.origin = base;
  return { origin: base, pid: server.pid, database: 'disposable', sameOrigin: true };
}
function errorKey(label, method, pathname) { return `${label}:${method}:${pathname}`; }
async function makePage(label) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 }, locale: 'en-IN', timezoneId: 'UTC',
    reducedMotion: 'reduce', deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.setDefaultNavigationTimeout(30000);
  page.on('pageerror', (error) => report.pageErrors.push({ context: label, message: error.message }));
  page.on('console', (message) => {
    if (message.type() === 'error') report.consoleErrors.push({ context: label, text: message.text(), url: message.location().url });
  });
  page.on('requestfailed', (request) => {
    if (request.failure()?.errorText !== 'net::ERR_ABORTED')
      report.failedRequests.push({ context: label, url: request.url(), error: request.failure()?.errorText });
  });
  page.on('response', (response) => {
    if (response.status() >= 400) {
      const pathname = new URL(response.url()).pathname;
      report.httpErrors.push({
        context: label, method: response.request().method(), path: pathname, status: response.status(),
        expected: expectedFailures.has(errorKey(label, response.request().method(), pathname)) ||
                  (pathname === '/favicon.ico' && response.status() === 404),
      });
    }
  });
  pages.push({ page, label });
  return page;
}
async function screenshot(page, filename, fullPage = true) {
  await page.evaluate(async () => { await document.fonts.ready; });
  const target = path.join(artifacts, filename);
  await page.screenshot({ path: target, fullPage, animations: 'disabled' });
  report.screenshots.push(target);
  return target;
}
async function responseAction(page, pathname, method, action, status = 200, query = {}) {
  const pending = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === `/api${pathname}` && response.request().method() === method &&
      Object.entries(query).every(([key, value]) => url.searchParams.get(key) === String(value));
  });
  await action();
  const response = await pending;
  if (response.status() !== status) {
    throw new Error(`${method} ${pathname}: expected ${status}, received ${response.status()}: ${await response.text()}`);
  }
  return status === 204 ? null : response.json();
}
async function inventory(page, action, query = {}) {
  const result = await responseAction(page, '/vehicles/search', 'GET', action, 200, query);
  await until('inventory cards match server response', async () =>
    await page.locator('article.vehicle-card').count() === result.items.length &&
    (await page.locator('.results-line').innerText()).includes(`of ${result.total} vehicles`));
  return result;
}
async function register(page, label) {
  await page.goto(base);
  await page.getByRole('button', { name: 'Create an account', exact: true }).click();
  await page.getByLabel('Email address', { exact: true }).fill(`browser-${label}-${randomBytes(6).toString('hex')}@example.com`);
  await page.getByLabel('Password', { exact: true }).fill(`Browser-${randomBytes(20).toString('hex')}!9`);
  let session;
  const listing = await inventory(page, async () => {
    session = await responseAction(page, '/auth/register', 'POST',
      () => page.getByRole('button', { name: 'Create account', exact: true }).click(), 201);
  });
  assert.equal(listing.total, 200);
  assert.equal(listing.items.length, 12);
  assert.equal(session.user.role, 'admin');
  assert.equal(await page.getByRole('button', { name: /^Inventory/ }).getAttribute('aria-current'), 'page');
  return { session, listing };
}
async function api(page, session, pathname, { method = 'GET', body, status = 200 } = {}) {
  const label = pages.find((item) => item.page === page).label;
  if (status >= 400) expectedFailures.add(errorKey(label, method, `/api${pathname.split('?')[0]}`));
  const result = await page.evaluate(async ({ token, pathname, method, body }) => {
    const response = await fetch(`/api${pathname}`, {
      method, headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    return { status: response.status, body: response.status === 204 ? null : await response.json() };
  }, { token: session.access_token, pathname, method, body });
  assert.equal(result.status, status, `${method} ${pathname}: ${JSON.stringify(result.body)}`);
  return result.body;
}
async function allVehicles(page, session) {
  const rows = [];
  for (let current = 1; current <= 2; current++) {
    const result = await api(page, session, `/vehicles?page=${current}&page_size=100`);
    assert.equal(result.total, 200);
    rows.push(...result.items);
  }
  assert.equal(new Set(rows.map((vehicle) => vehicle.id)).size, 200);
  return rows;
}
async function assertPhotos(page, vehicles) {
  const urls = [...new Set(vehicles.flatMap((vehicle) => vehicle.images.map((image) => image.url)))];
  assert.ok(urls.length >= 25);
  assert.ok(urls.every((url) => url.startsWith('/cars/')));
  const decoded = await page.evaluate(async (urls) => Promise.all(urls.map(async (url) => {
    const image = new Image(); image.src = url;
    await image.decode();
    return { url, width: image.naturalWidth, height: image.naturalHeight };
  })), urls);
  assert.ok(decoded.every((image) => image.width > 300 && image.height > 200));
  const images = page.locator('article.vehicle-card img.vehicle-photo');
  assert.equal(await images.count(), 12);
  for (const image of await images.all()) {
    await image.scrollIntoViewIfNeeded();
    await until('visible listing photograph loads', () => image.evaluate((element) => element.complete && element.naturalWidth > 0));
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  return { listings: vehicles.length, decodedLocalPhotos: decoded.length, renderedCardPhotos: 12 };
}
async function noOverflow(page, label) {
  const dimensions = await page.evaluate(() => {
    const dialog = document.querySelector('dialog[open]');
    const width = innerWidth;
    return {
      viewport: width, document: document.documentElement.scrollWidth, body: document.body.scrollWidth,
      dialog: dialog ? { client: dialog.clientWidth, scroll: dialog.scrollWidth, left: dialog.getBoundingClientRect().left,
        right: dialog.getBoundingClientRect().right } : null,
      offenders: [...document.querySelectorAll('body *')].filter((element) => {
        const box = element.getBoundingClientRect();
        return box.width && (box.right > width + 1 || box.left < -1) && getComputedStyle(element).position !== 'absolute';
      }).slice(0, 12).map((element) => ({ tag: element.tagName, class: element.className?.baseVal ?? element.className })),
    };
  });
  report.overflowChecks.push({ label, ...dimensions });
  assert.ok(Math.max(dimensions.document, dimensions.body) <= dimensions.viewport + 1,
    `${label}: horizontal page overflow ${JSON.stringify(dimensions)}`);
  if (dimensions.dialog) {
    assert.ok(dimensions.dialog.scroll <= dimensions.dialog.client + 1, `${label}: dialog has horizontal overflow`);
    assert.ok(dimensions.dialog.left >= -1 && dimensions.dialog.right <= dimensions.viewport + 1, `${label}: dialog escapes viewport`);
  }
}
async function openDetails(page, index, vehicle) {
  const details = await responseAction(page, `/vehicles/${vehicle.id}`, 'GET',
    () => page.locator('article.vehicle-card').nth(index).getByRole('button', { name: 'View details' }).click());
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('heading', { name: `${vehicle.make} ${vehicle.model}`, exact: true }).waitFor();
  assert.ok((await dialog.innerText()).includes(details.images[0].credit));
  assert.ok((await dialog.innerText()).includes(details.images[0].license));
  assert.match(await dialog.getByRole('link', { name: /Manufacturer \/ model information/ }).getAttribute('href'), /^https:\/\//);
  assert.match(await dialog.getByRole('link', { name: /Photo source/ }).getAttribute('href'), /^https:\/\/commons\.wikimedia\.org\//);
  await until('detail photograph loads', () => dialog.locator('img.vehicle-photo').first().evaluate((image) => image.complete && image.naturalWidth > 0));
  return dialog;
}
async function closeDetails(page) {
  await page.getByRole('dialog').getByRole('button', { name: 'Close dialog' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
}
async function analyticsToday(page) {
  await responseAction(page, '/analytics', 'GET', () => page.getByRole('button', { name: 'Analytics', exact: true }).click());
  const today = new Date().toISOString().slice(0, 10);
  await page.getByLabel('From date', { exact: true }).fill(today);
  await page.getByLabel('To date', { exact: true }).fill(today);
  const result = await responseAction(page, '/analytics', 'GET',
    () => page.getByRole('button', { name: 'Apply dates' }).click(), 200, { start_date: today, end_date: today });
  await until('today units sold render', async () => {
    const stat = page.locator('.analytics-stats .stat').filter({ has: page.getByText('Units sold', { exact: true }) });
    return await stat.locator('strong').innerText() === String(result.summary.units_sold);
  });
  return result;
}

try {
  await access(CHROME);
  await access(path.join(ROOT, '.venv/bin/python'));
  await step('Fresh stable frontend build', buildFrontend);
  await step('Isolated same-origin FastAPI server', startServer);
  browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--disable-dev-shm-usage'] });
  report.browserVersion = browser.version();
  const owner = await makePage('owner');
  const independent = await makePage('independent');
  let first, second, ownerRows, independentRows;
  await step('Two independent browser registrations and private 200-car catalogs', async () => {
    first = await register(owner, 'owner');
    second = await register(independent, 'independent');
    assert.notEqual(first.session.user.workspace_id, second.session.user.workspace_id);
    assert.notEqual(first.session.access_token, second.session.access_token);
    ownerRows = await allVehicles(owner, first.session);
    independentRows = await allVehicles(independent, second.session);
    const otherIds = new Set(independentRows.map((vehicle) => vehicle.id));
    assert.ok(ownerRows.every((vehicle) => !otherIds.has(vehicle.id)));
    return { workspaces: [first.session.user.workspace_id, second.session.user.workspace_id], listingsEach: 200, disjointIds: true };
  });
  await step('Real local photographs decode and visible cards load', async () => {
    const details = await assertPhotos(owner, ownerRows);
    await noOverflow(owner, 'desktop inventory');
    await screenshot(owner, 'desktop-inventory.png');
    return details;
  });
  await step('Vehicle details show source credit, license and HTTPS manufacturer link', async () => {
    await openDetails(owner, 0, first.listing.items[0]);
    await noOverflow(owner, 'desktop details');
    await screenshot(owner, 'desktop-details.png', false);
    await closeDetails(owner);
  });
  let listing;
  await step('New/used filters and server pagination', async () => {
    for (const condition of ['new', 'used']) {
      await owner.getByLabel('Condition', { exact: true }).selectOption(condition);
      const filtered = await inventory(owner, () => owner.getByRole('button', { name: 'Search', exact: true }).click(), { condition, page: 1 });
      assert.equal(filtered.total, 100);
      assert.ok(filtered.items.every((vehicle) => vehicle.condition === condition));
      await until(`${condition} badges render`, async () =>
        (await owner.locator('article.vehicle-card .condition-badge').allTextContents()).every((text) => text.toLowerCase() === condition));
    }
    const pageTwo = await inventory(owner, () => owner.getByRole('button', { name: 'Next page', exact: true }).click(), { page: 2, condition: 'used' });
    assert.equal(pageTwo.page, 2);
    assert.match(await owner.getByRole('navigation', { name: 'Inventory pages' }).innerText(), /Page 2 of 9/);
    listing = await inventory(owner, () => owner.getByRole('button', { name: 'Clear filters' }).click(), { page: 1 });
    assert.equal(listing.total, 200);
  });
  const targetIndex = listing.items.findIndex((vehicle) => vehicle.condition === 'used' && vehicle.quantity === 1);
  assert.ok(targetIndex >= 0, 'First page needs an available used car');
  const target = listing.items[targetIndex];
  const counterpart = independentRows.find((vehicle) => vehicle.stock_number === target.stock_number);
  assert.equal(counterpart.quantity, 1);
  await step('Browser purchase updates stock and only its workspace today analytics', async () => {
    const today = new Date().toISOString().slice(0, 10);
    const filter = `/analytics?start_date=${today}&end_date=${today}`;
    assert.equal((await api(owner, first.session, filter)).summary.units_sold, 0);
    assert.equal((await api(independent, second.session, filter)).summary.units_sold, 0);
    await owner.locator('article.vehicle-card').nth(targetIndex).getByRole('button', { name: 'Purchase', exact: true }).click();
    const purchased = await responseAction(owner, `/vehicles/${target.id}/purchase`, 'POST',
      () => owner.getByRole('dialog').getByRole('button', { name: 'Confirm purchase' }).click());
    assert.equal(purchased.quantity, 0);
    await owner.getByRole('dialog').waitFor({ state: 'hidden' });
    await until('purchased used car is disabled', () => owner.locator('article.vehicle-card').nth(targetIndex)
      .getByRole('button', { name: 'Out of stock', exact: true }).isDisabled());
    const todaySales = await analyticsToday(owner);
    assert.equal(todaySales.summary.units_sold, 1);
    assert.equal(todaySales.summary.recorded_sales, target.price);
    assert.equal((await api(independent, second.session, filter)).summary.units_sold, 0);
    assert.equal((await api(independent, second.session, `/vehicles/${counterpart.id}`)).quantity, 1);
    await screenshot(owner, 'desktop-analytics-today.png');
    await owner.getByRole('button', { name: /^Inventory/ }).click();
    await owner.locator('article.vehicle-card').first().waitFor();
    return { vehicleId: target.id, before: 1, after: 0, ownTodayUnits: 1, independentTodayUnits: 0 };
  });
  await step('Archive persists original ID/stock and is isolated across browser contexts', async () => {
    await owner.locator('article.vehicle-card').nth(targetIndex).getByRole('button', { name: 'Delete', exact: true }).click();
    await responseAction(owner, `/vehicles/${target.id}`, 'DELETE',
      () => owner.getByRole('dialog').getByRole('button', { name: 'Archive vehicle', exact: true }).click(), 204);
    await owner.getByRole('dialog').waitFor({ state: 'hidden' });
    await until('active inventory decreases to 199', async () => (await owner.locator('.results-line').innerText()).includes('of 199 vehicles'));
    const archived = await responseAction(owner, '/vehicles/archived', 'GET',
      () => owner.getByRole('button', { name: 'Archived vehicles', exact: true }).click());
    assert.equal(archived.length, 1);
    assert.equal(archived[0].id, target.id);
    assert.equal(archived[0].quantity, 0);
    await owner.getByRole('button', { name: 'Restore', exact: true }).waitFor();
    await screenshot(owner, 'desktop-archive.png');
    await owner.setViewportSize({ width: 390, height: 844 });
    await noOverflow(owner, '390px archived inventory');
    await screenshot(owner, 'mobile-archive-390.png');
    const foreignArchive = await responseAction(independent, '/vehicles/archived', 'GET',
      () => independent.getByRole('button', { name: 'Archived vehicles', exact: true }).click());
    assert.deepEqual(foreignArchive, []);
    await independent.getByRole('heading', { name: 'No archived vehicles.' }).waitFor();
    await api(independent, second.session, `/vehicles/${target.id}`, { status: 404 });
    await api(independent, second.session, `/vehicles/${target.id}/restore`, { method: 'POST', status: 404 });
    await api(independent, second.session, `/vehicles/${target.id}`, { method: 'DELETE', status: 404 });
    return { archivedId: target.id, preservedQuantity: 0, independentArchive: [], foreignReadRestoreDelete: 404 };
  });
  await step('Restore through mobile UI preserves ID/stock and restores 200 active listings', async () => {
    await owner.getByRole('button', { name: 'Restore', exact: true }).click();
    const restored = await responseAction(owner, `/vehicles/${target.id}/restore`, 'POST',
      () => owner.getByRole('dialog').getByRole('button', { name: 'Confirm restore', exact: true }).click());
    assert.equal(restored.id, target.id);
    assert.equal(restored.quantity, 0);
    assert.equal(restored.deleted_at, null);
    await owner.getByRole('heading', { name: 'No archived vehicles.' }).waitFor();
    await owner.getByRole('button', { name: /^Inventory/ }).click();
    await owner.locator('article.vehicle-card').first().waitFor();
    await until('restored inventory shows 200 vehicles', async () => (await owner.locator('.results-line').innerText()).includes('of 200 vehicles'));
    assert.equal((await api(independent, second.session, `/vehicles/${counterpart.id}`)).quantity, 1);
    assert.equal((await api(independent, second.session, '/vehicles')).total, 200);
    await noOverflow(owner, '390px restored inventory');
    await screenshot(owner, 'mobile-inventory-390.png');
  });
  await step('390px detail and analytics layouts have no horizontal overflow', async () => {
    await openDetails(owner, targetIndex, target);
    await noOverflow(owner, '390px vehicle details');
    await screenshot(owner, 'mobile-details-390.png', false);
    await closeDetails(owner);
    const summary = await analyticsToday(owner);
    assert.equal(summary.summary.units_sold, 1);
    await noOverflow(owner, '390px analytics');
    await screenshot(owner, 'mobile-analytics-390.png');
  });
  await step('No unexpected browser exceptions or failed application requests', async () => {
    assert.deepEqual(report.pageErrors, []);
    assert.deepEqual(report.failedRequests, []);
    assert.deepEqual(report.httpErrors.filter((error) => !error.expected), []);
    const unexpectedConsole = report.consoleErrors.filter((error) => {
      let pathname;
      try { pathname = new URL(error.url).pathname; } catch { return true; }
      return !/^Failed to load resource:/.test(error.text) ||
        (pathname !== '/favicon.ico' && !report.httpErrors.some((http) => http.expected && http.path === pathname && http.context === error.context));
    });
    assert.deepEqual(unexpectedConsole, []);
    return { expectedCrossWorkspace404s: report.httpErrors.filter((error) => error.expected && error.path.startsWith('/api/')).length };
  });
  report.status = 'passed';
} catch (error) {
  report.status = 'failed';
  report.failure = { step: currentStep, message: error.message, stack: error.stack };
  console.error(`FAIL ${currentStep}: ${error.stack}`);
  for (const { page, label } of pages) {
    if (!page.isClosed()) {
      try { await screenshot(page, `failure-${label}.png`); } catch { /* Original failure stays primary. */ }
    }
  }
  process.exitCode = 1;
} finally {
  try { await cleanup(); } catch (error) {
    report.status = 'failed';
    report.cleanup.error = error.message;
    console.error(`Cleanup failed: ${error.message}`);
    process.exitCode = 1;
  }
  await saveReport();
  console.log(`Browser QA ${report.status}: ${report.checks.length} checks. Report: ${path.join(artifacts, 'report.json')}`);
  for (const filename of report.screenshots) console.log(`Screenshot: ${filename}`);
  console.log(`Cleanup: ${JSON.stringify(report.cleanup)}`);
}
