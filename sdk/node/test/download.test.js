import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("missing checksum fails before extracting or launching", async (t) => {
  const cache = mkdtempSync(join(tmpdir(), "fortress-unverified-"));
  const oldCache = process.env.FORTRESS_BROWSERS_PATH;
  const oldFetch = globalThis.fetch;
  process.env.FORTRESS_BROWSERS_PATH = cache;
  globalThis.fetch = async (url) => String(url).endsWith("SHA256SUMS")
    ? new Response("not found", { status: 404 })
    : new Response("unverified bytes, not a browser or archive");
  t.after(() => {
    globalThis.fetch = oldFetch;
    if (oldCache === undefined) delete process.env.FORTRESS_BROWSERS_PATH;
    else process.env.FORTRESS_BROWSERS_PATH = oldCache;
    rmSync(cache, { recursive: true, force: true });
  });
  const { Fortress } = await import("../index.js?missing-checksum-test");
  const browser = new Fortress({ channel: "latest" });
  await assert.rejects(browser.start(), /refusing extraction/);
  assert.equal(browser.proc, null);
  assert.equal(existsSync(join(cache, browser.tag, "linux-x64", "tilion-fortress")), false);
});
