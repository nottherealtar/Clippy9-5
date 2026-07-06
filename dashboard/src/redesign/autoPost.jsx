// Auto Post — durable server-side posting queue across jobs.
import { useState, useEffect, useMemo, useCallback } from 'react';
import { Icon, Btn, Panel, Badge, PlatPill, PLATFORMS } from './primitives';
import { Hero } from './chrome';
import {
  fetchAutoPostCandidates,
  fetchAutoPostCampaigns,
  fetchAutoPostCampaign,
  createAutoPostCampaign,
  pauseAutoPostCampaign,
  resumeAutoPostCampaign,
  retryAutoPostItem,
} from './realApi';
import { seedToggles, seedHookParams, seedSubtitleParams, seedLogoParams } from '../lib/seedClipParams';
import { localDatePlus } from '../lib/scheduleDates';

const PLAT_MAP = { tiktok: 'tiktok', ig: 'instagram', yt: 'youtube' };

function statusTone(st) {
  if (st === 'published') return 'teal';
  if (st === 'failed') return 'danger';
  if (st === 'deferred' || st === 'processing') return 'blue';
  return 'out';
}

function ClipPicker({ candidates, selected, onToggle, onSelectTop }) {
  const key = (c) => `${c.job_id}:${c.clip_index}`;
  const sel = selected;
  return (
    <div className="auto-post-picker">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Btn variant="secondary" size="sm" onClick={() => onSelectTop(22)}>Select top 22 by score</Btn>
        <Btn variant="ghost" size="sm" onClick={() => onToggle([])}>Clear</Btn>
        <span className="cm-small">{sel.length} selected</span>
      </div>
      <div className="auto-post-grid">
        {candidates.map((c) => {
          const k = key(c);
          const on = sel.some((s) => s.job_id === c.job_id && s.clip_index === c.clip_index);
          return (
            <button key={k} type="button" className={'ap-card' + (on ? ' on' : '')}
              onClick={() => {
                if (on) onToggle(sel.filter((s) => !(s.job_id === c.job_id && s.clip_index === c.clip_index)));
                else onToggle([...sel, c]);
              }}>
              <div className="ap-score">{c.viral_score || '—'}</div>
              <div className="ap-title">{c.title}</div>
              <div className="ap-meta">{c.source?.slice(0, 40)} · {c.duration}s</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function CampaignRow({ c, onOpen, onPause, onResume }) {
  const counts = c.counts || {};
  return (
    <div className="ap-campaign-row" onClick={() => onOpen(c.id)} role="button" tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onOpen(c.id); }}>
      <div>
        <div className="ap-c-name">{c.name || 'Campaign'}</div>
        <div className="cm-small">{c.item_count} clips · {c.policy?.posts_per_day || 1}/day from {c.policy?.start_date}</div>
      </div>
      <div className="ap-c-stats">
        <span>{counts.published || 0} live</span>
        <span>{counts.pending || 0} queued</span>
        <span>{counts.failed || 0} failed</span>
      </div>
      <div className="ap-c-actions">
        {c.status === 'active' ? (
          <Btn variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onPause(c.id); }}>Pause</Btn>
        ) : c.status === 'paused' ? (
          <Btn variant="secondary" size="sm" onClick={(e) => { e.stopPropagation(); onResume(c.id); }}>Resume</Btn>
        ) : (
          <span className="cm-small">{c.status}</span>
        )}
      </div>
    </div>
  );
}

function CampaignDetail({ campaign, onBack, onPause, onResume, onRetry, pushToast }) {
  const items = campaign.items || [];
  return (
    <div className="fade-in">
      <div style={{ marginBottom: 16 }}>
        <Btn variant="secondary" size="sm" icon="arrow-left" onClick={onBack}>All campaigns</Btn>
      </div>
      <Panel title={campaign.name} sub={`Status: ${campaign.status} · ${items.length} clips`}
        icon="calendar-clock" style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          {campaign.status === 'active' ? (
            <Btn variant="ghost" size="sm" onClick={() => onPause(campaign.id)}>Pause campaign</Btn>
          ) : (
            <Btn variant="secondary" size="sm" onClick={() => onResume(campaign.id)}>Resume campaign</Btn>
          )}
        </div>
        <div className="ap-items">
          {items.map((it) => (
            <div key={it.id} className="ap-item">
              <div className="ap-item-main">
                <Badge tone={statusTone(it.status)}>{it.status}</Badge>
                <span className="ap-item-title">{it.title || `Clip ${it.clip_index + 1}`}</span>
                <span className="cm-small">Day {it.scheduled_date}</span>
              </div>
              <div className="cm-small" style={{ color: 'var(--fg-3)' }}>
                {it.job_id.slice(0, 8)}… #{it.clip_index + 1}
                {it.viral_score ? ` · score ${it.viral_score}` : ''}
              </div>
              {it.last_error && (
                <div className="cm-small" style={{ color: 'var(--danger)', marginTop: 4 }} title={it.last_error}>
                  {it.last_error.slice(0, 80)}
                </div>
              )}
              {it.status === 'failed' && (
                <Btn variant="ghost" size="sm" style={{ marginTop: 6 }}
                  onClick={async () => {
                    try {
                      await onRetry(campaign.id, it.id);
                      pushToast?.('success', 'Queued for retry');
                    } catch (e) {
                      pushToast?.('error', e?.message || 'Retry failed');
                    }
                  }}>Retry</Btn>
              )}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

export function AutoPostView({ preselections, pushToast }) {
  const [view, setView] = useState('list'); // list | create | detail
  const [campaigns, setCampaigns] = useState([]);
  const [detail, setDetail] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [selected, setSelected] = useState([]);
  const [name, setName] = useState('');
  const [plats, setPlats] = useState({ tiktok: true, ig: true, yt: false });
  const [startDate, setStartDate] = useState(() => localDatePlus(1));
  const [postsPerDay, setPostsPerDay] = useState(1);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { campaigns: cs } = await fetchAutoPostCampaigns();
      setCampaigns(cs || []);
    } catch {
      pushToast?.('error', 'Failed to load campaigns');
    } finally {
      setLoading(false);
    }
  }, [pushToast]);

  useEffect(() => { load(); }, [load]);

  const openCreate = async () => {
    setView('create');
    setSelected([]);
    try {
      const { candidates: cs } = await fetchAutoPostCandidates();
      setCandidates(cs || []);
    } catch {
      pushToast?.('error', 'Failed to load clips');
    }
  };

  const selectTop = (n) => {
    setSelected(candidates.slice(0, n));
  };

  const composeSnapshot = useMemo(() => ({
    toggles: seedToggles(preselections),
    hook_params: seedHookParams({}, preselections),
    subtitle_params: seedSubtitleParams(preselections),
    logo_params: seedLogoParams(preselections),
    grade_params: { preset: preselections?.grade?.preset || 'none' },
  }), [preselections]);

  const activeLayers = useMemo(() => {
    const t = composeSnapshot.toggles;
    return ['grade', 'subtitles', 'smartcut', 'hook', 'logo'].filter((k) => t[k]);
  }, [composeSnapshot]);

  const submitCampaign = async () => {
    if (!selected.length) {
      pushToast?.('warn', 'Select at least one clip');
      return;
    }
    setCreating(true);
    try {
      const platforms = Object.keys(plats).filter((k) => plats[k]).map((k) => PLAT_MAP[k]);
      const campaign = await createAutoPostCampaign({
        name: name.trim() || `Auto-post ${selected.length} clips`,
        items: selected.map((c) => ({
          job_id: c.job_id,
          clip_index: c.clip_index,
          viral_score: c.viral_score,
          title: c.title,
        })),
        platforms,
        posts_per_day: postsPerDay,
        start_date: startDate,
        compose_snapshot: composeSnapshot,
        publish_defaults: {
          auto_caption: true,
          use_cover_thumbnail: true,
          instagram_share_to_feed: true,
        },
      });
      pushToast?.('success', `Campaign created — ${selected.length} clips queued`);
      setView('list');
      setName('');
      await load();
      setDetail(campaign);
      setView('detail');
    } catch (e) {
      pushToast?.('error', e?.message || 'Create failed');
    } finally {
      setCreating(false);
    }
  };

  const openDetail = async (id) => {
    try {
      const c = await fetchAutoPostCampaign(id);
      setDetail(c);
      setView('detail');
    } catch {
      pushToast?.('error', 'Failed to load campaign');
    }
  };

  if (view === 'detail' && detail) {
    return (
      <div className="container narrow fade-in">
        <CampaignDetail campaign={detail} pushToast={pushToast}
          onBack={() => { setView('list'); setDetail(null); load(); }}
          onPause={async (id) => { await pauseAutoPostCampaign(id); openDetail(id); }}
          onResume={async (id) => { await resumeAutoPostCampaign(id); openDetail(id); }}
          onRetry={retryAutoPostItem} />
      </div>
    );
  }

  if (view === 'create') {
    return (
      <div className="container fade-in">
        <Hero eyebrow="Auto Post" line1="Schedule clips." grad="Set & forget."
          sub="Pick clips from any completed job. The server posts one per day with your preset layers." />
        <Panel title="Select clips" sub={`${candidates.length} available across all jobs`} icon="layers" style={{ marginBottom: 18 }}>
          <ClipPicker candidates={candidates} selected={selected} onToggle={setSelected} onSelectTop={selectTop} />
        </Panel>
        <Panel title="Schedule" icon="calendar-clock" style={{ marginBottom: 18 }}>
          <div className="field">
            <span className="field-label">Campaign name</span>
            <input className="key-input" value={name} onChange={(e) => setName(e.target.value)}
              placeholder={`Auto-post ${selected.length || ''} clips`} />
          </div>
          <div className="field">
            <span className="field-label">Platforms</span>
            <div className="plats">
              {PLATFORMS.map((p) => (
                <PlatPill key={p.id} {...p} on={plats[p.id]}
                  onClick={() => setPlats((x) => ({ ...x, [p.id]: !x[p.id] }))} />
              ))}
            </div>
          </div>
          <div className="field">
            <span className="field-label">Start date</span>
            <input type="date" className="key-input" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </div>
          <div className="opt" style={{ borderBottom: 0 }}>
            <div className="otxt"><div className="ot">Posts per day</div><div className="od">1 recommended to stay under platform daily caps</div></div>
            <div className="r">
              <select className="key-input" value={postsPerDay} onChange={(e) => setPostsPerDay(Number(e.target.value))}>
                {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>
          {activeLayers.length > 0 && (
            <div className="cm-small" style={{ marginTop: 12, color: 'var(--brand-teal)' }}>
              Preset layers burned before each post: {activeLayers.join(' → ')}
            </div>
          )}
        </Panel>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <Btn variant="ghost" onClick={() => setView('list')}>Cancel</Btn>
          <Btn variant="grad" icon="calendar-clock" disabled={creating || !selected.length} onClick={submitCampaign}>
            {creating ? 'Creating…' : `Start campaign (${selected.length})`}
          </Btn>
        </div>
      </div>
    );
  }

  return (
    <div className="container narrow fade-in">
      <Hero eyebrow="Auto Post" line1="Hands-off publishing." grad="Queue & schedule."
        sub="Background worker posts your curated clips via Zernio — retries on network blips and rate limits." />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Btn variant="grad" icon="plus" onClick={openCreate}>New campaign</Btn>
      </div>
      <Panel title="Campaigns" icon="rss" sub="Worker checks every 15 minutes">
        {loading ? <div className="cm-small">Loading…</div> : campaigns.length === 0 ? (
          <div className="empty" style={{ padding: '24px 12px' }}>
            <div className="ei"><Icon n="calendar-clock" /></div>
            <h3>No campaigns yet</h3>
            <p>Select clips from completed jobs and schedule them to post automatically.</p>
          </div>
        ) : (
          <div className="ap-campaign-list">
            {campaigns.map((c) => (
              <CampaignRow key={c.id} c={c} onOpen={openDetail}
                onPause={async (id) => { await pauseAutoPostCampaign(id); load(); }}
                onResume={async (id) => { await resumeAutoPostCampaign(id); load(); }} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
