import { spawn } from "node:child_process";

function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    const out = [];
    let err = "";
    p.stdout.on("data", (c) => out.push(c));
    p.stderr.on("data", (c) => (err += c));
    p.on("error", (e) =>
      reject(e.code === "ENOENT" ? new Error(`${cmd} not found. Please install FFmpeg and make sure it is on the PATH.`) : e));
    p.on("close", (code) => (code === 0 ? resolve(Buffer.concat(out)) : reject(new Error(`${cmd} failed: ${err.trim().slice(-300)}`))));
  });
}

/** List audio and subtitle streams of a media file. */
export async function probe(file) {
  const out = await run("ffprobe", ["-v", "error", "-show_streams", "-show_format", "-of", "json", file]);
  const json = JSON.parse(out.toString());
  const tags = (s) => Object.fromEntries(Object.entries(s.tags ?? {}).map(([k, v]) => [k.toUpperCase(), v]));
  const audio = [], subs = [];
  for (const s of json.streams ?? []) {
    if (s.codec_type === "audio") {
      const t = tags(s);
      audio.push({
        index: s.index,
        sampleRate: Number(s.sample_rate),
        channels: s.channels,
        title: t.TITLE ?? null,
        timestamp: t.TIMESTAMP ? Number(t.TIMESTAMP) : null,
        measures: t.CHANNEL_TAGS ? t.CHANNEL_TAGS.split(",").map((m) => m.trim().toLowerCase()) : null,
      });
    } else if (s.codec_type === "subtitle") subs.push({ index: s.index });
  }
  return { audio, subs, duration: Number(json.format?.duration ?? 0) };
}

/** Decode one audio stream to interleaved float32 samples. */
export async function decodeAudio(file, streamIndex) {
  const buf = await run("ffmpeg", ["-v", "error", "-i", file, "-map", `0:${streamIndex}`, "-f", "f32le", "-acodec", "pcm_f32le", "-"]);
  return new Float32Array(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength - (buf.byteLength % 4)));
}

/** First subtitle stream as SRT text, or null. */
export async function extractSubtitles(file, streamIndex) {
  try {
    return (await run("ffmpeg", ["-v", "error", "-i", file, "-map", `0:${streamIndex}`, "-f", "srt", "-"])).toString();
  } catch {
    return null;
  }
}

/** Split interleaved channels into one Float32Array per channel. */
export function deinterleave(samples, channels) {
  const n = Math.floor(samples.length / channels);
  const out = Array.from({ length: channels }, () => new Float32Array(n));
  for (let i = 0; i < n; i++) for (let c = 0; c < channels; c++) out[c][i] = samples[i * channels + c];
  return out;
}
