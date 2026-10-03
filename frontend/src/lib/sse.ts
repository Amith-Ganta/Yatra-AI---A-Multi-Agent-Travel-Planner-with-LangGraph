// Minimal server-sent-events parser for fetch() streams. EventSource cannot be used because
// POST /api/plan is a POST request with a JSON body.

/**
 * Split a buffer into complete SSE frames and return the JSON payload of each `data:` line,
 * plus whatever is left over (an incomplete trailing frame) to prepend to the next chunk.
 * Frames that are not valid JSON are skipped.
 */
export function parseSseBuffer(buffer: string): { payloads: unknown[]; rest: string } {
  const normalised = buffer.replace(/\r\n/g, '\n');
  const frames = normalised.split('\n\n');
  const rest = frames.pop() ?? '';

  const payloads: unknown[] = [];
  for (const frame of frames) {
    const data = frame
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (!data) continue;
    try {
      payloads.push(JSON.parse(data));
    } catch {
      // ignore a malformed frame rather than killing the whole stream
    }
  }
  return { payloads, rest };
}
