/** Merge localStorage history rows with disk-scanned jobs from GET /api/history. */
export function mergeHistoryEntries(local = [], disk = []) {
  const byId = new Map();

  for (const d of disk || []) {
    if (!d?.jobId) continue;
    byId.set(d.jobId, {
      jobId: d.jobId,
      timestamp: d.timestamp || 0,
      clipCount: d.clipCount ?? 0,
      totalClips: d.totalClips ?? d.clipCount ?? 0,
      cost: d.cost ?? null,
      source: d.source || d.jobId,
      sourceType: 'url',
      status: d.status || ((d.clipCount ?? 0) > 0 ? 'complete' : 'pending'),
      recoveryPhase: d.recoveryPhase ?? null,
      recoverySummary: d.recoverySummary ?? null,
    });
  }

  for (const l of local || []) {
    if (!l?.jobId) continue;
    const existing = byId.get(l.jobId);
    if (existing) {
      byId.set(l.jobId, {
        ...existing,
        ...l,
        clipCount: l.clipCount ?? existing.clipCount,
        totalClips: l.totalClips ?? existing.totalClips,
        cost: l.cost ?? existing.cost,
        source: l.source || existing.source,
        status: existing.status || l.status,
        recoveryPhase: existing.recoveryPhase ?? l.recoveryPhase,
        recoverySummary: existing.recoverySummary ?? l.recoverySummary,
        sourceType: l.sourceType || existing.sourceType,
      });
    } else {
      byId.set(l.jobId, l);
    }
  }

  return [...byId.values()].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
}
