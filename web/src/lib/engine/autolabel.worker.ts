import { detectEvents, type DetectOptions } from './autolabel.ts'

self.onmessage = (e: MessageEvent<{ id: number; values: Float64Array; rate: number; options: DetectOptions }>) => {
  const { id, values, rate, options } = e.data
  try {
    self.postMessage({ id, ...detectEvents(values, rate, options) })
  } catch (err) {
    self.postMessage({ id, error: (err as Error).message })
  }
}
