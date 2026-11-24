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

  it("throws DISCOVERY_FAILED when the plugin directory is missing", async () => {
    const missing = join(tmpdir(), "zero-plugin-missing-dir");
    await assert.rejects(
      () => discoverPluginsWithErrors(missing),
      (error: unknown) => {
        assert.ok(error instanceof PluginManifestError);
        assert.equal(error.code, "DISCOVERY_FAILED");
        return true;
      },
    );
  });

  it("returns empty discovery for a manifestless directory", async () => {
    const root = await temporaryDirectory();
    await mkdir(join(root, "empty"), { recursive: true });

    const result = await discoverPluginsWithErrors(root);

    assert.equal(result.plugins.length, 0);
    assert.equal(result.failures.length, 0);
    assert.deepEqual(await discoverPlugins(root), []);
    assert.equal(await findPlugin(root, "anything"), undefined);
  });

  it("loadPluginManifest throws READ_FAILED for a missing file", async () => {
    const missing = join(tmpdir(), "zero-plugin-missing-manifest.json");
    await assert.rejects(
      () => loadPluginManifest(missing),
      (error: unknown) => {
        assert.ok(error instanceof PluginManifestError);
        assert.equal(error.code, "READ_FAILED");
        return true;
      },
    );
  });

  it("loadPluginManifest throws INVALID_JSON for malformed content", async () => {
    const root = await temporaryDirectory();
    const manifestPath = join(root, "bad", "plugin.json");
    await mkdir(join(root, "bad"), { recursive: true });
    await writeFile(manifestPath, "{ not valid json", "utf8");

    await assert.rejects(
      () => loadPluginManifest(manifestPath),
      (error: unknown) => {
        assert.ok(error instanceof PluginManifestError);
        assert.equal(error.code, "INVALID_JSON");
        return true;
      },
    );
  });

  it("parsePluginManifest ignores unknown fields like serde", () => {
    const manifest = parsePluginManifest({
      name: "alpha",
      version: "1.0.0",
      description: "Alpha",
      entrypoint: "index.js",
      permissions: ["workspace:read"],
      rustOnlyField: "ignored",
      anotherExtra: 42,
    });

    assert.equal(manifest.name, "alpha");
    assert.equal(manifest.permissions.length, 1);
  });

  it("parsePluginManifest rejects missing entrypoint", () => {
    assert.throws(
      () =>
        parsePluginManifest({
          name: "alpha",
          version: "1.0.0",
          description: "Alpha",
          permissions: [],
        }),
      PluginManifestError,
    );
  });

  it("parsePluginManifest rejects permissions that are not an array", () => {
    assert.throws(
      () =>
        parsePluginManifest({
          name: "alpha",
          version: "1.0.0",
          description: "Alpha",
          entrypoint: "index.js",
          permissions: "workspace:read",
        }),
      PluginManifestError,
    );
  });

  it("parsePluginManifest rejects empty name", () => {
    assert.throws(
      () =>
        parsePluginManifest({
          name: "",
          version: "1.0.0",
          description: "Alpha",
          entrypoint: "index.js",
          permissions: [],
        }),
      PluginManifestError,
    );
  });

  // --- New manifest-shape validation tests (Rust/TS parity) ---

  it("parsePluginManifest rejects non-object input", () => {
    assert.throws(
      () => parsePluginManifest("not an object"),
      PluginManifestError,
    );
    assert.throws(
      () => parsePluginManifest(null),
      PluginManifestError,
    );
    assert.throws(
      () => parsePluginManifest(123),
      PluginManifestError,
    );
    assert.throws(
      () => parsePluginManifest(["array"]),
      PluginManifestError,
    );
  });

  it("parsePluginManifest rejects non-string entrypoint (number)", () => {
    assert.throws(
      () =>
        parsePluginManifest({
          name: "alpha",
          version: "1.0.0",
          description: "Alpha",
          entrypoint: 123,
          permissions: [],
        }),
      PluginManifestError,
    );
  });

  it("parsePluginManifest rejects missing version", () => {
    assert.throws(
      () =>
        parsePluginManifest({
          name: "alpha",
          description: "Alpha",
          entrypoint: "index.js",
          permissions: [],
        }),
      PluginManifestError,
    );
  });

  it("parsePluginManifest rejects missing description", () => {
    assert.throws(
      () =>
        parsePluginManifest({
          name: "alpha",
          version: "1.0.0",
          entrypoint: "index.js",
          permissions: [],
        }),
      PluginManifestError,
    );
  });

  it("parsePluginManifest rejects permissions with non-string elements", () => {
    assert.throws(
      () =>
        parsePluginManifest({
          name: "alpha",
          version: "1.0.0",
          description: "Alpha",
          entrypoint: "index.js",
          permissions: [123],
        }),
      PluginManifestError,
    );
    assert.throws(
      () =>
        parsePluginManifest({
          name: "alpha",
          version: "1.0.0",
          description: "Alpha",
          entrypoint: "index.js",
          permissions: ["valid", 456, "also-valid"],
        }),
      PluginManifestError,
    );
    assert.throws(
      () =>
        parsePluginManifest({
          name: "alpha",
          version: "1.0.0",
          description: "Alpha",
          entrypoint: "index.js",
          permissions: [null],
        }),
      PluginManifestError,
    );
  });

  // --- Rust/TS parity test ---
  // This test defines a shared fixture set. The Rust side (src/zero/loader.rs)
  // should have a corresponding test that loads the same fixtures and asserts
  // identical accept/reject decisions. The fixture list is declared here as a
  // constant so both sides can stay in sync.
  it("parity: TS accept/reject decisions match Rust loader for shared fixtures", async () => {
    const root = await temporaryDirectory();

    // Fixture: (directory name, manifest content, expectedAccept)
    const fixtures: Array<[string, Record<string, unknown>, boolean]> = [
      // Valid manifests
      [
        "valid-minimal",
        {
          name: "valid-minimal",
          version: "1.0.0",
          description: "Minimal valid plugin",
          entrypoint: "index.js",
          permissions: [],
        },
        true,
      ],
      [
        "valid-with-permissions",
        {
          name: "valid-with-permissions",
          version: "2.3.4",
          description: "Plugin with permissions",
          entrypoint: "main.js",
          permissions: ["workspace:read", "workspace:write"],
        },
        true,
      ],
      [
        "valid-extra-fields-ignored",
        {
          name: "valid-extra-fields-ignored",
          version: "1.0.0",
          description: "Extra fields should be ignored",
          entrypoint: "index.js",
          permissions: [],
          rustOnlyField: "ignored",
          anotherExtra: 42,
        },
        true,
      ],
      // Invalid: non-object (simulated by writing invalid JSON that parses to non-object)
      // Note: JSON.parse of a non-object string throws, so this is tested via INVALID_JSON path
      // Invalid: missing entrypoint
      [
        "invalid-missing-entrypoint",
        {
          name: "invalid-missing-entrypoint",
          version: "1.0.0",
          description: "Missing entrypoint",
          permissions: [],
        },
        false,
      ],
      // Invalid: entrypoint is number
      [
        "invalid-entrypoint-number",
        {
          name: "invalid-entrypoint-number",
          version: "1.0.0",
          description: "Entrypoint is number",
          entrypoint: 123,
          permissions: [],
        },
        false,
      ],
      // Invalid: missing version
      [
        "invalid-missing-version",
        {
          name: "invalid-missing-version",
          description: "Missing version",
          entrypoint: "index.js",
          permissions: [],
        },
        false,
      ],
      // Invalid: missing description
      [
        "invalid-missing-description",
        {
          name: "invalid-missing-description",
          version: "1.0.0",
          entrypoint: "index.js",
          permissions: [],
        },
        false,
      ],
      // Invalid: permissions not array
      [
        "invalid-permissions-string",
        {
          name: "invalid-permissions-string",
          version: "1.0.0",
          description: "Permissions is string",
          entrypoint: "index.js",
          permissions: "workspace:read",
        },
        false,
      ],
      // Invalid: permissions contains non-string
      [
        "invalid-permissions-non-string-element",
        {
          name: "invalid-permissions-non-string-element",
          version: "1.0.0",
          description: "Permissions has number element",
          entrypoint: "index.js",
          permissions: [123],
        },
        false,
      ],
      // Invalid: empty name
      [
        "invalid-empty-name",
        {
          name: "",
          version: "1.0.0",
          description: "Empty name",
          entrypoint: "index.js",
          permissions: [],
        },
        false,
      ],
    ];

    for (const [dirName, manifest, expectedAccept] of fixtures) {
      await writeManifest(join(root, dirName), manifest);
    }

    const result = await discoverPluginsWithErrors(root);
    const acceptedNames = new Set(result.plugins.map((p) => p.manifest.name));
    const rejectedNames = new Set(result.failures.map((f) => {
      const parts = f.manifestPath.split("/");
      return parts[parts.length - 2]; // directory name
    }));

    for (const [dirName, , expectedAccept] of fixtures) {
      if (expectedAccept) {
        assert.ok(
          acceptedNames.has(dirName),
          `Expected ${dirName} to be accepted, but it was rejected`,
        );
      } else {
        assert.ok(
          rejectedNames.has(dirName),
          `Expected ${dirName} to be rejected, but it was accepted`,
        );
      }
    }

    // Also verify total counts match
    const expectedAcceptCount = fixtures.filter(([, , accept]) => accept).length;
    const expectedRejectCount = fixtures.filter(([, , accept]) => !accept).length;
    assert.equal(result.plugins.length, expectedAcceptCount);
    assert.equal(result.failures.length, expectedRejectCount);
  });
});
