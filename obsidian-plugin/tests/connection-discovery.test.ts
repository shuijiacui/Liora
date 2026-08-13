import assert from "node:assert/strict";
import test from "node:test";
import { defaultConnectionPath, parseConnectionFile } from "../src/connection-discovery.ts";

test("parses a loopback Liora runtime connection", () => {
  assert.deepEqual(parseConnectionFile({
    schema_version: 1,
    host: "127.0.0.1",
    port: 43117,
    token: "temporary-token"
  }), {
    engineUrl: "http://127.0.0.1:43117",
    accessToken: "temporary-token"
  });
});

test("rejects remote or incomplete runtime connections", () => {
  assert.equal(parseConnectionFile({ schema_version: 1, host: "example.com", port: 43117, token: "x" }), null);
  assert.equal(parseConnectionFile({ schema_version: 1, host: "127.0.0.1", port: 0, token: "x" }), null);
  assert.equal(parseConnectionFile({ schema_version: 2, host: "127.0.0.1", port: 43117, token: "x" }), null);
});

test("uses the explicit Liora user data directory when present", () => {
  assert.equal(
    defaultConnectionPath({ LIORA_USER_DATA_DIR: "D:\\LioraData" }),
    "D:\\LioraData\\knowledge-engine.json"
  );
});
