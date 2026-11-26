/**
 * Grid error mapper.
 *
 * Pure, hermetic mapping of arbitrary unknown values into the four
 * admissible GridErrorCode values. Never invents a code outside the
 * registry; anything unmeasurable becomes UNKNOWN.
 */

export type GridErrorCode =
  | "INVALID_PORT"
  | "INVALID_HOST"
  | "TRANSPORT_FAILED"
  | "UNKNOWN";

export const GRID_ERROR_CODES: readonly GridErrorCode[] = [
  "INVALID_PORT",
  "INVALID_HOST",
  "TRANSPORT_FAILED",
  "UNKNOWN",
] as const;

export interface GridError {
  readonly kind: "GridError";
  readonly code: GridErrorCode;
  readonly message: string;
  readonly detail?: unknown;
}

function isPlainObjectWithCode(value: unknown): value is { code: unknown } {
  return typeof value === "object" && value !== null && "code" in value;
}

/**
 * Map an arbitrary value to a GridErrorCode.
 *
 * Pure function: same input, same output, no ambient environment, no wall
 * clock, no network. The only admissible outputs are the four registered
 * codes; UNKNOWN is the terminal fallback for everything else.
 */
export function mapGridErrorToCode(error: unknown): GridErrorCode {
  if (!isPlainObjectWithCode(error)) {
    return "UNKNOWN";
  }

  if (typeof error.code !== "string") {
    return "UNKNOWN";
  }

  switch (error.code) {
    case "INVALID_PORT":
      return "INVALID_PORT";
    case "INVALID_HOST":
      return "INVALID_HOST";
    case "TRANSPORT_FAILED":
      return "TRANSPORT_FAILED";
    case "UNKNOWN":
      return "UNKNOWN";
    default:
      return "UNKNOWN";
  }
}

/**
 * Type guard for GridErrorCode. Narrows `unknown` to `GridErrorCode`.
 */
export function isGridErrorCode(value: unknown): value is GridErrorCode {
  return (
    typeof value === "string" &&
    (value === "INVALID_PORT" ||
      value === "INVALID_HOST" ||
      value === "TRANSPORT_FAILED" ||
      value === "UNKNOWN")
  );
}

/**
 * Build a GridError record from an arbitrary error and a message.
 * The code is always measured via mapGridErrorToCode; never asserted.
 */
export function asGridError(error: unknown, message: string): GridError {
  return {
    kind: "GridError",
    code: mapGridErrorToCode(error),
    message,
    detail: error === null || error === undefined ? undefined : error,
  };
}
