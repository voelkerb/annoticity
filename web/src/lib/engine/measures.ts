export interface Measure { id: string; name: string; unit: string; axis: string; color: string; kind: 'power' | 'wave' }

const BASE: Record<string, Omit<Measure, 'id'>> = {
  p: { name: "Active Power", unit: "W", axis: "Power", color: "#ef4444", kind: "power" },
  q: { name: "Reactive Power", unit: "var", axis: "Power", color: "#38bdf8", kind: "power" },
  s: { name: "Apparent Power", unit: "VA", axis: "Power", color: "#f59e0b", kind: "power" },
  v: { name: "Voltage", unit: "V", axis: "Voltage", color: "#22c55e", kind: "wave" },
  i: { name: "Current", unit: "A", axis: "Current", color: "#60a5fa", kind: "wave" },
  v_rms: { name: "RMS Voltage", unit: "V", axis: "Voltage", color: "#22c55e", kind: "power" },
  i_rms: { name: "RMS Current", unit: "A", axis: "Current", color: "#60a5fa", kind: "power" },
};
const FALLBACK = ["#a78bfa", "#f472b6", "#2dd4bf", "#fb923c", "#a3e635", "#e879f9"];
const PHASE_SHADE = ["", "", "cc", "99"];

/** Describe a measure id such as "p", "q_l2" or any custom CSV column. */
export function describeMeasure(id: string, index = 0): Measure {
  const m = /^(.*?)(?:_l(\d))?$/.exec(id)!;
  const base = BASE[m[1].toLowerCase()];
  const leg = m[2] ? Number(m[2]) : null;
  if (!base) {
    return { id, name: id, unit: "", axis: "Value", color: FALLBACK[index % FALLBACK.length], kind: "power" };
  }
  return {
    id,
    name: leg ? `${base.name} L${leg}` : base.name,
    unit: base.unit,
    axis: base.axis,
    color: leg && leg > 1 ? base.color + PHASE_SHADE[leg] : base.color,
    kind: base.kind,
  };
}
