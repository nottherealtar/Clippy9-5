import test from 'node:test';
import assert from 'node:assert/strict';
import {
  resolveComposeParams,
  buildPublishBody,
  activeComposeLayers,
} from './buildPublishBody.js';

test('resolveComposeParams merges preset toggles with clip overrides', () => {
  const pre = { smartcut: true, subtitles: true, hook: false, logo: false, grade: false };
  const clip = { viral_hook_text: 'Hook!' };
  const cs = { toggles: { hook: true } };
  const { toggles, hookParams } = resolveComposeParams(clip, cs, pre);
  assert.equal(toggles.smartcut, true);
  assert.equal(toggles.subtitles, true);
  assert.equal(toggles.hook, true);
  assert.equal(hookParams.text, 'Hook!');
});

test('buildPublishBody includes compose_first when preset subtitles on', () => {
  const body = buildPublishBody({
    clip: { video_title_for_youtube_short: 'Title' },
    idx: 0,
    clipState: {},
    preselections: { subtitles: { preset: 'hormozi_bold', mode: 'karaoke' }, smartcut: false, hook: false, logo: false },
    plats: { tiktok: true, ig: false, yt: false },
    accounts: { tiktok: 'acc1' },
    zernio: { timezone: 'Europe/Rome' },
    schedule: false,
    captionText: 'Caption #viral',
    publishDefaults: { first_comment: 'First!', use_cover_thumbnail: true },
  });
  assert.equal(body.compose_first, true);
  assert.equal(body.toggles.subtitles, true);
  assert.equal(body.first_comment, 'First!');
  assert.equal(body.use_cover_thumbnail, true);
});

test('activeComposeLayers lists enabled layers in order', () => {
  const layers = activeComposeLayers({ grade: true, subtitles: true, smartcut: true, hook: false, logo: true });
  assert.deepEqual(layers, ['Grade', 'Subtitles', 'Smart Cut', 'Logo']);
});
