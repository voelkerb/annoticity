/** Header of the server's binary channel format (see server/src/binary.js). */
export interface ChannelHeader {
  title: string; info?: string; tz?: string; t0: number; sampleRate: number
  measures: string[]; length: number
  meta?: Record<string, unknown>
  warnings?: string[]
  embeddedLabels?: { format: 'srt'; text: string } | null
}

export function decodeChannels(buf: ArrayBuffer): { header: ChannelHeader; data: Record<string, Float32Array> } {
  const view = new DataView(buf)
  const len = view.getUint32(0, true)
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, len))) as ChannelHeader
  let offset = 4 + len + ((4 - ((4 + len) % 4)) % 4)
  const data: Record<string, Float32Array> = {}
  for (const id of header.measures) {
    data[id] = new Float32Array(buf, offset, header.length)
    offset += header.length * 4
  }
  return { header, data }
}
