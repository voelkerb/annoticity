import { spawn } from "node:child_process";
import { createReadStream } from "node:fs";

function run(cmd, args, { input, maxOutputBytes = Infinity, timeoutMs = 0 } = {}) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: [input ? "pipe" : "ignore", "pipe", "pipe"] });
    const out = [];
    let err = "";
    let bytes = 0, failure;
    const stop = (error) => { if (!failure) failure = error; p.kill("SIGKILL"); };
    const timer = timeoutMs ? setTimeout(() => stop(Object.assign(new Error(`${cmd} timed out`), { status: 413 })), timeoutMs) : null;
    if (input) {
      const source = createReadStream(input);
      source.on("error", stop);
      p.stdin.on("error", (e) => { if (e.code !== "EPIPE") stop(e); });
      p.on("close", () => source.destroy());
      source.pipe(p.stdin);
    }
    p.stdout.on("data", (c) => {
      bytes += c.length;
      if (bytes > maxOutputBytes) stop(Object.assign(new Error("Decoded media is too large"), { status: 413 }));
      else out.push(c);
    });
    p.stderr.on("data", (c) => { err = (err + c).slice(-4096); });
    p.on("error", (e) => { failure = e.code === "ENOENT" ? new Error(`${cmd} not found. Please install FFmpeg and make sure it is on the PATH.`) : e; });
    p.on("close", (code) => {
      if (timer) clearTimeout(timer);
      if (failure) reject(failure);
      else if (code === 0) resolve(Buffer.concat(out));
      else reject(new Error(`${cmd} failed: ${err.trim().slice(-300)}`));
    });
  });
}

/** List audio and subtitle streams of a media file. */
export async function probe(file, untrusted = false) {
  const out = await run("ffprobe", ["-v", "error", "-show_streams", "-show_format", "-of", "json",
    ...(untrusted ? ["-protocol_whitelist", "pipe", "pipe:0"] : [file])],
  untrusted ? { input: file, maxOutputBytes: 4 * 1024 ** 2, timeoutMs: 120_000 } : {});
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
export async function decodeAudio(file, streamIndex, untrusted = false) {
  const input = untrusted ? ["-protocol_whitelist", "pipe", "-i", "pipe:0"] : ["-i", file];
  const buf = await run("ffmpeg", ["-v", "error", ...input, "-map", `0:${streamIndex}`, "-f", "f32le", "-acodec", "pcm_f32le", "-"],
    untrusted ? { input: file, maxOutputBytes: 128 * 1024 ** 2, timeoutMs: 120_000 } : {});
  return new Float32Array(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength - (buf.byteLength % 4)));
}

/** First subtitle stream as SRT text, or null. */
export async function extractSubtitles(file, streamIndex, untrusted = false) {
  try {
    const input = untrusted ? ["-protocol_whitelist", "pipe", "-i", "pipe:0"] : ["-i", file];
    return (await run("ffmpeg", ["-v", "error", ...input, "-map", `0:${streamIndex}`, "-f", "srt", "-"],
      untrusted ? { input: file, maxOutputBytes: 4 * 1024 ** 2, timeoutMs: 120_000 } : {})).toString();
  } catch (e) {
    console.error("Could not extract subtitles:", e);
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
