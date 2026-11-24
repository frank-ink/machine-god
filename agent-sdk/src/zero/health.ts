import { readFile, realpath, stat } from "node:fs/promises";
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

/* ------------------------------------------------------------------ *
 * Logical clock injection (wall-clock guard).
 *
 * GRF: precedence is the FUNCTIONAL order (turn/journal/tick), never
 * wall-clock time. This module never reads the host clock: the tick is
 * always injected by the caller through a LogicalClock. A fixed logical
 * clock makes R_{t+1} a pure, replayable function of
 * (R_t, event, receipt).
 * ------------------------------------------------------------------ */

export interface LogicalClock {
  readonly kind: "LogicalClock";
  readonly now: () => number;
}

/** A deterministic clock that always yields the same logical tick. */
export function fixedLogicalClock(tick: number): LogicalClock {
  assertTick(tick);
  const clock: LogicalClock = { kind: "LogicalClock", now: () => tick };
  return Object.freeze(clock);
}

function assertLogicalClock(clock: unknown): asserts clock is LogicalClock {
  if (typeof clock !== "object" || clock === null) {
    throw new HealthTransitionViolation(
      "known_clock_kind",
      "clock must be a LogicalClock",
    );
  }
  const candidate = clock as { kind?: unknown; now?: unknown };
  if (
    candidate.kind !== "LogicalClock" ||
    typeof candidate.now !== "function"
  ) {
    throw new HealthTransitionViolation(
      "known_clock_kind",
      "clock must be a LogicalClock",
    );
  }
}

function isClockLike(value: unknown): value is LogicalClock {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  return typeof (value as { now?: unknown }).now === "function";
}

/**
 * F(R_t, eventKind, clock, receipt?) -> R_{t+1}.
 *
 * The tick is read from the injected logical clock only. A clock that
 * does not yield a valid logical tick fails closed.
 */
export function transitionHealthWithClock(
  state: HealthState,
  eventKind: HealthEventKind,
  clock: LogicalClock,
  receipt?: HealthReceipt | undefined,
): HealthState;
/**
 * F(R_t, eventKind, receipt, clock) -> R_{t+1} (argument-order tolerant).
 */
export function transitionHealthWithClock(
  state: HealthState,
  eventKind: HealthEventKind,
  receipt: HealthReceipt | undefined,
  clock: LogicalClock,
): HealthState;
export function transitionHealthWithClock(
  state: HealthState,
  eventKind: HealthEventKind,
  third: LogicalClock | HealthReceipt | undefined,
  fourth?: LogicalClock | HealthReceipt | undefined,
): HealthState {
  const thirdIsClock = isClockLike(third);
  const clock = (thirdIsClock ? third : fourth) as LogicalClock | undefined;
  const receipt = (thirdIsClock ? fourth : third) as HealthReceipt | undefined;
  assertLogicalClock(clock);
  const tick = clock.now();
  assertTick(tick);
  return transitionHealthState(state, eventKind, tick, receipt);
}

/**
 * Canonical, key-sorted serialisation of R_{t+1}. Two runs with
 * identical inputs must produce byte-identical output.
 */
export function canonicalHealthState(state: HealthState): string {
  return JSON.stringify(canonicalizeValue(state));
}

function canonicalizeValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => canonicalizeValue(item));
  }
  if (typeof value === "object" && value !== null) {
    const source = value as Record<string, unknown>;
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(source).sort()) {
      const entry = source[key];
      if (entry !== undefined) {
        sorted[key] = canonicalizeValue(entry);
      }
    }
    return sorted;
  }
  return value;
}

/* ------------------------------------------------------------------ *
 * Entrypoint containment.
 *
 * Compound verdict: the entrypoint is either Contained, a containment
 * Violation (absolute path, lexical escape, or symlink escape), not
 * available, or unverified. A Violation also invalidates the manifest
 * check: the manifest declares an entrypoint outside the plugin root.
 * ------------------------------------------------------------------ */

export type EntrypointInspection =
  | {
      readonly kind: "Contained";
      readonly path: string;
      readonly detail: string;
    }
  | {
      readonly kind: "Violation";
      readonly path: string;
      readonly detail: string;
    }
  | {
      readonly kind: "Unavailable";
      readonly path: string;
      readonly detail: string;
    }
  | {
      readonly kind: "Unverified";
      readonly path: string;
      readonly detail: string;
    };

export const CONTAINMENT_VIOLATION_PREFIX = "containment violation: ";

function containmentViolation(reason: string): string {
  return `${CONTAINMENT_VIOLATION_PREFIX}${reason}`;
}

function errorDetail(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
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

async function inspectEntrypoint(
  pluginRoot: string,
  declaredEntrypoint: string,
): Promise<EntrypointInspection> {
  const resolvedEntrypoint = resolve(pluginRoot, declaredEntrypoint);

  if (isAbsolute(declaredEntrypoint)) {
    return {
      kind: "Violation",
      path: resolvedEntrypoint,
      detail: containmentViolation(
        "entrypoint must be relative to the plugin directory",
      ),
    };
  }

  if (!isInsideDirectory(pluginRoot, resolvedEntrypoint)) {
    return {
      kind: "Violation",
      path: resolvedEntrypoint,
      detail: containmentViolation(
        "entrypoint escapes the plugin directory",
      ),
    };
  }

  let entrypointIsFile = false;
  try {
    const entrypointStat = await stat(resolvedEntrypoint);
    if (!entrypointStat.isFile()) {
      return {
        kind: "Unavailable",
        path: resolvedEntrypoint,
        detail: "Entrypoint does not resolve to a regular file.",
      };
    }
    entrypointIsFile = true;
  } catch (error: unknown) {
    return {
      kind: "Unavailable",
      path: resolvedEntrypoint,
      detail: `Entrypoint is unavailable: ${errorDetail(error)}`,
    };
  }

  if (!entrypointIsFile) {
    return {
      kind: "Unavailable",
      path: resolvedEntrypoint,
      detail: "Entrypoint does not resolve to a regular file.",
    };
  }

  try {
    const realRoot = await realpath(pluginRoot);
    const realEntrypoint = await realpath(resolvedEntrypoint);
    if (!isInsideDirectory(realRoot, realEntrypoint)) {
      return {
        kind: "Violation",
        path: resolvedEntrypoint,
        detail: containmentViolation(
          "entrypoint resolves outside the plugin directory",
        ),
      };
    }
    return {
      kind: "Contained",
      path: resolvedEntrypoint,
      detail: "Entrypoint resolves to a contained regular file.",
    };
  } catch (error: unknown) {
    return {
      kind: "Unverified",
      path: resolvedEntrypoint,
      detail: `Entrypoint containment could not be verified: ${errorDetail(error)}`,
    };
  }
}

function entrypointCheckStatus(
  kind: EntrypointInspection["kind"],
): HealthCheckStatus {
  switch (kind) {
    case "Contained":
      return "pass";
    case "Violation":
      return "fail";
    case "Unavailable":
      return "fail";
    case "Unverified":
      return "unknown";
    default: {
      const exhaustive: never = kind;
      throw new HealthTransitionViolation(
        "known_entrypoint_inspection",
        String(exhaustive),
      );
    }
  }
}

function readStringField(value: unknown, field: string): string | undefined {
  if (typeof value !== "object" || value === null) {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  const candidate = record[field];
  return typeof candidate === "string" ? candidate : undefined;
}

function readPermissionsCount(value: unknown): number | undefined {
  if (typeof value !== "object" || value === null) {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  const candidate = record["permissions"];
  return Array.isArray(candidate) ? candidate.length : undefined;
}

/**
 * Validates a parsed manifest object (single source of truth).
 * Returns { valid: true, manifest: PluginManifest } or { valid: false, error: string }.
 * This replaces the call to loadPluginManifest which would re-read the file.
 */
function validateManifestShape(parsed: unknown): { valid: true; manifest: PluginManifest } | { valid: false; error: string } {
  if (typeof parsed !== "object" || parsed === null) {
    return { valid: false, error: "Manifest is not an object." };
  }
  const obj = parsed as Record<string, unknown>;

  const name = readStringField(obj, "name");
  if (!name) {
    return { valid: false, error: "Manifest missing required field 'name' (string)." };
  }

  const version = readStringField(obj, "version");
  if (!version) {
    return { valid: false, error: "Manifest missing required field 'version' (string)." };
  }

  const description = readStringField(obj, "description");
  if (!description) {
    return { valid: false, error: "Manifest missing required field 'description' (string)." };
  }

  const entrypoint = readStringField(obj, "entrypoint");
  if (!entrypoint) {
    return { valid: false, error: "Manifest missing required field 'entrypoint' (string)." };
  }

  const permissions = obj["permissions"];
  if (!Array.isArray(permissions)) {
    return { valid: false, error: "Manifest missing required field 'permissions' (array)." };
  }
  for (const perm of permissions) {
    if (typeof perm !== "string") {
      return { valid: false, error: "Manifest 'permissions' must be an array of strings." };
    }
  }

  const manifest: PluginManifest = {
    name,
    version,
    description,
    entrypoint,
    permissions,
  };
  return { valid: true, manifest };
}

interface InspectPluginOptions {
  /** Optional injected file reader for testing. Must return the same content on every call. */
  readFile?: (path: string) => Promise<string>;
}

async function inspectPlugin(
  pluginPath: string,
  manifestPath: string,
  options: InspectPluginOptions = {},
): Promise<PluginHealthReport> {
  const absolutePluginPath = resolve(pluginPath);
  const absoluteManifestPath = resolve(manifestPath);

  const reader = options.readFile ?? readFile;

  // SINGLE READ: read and parse exactly once. All verdicts derive from this one parsed object.
  let rawManifest: string;
  try {
    const readResult = await reader(absoluteManifestPath);
    rawManifest = typeof readResult === "string" ? readResult : readResult.toString("utf8");
  } catch (error: unknown) {
    return {
      pluginName: basename(absolutePluginPath),
      status: "unhealthy",
      manifestPath: absoluteManifestPath,
      checks: [
        {
          name: "manifest",
          status: "fail",
          detail: `Manifest is unavailable: ${errorDetail(error)}`,
          path: absoluteManifestPath,
        },
        {
          name: "entrypoint",
          status: "unknown",
          detail: "Entrypoint cannot be resolved without a readable manifest.",
        },
      ],
    };
  }

  let parsedManifest: unknown;
  let manifestParseFailed = false;
  try {
    parsedManifest = JSON.parse(rawManifest) as unknown;
  } catch (error: unknown) {
    manifestParseFailed = true;
    parsedManifest = undefined;
    void errorDetail(error);
  }

  // Validate shape on the SINGLE parsed object (no re-read)
  let manifest: PluginManifest | undefined;
  let manifestErrorDetail = "";
  if (!manifestParseFailed) {
    const validation = validateManifestShape(parsedManifest);
    if (validation.valid) {
      manifest = validation.manifest;
    } else {
      manifestErrorDetail = `Manifest is invalid: ${validation.error}`;
    }
  } else {
    manifestErrorDetail = "Manifest contains invalid JSON.";
  }
  const manifestValid = manifest !== undefined;

  const declaredEntrypoint = manifestParseFailed
    ? undefined
    : readStringField(parsedManifest, "entrypoint");

  const entrypointInspection: EntrypointInspection | undefined =
    declaredEntrypoint === undefined
      ? undefined
      : await inspectEntrypoint(absolutePluginPath, declaredEntrypoint);
  const containmentFailed = entrypointInspection?.kind === "Violation";

  const manifestStatus: HealthCheckStatus =
    manifestValid && !containmentFailed ? "pass" : "fail";
  const manifestDetail = containmentFailed
    ? `containment violation: manifest entrypoint is not contained in the plugin root; ${entrypointInspection?.detail ?? ""}`
    : manifestValid
      ? "Manifest shape and required fields are valid."
      : manifestErrorDetail;

  const entrypointCheck: HealthCheck =
    entrypointInspection === undefined
      ? {
          name: "entrypoint",
          status: "unknown",
          detail: "Entrypoint cannot be resolved without a valid manifest.",
        }
      : {
          name: "entrypoint",
          status: entrypointCheckStatus(entrypointInspection.kind),
          detail: entrypointInspection.detail,
          path: entrypointInspection.path,
        };

  const permissionsCount =
    manifest?.permissions.length ?? readPermissionsCount(parsedManifest);
  const permissionsCheck: HealthCheck =
    permissionsCount === undefined
      ? {
          name: "permissions",
          status: "unknown",
          detail: "Permissions could not be parsed from the manifest.",
        }
      : {
          name: "permissions",
          status: "pass",
          detail: `${permissionsCount} permission declaration(s) parsed.`,
        };

  const checks: HealthCheck[] = [
    {
      name: "manifest",
      status: manifestStatus,
      detail: manifestDetail,
      path: absoluteManifestPath,
    },
    entrypointCheck,
    permissionsCheck,
  ];

  const hasFailure = checks.some((check) => check.status === "fail");
  const hasUnknown = checks.some((check) => check.status === "unknown");
  const status: HealthStatus = hasFailure
    ? "unhealthy"
    : hasUnknown
      ? "unknown"
      : "healthy";

  const report: PluginHealthReport = {
    pluginName: manifest?.name ?? basename(absolutePluginPath),
    status,
    manifestPath: absoluteManifestPath,
    checks,
  };

  if (entrypointInspection !== undefined) {
    return { ...report, entrypointPath: entrypointInspection.path };
  }
  return report;
}

/**
 * Reports structural health without executing plugin code.
 * Reads and parses plugin.json exactly once.
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
