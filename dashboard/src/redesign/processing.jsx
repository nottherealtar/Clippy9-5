// ClippyMe redesign — ProcessingView wired to real polling: live logs, a
// vertical pipeline driven by the detected step, and real clips streaming in
// as partial results arrive.
import { useEffect, useRef, useState } from 'react';
import { Icon, Btn, Badge, Panel } from './primitives';
import { Hero } from './chrome';
import { PIPE } from './data';
import { pipelineStepMeta } from '../lib/pipelineStep';
import { parseTranscriptionRetryStatus } from '../lib/retryStatus';
import { clipVideoSrc, clipCoverSrc, fmtDuration } from './realApi';

// Map the backend's detected pipeline step to an approximate % + pipe index.
// (The backend streams logs, not a numeric %, so this is a visual estimate.)
const STEP_INFO = {
  queued: { pct: 5, idx: 0 },
  downloading: { pct: 18, idx: 0 },
  transcribing: { pct: 38, idx: 1 },
  analyzing: { pct: 58, idx: 2 },
  processing: { pct: 80, idx: 3 },
};

function BatchStrip({ jobs = [] }) {
  if (!jobs.length) return null;
  return (
    <div className="batch-strip">
      {jobs.map((j) => {
        const cls = 'batch-row' + (j.status === 'done' ? ' done' : j.status === 'failed' ? ' failed' : '');
        const speed = j.status === 'downloading' && j.downloadSpeed
          ? `${j.downloadSpeed}${j.downloadPct != null ? ` · ${j.downloadPct.toFixed(0)}%` : ''}`
          : j.status === 'done' ? 'done'
            : j.status === 'failed' ? 'failed'
              : j.status === 'working' ? (j.step || 'working')
                : 'queued';
        return (
          <div key={j.id} className={cls}>
            <span className="bl">{j.label}</span>
            <span className="bp">{j.status === 'downloading' && j.downloadEta ? j.downloadEta : ''}</span>
            <span className="bs">{speed}</span>
          </div>
        );
      })}
    </div>
  );
}

function MiniClip({ clip }) {
  const [videoReady, setVideoReady] = useState(false);
  const [retryBust, setRetryBust] = useState(0);
  const [failed, setFailed] = useState(false);
  const poster = clipCoverSrc(clip, retryBust);
  const src = clipVideoSrc(clip, retryBust);

  useEffect(() => {
    setVideoReady(false);
    setFailed(false);
    setRetryBust(0);
  }, [clip?.video_url, clip?.original_index]);

  const onVideoError = () => {
    // During live rendering the mp4 may not be readable yet — retry a few times.
    if (retryBust < 3) {
      window.setTimeout(() => setRetryBust(Date.now()), 1500);
    } else {
      setFailed(true);
    }
  };

  return (
    <div className="clip fade-in" style={{ cursor: 'default' }}>
      <div className="clip-media" style={{ padding: 0, background: '#000' }}>
        {poster && (
          <img src={poster} alt="" aria-hidden="true"
            className={'clip-poster' + (videoReady ? ' clip-poster--hide' : '')}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', zIndex: 0 }} />
        )}
        {!failed ? (
          <video src={src} poster={poster || undefined} muted playsInline preload="auto"
            onLoadedData={() => setVideoReady(true)}
            onError={onVideoError}
            style={{
              position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover',
              zIndex: 0, opacity: videoReady || poster ? 1 : 0,
            }} />
        ) : (
          <div className="clip-preview-fallback" style={{ position: 'absolute', inset: 0, zIndex: 0 }}>
            <Icon n="film" />
            <span>Preview loading…</span>
          </div>
        )}
        <div className="clip-top" style={{ padding: 8 }}>
          <span className="score" style={{ fontSize: 12, padding: '3px 7px' }}>{Math.round(clip.viral_score || 0)}</span>
        </div>
        <div className="clip-bottom" style={{ padding: 8 }}><span className="dur">{fmtDuration(clip.start, clip.end)}</span></div>
      </div>
    </div>
  );
}

export function ProcessingView({ media, status, logs = [], step, clips = [], batchJobs = [], onCancel, onRetry,
                                 paused = false, onPause, onResume, onStop, opts = {} }) {
  const logRef = useRef(null);
  const stickRef = useRef(true);

  const onLogScroll = () => {
    const el = logRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickRef.current = dist < 48;
  };

  useEffect(() => {
    const el = logRef.current;
    if (!el || !stickRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [logs]);

  const failed = status === 'error';
  const info = STEP_INFO[step] || STEP_INFO.queued;
  // Once clips start arriving, push the bar toward the finish.
  const clipBoost = clips.length > 0 ? Math.min(18, clips.length * 3) : 0;
  const pct = failed ? 100 : Math.min(96, info.pct + clipBoost);
  const activeIdx = clips.length > 0 ? Math.max(info.idx, 4) : info.idx;
  const sourceLabel = media?.type === 'url' ? media.payload : (media?.payload?.name || media?.payload || 'your video');
  // Honest phase word instead of a fabricated percentage (the backend streams
  // logs, not a number — the bar below is a coarse estimate, the word is the
  // ground truth from the detected step).
  const STEP_WORD = { queued: 'queued', downloading: 'fetching', transcribing: 'transcribing', analyzing: 'scoring', processing: 'rendering' };
  const phase = failed ? 'failed' : clips.length > 0 ? 'rendering' : (STEP_WORD[step] || 'working');
  // Auto-adapt each step's sub-label to what actually ran (deepgram vs whisper
  // fallback, gemini model vs no-AI TextTiling, reframe mode, local-vs-URL
  // source) — falls back to the static PIPE meta for steps we can't resolve.
  const metaOverride = pipelineStepMeta(logs, { ...opts, mediaType: media?.type });
  const retryStatus = parseTranscriptionRetryStatus(logs);
  // The reframe step name hard-codes "9:16"; reflect the real output aspect so
  // a 1:1 / 16:9 job isn't mislabelled.
  const nameOverride = { reframe: `Reframe ${opts.aspect || '9:16'}` };

  return (
    <div className="container fade-in">
      <Hero eyebrow={failed ? 'Pipeline error' : 'Pipeline running'}
        line1={failed ? 'Something broke.' : 'Cutting your clips.'}
        sub={failed ? 'The job failed. Check the log below, then retry or start over.'
          : "ClippyMe is working through the pipeline. Clips show up below the moment each one is rendered, so you don't have to wait for the whole batch."} />
      <div className="proc">
        <aside className="proc-aside">
          <Panel pad={true}>
            <div className="pipe">
              {PIPE.map((s, i) => {
                const done = !failed && (i < activeIdx);
                const active = !failed && i === activeIdx;
                const meta = metaOverride[s.id] || s.meta;
                const name = nameOverride[s.id] || s.name;
                return (
                  <div key={s.id} className={'pstep' + (done ? ' done' : active ? ' active' : '')}>
                    <div className="rail">
                      <div className="pdot"><Icon n={done ? 'check' : s.icon} /></div>
                      {i < PIPE.length - 1 && <div className="pseg-v"></div>}
                    </div>
                    <div className="pbody">
                      <div className="pname">{name}</div>
                      <div className="pmeta">{active ? meta + ' …' : done ? 'done' : meta}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>
        </aside>

        <div>
          <Panel pad={true}>
            <div className="pbar-wrap">
              <div className="pbar"><i style={{ width: pct + '%', background: failed ? 'var(--danger)' : undefined }}></i></div>
              <div className="pbar-pct" style={{ fontFamily: 'var(--font-mono)', fontSize: 13, letterSpacing: '.04em', minWidth: 110, color: failed ? 'var(--danger)' : 'var(--blue-300)' }}>{phase}</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 10 }}>
              <span className="label" style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>
                <span className="mono" style={{ color: 'var(--fg-4)' }}>src ·</span> {String(sourceLabel).slice(0, 46)}
              </span>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                {failed && <Btn variant="secondary" size="sm" icon="wand-sparkles" onClick={onRetry}>Retry</Btn>}
                {!failed && onPause && (
                  paused
                    ? <Btn variant="secondary" size="sm" icon="play" onClick={onResume}>Resume</Btn>
                    : <Btn variant="ghost" size="sm" icon="clock" onClick={onPause}>Pause</Btn>
                )}
                {!failed && onStop && clips.length > 0 && (
                  <Btn variant="secondary" size="sm" icon="check-square" onClick={onStop}>Stop &amp; keep</Btn>
                )}
                <Btn variant="ghost" size="sm" icon="x" onClick={onCancel}>{failed ? 'Start over' : 'Discard'}</Btn>
              </span>
            </div>
            {media?.type === 'batch' && batchJobs.length > 0 && (
              <BatchStrip jobs={batchJobs} />
            )}
            {retryStatus && !failed && (
              <div className="retry-banner" role="status">
                <Icon n="clock" />
                <span>{retryStatus.message}</span>
              </div>
            )}
            <div className="log" ref={logRef} onScroll={onLogScroll}>
              {logs.length === 0 && <div className="ln"><span className="ts">··</span> <span>waiting for the worker…</span></div>}
              {logs.map((l, i) => (
                <div key={i} className="ln">
                  <span className={
                    /error|failed|❌/i.test(l) ? '' :
                    /🔁|retry|fallback|falling back/i.test(l) ? 'retry' :
                    /✓|done|complete|found/i.test(l) ? 'ok' : ''
                  }
                    style={/error|failed|❌/i.test(l) ? { color: 'var(--danger)' } : undefined}>{l}</span>
                </div>
              ))}
              {!failed && <div><span className="cursor"></span></div>}
            </div>
          </Panel>

          <div className="stream-head">
            <h3>Clips</h3>
            {clips.length > 0
              ? <Badge tone="teal" icon="check">{clips.length} ready</Badge>
              : <Badge tone="out">{failed ? 'no clips' : 'finding moments…'}</Badge>}
          </div>
          <div className="stream">
            {clips.slice(0, 8).map((c, i) => <MiniClip key={c.original_index ?? i} clip={c} idx={i} />)}
            {!failed && clips.length < 4 && Array.from({ length: 4 - clips.length }).map((_, i) => (
              <div key={'slot' + i} className="slot">{i === 0 && clips.length > 0 ? <div className="sk"></div> : (clips.length === 0 && i === 0 ? <div className="sk"></div> : null)}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
