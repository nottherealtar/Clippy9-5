// ClippyMe redesign — PublishModal: real concurrent publish to Zernio.

// Every selected clip is published in parallel (Promise.allSettled) — the fix

// for the old sequential stall — each row showing live queued→uploading→

// live/error status. Per-clip compose_first honours the clip's toggles.

import { useState, useEffect, useRef, useMemo } from 'react';

import { Icon, Social, Btn, Switch, PlatPill, PLATFORMS } from './primitives';

import { clipVideoSrc } from './realApi';

import { publishClip, getZernio, generateCaption } from './realApi';

import { defaultClipCaption, captionFromAIResult, captionsFromAIAll } from '../lib/clipCaption';

import {

  buildPublishBody, resolveComposeParams, activeComposeLayers, captionAIPlatform,

} from '../lib/buildPublishBody';

import { useModalA11y } from './useModalA11y';



const PLAT = {

  tiktok: { platform: 'tiktok', acct: 'tiktok', icon: 'tiktok', label: 'TikTok' },

  ig: { platform: 'instagram', acct: 'instagram', icon: 'instagram', label: 'Reels' },

  yt: { platform: 'youtube', acct: 'youtube', icon: 'youtube', label: 'Shorts' },

};



const DEFAULT_PUBLISH_DEFAULTS = {

  first_comment: '',

  use_cover_thumbnail: true,

  auto_caption: true,

  instagram_share_to_feed: true,

};



function PubRow({ clip, idx, st, plats }) {

  const status = typeof st === 'object' && st ? st.state : st;

  const errMsg = typeof st === 'object' && st ? st.error : null;

  const tasks = Object.keys(plats).filter((k) => plats[k]);

  const done = status === 'done';

  const error = status === 'error';

  return (

    <div className={'pubrow' + (done ? ' done' : '')}>

      <div className="pthumb" style={{ background: '#000', overflow: 'hidden' }}>

        <video src={clipVideoSrc(clip)} muted playsInline preload="metadata"

          style={{ width: '100%', height: '100%', objectFit: 'cover' }} />

      </div>

      <div className="pinfo">

        <div className="pttl">{clip.video_title_for_youtube_short || `Clip ${idx + 1}`}</div>

        <div className="pplats">

          {tasks.map((p) => (

            <div className="pp" key={p}>

              <Social n={PLAT[p].icon} color={done ? '02C5BF' : '7E7E8F'} size={13} />

              <div className="ptrack"><i className={p} style={{ width: done ? '100%' : status === 'uploading' ? '70%' : '0%', transition: 'width .4s' }}></i></div>

            </div>

          ))}

          <span className={'pstat' + (done ? ' done' : status === 'uploading' ? '' : ' wait')}

            style={error ? { color: 'var(--danger)' } : undefined}

            title={error && errMsg ? errMsg : undefined}>

            {error ? (errMsg ? `failed: ${errMsg.slice(0, 60)}` : 'failed') : done ? 'live' : status === 'uploading' ? 'uploading' : 'queued'}

          </span>

        </div>

      </div>

      <div className="pcheck"><Icon n={done ? 'check' : error ? 'x' : 'loader'} /></div>

    </div>

  );

}



export function PublishModal({ clips, jobId, clipStates = {}, preselections, onClose, onPublished, pushToast }) {

  const all = clips.length > 1;

  const [zernio, setZernio] = useState(null);

  const [plats, setPlats] = useState({ tiktok: true, ig: true, yt: false });

  const [schedule, setSchedule] = useState(true);

  const [caption, setCaption] = useState(() => defaultClipCaption(clips[0]));

  const [clipCaptions, setClipCaptions] = useState({});

  const [clipTags, setClipTags] = useState({});

  const [firstComment, setFirstComment] = useState('');

  const [useCoverThumb, setUseCoverThumb] = useState(true);

  const [autoCaption, setAutoCaption] = useState(true);

  const [shareToFeed, setShareToFeed] = useState(true);

  const [generating, setGenerating] = useState(false);

  const [stage, setStage] = useState('setup');

  const [progress, setProgress] = useState({});



  useEffect(() => {

    getZernio().then((cfg) => {

      setZernio(cfg || { configured: false });

      const pd = { ...DEFAULT_PUBLISH_DEFAULTS, ...(cfg?.publish_defaults || {}) };

      setFirstComment(pd.first_comment || '');

      setUseCoverThumb(pd.use_cover_thumbnail !== false);

      setAutoCaption(pd.auto_caption !== false);

      setShareToFeed(pd.instagram_share_to_feed !== false);

    }).catch(() => setZernio({ configured: false }));

  }, []);



  const panelRef = useModalA11y(onClose);

  const mountedRef = useRef(true);

  useEffect(() => () => { mountedRef.current = false; }, []);



  const accounts = zernio?.accounts || {};

  const toggle = (k) => setPlats((p) => ({ ...p, [k]: !p[k] }));

  const targets = Object.keys(plats)

    .filter((k) => plats[k] && accounts[PLAT[k].acct])

    .map((k) => ({ platform: PLAT[k].platform, accountId: accounts[PLAT[k].acct] }));

  const ready = zernio?.configured && targets.length > 0;



  const composeLayers = useMemo(() => {

    const sample = clips[0];

    if (!sample) return [];

    return activeComposeLayers(resolveComposeParams(sample, clipStates[sample._idx], preselections).toggles);

  }, [clips, clipStates, preselections]);



  const resolveCaption = (clip, idx) => {

    const generated = clipCaptions[idx];

    if (generated) return generated;

    if (!all && caption.trim()) return caption.trim();

    const plat = captionAIPlatform(plats);

    const perClip = defaultClipCaption(clip, plat === 'all' ? 'tiktok' : plat);

    if (perClip) return perClip;

    return caption.trim();

  };



  const resolvePerPlatform = (clip, idx) => {

    const stored = clipCaptions[`${idx}_all`];

    if (stored) return stored;

    const text = resolveCaption(clip, idx);

    const plat = captionAIPlatform(plats);

    if (plat === 'all') return null;

    return { [plat === 'instagram' ? 'instagram' : plat]: text };

  };



  const runGenerateCaptions = async () => {

    setGenerating(true);

    const plat = captionAIPlatform(plats);

    try {

      const capUpdates = {};

      const tagUpdates = {};

      const allUpdates = {};

      await Promise.all(clips.map(async (clip) => {

        const idx = clip._idx;

        const result = await generateCaption(jobId, idx, { platform: plat });

        if (result.error) pushToast?.('warn', result.error);

        if (plat === 'all') {

          const { captions, youtubeTags } = captionsFromAIAll(result);

          allUpdates[idx] = captions;

          capUpdates[idx] = captions.tiktok || captions.instagram || captions.youtube || '';

          if (youtubeTags.length) tagUpdates[idx] = youtubeTags;

        } else {

          const text = captionFromAIResult(result, plat);

          if (text) capUpdates[idx] = text;

          if (result.hashtags?.length) tagUpdates[idx] = result.hashtags.map((t) => t.replace(/^#+/, ''));

        }

      }));

      setClipCaptions((p) => ({ ...p, ...capUpdates, ...Object.fromEntries(

        Object.entries(allUpdates).map(([k, v]) => [`${k}_all`, v]),

      ) }));

      setClipTags((p) => ({ ...p, ...tagUpdates }));

      if (clips.length === 1) {

        const only = capUpdates[clips[0]._idx];

        if (only) setCaption(only);

      }

      pushToast?.('ok', all ? `Generated captions for ${clips.length} clips` : 'Caption generated');

    } catch (e) {

      pushToast?.('error', e?.message || 'Caption generation failed');

    } finally {

      setGenerating(false);

    }

  };



  const ensureAutoCaptions = async () => {
    if (!autoCaption) return null;
    const plat = captionAIPlatform(plats);
    const capUpdates = {};
    const tagUpdates = {};
    const allUpdates = {};
    const pending = clips.filter((clip) => {
      const idx = clip._idx;
      if (clipCaptions[idx] || clipCaptions[`${idx}_all`]) return false;
      const fallback = defaultClipCaption(clip, plat === 'all' ? 'tiktok' : plat);
      return !fallback?.trim();
    });
    if (!pending.length) return null;
    await Promise.all(pending.map(async (clip) => {
      const idx = clip._idx;
      const result = await generateCaption(jobId, idx, { platform: plat });
      if (plat === 'all') {
        const { captions, youtubeTags } = captionsFromAIAll(result);
        allUpdates[idx] = captions;
        capUpdates[idx] = captions.tiktok || captions.instagram || captions.youtube || '';
        if (youtubeTags.length) tagUpdates[idx] = youtubeTags;
      } else {
        const text = captionFromAIResult(result, plat);
        if (text) capUpdates[idx] = text;
        if (result.hashtags?.length) tagUpdates[idx] = result.hashtags.map((t) => t.replace(/^#+/, ''));
      }
    }));
    return {
      capUpdates,
      tagUpdates,
      allUpdates,
      merged: {
        ...capUpdates,
        ...Object.fromEntries(Object.entries(allUpdates).map(([k, v]) => [`${k}_all`, v])),
        ...Object.fromEntries(Object.entries(tagUpdates).map(([k, v]) => [`${k}_tags`, v])),
      },
    };
  };



  const buildBody = (clip, idx, batchPos = 0, overrides = {}) => {
    const perPlatform = overrides[`${idx}_all`] || clipCaptions[`${idx}_all`] || resolvePerPlatform(clip, idx);
    const cap = overrides[idx] || clipCaptions[idx] || resolveCaption(clip, idx) || '';
    const tags = overrides[`${idx}_tags`] || clipTags[idx] || [];

    return buildPublishBody({

      clip,

      idx,

      batchPos,

      clipState: clipStates[idx],

      preselections,

      plats,

      accounts,

      zernio,

      schedule,

      captionText: cap,

      perPlatformCaptions: perPlatform,

      youtubeTags: tags,

      publishDefaults: {

        first_comment: firstComment,

        use_cover_thumbnail: useCoverThumb,

        instagram_share_to_feed: shareToFeed,

      },

    });

  };



  const run = async () => {

    setStage('uploading');

    const init = {};

    clips.forEach((c) => { init[c._idx] = { state: 'uploading' }; });

    setProgress(init);



    let overrides = {};
    try {
      const auto = await ensureAutoCaptions();
      if (auto) {
        setClipCaptions((p) => ({ ...p, ...auto.capUpdates, ...Object.fromEntries(
          Object.entries(auto.allUpdates).map(([k, v]) => [`${k}_all`, v]),
        ) }));
        setClipTags((p) => ({ ...p, ...auto.tagUpdates }));
        overrides = auto.merged;
      }
    } catch (e) {
      pushToast?.('warn', e?.message || 'Auto-caption skipped');
    }

    const results = await Promise.allSettled(clips.map(async (clip, batchPos) => {
      const idx = clip._idx;
      try {
        await publishClip(jobId, idx, buildBody(clip, idx, batchPos, overrides));

        setProgress((p) => ({ ...p, [idx]: { state: 'done' } }));

        onPublished?.(idx);

        return true;

      } catch (e) {

        setProgress((p) => ({ ...p, [idx]: { state: 'error', error: e?.message || 'Publish failed' } }));

        return false;

      }

    }));

    const ok = results.filter((r) => r.status === 'fulfilled' && r.value).length;

    const fail = clips.length - ok;

    setTimeout(() => {

      if (!mountedRef.current) return;

      setStage('done');

      pushToast?.(fail === 0 ? 'success' : 'warn', `Published ${ok}/${clips.length}${fail ? `, ${fail} failed` : ''}`);

    }, 500);

  };



  const title = stage === 'done' ? (schedule ? 'Scheduled' : 'Published')

    : all ? `Publish ${clips.length} clips` : `Publish · ${clips[0]?.video_title_for_youtube_short || ''}`;



  return (
    // Backdrop click is a mouse-only convenience; keyboard users close via Esc (useModalA11y).
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
    <div className="overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>

      <div className={'modal' + (all ? ' wide' : '')} ref={panelRef}

        role="dialog" aria-modal="true" aria-labelledby="publish-modal-title">

        <div className="modal-head">

          <div>

            <h3 id="publish-modal-title">{title}</h3>

            {stage === 'uploading' && <div className="mh-sub">uploading concurrently · daily-limit checks server-side</div>}

          </div>

          <button className="x" onClick={onClose} aria-label="Close"><Icon n="x" /></button>

        </div>



        {stage === 'setup' && (

          <>

            <div className="modal-body">

              {!zernio ? <div className="cm-small">Loading Zernio…</div> : !zernio.configured ? (

                <div className="empty" style={{ padding: '24px 12px' }}>

                  <div className="ei"><Icon n="rss" /></div>

                  <h3>Zernio not connected</h3>

                  <p>Add your Zernio API key + account IDs in Settings to publish.</p>

                </div>

              ) : (

                <>

                  <div className="field">

                    <span className="field-label">Platforms</span>

                    <div className="plats">

                      {PLATFORMS.map((p) => {

                        const has = !!accounts[PLAT[p.id].acct];

                        return <PlatPill key={p.id} {...p} on={plats[p.id] && has}

                          onClick={() => has ? toggle(p.id) : pushToast?.('warn', `No ${PLAT[p.id].label} account saved`)} />;

                      })}

                    </div>

                  </div>



                  {composeLayers.length > 0 && (

                    <div className="cm-small" style={{ marginBottom: 12, color: 'var(--brand-teal)' }}>

                      Preset layers will be burned before upload: {composeLayers.join(' → ')}

                    </div>

                  )}



                  <div className="field">

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>

                      <span className="field-label" style={{ margin: 0 }}>Caption</span>

                      <Btn variant="ghost" size="sm" icon="sparkles" disabled={generating}

                        onClick={runGenerateCaptions}>

                        {generating ? 'Generating…' : 'Generate with AI'}

                      </Btn>

                    </div>

                    <textarea className="ta" rows="4" value={caption} onChange={(e) => setCaption(e.target.value)}

                      placeholder={all ? 'Optional — auto-generated with hashtags if empty at publish' : 'Edit caption or leave blank for AI + hashtags'} />

                    {all && (

                      <div className="cm-small" style={{ marginTop: 6 }}>

                        Batch: each clip gets its own AI caption + hashtags when auto-caption is on.

                      </div>

                    )}

                  </div>



                  <div className="field">

                    <span className="field-label">First comment</span>

                    <textarea className="ta" rows="2" value={firstComment} onChange={(e) => setFirstComment(e.target.value)}

                      placeholder="Auto-posted as the first comment on TikTok, Reels, and Shorts (optional)" />

                  </div>



                  <div className="opt">

                    <div className="oico"><Icon n="image" /></div>

                    <div className="otxt"><div className="ot">Use auto cover thumbnail</div><div className="od">Uploads the pipeline cover frame to TikTok + Instagram</div></div>

                    <div className="r"><Switch on={useCoverThumb} onChange={setUseCoverThumb} /></div>

                  </div>

                  <div className="opt">

                    <div className="oico"><Icon n="sparkles" /></div>

                    <div className="otxt"><div className="ot">Auto caption + hashtags</div><div className="od">Generate with AI before publish when caption is empty</div></div>

                    <div className="r"><Switch on={autoCaption} onChange={setAutoCaption} /></div>

                  </div>

                  {plats.ig && (

                    <div className="opt">

                      <div className="oico"><Icon n="instagram" /></div>

                      <div className="otxt"><div className="ot">Share Reel to profile feed</div><div className="od">Instagram shareToFeed — off = Reels tab only</div></div>

                      <div className="r"><Switch on={shareToFeed} onChange={setShareToFeed} /></div>

                    </div>

                  )}

                  <div className="opt" style={{ borderBottom: 0 }}>

                    <div className="oico"><Icon n="calendar-clock" /></div>

                    <div className="otxt"><div className="ot">Schedule for prime time</div><div className="od">SmartScheduler picks the slot · off = publish now</div></div>

                    <div className="r"><Switch on={schedule} onChange={setSchedule} /></div>

                  </div>

                </>

              )}

            </div>

            <div className="modal-foot">

              <Btn variant="ghost" onClick={onClose}>Cancel</Btn>

              <div className="mf-right">

                <Btn variant="secondary" icon="send" disabled={!ready} onClick={() => { setSchedule(false); run(); }}>Publish now</Btn>

                <Btn variant="grad" icon="calendar-clock" disabled={!ready} onClick={run}>{schedule ? 'Schedule' : 'Queue'}</Btn>

              </div>

            </div>

          </>

        )}



        {stage === 'uploading' && (

          <div className="modal-body">

            <div className="pubgrid">

              {clips.map((c) => <PubRow key={c._idx} clip={c} idx={c._idx} st={progress[c._idx]} plats={plats} />)}

            </div>

          </div>

        )}



        {stage === 'done' && (

          <div className="modal-body" style={{ textAlign: 'center', padding: '36px 24px' }}>

            <div style={{ width: 60, height: 60, borderRadius: '50%', background: 'var(--success-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 18px' }}>

              <Icon n={schedule ? 'calendar-check' : 'party-popper'} style={{ width: 28, height: 28, color: 'var(--brand-teal)' }} />

            </div>

            <div style={{ fontWeight: 700, fontSize: 18 }}>{all ? `${clips.length} clips ` : 'Clip '}{schedule ? 'scheduled' : 'published'}</div>

            <p style={{ color: 'var(--fg-3)', fontSize: 13.5, marginTop: 8, lineHeight: 1.5 }}>

              {schedule ? 'Queued via Zernio for the next prime-time slot.' : 'Sent to Zernio for immediate publish.'}

            </p>

            <div style={{ marginTop: 22 }}><Btn variant="secondary" onClick={onClose}>Done</Btn></div>

          </div>

        )}

      </div>

    </div>

  );

}

