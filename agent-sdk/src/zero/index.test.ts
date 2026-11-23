import assert from "node:assert/strict";
import { describe, it } from "node:test";

import * as zero from "./index.js";

describe("zero bridge exports", () => {
  it("exports the typed plugin discovery and health helpers", () => {
    assert.equal(typeof zero.discoverPlugins, "function");
    assert.equal(typeof zero.loadPluginManifest, "function");
    assert.equal(typeof zero.checkPluginHealth, "function");
    assert.equal(typeof zero.reportHealth, "function");
    assert.equal(typeof zero.summarizeHealth, "function");
  });
});
