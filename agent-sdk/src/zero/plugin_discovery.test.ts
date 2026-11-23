import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";

import {
  PluginDiscoveryError,
  PluginManifestError,
  discoverPlugins,
  discoverPluginsWithErrors,
  findPlugin,
  loadPluginManifest,
  parsePluginManifest,
} from "./plugin_discovery.js";

const temporaryDirectories: string[] = [];

async function temporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "zero-plugin-discovery-"));
  temporaryDirectories.push(directory);
  return directory;
}

async function writeManifest(
  pluginPath: string,
  manifest: Record<string, unknown>,
): Promise<string> {
  await mkdir(pluginPath, { recursive: true });
  const manifestPath = join(pluginPath, "plugin.json");
  await writeFile(manifestPath, JSON.stringify(manifest), "utf8");
  return manifestPath;
}

after(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((directory) =>
      rm(directory, { recursive: true, force: true }),
    ),
  );
});

describe("plugin discovery", () => {
  it("loads a manifest with the Rust PluginManifest shape", async () => {
    const root = await temporaryDirectory();
    const manifestPath = await writeManifest(join(root, "alpha"), {
      name: "alpha",
      version: "1.2.3",
      description: "Alpha plugin",
      entrypoint: "index.js",
      permissions: ["workspace:read"],
      ignoredRustField: "ignored",
    });

    const manifest = await loadPluginManifest(manifestPath);

    assert.deepEqual(manifest, {
      name: "alpha",
      version: "1.2.3",
      description: "Alpha plugin",
      entrypoint: "index.js",
      permissions: ["workspace:read"],
    });
  });

  it("discovers plugins in deterministic path order", async () => {
    const root = await temporaryDirectory();
    await writeManifest(join(root, "beta"), {
      name: "beta",
      version: "1.0.0",
      description: "Beta plugin",
      entrypoint: "main.js",
      permissions: [],
    });
    await writeManifest(join(root, "alpha"), {
      name: "alpha",
      version: "1.0.0",
      description: "Alpha plugin",
      entrypoint: "main.js",
      permissions: [],
    });

    const plugins = await discoverPlugins(root);

    assert.deepEqual(
      plugins.map((plugin) => plugin.manifest.name),
      ["alpha", "beta"],
    );
  });

  it("reports malformed manifests without treating them as absent", async () => {
    const root = await temporaryDirectory();
    await writeManifest(join(root, "broken"), {
      name: "broken",
      version: "1.0.0",
    });

    const result = await discoverPluginsWithErrors(root);

    assert.equal(result.plugins.length, 0);
    assert.equal(result.failures.length, 1);
    assert.equal(result.failures[0]?.code, "INVALID_MANIFEST");
    await assert.rejects(
      () => discoverPlugins(root),
      PluginDiscoveryError,
    );
  });

  it("finds a plugin by its manifest name", async () => {
    const root = await temporaryDirectory();
    await writeManifest(join(root, "alpha"), {
      name: "alpha",
      version: "1.0.0",
      description: "Alpha plugin",
      entrypoint: "main.js",
      permissions: [],
    });

    const plugin = await findPlugin(root, "alpha");

    assert.equal(plugin?.manifest.version, "1.0.0");
    assert.equal(await findPlugin(root, "missing"), undefined);
  });

  it("rejects a manifest that violates the required shape", () => {
    assert.throws(
      () => parsePluginManifest({ name: "x", version: "1.0.0" }),
      PluginManifestError,
    );
  });
});
