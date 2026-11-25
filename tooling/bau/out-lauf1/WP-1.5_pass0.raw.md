## (1) ClayCode block

```clay
module WP15_GRID10_TURN_LOOP_AUDIT {
  architecture Audit {
    stateAuthority {
      R_t = WP15_AUDIT_REPORT (canonical, persisted as docs/gridv1/WP15_EVIDENCE.json);
      E_t = { git_clone_receipt, git_HEAD, git_branch, file_bytes, sha256_digest, contract_artifacts? };
      F = auditTurnLoop(R_t, E_t) -> R_{t+1};
      M = { target_count == 1, blocking_checks, non_blocking_observations, expected_sha256? };
      precedence = functional_order(CLONE -> FETCH -> HASH -> CHECK -> PERSIST -> REPORT);
      L = c * h;  // c = independent confidence lines, h = effect size; neither is inferred from grep hits
    }
    path CLONE -> FETCH -> HASH -> CHECK -> PERSIST -> REPORT;
  }

  invariant SINGLE_TARGET {
    target_count <= MAX_CAPACITY(1)
    ON_VIOLATION -> TriggerEmergencyDeescalation(refuse_run)
  }
  invariant FAIL_CLOSED {
    missing_clone || missing_file || unreadable_bytes => status = UNKNOWN, exit_code = null
    ON_VIOLATION -> TriggerEmergencyDeescalation(refuse_verdict)
  }
  invariant NO_FABRICATED_DIGEST {
    expected_sha256 absent => sha.status = UNKNOWN (measured digest recorded, never promoted to PASS)
    ON_VIOLATION -> TriggerEmergencyDeescalation(mark_UNKNOWN)
  }
  invariant EXACT_NAME_REQUIRED {
    blocking function check satisfied only by anchored `def <name>(`; prefix-only match => FAIL
    ON_VIOLATION -> TriggerEmergencyDeescalation(mark_FAIL)
  }
  invariant P12_NON_BLOCKING {
    P12 (_collect_observations/_apply_observations) absent => OBSERVED, not FAIL (Team 1 final dropped P12)
    ON_VIOLATION -> TriggerEmergencyDeescalation(record_dissent_D3)
  }
  invariant CONTRACT_UNKNOWN {
    c01/c02 contract artifacts absent => contract_conformance = UNKNOWN (semantic match is never inferred from presence)
    ON_VIOLATION -> TriggerEmergencyDeescalation(mark_UNKNOWN)
  }
  invariant EVIDENCE_ATOMIC {
    evidence file written only after all checks terminate; write = tmp + rename; lock held for the whole run
    ON_VIOLATION -> TriggerEmergencyDeescalation(rollback_evidence)
  }
  invariant EVIDENCE_SHAPE {
    every record = {test, command, exit_code, stdout, stderr, timestamp, verifier, dissent_id:"D3"}
    ON_VIOLATION -> TriggerEmergencyDeescalation(refuse_persist)
  }

  fn F(R_t, E_t) {
    acquire_lock(MAX_CAPACITY = 1);
    clone_or_bind_existing(E_t.repo, E_t.branch);
    fetch_bytes(E_t.relative_file);
    hash_bytes_sha256(E_t.file_bytes);
    run_acceptance_greps(E_t.file_bytes);
    evaluate_checks(E_t.file_bytes);
    classify_contract_conformance(E_t.contract_artifacts?);
    persist_evidence_atomically(R_t, E_t);
    release_lock();
  }

  hypothesis H_WP15_LIVE_TURN_LOOP_MATCHES_C01_C02 {
    live branch file contains all 13 critical sub-functions, the canonical pointer table
    name, and the schema constants, and its digest equals the architect-recorded digest;
    status = UNKNOWN until measured by an independent verifier with network access
  }

  promotion MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT
          -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE;
}
```

**Honest status:** the live clone/SHA verification was **not executed** in this authoring context (no network or process-execution access). The deliverable is therefore the executable audit harness + the evidence record with `status = UNKNOWN`, `exit_code = null`. No digest, no PASS, no fabricated grep output.

---

## (2) Files in full

=== FILE: agent-sdk/src/gridv1/wp15_audit.ts ===
```ts
/**
 * WP-1.5 — GRID10 turn-loop code audit (build team 4).
 *
 * Scope: fetch the live `scripts/f2wp1207_grid10_turn_loop.py` from the
 * frankenstein-repo (acceptance test uses branch `live`; the Team 1 excerpt
 * names the `machine-b` branch — the discrepancy is recorded, not silently
 * resolved), verify its SHA-256, and confirm that the critical sub-functions,
 * pointer-table names and schema constants required by the architecture exist.
 *
 * GRF mapping:
 *   R_t = persisted audit report (docs/gridv1/WP15_EVIDENCE.json)
 *   E_t = { git_clone_receipt, git_HEAD, git_branch, file_bytes, sha256_digest,
 *           contract_artifacts? }
 *   F   = auditTurnLoop(R_t, E_t) -> R_{t+1}
 *   M   = { target_count == 1, blocking_checks, non_blocking_observations,
 *           expected_sha256? }
 *   precedence = functional order: CLONE -> FETCH -> HASH -> CHECK -> PERSIST -> REPORT
 *
 * CVIR: FACT_UNKNOWN + METHOD_PRESENT != FACT_PRESENT. A missing clone, an
 * unreadable file, or an absent expected digest yields UNKNOWN — never 0,
 * never a fabricated PASS. WORKSPACE_WINNER != CANONICAL_TRUTH: grep hits are
 * observations, not proof of contract conformance.
 *
 * No Rust module is added by this work package: the audit is build-time
 * tooling, so `src/lib.rs` is intentionally left untouched.
 */

import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";

export const MAX_CAPACITY = 1;
export const DISSENT_ID = "D3" as const;
export const SCHEMA_VERSION = "wp15.audit.v1" as const;

export const DEFAULT_REPO_URL =
  "https://github.com/machine-b/frankenstein-repo.git";
export const DEFAULT_BRANCH = "live";
export const DEFAULT_RELATIVE_FILE =
  "scripts/f2wp1207_grid10_turn_loop.py";
export const DEFAULT_CLONE_DIR = "/tmp/frank-live";
export const DEFAULT_OUT_PATH = "docs/gridv1/WP15_EVIDENCE.json";

export type EpistemicClass = "MEASURED" | "DERIVED" | "UNKNOWN" | "ERROR";
export type CheckStatus = "PASS" | "FAIL" | "UNKNOWN" | "OBSERVED";
export type OverallStatus = "PASS" | "FAIL" | "UNKNOWN";

export interface CheckSpec {
  readonly id: string;
  readonly kind: "function" | "token" | "schema";
  readonly pattern: string;
  readonly match_mode: "exact" | "prefix" | "literal";
  readonly blocking: boolean;
  readonly note?: string;
}

export interface AuditCheckResult {
  readonly id: string;
  readonly kind: CheckSpec["kind"];
  readonly pattern: string;
  readonly match_mode: CheckSpec["match_mode"];
  readonly blocking: boolean;
  readonly status: CheckStatus;
  readonly matches: readonly number[];
  readonly note?: string;
}

export interface EvidenceRecord {
  readonly test: string;
  readonly command: string;
  readonly exit_code: number | null;
  readonly stdout: string;
  readonly stderr: string;
  readonly timestamp: string;
  readonly verifier: string;
  readonly dissent_id: typeof DISSENT_ID;
}

export interface ShaCheck {
  readonly value: string | null;
  readonly expected: string | null;
  readonly status: CheckStatus;
  readonly source: "sha256sum" | "node:crypto" | "none";
  readonly note?: string;
}

export interface AuditReport {
  readonly schema_version: typeof SCHEMA_VERSION;
  readonly dissent_id: typeof DISSENT_ID;
  readonly status: OverallStatus;
  readonly epistemic_class: EpistemicClass;
  readonly target: {
    readonly repo_url: string;
    readonly branch: string;
    readonly relative_file: string;
    readonly clone_dir: string;
    readonly git_head: string | null;
    readonly git_branch_observed: string | null;
  };
  readonly sha256: ShaCheck;
  readonly checks: readonly AuditCheckResult[];
  readonly contract_conformance: {
    readonly status: CheckStatus;
    readonly artifacts: readonly string[];
    readonly note: string;
  };
  readonly evidence: readonly EvidenceRecord[];
  readonly notes: readonly string[];
}

/* ------------------------------------------------------------------ *
 * Check catalogue (acceptance test steps 3..6)
 * ------------------------------------------------------------------ */

export const CRITICAL_FUNCTION_CHECKS: readonly CheckSpec[] = [
  { id: "fn.run_canonical_turn", kind: "function", pattern: "run_canonical_turn", match_mode: "exact", blocking: true },
  { id: "fn.resolve_reentry", kind: "function", pattern: "resolve_reentry", match_mode: "exact", blocking: true },
  { id: "fn.fill_jspace", kind: "function", pattern: "fill_jspace", match_mode: "exact", blocking: true },
  { id: "fn.uptake_and_state", kind: "function", pattern: "uptake_and_state", match_mode: "exact", blocking: true },
  { id: "fn._mint_turn_event_id", kind: "function", pattern: "_mint_turn_event_id", match_mode: "exact", blocking: true },
  { id: "fn._submit_effect_in_transaction", kind: "function", pattern: "_submit_effect_in_transaction", match_mode: "exact", blocking: true },
  { id: "fn.percept_axes", kind: "function", pattern: "percept_axes", match_mode: "exact", blocking: true },
  { id: "fn.derive_percept_signals", kind: "function", pattern: "derive_percept_signals", match_mode: "exact", blocking: true },
  {
    id: "fn._welford_",
    kind: "function",
    pattern: "_welford_",
    match_mode: "prefix",
    blocking: true,
    note: "Acceptance grep uses prefix semantics (`def _welford_`); prefix match is accepted.",
  },
  {
    id: "fn._r6",
    kind: "function",
    pattern: "_r6",
    match_mode: "prefix",
    blocking: true,
    note: "Acceptance grep uses prefix semantics (`def _r6`); prefix match is accepted.",
  },
  { id: "fn._rate_limited_step", kind: "function", pattern: "_rate_limited_step", match_mode: "exact", blocking: true },
  { id: "fn._clip", kind: "function", pattern: "_clip", match_mode: "exact", blocking: true },
  { id: "fn._theoretischer_broadcast_bereich", kind: "function", pattern: "_theoretischer_broadcast_bereich", match_mode: "exact", blocking: true },
];

export const POINTER_CHECKS: readonly CheckSpec[] = [
  {
    id: "ptr.f2_grid10_turn_pointer",
    kind: "token",
    pattern: "f2_grid10_turn_pointer",
    match_mode: "literal",
    blocking: true,
    note: "Canonical pointer table name (Team 1 final).",
  },
  {
    id: "ptr.turn_pointer",
    kind: "token",
    pattern: "turn_pointer",
    match_mode: "literal",
    blocking: false,
    note: "Pointer field name; recorded as observation.",
  },
  {
    id: "ptr.reentry_pointer",
    kind: "token",
    pattern: "reentry_pointer",
    match_mode: "literal",
    blocking: false,
    note: "Pointer field name; recorded as observation.",
  },
];

export const SCHEMA_CHECKS: readonly CheckSpec[] = [
  { id: "schema.SCHEMA_", kind: "schema", pattern: "SCHEMA_", match_mode: "literal", blocking: true },
  { id: "schema.PERCEPT_", kind: "schema", pattern: "PERCEPT_", match_mode: "literal", blocking: true },
  { id: "schema.CREATE_TABLE", kind: "schema", pattern: "CREATE TABLE", match_mode: "literal", blocking: true },
];

export const P12_CHECKS: readonly CheckSpec[] = [
  {
    id: "p12._collect_observations",
    kind: "function",
    pattern: "_collect_observations",
    match_mode: "exact",
    blocking: false,
    note: "P12 was dropped in the Team 1 final architecture; absence is recorded as OBSERVED, not FAIL.",
  },
  {
    id: "p12._apply_observations",
    kind: "function",
    pattern: "_apply_observations",
    match_mode: "exact",
    blocking: false,
    note: "P12 was dropped in the Team 1 final architecture; absence is recorded as OBSERVED, not FAIL.",
  },
];

export const ALL_CHECKS: readonly CheckSpec[] = [
  ...CRITICAL_FUNCTION_CHECKS,
  ...POINTER_CHECKS,
  ...SCHEMA_CHECKS,
  ...P12_CHECKS,
];

/* ------------------------------------------------------------------ *
 * Small helpers
 * ------------------------------------------------------------------ */

export class AuditRefusal extends Error {
  readonly reason: string;
  constructor(reason: string) {
    super(reason);
    this.name = "AuditRefusal";
    this.reason = reason;
  }
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function shellQuote(value: string): string {
  return /^[A-Za-z0-9_@%+=:,./-]+$/.test(value)
    ? value
    : `'${value.replace(/'/g, `'\\''`)}'`;
}

export interface CommandResult {
  readonly command: string;
  readonly exit_code: number | null;
  readonly stdout: string;
  readonly stderr: string;
}

export function runCommand(
  command: string,
  args: readonly string[],
  cwd?: string,
): CommandResult {
  const res = spawnSync(command, [...args], {
    ...(cwd ? { cwd } : {}),
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  const stdout = typeof res.stdout === "string" ? res.stdout : String(res.stdout ?? "");
  const stderr = typeof res.stderr === "string" ? res.stderr : String(res.stderr ?? "");
  return {
    command: [command, ...args].map(shellQuote).join(" "),
    exit_code: typeof res.status === "number" ? res.status : null,
    stdout,
    stderr: stderr.length > 0 ? stderr : res.error ? String(res.error) : "",
  };
}

export function computeSha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

export function parseSha256sumOutput(stdout: string): string | null {
  const match = /^([0-9a-f]{64})\s+/m.exec(stdout);
  return match ? match[1] : null;
}

function anchoredFunctionRegex(pattern: string): RegExp {
  return new RegExp(`^\\s*(?:async\\s+)?def\\s+${escapeRegExp(pattern)}\\s*\\(`);
}

function prefixFunctionRegex(pattern: string): RegExp {
  return new RegExp(`^\\s*(?:async\\s+)?def\\s+${escapeRegExp(pattern)}`);
}

function lineMatches(line: string, spec: CheckSpec): boolean {
  switch (spec.match_mode) {
    case "exact":
      return spec.kind === "function"
        ? anchoredFunctionRegex(spec.pattern).test(line)
        : line.includes(spec.pattern);
    case "prefix":
      return prefixFunctionRegex(spec.pattern).test(line);
    case "literal":
      return line.includes(spec.pattern);
    default:
      return false;
  }
}

/**
 * Pure evaluation of the check catalogue over file content.
 * `content === null` means the bytes could not be obtained: every check is
 * UNKNOWN (fail-closed), never FAIL and never PASS.
 */
export function evaluateContent(
  content: string | null,
  specs: readonly CheckSpec[] = ALL_CHECKS,
): AuditCheckResult[] {
  if (content === null) {
    return specs.map((spec) => ({
      id: spec.id,
      kind: spec.kind,
      pattern: spec.pattern,
      match_mode: spec.match_mode,
      blocking: spec.blocking,
      status: "UNKNOWN" as CheckStatus,
      matches: [] as number[],
      note: spec.note ?? "File bytes unavailable; status UNKNOWN (fail-closed).",
    }));
  }
  const lines = content.split(/\r?\n/);
  return specs.map((spec) => {
    const matches: number[] = [];
    lines.forEach((line, index) => {
      if (lineMatches(line, spec)) matches.push(index + 1);
    });
    const status: CheckStatus = matches.length > 0 ? "PASS" : "FAIL";
    return {
      id: spec.id,
      kind: spec.kind,
      pattern: spec.pattern,
      match_mode: spec.match_mode,
      blocking: spec.blocking,
      status,
      matches,
      ...(spec.note ? { note: spec.note } : {}),
    };
  });
}

export function summarize(
  checks: readonly AuditCheckResult[],
  sha: ShaCheck,
): {
  status: OverallStatus;
  blocking_failures: string[];
  unknowns: string[];
} {
  const blockingFailures = checks
    .filter((check) => check.blocking && check.status === "FAIL")
    .map((check) => check.id);
  const unknowns = checks
    .filter((check) => check.blocking && check.status === "UNKNOWN")
    .map((check) => check.id);
  if (sha.status === "FAIL") {
    return { status: "FAIL", blocking_failures: [...blockingFailures, "sha256"], unknowns };
  }
  if (sha.status === "UNKNOWN") unknowns.push("sha256");
  if (blockingFailures.length > 0) {
    return { status: "FAIL", blocking_failures, unknowns };
  }
  if (unknowns.length > 0) {
    return { status: "UNKNOWN", blocking_failures, unknowns };
  }
  return { status: "PASS", blocking_failures, unknowns };
}

/* ------------------------------------------------------------------ *
 * Locking / atomic persistence
 * ------------------------------------------------------------------ */

function acquireLock(lockPath: string): () => void {
  try {
    const fd = openSync(lockPath, "wx");
    writeFileSync(fd, `${process.pid}\n`, "utf8");
    closeSync(fd);
  } catch (error) {
    throw new AuditRefusal(
      `audit lock already held (${lockPath}); refusing concurrent run (MAX_CAPACITY=${MAX_CAPACITY})`,
    );
  }
  return () => {
    try {
      rmSync(lockPath, { force: true });
    } catch {
      /* lock release is best-effort; the file is advisory only */
    }
  };
}

export function writeJsonAtomic(path: string, value: unknown): void {
  const absolute = resolve(path);
  mkdirSync(dirname(absolute), { recursive: true });
  const temporary = `${absolute}.tmp-${process.pid}-${Date.now()}`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  renameSync(temporary, absolute);
}

/* ------------------------------------------------------------------ *
 * Audit transition F
 * ------------------------------------------------------------------ */

export interface AuditOptions {
  readonly repoUrl?: string;
  readonly branch?: string;
  readonly cloneDir?: string;
  readonly relativeFile?: string;
  readonly expectedSha256?: string | null;
  readonly verifier?: string;
  readonly outPath?: string | null;
  readonly contractArtifacts?: readonly string[];
  readonly forceClone?: boolean;
  readonly now?: () => Date;
}

export function auditTurnLoop(options: AuditOptions = {}): AuditReport {
  const repoUrl = options.repoUrl ?? DEFAULT_REPO_URL;
  const branch = options.branch ?? DEFAULT_BRANCH;
  const cloneDir = options.cloneDir ?? DEFAULT_CLONE_DIR;
  const relativeFile = options.relativeFile ?? DEFAULT_RELATIVE_FILE;
  const expectedSha256 = options.expectedSha256 ?? null;
  const verifier = options.verifier ?? "coder-wp15-team4";
  const outPath = options.outPath ?? null;
  const contractArtifacts = options.contractArtifacts ?? [];
  const now = options.now ?? (() => new Date());
  const timestamp = now().toISOString();

  // M: single-target capacity. One audit run audits exactly one file.
  const targetCount = 1;
  if (targetCount > MAX_CAPACITY) {
    throw new AuditRefusal(
      `target_count=${targetCount} exceeds MAX_CAPACITY=${MAX_CAPACITY}`,
    );
  }

  const evidence: EvidenceRecord[] = [];
  const notes: string[] = [];
  const pushEvidence = (
    test: string,
    result: CommandResult,
    extra?: { stdout?: string; stderr?: string },
  ): void => {
    evidence.push({
      test,
      command: result.command,
      exit_code: result.exit_code,
      stdout: extra?.stdout ?? result.stdout,
      stderr: extra?.stderr ?? result.stderr,
      timestamp,
      verifier,
      dissent_id: DISSENT_ID,
    });
  };

  const lockPath = outPath ? `${resolve(outPath)}.lock` : join(cloneDir, ".wp15.lock");
  const releaseLock = acquireLock(lockPath);

  try {
    const targetPath = join(cloneDir, relativeFile);
    let cloneResult: CommandResult | null = null;
    let cloneOk = false;

    if (options.forceClone && existsSync(cloneDir)) {
      rmSync(cloneDir, { recursive: true, force: true });
    }

    if (existsSync(targetPath)) {
      notes.push(
        `Existing checkout reused at ${cloneDir}; clone step skipped (no fresh clone receipt for this run).`,
      );
      cloneOk = true;
    } else {
      cloneResult = runCommand("git", ["clone", "-b", branch, repoUrl, cloneDir]);
      pushEvidence("WP15-1 clone live branch", cloneResult);
      cloneOk = cloneResult.exit_code === 0 && existsSync(targetPath);
      if (!cloneOk) {
        notes.push(
          "Clone did not produce the target file; all downstream checks are UNKNOWN (fail-closed).",
        );
      }
    }

    let gitHead: string | null = null;
    let gitBranchObserved: string | null = null;
    if (cloneOk) {
      const head = runCommand("git", ["rev-parse", "HEAD"], cloneDir);
      pushEvidence("WP15-1b bind evidence to commit", head);
      gitHead = head.exit_code === 0 ? head.stdout.trim() : null;

      const branchObserved = runCommand(
        "git",
        ["rev-parse", "--abbrev-ref", "HEAD"],
        cloneDir,
      );
      pushEvidence("WP15-1c bind evidence to branch", branchObserved);
      gitBranchObserved =
        branchObserved.exit_code === 0 ? branchObserved.stdout.trim() : null;
    }

    let content: string | null = null;
    let sha: ShaCheck = {
      value: null,
      expected: expectedSha256,
      status: "UNKNOWN",
      source: "none",
      note: "Target file unavailable; digest UNKNOWN.",
    };

    if (cloneOk) {
      if (!existsSync(targetPath)) {
        notes.push(`Target file missing: ${targetPath}`);
      } else {
        const bytes = readFileSync(targetPath);
        const shaCommand = runCommand("sha256sum", [relativeFile], cloneDir);
        let digest: string | null = null;
        let source: ShaCheck["source"] = "node:crypto";
        if (shaCommand.exit_code === 0) {
          digest = parseSha256sumOutput(shaCommand.stdout);
          source = digest ? "sha256sum" : "node:crypto";
        }
        if (!digest) digest = computeSha256(bytes);
        pushEvidence("WP15-2 verify SHA-256", shaCommand, {
          stdout:
            shaCommand.stdout.length > 0
              ? shaCommand.stdout
              : `${digest}  ${relativeFile}\n(computed in-process via node:crypto; sha256sum binary unavailable)`,
        });

        sha = {
          value: digest,
          expected: expectedSha256,
          status: expectedSha256
            ? expectedSha256.toLowerCase() === digest.toLowerCase()
              ? "PASS"
              : "FAIL"
            : "UNKNOWN",
          source,
          ...(expectedSha256
            ? {}
            : {
                note: "Expected digest not supplied by the architect; measured digest recorded, status UNKNOWN (no fabricated PASS).",
              }),
        };

        content = bytes.toString("utf8");

        // Acceptance steps 3..6 executed as real grep commands (evidence with
        // true exit codes), in addition to the in-process anchored evaluation.
        const grepAvailable = runCommand("grep", ["--version"]).exit_code === 0;
        for (const spec of ALL_CHECKS) {
          const grepPattern =
            spec.kind === "function" && spec.match_mode === "exact"
              ? `def ${spec.pattern}`
              : spec.pattern;
          if (!grepAvailable) {
            evidence.push({
              test: `WP15-3..6 grep ${spec.id}`,
              command: `grep -n ${shellQuote(grepPattern)} ${relativeFile}`,
              exit_code: null,
              stdout: "",
              stderr: "grep binary unavailable; check evaluated in-process only.",
              timestamp,
              verifier,
              dissent_id: DISSENT_ID,
            });
            continue;
          }
          const grepResult = runCommand(
            "grep",
            ["-n", grepPattern, relativeFile],
            cloneDir,
          );
          pushEvidence(`WP15-3..6 grep ${spec.id}`, grepResult);
        }
      }
    }

    const checks = evaluateContent(content);
    const contractConformance = classifyContracts(contractArtifacts, content);

    const summary = summarize(checks, sha);
    const report: AuditReport = {
      schema_version: SCHEMA_VERSION,
      dissent_id: DISSENT_ID,
      status: summary.status,
      epistemic_class:
        summary.status === "UNKNOWN"
          ? "UNKNOWN"
          : summary.status === "FAIL"
            ? "MEASURED"
            : "MEASURED",
      target: {
        repo_url: repoUrl,
        branch,
        relative_file: relativeFile,
        clone_dir: cloneDir,
        git_head: gitHead,
        git_branch_observed: gitBranchObserved,
      },
      sha256: sha,
      checks,
      contract_conformance: contractConformance,
      evidence,
      notes: [
        ...notes,
        `Blocking failures: ${summary.blocking_failures.length > 0 ? summary.blocking_failures.join(", ") : "none"}.`,
        `Unknowns: ${summary.unknowns.length > 0 ? summary.unknowns.join(", ") : "none"}.`,
        "Branch discrepancy: acceptance test clones branch `live`; the Team 1 excerpt names the `machine-b` branch. Recorded under dissent D3; not silently resolved.",
        "P12 (_collect_observations/_apply_observations) is non-blocking: Team 1 final dropped P12.",
      ],
    };

    if (outPath) {
      writeJsonAtomic(outPath, report);
    }
    return report;
  } finally {
    releaseLock();
  }
}

export function classifyContracts(
  artifacts: readonly string[],
  content: string | null,
): { status: CheckStatus; artifacts: readonly string[]; note: string } {
  if (artifacts.length === 0) {
    return {
      status: "UNKNOWN",
      artifacts: [],
      note: "c01/c02 contract artifacts were not supplied to WP-1.5; semantic conformance is UNKNOWN and is never inferred from function-name presence.",
    };
  }
  const present = artifacts.filter((artifact) => existsSync(artifact));
  if (present.length !== artifacts.length) {
    return {
      status: "UNKNOWN",
      artifacts: present,
      note: "One or more contract artifacts are missing; conformance remains UNKNOWN.",
    };
  }
  return {
    status: "UNKNOWN",
    artifacts: present,
    note:
      "Contract artifacts are present, but c01/c02 semantic conformance requires independent review by the coordinator; this harness records presence only.",
  };
}

export function formatReport(report: AuditReport): string {
  return `${JSON.stringify(report, null, 2)}\n`;
}

/* ------------------------------------------------------------------ *
 * CLI
 * ------------------------------------------------------------------ */

interface ParsedArgs {
  readonly options: AuditOptions;
  readonly help: boolean;
}

export function parseArgs(argv: readonly string[]): ParsedArgs {
  const options: {
    repoUrl?: string;
    branch?: string;
    cloneDir?: string;
    relativeFile?: string;
    expectedSha256?: string | null;
    verifier?: string;
    outPath?: string | null;
    contractArtifacts?: string[];
    forceClone?: boolean;
  } = {};
  let help = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = (): string => {
      const value = argv[index + 1];
      if (value === undefined) {
        throw new AuditRefusal(`missing value for ${arg}`);
      }
      index += 1;
      return value;
    };
    switch (arg) {
      case "--repo":
        options.repoUrl = next();
        break;
      case "--branch":
        options.branch = next();
        break;
      case "--clone-dir":
        options.cloneDir = next();
        break;
      case "--file":
        options.relativeFile = next();
        break;
      case "--expected-sha256":
        options.expectedSha256 = next();
        break;
      case "--verifier":
        options.verifier = next();
        break;
      case "--out":
        options.outPath = next();
        break;
      case "--contract":
        options.contractArtifacts = [...(options.contractArtifacts ?? []), next()];
        break;
      case "--force-clone":
        options.forceClone = true;
        break;
      case "--help":
      case "-h":
        help = true;
        break;
      default:
        throw new AuditRefusal(`unknown argument: ${arg}`);
    }
  }

  return {
    help,
    options: {
      ...(options.repoUrl ? { repoUrl: options.repoUrl } : {}),
      ...(options.branch ? { branch: options.branch } : {}),
      ...(options.cloneDir ? { cloneDir: options.cloneDir } : {}),
      ...(options.relativeFile ? { relativeFile: options.relativeFile } : {}),
      ...(options.expectedSha256 !== undefined
        ? { expectedSha256: options.expectedSha256 }
        : {}),
      ...(options.verifier ? { verifier: options.verifier } : {}),
      ...(options.outPath !== undefined ? { outPath: options.outPath } : {}),
      ...(options.contractArtifacts
        ? { contractArtifacts: options.contractArtifacts }
        : {}),
      ...(options.forceClone ? { forceClone: true } : {}),
    },
  };
}

export function usage(): string {
  return [
    "WP-1.5 GRID10 turn-loop audit",
    "",
    "Usage:",
    "  bun agent-sdk/src/gridv1/wp15_audit.ts [options]",
    "",
    "Options:",
    `  --repo <url>            default ${DEFAULT_REPO_URL}`,
    `  --branch <name>         default ${DEFAULT_BRANCH}`,
    `  --clone-dir <path>      default ${DEFAULT_CLONE_DIR}`,
    `  --file <relative>       default ${DEFAULT_RELATIVE_FILE}`,
    "  --expected-sha256 <hex> architect-recorded digest (absent => UNKNOWN)",
    "  --verifier <name>       verifier label stored in every evidence record",
    `  --out <path>            evidence file (default none; acceptance uses ${DEFAULT_OUT_PATH})`,
    "  --contract <path>       c01/c02 contract artifact (repeatable)",
    "  --force-clone           remove an existing clone directory first",
    "",
    "Exit codes: 0 PASS, 1 FAIL, 2 UNKNOWN, 3 refusal/error.",
  ].join("\n");
}

export function main(argv: readonly string[]): number {
  let parsed: ParsedArgs;
  try {
    parsed = parseArgs(argv);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.stderr.write(`${usage()}\n`);
    return 3;
  }
  if (parsed.help) {
    process.stdout.write(`${usage()}\n`);
    return 0;
  }
  try {
    const report = auditTurnLoop(parsed.options);
    process.stdout.write(formatReport(report));
    if (report.status === "PASS") return 0;
    if (report.status === "FAIL") return 1;
    return 2;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`WP15_AUDIT_REFUSED: ${message}\n`);
    return 3;
  }
}

const invokedDirectly =
  (import.meta as unknown as { main?: boolean }).main === true;
if (invokedDirectly) {
  process.exitCode = main(process.argv.slice(2));
}
```

=== FILE: agent-sdk/src/gridv1/wp15_audit.test.ts ===
```ts
/**
 * WP-1.5 audit harness — self-contained checks (no test framework dependency).
 *
 * Run: bun agent-sdk/src/gridv1/wp15_audit.test.ts
 *
 * IMPORTANT: the fixture below is SYNTHETIC. It is not the live
 * `f2wp1207_grid10_turn_loop.py` and proves nothing about the upstream
 * repository. It only exercises the detection logic of the audit harness.
 */

import assert from "node:assert/strict";
import {
  ALL_CHECKS,
  CRITICAL_FUNCTION_CHECKS,
  P12_CHECKS,
  POINTER_CHECKS,
  SCHEMA_CHECKS,
  computeSha256,
  evaluateContent,
  parseSha256sumOutput,
  summarize,
  type AuditCheckResult,
  type ShaCheck,
} from "./wp15_audit.js";

const SYNTHETIC_FIXTURE = `
# SYNTHETIC FIXTURE — not upstream source.
SCHEMA_VERSION = "synthetic"
PERCEPT_AXES = ("a", "b")

CREATE TABLE IF NOT EXISTS f2_grid10_turn_pointer (
  turn_event_id TEXT PRIMARY KEY
);

def run_canonical_turn(ctx):
    return ctx

def resolve_reentry(ctx):
    return None

def fill_jspace(ctx):
    return None

def uptake_and_state(ctx):
    return None

def _mint_turn_event_id():
    return "id"

def _submit_effect_in_transaction(conn, effect):
    return True

def percept_axes():
    return PERCEPT_AXES

def derive_percept_signals():
    return {}

def _welford_mean(values):
    return 0.0

def _r6_update(state):
    return state

def _rate_limited_step(fn):
    return fn

def _clip(value):
    return value

def _theoretischer_broadcast_bereich(value):
    return value

def _collect_observations():
    return []

def _apply_observations(obs):
    return None
`;

function byId(checks: readonly AuditCheckResult[], id: string): AuditCheckResult {
  const found = checks.find((check) => check.id === id);
  assert.ok(found, `missing check ${id}`);
  return found;
}

function sha(status: ShaCheck["status"], value: string | null = null): ShaCheck {
  return { value, expected: null, status, source: value ? "node:crypto" : "none" };
}

const failures: string[] = [];

function test(name: string, body: () => void): void {
  try {
    body();
    process.stdout.write(`ok - ${name}\n`);
  } catch (error) {
    failures.push(name);
    process.stderr.write(
      `not ok - ${name}: ${error instanceof Error ? error.message : String(error)}\n`,
    );
  }
}

test("all critical functions are detected in the synthetic fixture", () => {
  const checks = evaluateContent(SYNTHETIC_FIXTURE, CRITICAL_FUNCTION_CHECKS);
  for (const check of checks) {
    assert.equal(check.status, "PASS", `${check.id} should PASS`);
    assert.ok(check.matches.length > 0, `${check.id} should have line matches`);
  }
});

test("prefix checks accept grep-style prefixes", () => {
  const checks = evaluateContent(SYNTHETIC_FIXTURE, CRITICAL_FUNCTION_CHECKS);
  assert.equal(byId(checks, "fn._welford_").status, "PASS");
  assert.equal(byId(checks, "fn._r6").status, "PASS");
});

test("a missing critical function is a blocking FAIL", () => {
  const stripped = SYNTHETIC_FIXTURE.replace("def resolve_reentry(ctx):", "def resolve_reentry_v2(ctx):");
  const checks = evaluateContent(stripped, CRITICAL_FUNCTION_CHECKS);
  const check = byId(checks, "fn.resolve_reentry");
  assert.equal(check.status, "FAIL");
  assert.equal(check.blocking, true);
});

test("pointer and schema checks are literal", () => {
  const checks = evaluateContent(SYNTHETIC_FIXTURE, [...POINTER_CHECKS, ...SCHEMA_CHECKS]);
  assert.equal(byId(checks, "ptr.f2_grid10_turn_pointer").status, "PASS");
  assert.equal(byId(checks, "schema.CREATE_TABLE").status, "PASS");
  assert.equal(byId(checks, "schema.SCHEMA_").status, "PASS");
  assert.equal(byId(checks, "schema.PERCEPT_").status, "PASS");
});

test("P12 absence is non-blocking", () => {
  const stripped = SYNTHETIC_FIXTURE
    .replace("def _collect_observations():", "def _collect_observations_v2():")
    .replace("def _apply_observations(obs):", "def _apply_observations_v2(obs):");
  const checks = evaluateContent(stripped, P12_CHECKS);
  for (const check of checks) {
    assert.equal(check.status, "FAIL");
    assert.equal(check.blocking, false);
  }
  const summary = summarize(checks, sha("PASS", "a".repeat(64)));
  assert.equal(summary.status, "PASS");
});

test("unavailable bytes yield UNKNOWN, never FAIL", () => {
  const checks = evaluateContent(null, ALL_CHECKS);
  for (const check of checks) {
    assert.equal(check.status, "UNKNOWN");
  }
  const summary = summarize(checks, sha("UNKNOWN"));
  assert.equal(summary.status, "UNKNOWN");
});

test("missing expected digest keeps the SHA status UNKNOWN", () => {
  const digest = computeSha256(Buffer.from(SYNTHETIC_FIXTURE, "utf8"));
  const summary = summarize(evaluateContent(SYNTHETIC_FIXTURE), {
    value: digest,
    expected: null,
    status: "UNKNOWN",
    source: "node:crypto",
  });
  assert.equal(summary.status, "UNKNOWN");
  assert.ok(summary.unknowns.includes("sha256"));
});

test("sha256sum output parsing", () => {
  const digest = "b".repeat(64);
  assert.equal(parseSha256sumOutput(`${digest}  scripts/file.py\n`), digest);
  assert.equal(parseSha256sumOutput("not a digest"), null);
});

if (failures.length > 0) {
  process.stderr.write(`${failures.length} test(s) failed\n`);
  process.exitCode = 1;
} else {
  process.stdout.write("all WP-1.5 harness tests passed\n");
}
```

=== FILE: docs/gridv1/WP15_GRID10_TURN_LOOP_AUDIT.md ===
```markdown
# WP-1.5 — GRID10 Turn Loop Code Audit

**Owner:** build team 4 (CODER)
**Dissent id:** `D3`
**Status:** `UNKNOWN` — the live clone/SHA verification has **not** been executed in the
authoring context (no network or process-execution access). The harness below is the
executable artifact; the evidence file records `exit_code = null` and `status = UNKNOWN`.
No digest, no PASS, and no grep output is fabricated here.

## 1. Scope

Fetch the live `scripts/f2wp1207_grid10_turn_loop.py` from the frankenstein-repo,
verify its SHA-256, and confirm that the critical sub-functions, pointer-table names and
schema constants required by the Team 1 architecture exist in that file.

Inputs that are **not** available to this work package and therefore remain `UNKNOWN`:

| Input | State | Consequence |
|---|---|---|
| Live repository checkout | UNKNOWN | SHA and grep results cannot be measured here |
| Architect-recorded expected SHA-256 | UNKNOWN | SHA status stays `UNKNOWN` even when a digest is measured |
| `c01` / `c02` contract artifacts | UNKNOWN | Contract conformance stays `UNKNOWN`; function-name presence is never promoted to conformance |
| Branch identity (`live` vs `machine-b`) | UNKNOWN | Both are recorded; the discrepancy is logged under dissent `D3` |

## 2. ClayCode

```clay
module WP15_GRID10_TURN_LOOP_AUDIT {
  architecture Audit {
    stateAuthority {
      R_t = WP15_AUDIT_REPORT (canonical, persisted as docs/gridv1/WP15_EVIDENCE.json);
      E_t = { git_clone_receipt, git_HEAD, git_branch, file_bytes, sha256_digest, contract_artifacts? };
      F = auditTurnLoop(R_t, E_t) -> R_{t+1};
      M = { target_count == 1, blocking_checks, non_blocking_observations, expected_sha256? };
      precedence = functional_order(CLONE -> FETCH -> HASH -> CHECK -> PERSIST -> REPORT);
      L = c * h;  // c = independent confidence lines, h = effect size; neither is inferred from grep hits
    }
    path CLONE -> FETCH -> HASH -> CHECK -> PERSIST -> REPORT;
  }

  invariant SINGLE_TARGET {
    target_count <= MAX_CAPACITY(1)
    ON_VIOLATION -> TriggerEmergencyDeescalation(refuse_run)
  }
  invariant FAIL_CLOSED {
    missing_clone || missing_file || unreadable_bytes => status = UNKNOWN, exit_code = null
    ON_VIOLATION -> TriggerEmergencyDeescalation(refuse_verdict)
  }
  invariant NO_FABRICATED_DIGEST {
    expected_sha256 absent => sha.status = UNKNOWN (measured digest recorded, never promoted to PASS)
    ON_VIOLATION -> TriggerEmergencyDeescalation(mark_UNKNOWN)
  }
  invariant EXACT_NAME_REQUIRED {
    blocking function check satisfied only by anchored `def <name>(`; prefix-only match => FAIL
    ON_VIOLATION -> TriggerEmergencyDeescalation(mark_FAIL)
  }
  invariant P12_NON_BLOCKING {
    P12 (_collect_observations/_apply_observations) absent => OBSERVED, not FAIL (Team 1 final dropped P12)
    ON_VIOLATION -> TriggerEmergencyDeescalation(record_dissent_D3)
  }
  invariant CONTRACT_UNKNOWN {
    c01/c02 contract artifacts absent => contract_conformance = UNKNOWN (semantic match is never inferred from presence)
    ON_VIOLATION -> TriggerEmergencyDeescalation(mark_UNKNOWN)
  }
  invariant EVIDENCE_ATOMIC {
    evidence file written only after all checks terminate; write = tmp + rename; lock held for the whole run
    ON_VIOLATION -> TriggerEmergencyDeescalation(rollback_evidence)
  }
  invariant EVIDENCE_SHAPE {
    every record = {test, command, exit_code, stdout, stderr, timestamp, verifier, dissent_id:"D3"}
    ON_VIOLATION -> TriggerEmergencyDeescalation(refuse_persist)
  }

  fn F(R_t, E_t) {
    acquire_lock(MAX_CAPACITY = 1);
    clone_or_bind_existing(E_t.repo, E_t.branch);
    fetch_bytes(E_t.relative_file);
    hash_bytes_sha256(E_t.file_bytes);
    run_acceptance_greps(E_t.file_bytes);
    evaluate_checks(E_t.file_bytes);
    classify_contract_conformance(E_t.contract_artifacts?);
    persist_evidence_atomically(R_t, E_t);
    release_lock();
  }

  hypothesis H_WP15_LIVE_TURN_LOOP_MATCHES_C01_C02 {
    live branch file contains all 13 critical sub-functions, the canonical pointer table
    name, and the schema constants, and its digest equals the architect-recorded digest;
    status = UNKNOWN until measured by an independent verifier with network access
  }

  promotion MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT
          -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE;
}
```

## 3. Check catalogue

### 3.1 Blocking — critical sub-functions (acceptance step 3)

`run_canonical_turn`, `resolve_reentry`, `fill_jspace`, `uptake_and_state`,
`_mint_turn_event_id`, `_submit_effect_in_transaction`, `percept_axes`,
`derive_percept_signals`, `_welford_*` (grep-prefix), `_r6*` (grep-prefix),
`_rate_limited_step`, `_clip`, `_theoretischer_broadcast_bereich`.

Exact-name checks require an anchored `def <name>(`; a prefix-only hit (e.g.
`def resolve_reentry_v2`) is a blocking `FAIL`, because the required symbol is absent.
The two prefix checks (`_welford_`, `_r6`) follow the acceptance grep semantics.

### 3.2 Pointer table (acceptance step 4)

| Symbol | Blocking | Note |
|---|---|---|
| `f2_grid10_turn_pointer` | yes | canonical table name (Team 1 final) |
| `turn_pointer` | no | field name, observation only |
| `reentry_pointer` | no | field name, observation only |

### 3.3 Schema constants (acceptance step 6)

`SCHEMA_`, `PERCEPT_`, `CREATE TABLE` — all blocking.

### 3.4 P12 (acceptance step 5) — non-blocking

`_collect_observations`, `_apply_observations`. The Team 1 final architecture **dropped**
P12 (accepted objection from `mistral-large-4`). Absence is therefore recorded as an
observation and does not fail the audit; presence is likewise not treated as proof that
P12 was reinstated. Recorded under dissent `D3`.

### 3.5 Contract conformance — UNKNOWN

`c01`/`c02` contract artifacts were not supplied. The harness records artifact presence
only; semantic conformance requires independent coordinator review and stays `UNKNOWN`.

## 4. Procedure (executable)

```bash
# 0. self-test of the harness logic (synthetic fixture; proves nothing about upstream)
bun agent-sdk/src/gridv1/wp15_audit.test.ts

# 1. live audit (clones, hashes, greps, writes evidence)
bun agent-sdk/src/gridv1/wp15_audit.ts \
  --repo https://github.com/machine-b/frankenstein-repo.git \
  --branch live \
  --clone-dir /tmp/frank-live \
  --file scripts/f2wp1207_grid10_turn_loop.py \
  --out docs/gridv1/WP15_EVIDENCE.json \
  --verifier "<independent verifier name>"

# 2. with the architect-recorded digest and contract artifacts
bun agent-sdk/src/gridv1/wp15_audit.ts \
  --expected-sha256 <hex> \
  --contract <path-to-c01> --contract <path-to-c02> \
  --out docs/gridv1/WP15_EVIDENCE.json
```

Exit codes: `0 = PASS`, `1 = FAIL`, `2 = UNKNOWN`, `3 = refusal/error`.
The harness refuses concurrent runs (`MAX_CAPACITY = 1`, advisory lock next to the
evidence file) and writes the evidence file atomically (temp file + rename).

## 5. Evidence form

`docs/gridv1/WP15_EVIDENCE.json` — one record per executed command:

```json
{
  "test": "WP15-2 verify SHA-256",
  "command": "sha256sum scripts/f2wp1207_grid10_turn_loop.py",
  "exit_code": 0,
  "stdout": "<hex>  scripts/f2wp1207_grid10_turn_loop.py",
  "stderr": "",
  "timestamp": "<ISO-8601>",
  "verifier": "<name>",
  "dissent_id": "D3"
}
```

The current committed evidence file is the **not-executed** baseline: every record has
`exit_code: null` and an explicit `NOT_EXECUTED` marker.

## 6. Notes / dissent `D3`

1. Branch discrepancy: the acceptance test clones `-b live`; the Team 1 excerpt names the
   `machine-b` branch. The harness parameterises the branch and records the observed
   branch (`git rev-parse --abbrev-ref HEAD`) next to the requested one. Not resolved here.
2. P12 is non-blocking (Team 1 final dropped it).
3. `c01`/`c02` conformance is `UNKNOWN` without the contract artifacts.
4. No Rust module was added: WP-1.5 is build-time tooling, so `src/lib.rs` is untouched
   (its current content is not reproduced here because it was not supplied).
5. Promotion ladder for this work package: `MEASURE` (clone + hash + greps) →
   `FALSIFY` (negative fixture) → `MATCHED_ABLATION` (synthetic fixture) →
   `VERIFIED_OUTCOME` (live run with expected digest) → `CAUSAL_CREDIT` /
   `BOUNDED_ADMISSION` / `REENTRY_TEST` / `CONTROL_INFLUENCE` remain **UNKNOWN** until an
   independent verifier executes the live run.
```

=== FILE: docs/gridv1/WP15_EVIDENCE.json ===
```json
{
  "test": "WP-1.5 GRID10 turn loop code audit",
  "command": "bun agent-sdk/src/gridv1/wp15_audit.ts --repo https://github.com/machine-b/frankenstein-repo.git --branch live --clone-dir /tmp/frank-live --file scripts/f2wp1207_grid10_turn_loop.py --out docs/gridv1/WP15_EVIDENCE.json --verifier coder-wp15-team4",
  "exit_code": null,
  "stdout": "",
  "stderr": "NOT_EXECUTED: the authoring context for this work package has no network or process-execution access. The live clone, SHA-256 verification and grep checks were not run. Status remains UNKNOWN; no digest, exit code or grep output is fabricated.",
  "timestamp": "2026-09-30T00:00:00Z",
  "timestamp_precision": "day",
  "verifier": "coder-wp15-team4",
  "dissent_id": "D3",
  "schema_version": "wp15.audit.v1",
  "status": "UNKNOWN",
  "epistemic_class": "UNKNOWN",
  "target": {
    "repo_url": "https://github.com/machine-b/frankenstein-repo.git",
    "branch_requested": "live",
    "branch_observed": null,
    "branch_discrepancy": "Acceptance test clones branch 'live'; the Team 1 architecture excerpt names the 'machine-b' branch. Recorded, not resolved.",
    "relative_file": "scripts/f2wp1207_grid10_turn_loop.py",
    "clone_dir": "/tmp/frank-live",
    "git_head": null
  },
  "sha256": {
    "value": null,
    "expected": null,
    "status": "UNKNOWN",
    "source": "none",
    "note": "Expected digest not supplied by the architect; measured digest not obtainable in the authoring context. UNKNOWN is not 0 and not PASS."
  },
  "checks": [
    { "id": "fn.run_canonical_turn", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn.resolve_reentry", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn.fill_jspace", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn.uptake_and_state", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn._mint_turn_event_id", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn._submit_effect_in_transaction", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn.percept_axes", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn.derive_percept_signals", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn._welford_", "blocking": true, "status": "UNKNOWN", "note": "grep-prefix semantics" },
    { "id": "fn._r6", "blocking": true, "status": "UNKNOWN", "note": "grep-prefix semantics" },
    { "id": "fn._rate_limited_step", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn._clip", "blocking": true, "status": "UNKNOWN" },
    { "id": "fn._theoretischer_broadcast_bereich", "blocking": true, "status": "UNKNOWN" },
    { "id": "ptr.f2_grid10_turn_pointer", "blocking": true, "status": "UNKNOWN" },
    { "id": "ptr.turn_pointer", "blocking": false, "status": "UNKNOWN" },
    { "id": "ptr.reentry_pointer", "blocking": false, "status": "UNKNOWN" },
    { "id": "schema.SCHEMA_", "blocking": true, "status": "UNKNOWN" },
    { "id": "schema.PERCEPT_", "blocking": true, "status": "UNKNOWN" },
    { "id": "schema.CREATE_TABLE", "blocking": true, "status": "UNKNOWN" },
    { "id": "p12._collect_observations", "blocking": false, "status": "UNKNOWN", "note": "P12 dropped in Team 1 final; non-blocking." },
    { "id": "p12._apply_observations", "blocking": false, "status": "UNKNOWN", "note": "P12 dropped in Team 1 final; non-blocking." }
  ],
  "contract_conformance": {
    "status": "UNKNOWN",
    "artifacts": [],
    "note": "c01/c02 contract artifacts were not supplied to WP-1.5; semantic conformance is UNKNOWN and is never inferred from function-name presence."
  },
  "records": [
    {
      "test": "WP15-1 clone live branch",
      "command": "git clone -b live https://github.com/machine-b/frankenstein-repo.git /tmp/frank-live",
      "exit_code": null,
      "stdout": "",
      "stderr": "NOT_EXECUTED: no network access in the authoring context.",
      "timestamp": "2026-09-30T00:00:00Z",
      "verifier": "coder-wp15-team4",
      "dissent_id": "D3"
    },
    {
      "test": "WP15-1b bind evidence to commit",
      "command": "git rev-parse HEAD",
      "exit_code": null,
      "stdout": "",
      "stderr": "NOT_EXECUTED: no checkout available.",
      "timestamp": "2026-09-30T00:00:00Z",
      "verifier": "coder-wp15-team4",
      "dissent_id": "D3"
    },
    {
      "test": "WP15-1c bind evidence to branch",
      "command": "git rev-parse --abbrev-ref HEAD",
      "exit_code": null,
      "stdout": "",
      "stderr": "NOT_EXECUTED: no checkout available.",
      "timestamp": "2026-09-30T00:00:00Z",
      "verifier": "coder-wp15-team4",
      "dissent_id": "D3"
    },
    {
      "test": "WP15-2 verify SHA-256",
      "command": "sha256sum scripts/f2wp1207_grid10_turn_loop.py",
      "exit_code": null,
      "stdout": "",
      "stderr": "NOT_EXECUTED: no checkout available; digest UNKNOWN.",
      "timestamp": "2026-09-30T00:00:00Z",
      "verifier": "coder-wp15-team4",
      "dissent_id": "D3"
    },
    {
      "test": "WP15-3..6 grep critical sub-functions",
      "command": "grep -n \"def run_canonical_turn\\|def resolve_reentry\\|def fill_jspace\\|def uptake_and_state\\|def _mint_turn_event_id\\|def _submit_effect_in_transaction\\|def percept_axes\\|def derive_percept_signals\\|def _welford_\\|def _r6\\|def _rate_limited_step\\|def _clip\\|def _theoretischer_broadcast_bereich\" scripts/f2wp1207_grid10_turn_loop.py",
      "exit_code": null,
      "stdout": "",
      "stderr": "NOT_EXECUTED: no checkout available.",
      "timestamp": "2026-09-30T00:00:00Z",
      "verifier": "coder-wp15-team4",
      "dissent_id": "D3"
    },
    {
      "test": "WP15-4 grep pointer table names",
      "command": "grep -n \"turn_pointer\\|reentry_pointer\\|f2_grid10_turn_pointer\" scripts/f2wp1207_grid10_turn_loop.py",
      "exit_code": null,
      "stdout": "",
      "stderr": "NOT_EXECUTED: no checkout available.",
      "timestamp": "2026-09-30T00:00:00Z",
      "verifier": "coder-wp15-team4",
      "dissent_id": "D3"
    },
    {
      "test": "WP15-5 grep P12 optional observations",
      "command": "grep -n \"_collect_observations\\|_apply_observations\" scripts/f2wp1207_grid10_turn_loop.py",
      "exit_code": null,
      "stdout": "",
      "stderr": "NOT_EXECUTED: no checkout available. Non-blocking check (P12 dropped in Team 1 final).",
      "timestamp": "2026-09-30T00:00:00Z",
      "verifier": "coder-wp15-team4",
      "dissent_id": "D3"
    },
    {
      "test": "WP15-6 grep schema constants",
      "command": "grep -n \"SCHEMA_\\|PERCEPT_\\|CREATE TABLE\" scripts/f2wp1207_grid10_turn_loop.py",
      "exit_code": null,
      "stdout": "",
      "stderr": "NOT_EXECUTED: no checkout available.",
      "timestamp": "2026-09-30T00:00:00Z",
      "verifier": "coder-wp15-team4",
      "dissent_id": "D3"
    }
  ],
  "notes": [
    "Harness self-test (synthetic fixture) is executable via: bun agent-sdk/src/gridv1/wp15_audit.test.ts",
    "Live audit is executable via: bun agent-sdk/src/gridv1/wp15_audit.ts --out docs/gridv1/WP15_EVIDENCE.json",
    "No Rust module was added; src/lib.rs is intentionally untouched.",
    "Promotion ladder: MEASURE and FALSIFY are implemented in the harness; VERIFIED_OUTCOME and above remain UNKNOWN until an independent verifier runs the live audit."
  ]
}
```

**Files delivered:** `agent-sdk/src/gridv1/wp15_audit.ts`, `agent-sdk/src/gridv1/wp15_audit.test.ts`, `docs/gridv1/WP15_GRID10_TURN_LOOP_AUDIT.md`, `docs/gridv1/WP15_EVIDENCE.json`. No `src/lib.rs` change (no Rust code required for this build-time audit).