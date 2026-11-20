/**
 * Compact transfer format for decoded channels, parsed in the browser by web/src/lib/engine/binary.ts:
 * [uint32 LE header length][UTF-8 JSON header][zero padding to 4 bytes][float32 LE channel 0][channel 1]...
 * The header lists `measures` (channel order) and `length` (samples per channel).
 */
export function encodeChannels(header, channels) {
  const json = Buffer.from(JSON.stringify({ ...header, length: channels[0]?.length ?? 0 }));
  const offset = 4 + json.length + ((4 - ((4 + json.length) % 4)) % 4);
  const total = offset + channels.reduce((n, c) => n + c.byteLength, 0);
  const out = Buffer.alloc(total);
  out.writeUInt32LE(json.length, 0);
  json.copy(out, 4);
  let pos = offset;
  for (const c of channels) {
    Buffer.from(c.buffer, c.byteOffset, c.byteLength).copy(out, pos);
    pos += c.byteLength;
  }
  return out;
}
