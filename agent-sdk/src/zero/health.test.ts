import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";

import {
  HEALTH_TRANSITION_TABLE,
  checkManifestHealth,
  checkPluginHealth,
  reportHealth,
  summarizeHealth,
  transitionHealth,
  transitionHealthState,
  type DiscoveredPlugin,
  type HealthCheckReceipt,
  type HealthEventKind,
  type HealthState,
  type HealthStateKind,
} from "./health.js";

const temporaryDirectories: string[] = [];

async function temporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "zero-health-"));
  temporaryDirectories.push(directory);
  return directory;
}

async function createPlugin(
  root: string,
  name: string,
  entrypoint: string,
  createEntrypoint: boolean,
): Promise<DiscoveredPlugin> {
  const pluginPath = join(root, name);
  await mkdir(pluginPath, { recursive: true });

  if (createEntrypoint) {
    await writeFile(join(pluginPath, entrypoint), "export {};\n", "utf8");
  }

  const manifestPath = join(pluginPath, "plugin.json");
  await writeFile(
    manifestPath,
    JSON.stringify({
      name,
      version: "1.0.0",
      description: `${name} plugin`,
      entrypoint,
      permissions: [],
    }),
    "utf8",
  );

  return {
    pluginPath,
    manifestPath,
    manifest: {
      name,
      version: "1.0.0",
      description: `${name} plugin`,
      entrypoint,
      permissions: [],
    },
  };
}

function readHealthSource(): string | undefined {
  for (const candidate of ["./health.ts", "./health.js"]) {
    try {
      return readFileSync(new URL(candidate, import.meta.url), "utf8");
    } catch {
      // Source layout differs in this build; tick assertions still hold.
    }
  }
  return undefined;
}

after(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((directory) =>
      rm(directory, { recursive: true, force: true }),
    ),
  );
});

describe("plugin health", () => {
  it("reports a structurally complete plugin as healthy", async () => {
    const root = await temporaryDirectory();
    const plugin = await createPlugin(root, "alpha", "index.js", true);

    const report = await checkPluginHealth(plugin.pluginPath);

    assert.equal(report.status, "healthy");
    assert.equal(report.pluginName, "alpha");
    assert.ok(report.checks.every((check) => check.status === "pass"));
  });

  it("reports a missing entrypoint as unhealthy", async () => {
    const root = await temporaryDirectory();
    const plugin = await createPlugin(root, "alpha", "missing.js", false);

    const report = await checkPluginHealth(plugin.pluginPath);

    assert.equal(report.status, "unhealthy");
    assert.equal(
      report.checks.find((check) => check.name === "entrypoint")?.status,
      "fail",
    );
  });

  it("rejects an entrypoint that escapes the plugin directory", async () => {
    const root = await temporaryDirectory();
    const plugin = await createPlugin(root, "alpha", "../outside.js", false);

    const report = await checkPluginHealth(plugin.pluginPath);

    assert.equal(report.status, "unhealthy");
    assert.match(
      report.checks.find((check) => check.name === "entrypoint")?.detail ?? "",
      /escapes/,
    );
  });

  it("reports an invalid manifest as unhealthy with an UNKNOWN entrypoint", async () => {
    const root = await temporaryDirectory();
    const pluginPath = join(root, "broken");
    await mkdir(pluginPath, { recursive: true });
    await writeFile(
      join(pluginPath, "plugin.json"),
      JSON.stringify({ name: "broken" }),
      "utf8",
    );

    const report = await checkManifestHealth(join(pluginPath, "plugin.json"));

    assert.equal(report.status, "unhealthy");
    assert.equal(
      report.checks.find((check) => check.name === "manifest")?.status,
      "fail",
    );
    assert.equal(
      report.checks.find((check) => check.name === "entrypoint")?.status,
      "unknown",
    );
  });

  it("aggregates plugin reports and preserves UNKNOWN for an empty set", async () => {
    const root = await temporaryDirectory();
    const healthy = await createPlugin(root, "alpha", "index.js", true);
    const unhealthy = await createPlugin(root, "beta", "missing.js", false);

    const summary = await reportHealth([healthy, unhealthy]);

    assert.equal(summary.total, 2);
    assert.equal(summary.healthy, 1);
    assert.equal(summary.unhealthy, 1);
    assert.equal(summary.status, "degraded");
    assert.equal(summarizeHealth([]).status, "unknown");
  });
});

describe("health status transitions", () => {
  const PASSING_RECEIPT: HealthCheckReceipt = {
    kind: "HealthCheckReceipt",
    status: "pass",
    tick: 7,
    check: "entrypoint",
    detail: "health check completed",
  };

  it("moves Degraded to Unhealthy on InvocationFailure and increments failureCount", () => {
    const next = transitionHealth("Degraded", "InvocationFailure", 7);

    assert.equal(next.kind, "Unhealthy");
    assert.equal(next.failureCount, 2);
    assert.equal(next.tick, 7);
    assert.equal(next.lastEvent, "InvocationFailure");
  });

  it("keeps Failed on ManifestParsed", () => {
    const next = transitionHealth("Failed", "ManifestParsed", 3);

    assert.equal(next.kind, "Failed");
    assert.equal(next.failureCount, 1);
    assert.equal(next.tick, 3);
    assert.equal(next.lastEvent, "ManifestParsed");
  });

  it("reaches Healthy only through HealthCheckSuccess with a health-check receipt", () => {
    const fromManifest = transitionHealth("Unknown", "ManifestParsed", 4);
    assert.notEqual(fromManifest.kind, "Healthy");

    const withoutReceipt = transitionHealth("Unknown", "HealthCheckSuccess", 4);
    assert.notEqual(withoutReceipt.kind, "Healthy");
    assert.equal(withoutReceipt.kind, "Unknown");

    const withManifestReceipt = transitionHealth(
      "Unknown",
      "HealthCheckSuccess",
      4,
      { kind: "ManifestReceipt", tick: 4, manifestPath: "plugin.json" },
    );
    assert.notEqual(withManifestReceipt.kind, "Healthy");

    const healthy = transitionHealth(
      "Unknown",
      "HealthCheckSuccess",
      4,
      PASSING_RECEIPT,
    );
    assert.equal(healthy.kind, "Healthy");
    if (healthy.kind !== "Healthy") {
      assert.fail("expected a Healthy state");
    }
    assert.equal(healthy.receipt.status, "pass");
    assert.equal(healthy.failureCount, 0);
  });

  it("does not accept a failing health-check receipt as Healthy", () => {
    const next = transitionHealth("Unknown", "HealthCheckSuccess", 5, {
      kind: "HealthCheckReceipt",
      status: "fail",
      tick: 5,
    });

    assert.notEqual(next.kind, "Healthy");
    assert.equal(next.kind, "Unknown");
  });

  it("carries failureCount through a stateful sequence", () => {
    const first = transitionHealth("Healthy", "InvocationFailure", 1);
    assert.equal(first.kind, "Degraded");
    assert.equal(first.failureCount, 1);

    const second = transitionHealthState(first, "InvocationFailure", 2);
    assert.equal(second.kind, "Unhealthy");
    assert.equal(second.failureCount, 2);

    const third = transitionHealthState(second, "InvocationFailure", 3);
    assert.equal(third.kind, "Unhealthy");
    assert.equal(third.failureCount, 3);
  });

  it("does not mutate the input state", () => {
    const degraded: HealthState = {
      kind: "Degraded",
      tick: 1,
      failureCount: 1,
      lastEvent: "InvocationFailure",
    };
    const snapshot = { ...degraded };

    const next = transitionHealthState(degraded, "InvocationFailure", 2);

    assert.deepEqual(degraded, snapshot);
    assert.equal(next.failureCount, 2);
  });

  it("uses the supplied tick and never reads wall-clock time", () => {
    const next = transitionHealth(
      "Unknown",
      "HealthCheckSuccess",
      99,
      PASSING_RECEIPT,
    );
    assert.equal(next.tick, 99);

    const source = readHealthSource();
    if (source !== undefined) {
      assert.doesNotMatch(source, /Date\.now\s*\(/);
    }
  });

  it("rejects invalid ticks and backwards ticks", () => {
    assert.throws(
      () => transitionHealth("Unknown", "ManifestParsed", -1),
      /tick/,
    );
    assert.throws(
      () => transitionHealth("Unknown", "ManifestParsed", 1.5),
      /tick/,
    );

    const healthy: HealthState = {
      kind: "Healthy",
      tick: 10,
      failureCount: 0,
      lastEvent: "HealthCheckSuccess",
      receipt: PASSING_RECEIPT,
    };
    assert.throws(
      () => transitionHealthState(healthy, "ManifestParsed", 9),
      /tick/,
    );
  });

  it("keys the transition table by (stateKind, eventKind) and gates Healthy", () => {
    const stateKinds: readonly HealthStateKind[] = [
      "Healthy",
      "Degraded",
      "Unhealthy",
      "Failed",
      "Unknown",
    ];
    const eventKinds: readonly HealthEventKind[] = [
      "HealthCheckSuccess",
      "HealthCheckFailure",
      "InvocationFailure",
      "ManifestParsed",
      "ManifestParseFailure",
    ];

    for (const stateKind of stateKinds) {
      for (const eventKind of eventKinds) {
        const rule = HEALTH_TRANSITION_TABLE[stateKind][eventKind];
        assert.ok(rule, `missing transition rule for ${stateKind}/${eventKind}`);
        if (rule.to === "Healthy") {
          assert.equal(eventKind, "HealthCheckSuccess");
          assert.equal(rule.requiresHealthCheckReceipt, true);
        }
      }
    }
  });

  it("maps a health-check failure to Unhealthy with an incremented failureCount", () => {
    const next = transitionHealth("Healthy", "HealthCheckFailure", 6, {
      kind: "HealthCheckReceipt",
      status: "fail",
      tick: 6,
    });

    assert.equal(next.kind, "Unhealthy");
    assert.equal(next.failureCount, 1);
  });
});
