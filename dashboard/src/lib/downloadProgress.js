import { detectPipelineStep } from './pipelineStep';

/** Parse a throttled yt-dlp progress line from the backend log. */
export function parseDownloadProgressLine(line) {
  if (!line || typeof line !== 'string') return null;
  const m = line.match(/📥 Download\s+([\d.]+)%\s·\s([^·]+?)\s·\sETA\s+(\S+)/);
  if (!m) return null;
  return { pct: parseFloat(m[1]), speed: m[2].trim(), eta: m[3] };
}

/** Summarise the latest download stats from a job's log tail. */
export function downloadStatsFromLogs(logs) {
  if (!Array.isArray(logs)) return null;
  for (let i = logs.length - 1; i >= 0; i -= 1) {
    const parsed = parseDownloadProgressLine(logs[i]);
    if (parsed) return parsed;
  }
  return null;
}

/** Build per-job batch row state from status payload + log tail. */
export function batchJobRow(jobId, index, statusPayload, finished) {
  const logs = statusPayload?.logs || [];
  const dl = downloadStatsFromLogs(logs);
  const step = detectPipelineStep(logs);
  let state = 'queued';
  if (finished) {
    state = statusPayload?.status === 'failed' || statusPayload?.status === 'cancelled'
      ? 'failed'
      : 'done';
  } else if (statusPayload?.status === 'processing') {
    state = step === 'downloading' ? 'downloading' : 'working';
  } else if (statusPayload?.status === 'paused') {
    state = 'paused';
  }
  return {
    id: jobId,
    label: `Job ${index + 1}`,
    status: state,
    step,
    downloadPct: dl?.pct ?? null,
    downloadSpeed: dl?.speed ?? null,
    downloadEta: dl?.eta ?? null,
  };
}
