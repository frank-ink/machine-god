import type { Dirent } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";

export const PLUGIN_MANIFEST_FILENAME = "plugin.json";

/**
 * Mirrors the Rust loader's PluginManifest shape.
 *
 * Unknown JSON fields are ignored, matching serde's default behavior.
 */
export interface PluginManifest {
  name: string;
  version: string;
  description: string;
  entrypoint: string;
  permissions: string[];
}

export interface DiscoveredPlugin {
  pluginPath: string;
  manifestPath: string;
  manifest: PluginManifest;
}

export type PluginManifestErrorCode =
  | "READ_FAILED"
  | "INVALID_JSON"
  | "INVALID_MANIFEST"
  | "DISCOVERY_FAILED";

export class PluginManifestError extends Error {
  readonly code: PluginManifestErrorCode;
  readonly manifestPath: string;

  constructor(
    code: PluginManifestErrorCode,
    manifestPath: string,
    message: string,
  ) {
    super(message);
    this.name = "PluginManifestError";
    this.code = code;
    this.manifestPath = manifestPath;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export interface PluginDiscoveryFailure {
  manifestPath: string;
  code: PluginManifestErrorCode;
  message: string;
}

export interface PluginDiscoveryResult {
  plugins: DiscoveredPlugin[];
  failures: PluginDiscoveryFailure[];
}

export class PluginDiscoveryError extends Error {
  readonly failures: readonly PluginDiscoveryFailure[];

  constructor(failures: readonly PluginDiscoveryFailure[]) {
    const summary = failures
      .map((failure) => `${failure.manifestPath}: ${failure.message}`)
      .join("; ");
    super(`Plugin discovery failed: ${summary}`);
    this.name = "PluginDiscoveryError";
    this.failures = failures;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Runtime validation is deliberately fail-closed. A malformed manifest is
 * never converted into a partially trusted plugin.
 */
export function isPluginManifest(value: unknown): value is PluginManifest {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isNonEmptyString(value.name) &&
    isNonEmptyString(value.version) &&
    typeof value.description === "string" &&
    isNonEmptyString(value.entrypoint) &&
    Array.isArray(value.permissions) &&
    value.permissions.every(
      (permission): permission is string => typeof permission === "string",
    )
  );
}

export function parsePluginManifest(
  value: unknown,
  manifestPath = "<memory>",
): PluginManifest {
  if (!isPluginManifest(value)) {
    throw new PluginManifestError(
      "INVALID_MANIFEST",
      manifestPath,
      "Manifest must contain name, version, description, entrypoint, and string permissions",
    );
  }

  return {
    name: value.name,
    version: value.version,
    description: value.description,
    entrypoint: value.entrypoint,
    permissions: [...value.permissions],
  };
}

export async function loadPluginManifest(
  manifestPath: string,
): Promise<PluginManifest> {
  const absolutePath = resolve(manifestPath);

  let contents: string;
  try {
    contents = await readFile(absolutePath, "utf8");
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new PluginManifestError(
      "READ_FAILED",
      absolutePath,
      `Unable to read plugin manifest: ${detail}`,
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(contents) as unknown;
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new PluginManifestError(
      "INVALID_JSON",
      absolutePath,
      `Plugin manifest is not valid JSON: ${detail}`,
    );
  }

  return parsePluginManifest(parsed, absolutePath);
}

export async function loadPluginManifestFromDirectory(
  pluginPath: string,
): Promise<PluginManifest> {
  const absolutePluginPath = resolve(pluginPath);
  return loadPluginManifest(
    join(absolutePluginPath, PLUGIN_MANIFEST_FILENAME),
  );
}

const SKIPPED_DIRECTORIES = new Set([
  ".git",
  ".hg",
  ".svn",
  "node_modules",
  "target",
  "dist",
  "build",
]);

const MAX_DISCOVERY_DEPTH = 32;

async function collectManifestPaths(
  directory: string,
  depth = 0,
): Promise<string[]> {
  if (depth > MAX_DISCOVERY_DEPTH) {
    throw new PluginManifestError(
      "DISCOVERY_FAILED",
      directory,
      `Plugin discovery exceeded the maximum depth of ${MAX_DISCOVERY_DEPTH}`,
    );
  }

  let entries: Dirent[];
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new PluginManifestError(
      "DISCOVERY_FAILED",
      directory,
      `Unable to scan plugin directory: ${detail}`,
    );
  }

  entries.sort((left, right) =>
    left.name < right.name ? -1 : left.name > right.name ? 1 : 0,
  );

  const manifests: string[] = [];
  for (const entry of entries) {
    const entryPath = join(directory, entry.name);

    if (entry.isDirectory()) {
      if (!SKIPPED_DIRECTORIES.has(entry.name)) {
        manifests.push(...(await collectManifestPaths(entryPath, depth + 1)));
      }
      continue;
    }

    if (entry.isFile() && entry.name === PLUGIN_MANIFEST_FILENAME) {
      manifests.push(entryPath);
    }
  }

  return manifests;
}

/**
 * Tolerant discovery: valid plugins and manifest failures are reported
 * separately so callers can surface both without treating failure as absence.
 */
export async function discoverPluginsWithErrors(
  pluginRoot: string,
): Promise<PluginDiscoveryResult> {
  const absoluteRoot = resolve(pluginRoot);
  const manifestPaths = await collectManifestPaths(absoluteRoot);
  const plugins: DiscoveredPlugin[] = [];
  const failures: PluginDiscoveryFailure[] = [];

  for (const manifestPath of manifestPaths) {
    try {
      const manifest = await loadPluginManifest(manifestPath);
      plugins.push({
        pluginPath: dirname(manifestPath),
        manifestPath,
        manifest,
      });
    } catch (error: unknown) {
      if (error instanceof PluginManifestError) {
        failures.push({
          manifestPath: error.manifestPath,
          code: error.code,
          message: error.message,
        });
        continue;
      }

      const detail = error instanceof Error ? error.message : String(error);
      failures.push({
        manifestPath,
        code: "INVALID_MANIFEST",
        message: detail,
      });
    }
  }

  plugins.sort((left, right) =>
    left.manifestPath < right.manifestPath
      ? -1
      : left.manifestPath > right.manifestPath
        ? 1
        : 0,
  );

  return { plugins, failures };
}

/**
 * Strict discovery. Any malformed manifest fails the operation instead of
 * being silently omitted.
 */
export async function discoverPlugins(
  pluginRoot: string,
): Promise<DiscoveredPlugin[]> {
  const result = await discoverPluginsWithErrors(pluginRoot);
  if (result.failures.length > 0) {
    throw new PluginDiscoveryError(result.failures);
  }
  return result.plugins;
}

export async function findPlugin(
  pluginRoot: string,
  pluginName: string,
): Promise<DiscoveredPlugin | undefined> {
  const plugins = await discoverPlugins(pluginRoot);
  return plugins.find((plugin) => plugin.manifest.name === pluginName);
}
