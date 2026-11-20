import path from "node:path";
import { encodeChannels } from "./binary.js";
import { probe, decodeAudio, deinterleave, extractSubtitles } from "./ffmpeg.js";

export const MEDIA_EXTENSIONS = [".mkv", ".mka", ".wv", ".wav", ".flac"];

const bad = (message) => Object.assign(new Error(message), { status: 400 });

/** Decode an uploaded media file (first audio stream + optional SRT labels) into the binary channel format. */
export async function decodeMedia(file, filename) {
  if (!MEDIA_EXTENSIONS.includes(path.extname(filename).toLowerCase())) {
    throw bad(`Unsupported file type. The server decodes ${MEDIA_EXTENSIONS.join(", ")} files; CSV is read in the browser.`);
  }
  const info = await probe(file, true);
  if (!info.audio.length) throw bad("The file contains no data stream.");
  const stream = info.audio[0];
  const channels = deinterleave(await decodeAudio(file, stream.index, true), stream.channels);
  const warnings = [];
  if (info.audio.length > 1) warnings.push("File has more than one stream, only the first one is shown.");
  if (!stream.timestamp) warnings.push("No timestamp found in file, showing seconds since start.");
  const subtitles = info.subs.length ? await extractSubtitles(file, info.subs[0].index, true) : null;
  return encodeChannels({
    title: stream.title ?? path.basename(filename).replace(/\.[^.]+$/, ""),
    tz: "UTC",
    t0: stream.timestamp ?? 0,
    sampleRate: stream.sampleRate,
    measures: stream.measures ?? channels.map((_, i) => `ch${i + 1}`),
    meta: { filename, label: filename },
    warnings,
    embeddedLabels: subtitles ? { format: "srt", text: subtitles } : null,
  }, channels);
}
