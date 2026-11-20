import test from "node:test";
import assert from "node:assert/strict";
import { encodeChannels } from "../src/binary.js";
import { zonedDayStart } from "../src/tz.js";

test("encodeChannels writes an aligned header followed by float32 channels", () => {
  const buf = encodeChannels({ t0: 5, measures: ["p", "q"] }, [Float32Array.of(1, 2, 3), Float32Array.of(4, 5, 6)]);
  const len = buf.readUInt32LE(0);
  const header = JSON.parse(buf.subarray(4, 4 + len).toString());
  assert.deepEqual(header, { t0: 5, measures: ["p", "q"], length: 3 });
  const offset = 4 + len + ((4 - ((4 + len) % 4)) % 4);
  assert.equal(offset % 4, 0);
  const floats = new Float32Array(buf.buffer.slice(buf.byteOffset + offset, buf.byteOffset + buf.length));
  assert.deepEqual([...floats], [1, 2, 3, 4, 5, 6]);
});

test("zonedDayStart handles DST", () => {
  assert.equal(zonedDayStart("2020-08-03", "Europe/Berlin"), 1596405600);
  assert.equal(zonedDayStart("2020-03-30", "Europe/Berlin") - zonedDayStart("2020-03-29", "Europe/Berlin"), 23 * 3600);
});
