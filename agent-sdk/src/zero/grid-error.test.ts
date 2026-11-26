import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  asGridError,
  type GridError,
  type GridErrorCode,
  GRID_ERROR_CODES,
  isGridErrorCode,
  mapGridErrorToCode,
} from "./grid-error.js";

const CODES: readonly GridErrorCode[] = [
  "INVALID_PORT",
  "INVALID_HOST",
  "TRANSPORT_FAILED",
  "UNKNOWN",
];

describe("mapGridErrorToCode", () => {
  it("maps INVALID_PORT", () => {
    assert.equal(mapGridErrorToCode({ code: "INVALID_PORT" }), "INVALID_PORT");
  });

  it("maps INVALID_HOST", () => {
    assert.equal(mapGridErrorToCode({ code: "INVALID_HOST" }), "INVALID_HOST");
  });

  it("maps TRANSPORT_FAILED", () => {
    assert.equal(
      mapGridErrorToCode({ code: "TRANSPORT_FAILED" }),
      "TRANSPORT_FAILED",
    );
  });

  it("maps UNKNOWN code to UNKNOWN", () => {
    assert.equal(mapGridErrorToCode({ code: "UNKNOWN" }), "UNKNOWN");
  });

  it("falls back to UNKNOWN for null", () => {
    assert.equal(mapGridErrorToCode(null), "UNKNOWN");
  });

  it("falls back to UNKNOWN for undefined", () => {
    assert.equal(mapGridErrorToCode(undefined), "UNKNOWN");
  });

  it("falls back to UNKNOWN for primitives", () => {
    assert.equal(mapGridErrorToCode("INVALID_PORT"), "UNKNOWN");
    assert.equal(mapGridErrorToCode(42), "UNKNOWN");
    assert.equal(mapGridErrorToCode(true), "UNKNOWN");
  });

  it("falls back to UNKNOWN for objects without a code", () => {
    assert.equal(mapGridErrorToCode({ message: "boom" }), "UNKNOWN");
    assert.equal(mapGridErrorToCode({}), "UNKNOWN");
  });

  it("falls back to UNKNOWN for objects with a non-string code", () => {
    assert.equal(mapGridErrorToCode({ code: 42 }), "UNKNOWN");
    assert.equal(mapGridErrorToCode({ code: null }), "UNKNOWN");
  });

  it("falls back to UNKNOWN for unregistered string codes", () => {
    assert.equal(mapGridErrorToCode({ code: "NOT_A_CODE" }), "UNKNOWN");
    assert.equal(mapGridErrorToCode({ code: "" }), "UNKNOWN");
  });

  it("is deterministic: same input yields the same code across repeated calls", () => {
    const input = { code: "TRANSPORT_FAILED", extra: true };
    const first = mapGridErrorToCode(input);
    const second = mapGridErrorToCode(input);
    assert.equal(first, second);
    assert.equal(first, "TRANSPORT_FAILED");
  });

  it("never returns a code outside the registry", () => {
    const inputs: unknown[] = [
      null,
      undefined,
      "INVALID_PORT",
      0,
      {},
      { code: "INVALID_PORT" },
      { code: "INVALID_HOST" },
      { code: "TRANSPORT_FAILED" },
      { code: "UNKNOWN" },
      { code: "GARBAGE" },
      { code: 7 },
      [],
    ];
    for (const input of inputs) {
      const code = mapGridErrorToCode(input);
      assert.ok(
        GRID_ERROR_CODES.includes(code),
        `code ${code} must be in the registry`,
      );
    }
  });
});

describe("isGridErrorCode", () => {
  it("narrows each GridErrorCode to true", () => {
    for (const code of CODES) {
      assert.equal(isGridErrorCode(code), true, `${code} is a GridErrorCode`);
    }
  });

  it("rejects arbitrary strings", () => {
    assert.equal(isGridErrorCode("INVALID_PORTX"), false);
    assert.equal(isGridErrorCode(""), false);
    assert.equal(isGridErrorCode("invalid_port"), false);
  });

  it("rejects non-strings", () => {
    assert.equal(isGridErrorCode(null), false);
    assert.equal(isGridErrorCode(undefined), false);
    assert.equal(isGridErrorCode(42), false);
    assert.equal(isGridErrorCode({ code: "INVALID_PORT" }), false);
    assert.equal(isGridErrorCode([]), false);
  });

  it("acts as a type guard in a narrowing context", () => {
    const value: unknown = "INVALID_HOST";
    assert.equal(isGridErrorCode(value), true);
    if (isGridErrorCode(value)) {
      assert.equal(value, "INVALID_HOST");
    }
  });
});

describe("asGridError", () => {
  it("builds a GridError with a measured code", () => {
    const error = asGridError({ code: "INVALID_PORT" }, "port out of range");
    assert.equal(error.kind, "GridError");
    assert.equal(error.code, "INVALID_PORT");
    assert.equal(error.message, "port out of range");
  });

  it("records UNKNOWN when the error is unmeasurable", () => {
    const error = asGridError(new TypeError("boom"), "failed");
    assert.equal(error.code, "UNKNOWN");
    assert.equal(error.message, "failed");
  });

  it("omits detail for null/undefined errors", () => {
    const error = asGridError(null, "nothing");
    assert.equal(error.detail, undefined);
  });
});
