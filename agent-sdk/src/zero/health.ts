import { realpath, stat } from "node:fs/promises";
import {
  basename,
  dirname,
  isAbsolute,
  join,
  relative,
  resolve,
  sep,
} from "node:path";

import {
  PLUGIN_MANIFEST_FILENAME,
  loadPluginManifest,
  type PluginManifest,
} from "./plugin_discovery.js";

export type { DiscoveredPlugin } from "./plugin_discovery.js";

export type HealthStatus = "healthy" | "degraded" | "unhealthy" | "unknown";
export type HealthCheckStatus = "pass" | "fail" | "unknown";
export type HealthCheckName = "manifest" | "entrypoint" | "permissions";

export interface HealthCheck {
  name: HealthCheckName;
  status: HealthCheckStatus;
  detail: string;
  path?: string;
}

export interface PluginHealthReport {
  pluginName: string;
  status: HealthStatus;
  manifestPath: string;
  entrypointPath?: string;
  checks: HealthCheck[];
}

export interface HealthSummary {
  status: HealthStatus;
  total: number;
  healthy: number;
  degraded: number;
  unhealthy: number;
  unknown: number;
  reports: PluginHealthReport[];
}

/* ------------------------------------------------------------------ *
 * Health state transition machine.
 *
 * GRF: R_{t+1} = F(R_t, E_t), where R_t is the realised health state,
 * E_t is the event plus its receipt, and the tick is an explicit
 * logical counter supplied by the caller (never wall-clock time).
 *
 * The transition table is keyed ONLY by (stateKind, eventKind); the
 * receipt is evidence that gates the Healthy target, it is not a key.
 * ------------------------------------------------------------------ */

export type HealthStateKind =
  | "Healthy"
  | "Degraded"
  | "Unhealthy"
  | "Failed"
  | "Unknown";

export type HealthEventKind =
  | "HealthCheckSuccess"
  | "HealthCheckFailure"
  | "InvocationFailure"
  | "ManifestParsed"
  | "ManifestParseFailure";

/**
 * Evidence that a health check actually ran. A manifest parse is NOT a
 * health check: it produces a ManifestReceipt, which can never open the
 * Healthy target.
 */
export interface HealthCheckReceipt {
  readonly kind: "HealthCheckReceipt";
  readonly status: "pass" | "fail";
  readonly tick?: number | undefined;
  readonly check?: HealthCheckName | undefined;
  readonly detail?: string | undefined;
}

/** Evidence that a manifest was parsed. Structural evidence only. */
export interface ManifestReceipt {
  readonly kind: "ManifestReceipt";
  readonly tick?: number | undefined;
  readonly manifestPath?: string | undefined;
}

export type HealthReceipt = HealthCheckReceipt | ManifestReceipt;

export interface HealthStateFields {
  readonly tick: number;
  readonly failureCount: number;
  readonly lastEvent?: HealthEventKind | undefined;
  readonly receipt?: HealthReceipt | undefined;
}

export interface HealthyHealthState extends HealthStateFields {
  readonly kind: "Healthy";
  readonly receipt: HealthCheckReceipt;
}

export interface DegradedHealthState extends HealthStateFields {
  readonly kind: "Degraded";
}

export interface UnhealthyHealthState extends HealthStateFields {
  readonly kind: "Unhealthy";
}

export interface FailedHealthState extends HealthStateFields {
  readonly kind: "Failed";
}

export interface UnknownHealthState extends HealthStateFields {
  readonly kind: "Unknown";
}

export type HealthState =
  | HealthyHealthState
  | DegradedHealthState
  | UnhealthyHealthState
  | FailedHealthState
  | UnknownHealthState;

export interface HealthTransitionRule {
  readonly to: HealthStateKind;
  readonly failureDelta: 0 | 1;
  readonly requiresHealthCheckReceipt: boolean;
}

/**
 * Kind-only keyed transition table: HEALTH_TRANSITION_TABLE[stateKind][eventKind].
 *
 * - Healthy is reachable ONLY through HealthCheckSuccess with a passing
 *   health-check receipt (a manifest parse is not health evidence).
 * - ManifestParsed never yields Healthy; it yields UNKNOWN because a
 *   structural parse does not establish health.
 * - Failed is sticky for manifest events; only a verified health check
 *   can leave it.
 */
export const HEALTH_TRANSITION_TABLE: Readonly<
  Record<
    HealthStateKind,
    Readonly<Record<HealthEventKind, HealthTransitionRule>>
  >
> = {
  Healthy: {
    HealthCheckSuccess: {
      to: "Healthy",
      failureDelta: 0,
      requiresHealthCheckReceipt: true,
    },
    HealthCheckFailure: {
      to: "Unhealthy",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    InvocationFailure: {
      to: "Degraded",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    ManifestParsed: {
      to: "Unknown",
      failureDelta: 0,
      requiresHealthCheckReceipt: false,
    },
    ManifestParseFailure: {
      to: "Failed",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
  },
  Degraded: {
    HealthCheckSuccess: {
      to: "Healthy",
      failureDelta: 0,
      requiresHealthCheckReceipt: true,
    },
    HealthCheckFailure: {
      to: "Unhealthy",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    InvocationFailure: {
      to: "Unhealthy",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    ManifestParsed: {
      to: "Unknown",
      failureDelta: 0,
      requiresHealthCheckReceipt: false,
    },
    ManifestParseFailure: {
      to: "Failed",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
  },
  Unhealthy: {
    HealthCheckSuccess: {
      to: "Healthy",
      failureDelta: 0,
      requiresHealthCheckReceipt: true,
    },
    HealthCheckFailure: {
      to: "Unhealthy",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    InvocationFailure: {
      to: "Unhealthy",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    ManifestParsed: {
      to: "Unknown",
      failureDelta: 0,
      requiresHealthCheckReceipt: false,
    },
    ManifestParseFailure: {
      to: "Failed",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
  },
  Failed: {
    HealthCheckSuccess: {
      to: "Healthy",
      failureDelta: 0,
      requiresHealthCheckReceipt: true,
    },
    HealthCheckFailure: {
      to: "Failed",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    InvocationFailure: {
      to: "Failed",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    ManifestParsed: {
      to: "Failed",
      failureDelta: 0,
      requiresHealthCheckReceipt: false,
    },
    ManifestParseFailure: {
      to: "Failed",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
  },
  Unknown: {
    HealthCheckSuccess: {
      to: "Healthy",
      failureDelta: 0,
      requiresHealthCheckReceipt: true,
    },
    HealthCheckFailure: {
      to: "Unhealthy",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    InvocationFailure: {
      to: "Degraded",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
    ManifestParsed: {
      to: "Unknown",
      failureDelta: 0,
      requiresHealthCheckReceipt: false,
    },
    ManifestParseFailure: {
      to: "Failed",
      failureDelta: 1,
      requiresHealthCheckReceipt: false,
    },
  },
};

/**
 * Canonical seed failure counts used by the kind-only entry point.
 * Degraded/Unhealthy/Failed each encode one already observed failure;
 * Healthy/Unknown encode none.
 */
export const HEALTH_STATE_SEED_FAILURE_COUNTS: Readonly<
  Record<HealthStateKind, number>
> = {
  Healthy: 0,
  Degraded: 1,
  Unhealthy: 1,
  Failed: 1,
  Unknown: 0,
};

/** Fail-closed invariant violation. */
export class HealthTransitionViolation extends Error {
  readonly invariant: string;

  constructor(invariant: string, detail: string) {
    super(`health invariant violated [${invariant}]: ${detail}`);
    this.name = "HealthTransitionViolation";
    this.invariant = invariant;
  }
}

function assertTick(tick: number): void {
  if (!Number.isSafeInteger(tick) || tick < 0) {
    throw new HealthTransitionViolation(
      "tick_is_logical_counter",
      `tick=${String(tick)}`,
    );
  }
}

function assertFailureCount(failureCount: number): void {
  if (!Number.isSafeInteger(failureCount) || failureCount < 0) {
    throw new HealthTransitionViolation(
      "failure_count_non_negative",
      `failureCount=${String(failureCount)}`,
    );
  }
}

/**
 * A receipt opens the Healthy target only when it is a PASSING health
 * check receipt. Manifest receipts and failing receipts do not.
 */
export function isPassingHealthCheckReceipt(
  receipt: HealthReceipt | undefined,
): receipt is HealthCheckReceipt {
  return (
    receipt !== undefined &&
    receipt.kind === "HealthCheckReceipt" &&
    receipt.status === "pass"
  );
}

function stateFields(
  tick: number,
  failureCount: number,
  eventKind: HealthEventKind,
  receipt: HealthReceipt | undefined,
): HealthStateFields {
  return receipt === undefined
    ? { tick, failureCount, lastEvent: eventKind }
    : { tick, failureCount, lastEvent: eventKind, receipt };
}

function buildState(
  kind: HealthStateKind,
  eventKind: HealthEventKind,
  tick: number,
  failureCount: number,
  receipt: HealthReceipt | undefined,
): HealthState {
  const fields = stateFields(tick, failureCount, eventKind, receipt);
  switch (kind) {
    case "Healthy": {
      if (!isPassingHealthCheckReceipt(receipt)) {
        throw new HealthTransitionViolation(
          "healthy_requires_health_check_receipt",
          `event=${eventKind}`,
        );
      }
      return { ...fields, kind: "Healthy", receipt };
    }
    case "Degraded":
      return { ...fields, kind: "Degraded" };
    case "Unhealthy":
      return { ...fields, kind: "Unhealthy" };
    case "Failed":
      return { ...fields, kind: "Failed" };
    case "Unknown":
      return { ...fields, kind: "Unknown" };
    default: {
      const exhaustive: never = kind;
      throw new HealthTransitionViolation(
        "known_state_kind",
        String(exhaustive),
      );
    }
  }
}

function transitionCore(
  stateKind: HealthStateKind,
  eventKind: HealthEventKind,
  tick: number,
  receipt: HealthReceipt | undefined,
  currentFailureCount: number,
): HealthState {
  assertTick(tick);
  assertFailureCount(currentFailureCount);

  const rule = HEALTH_TRANSITION_TABLE[stateKind]?.[eventKind];
  if (rule === undefined) {
    throw new HealthTransitionViolation(
      "known_transition_pair",
      `stateKind=${String(stateKind)} eventKind=${String(eventKind)}`,
    );
  }

  const receiptValid = isPassingHealthCheckReceipt(receipt);
  const gateFailed = rule.requiresHealthCheckReceipt && !receiptValid;

  // Fail closed: an unverified success claim is UNKNOWN, never Healthy.
  const target: HealthStateKind = gateFailed ? "Unknown" : rule.to;
  const nextFailureCount = gateFailed
    ? currentFailureCount
    : currentFailureCount + rule.failureDelta;
  assertFailureCount(nextFailureCount);

  return buildState(target, eventKind, tick, nextFailureCount, receipt);
}

/**
 * F(stateKind, eventKind, tick, receipt?) -> newState.
 *
 * Kind-only entry point: the incoming failure count is the canonical seed
 * for that state kind. Use transitionHealthState to carry an observed
 * failureCount across a sequence of events.
 */
export function transitionHealth(
  stateKind: HealthStateKind,
  eventKind: HealthEventKind,
  tick: number,
  receipt?: HealthReceipt,
): HealthState {
  return transitionCore(
    stateKind,
    eventKind,
    tick,
    receipt,
    HEALTH_STATE_SEED_FAILURE_COUNTS[stateKind],
  );
}

/**
 * F(R_t, eventKind, tick, receipt?) -> R_{t+1}, preserving the carried
 * failureCount of the realised state.
 */
export function transitionHealthState(
  state: HealthState,
  eventKind: HealthEventKind,
  tick: number,
  receipt?: HealthReceipt,
): HealthState {
  if (tick < state.tick) {
    throw new HealthTransitionViolation(
      "tick_monotonic",
      `previous=${state.tick} next=${tick}`,
    );
  }
  return transitionCore(
    state.kind,
    eventKind,
    tick,
    receipt,
    state.failureCount,
  );
}

/**
 * Builds a seed state. Healthy cannot be seeded without a passing
 * health-check receipt (fail closed).
 */
export function initialHealthState(
  kind: HealthStateKind,
  tick: number,
  receipt?: HealthReceipt,
): HealthState {
  assertTick(tick);
  const failureCount = HEALTH_STATE_SEED_FAILURE_COUNTS[kind];
  switch (kind) {
    case "Healthy": {
      if (!isPassingHealthCheckReceipt(receipt)) {
        throw new HealthTransitionViolation(
          "healthy_requires_health_check_receipt",
          "initial Healthy state requires a passing health-check receipt",
        );
      }
      return { kind: "Healthy", tick, failureCount, receipt };
    }
    case "Degraded":
      return { kind: "Degraded", tick, failureCount };
    case "Unhealthy":
      return { kind: "Unhealthy", tick, failureCount };
    case "Failed":
      return { kind: "Failed", tick, failureCount };
    case "Unknown":
      return { kind: "Unknown", tick, failureCount };
    default: {
      const exhaustive: never = kind;
      throw new HealthTransitionViolation(
        "known_state_kind",
        String(exhaustive),
      );
    }
  }
}

/** Maps the transition state onto the report-level HealthStatus. */
export function healthStatusFromState(state: HealthState): HealthStatus {
  switch (state.kind) {
    case "Healthy":
      return "healthy";
    case "Degraded":
      return "degraded";
    case "Unhealthy":
      return "unhealthy";
    case "Failed":
      return "unhealthy";
    case "Unknown":
      return "unknown";
    default: {
      const exhaustive: never = state;
      throw new HealthTransitionViolation(
        "known_state_kind",
        String(exhaustive),
      );
    }
  }
}

function isInsideDirectory(root: string, candidate: string): boolean {
  const relativePath = relative(root, candidate);
  return (
    relativePath.length > 0 &&
    relativePath !== ".." &&
    !relativePath.startsWith(`..${sep}`) &&
    !isAbsolute(relativePath)
  );
}

async function inspectPlugin(
  pluginPath: string,
  manifestPath: string,
): Promise<PluginHealthReport> {
  const absolutePluginPath = resolve(pluginPath);
  const absoluteManifestPath = resolve(manifestPath);

  let manifest: PluginManifest;
  try {
    manifest = await loadPluginManifest(absoluteManifestPath);
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    return {
      pluginName: basename(absolutePluginPath),
      status: "unhealthy",
      manifestPath: absoluteManifestPath,
      checks: [
        {
          name: "manifest",
          status: "fail",
          detail,
          path: absoluteManifestPath,
        },
        {
          name: "entrypoint",
          status: "unknown",
          detail: "Entrypoint cannot be resolved without a valid manifest.",
        },
      ],
    };
  }

  const checks: HealthCheck[] = [
    {
      name: "manifest",
      status: "pass",
      detail: "Manifest shape and required fields are valid.",
      path: absoluteManifestPath,
    },
  ];

  const absoluteEntrypoint = resolve(absolutePluginPath, manifest.entrypoint);
  const entrypointIsRelative = !isAbsolute(manifest.entrypoint);
  const entrypointIsContained = isInsideDirectory(
    absolutePluginPath,
    absoluteEntrypoint,
  );

  if (!entrypointIsRelative) {
    checks.push({
      name: "entrypoint",
      status: "fail",
      detail: "Entrypoint must be relative to the plugin directory.",
      path: absoluteEntrypoint,
    });
  } else if (!entrypointIsContained) {
    checks.push({
      name: "entrypoint",
      status: "fail",
      detail: "Entrypoint escapes the plugin directory.",
      path: absoluteEntrypoint,
    });
  } else {
    let entrypointExists = false;
    try {
      const entrypointStat = await stat(absoluteEntrypoint);
      if (!entrypointStat.isFile()) {
        checks.push({
          name: "entrypoint",
          status: "fail",
          detail: "Entrypoint does not resolve to a regular file.",
          path: absoluteEntrypoint,
        });
      } else {
        entrypointExists = true;
      }
    } catch (error: unknown) {
      const detail = error instanceof Error ? error.message : String(error);
      checks.push({
        name: "entrypoint",
        status: "fail",
        detail: `Entrypoint is unavailable: ${detail}`,
        path: absoluteEntrypoint,
      });
    }

    if (entrypointExists) {
      try {
        const realRoot = await realpath(absolutePluginPath);
        const realEntrypoint = await realpath(absoluteEntrypoint);
        if (!isInsideDirectory(realRoot, realEntrypoint)) {
          checks.push({
            name: "entrypoint",
            status: "fail",
            detail: "Entrypoint resolves outside the plugin directory.",
            path: absoluteEntrypoint,
          });
        } else {
          checks.push({
            name: "entrypoint",
            status: "pass",
            detail: "Entrypoint resolves to a contained regular file.",
            path: absoluteEntrypoint,
          });
        }
      } catch (error: unknown) {
        const detail = error instanceof Error ? error.message : String(error);
        checks.push({
          name: "entrypoint",
          status: "unknown",
          detail: `Entrypoint containment could not be verified: ${detail}`,
          path: absoluteEntrypoint,
        });
      }
    }
  }

  checks.push({
    name: "permissions",
    status: "pass",
    detail: `${manifest.permissions.length} permission declaration(s) parsed.`,
  });

  const hasFailure = checks.some((check) => check.status === "fail");
  const hasUnknown = checks.some((check) => check.status === "unknown");
  const status: HealthStatus = hasFailure
    ? "unhealthy"
    : hasUnknown
      ? "unknown"
      : "healthy";

  return {
    pluginName: manifest.name,
    status,
    manifestPath: absoluteManifestPath,
    entrypointPath: absoluteEntrypoint,
    checks,
  };
}

/**
 * Reports structural health without executing plugin code.
 */
export async function checkPluginHealth(
  pluginPath: string,
): Promise<PluginHealthReport> {
  const absolutePluginPath = resolve(pluginPath);
  return inspectPlugin(
    absolutePluginPath,
    join(absolutePluginPath, PLUGIN_MANIFEST_FILENAME),
  );
}

export async function checkManifestHealth(
  manifestPath: string,
): Promise<PluginHealthReport> {
  const absoluteManifestPath = resolve(manifestPath);
  return inspectPlugin(dirname(absoluteManifestPath), absoluteManifestPath);
}

export const reportPluginHealth = checkPluginHealth;

/**
 * Pure aggregation over already measured reports. An empty evidence set is
 * UNKNOWN, never healthy.
 */
export function summarizeHealth(
  reports: readonly PluginHealthReport[],
): HealthSummary {
  const counts = {
    healthy: 0,
    degraded: 0,
    unhealthy: 0,
    unknown: 0,
  };

  for (const report of reports) {
    counts[report.status] += 1;
  }

  const total = reports.length;
  let status: HealthStatus = "unknown";

  if (total > 0) {
    if (counts.healthy === total) {
      status = "healthy";
    } else if (counts.unhealthy === total) {
      status = "unhealthy";
    } else if (counts.unknown === total) {
      status = "unknown";
    } else if (counts.degraded === total) {
      status = "degraded";
    } else {
      status = "degraded";
    }
  }

  return {
    status,
    total,
    ...counts,
    reports: [...reports],
  };
}

/**
 * Measures health for every discovered plugin and aggregates the evidence.
 */
export async function reportHealth(
  plugins: readonly {
    pluginPath: string;
    manifestPath: string;
  }[],
): Promise<HealthSummary> {
  const reports: PluginHealthReport[] = [];
  for (const plugin of plugins) {
    reports.push(await checkManifestHealth(plugin.manifestPath));
  }
  return summarizeHealth(reports);
}
