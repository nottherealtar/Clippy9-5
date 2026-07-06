import { seedToggles, seedHookParams, seedSubtitleParams, seedLogoParams } from './seedClipParams.js';
import { primaryPublishPlatform } from './clipCaption.js';
import { localDatePlus } from './scheduleDates.js';

const PLAT = {
  tiktok: { platform: 'tiktok', acct: 'tiktok' },
  ig: { platform: 'instagram', acct: 'instagram' },
  yt: { platform: 'youtube', acct: 'youtube' },
};

/** Merge preset toggles with per-clip overrides (preset is the base). */
export function resolveComposeParams(clip, clipState, preselections) {
  const cs = clipState || {};
  const toggles = { ...seedToggles(preselections), ...(cs.toggles || {}) };
  const hookParams = { ...seedHookParams(clip, preselections), ...(cs.hookParams || {}) };
  const subtitleParams = { ...seedSubtitleParams(preselections), ...(cs.subtitleParams || {}) };
  const logoParams = { ...seedLogoParams(preselections), ...(cs.logoParams || {}) };
  const gradeParams = {
    preset: preselections?.grade?.preset || 'none',
    ...(cs.gradeParams || {}),
  };
  return { toggles, hookParams, subtitleParams, logoParams, gradeParams };
}

export function activeComposeLayers(toggles) {
  const labels = [];
  if (toggles.grade) labels.push('Grade');
  if (toggles.subtitles) labels.push('Subtitles');
  if (toggles.smartcut) labels.push('Smart Cut');
  if (toggles.hook) labels.push('Hook');
  if (toggles.logo) labels.push('Logo');
  return labels;
}

export function hashtagsToYoutubeTags(hashtags) {
  return (hashtags || [])
    .map((t) => String(t || '').trim().replace(/^#+/, ''))
    .filter(Boolean)
    .slice(0, 30);
}

export function buildPlatformTargets(plats, accounts) {
  return Object.keys(plats)
    .filter((k) => plats[k] && accounts[PLAT[k].acct])
    .map((k) => ({ platform: PLAT[k].platform, accountId: accounts[PLAT[k].acct] }));
}

/**
 * Build the POST /api/publish body for one clip.
 * @param {object} opts
 */
export function buildPublishBody({
  clip,
  idx,
  batchPos = 0,
  clipState,
  preselections,
  plats,
  accounts,
  zernio,
  schedule,
  captionText,
  perPlatformCaptions,
  youtubeTags,
  publishDefaults = {},
}) {
  const { toggles, hookParams, subtitleParams, logoParams, gradeParams } =
    resolveComposeParams(clip, clipState, preselections);
  const anyCompose = Object.values(toggles).some(Boolean);
  const targets = buildPlatformTargets(plats, accounts);
  const title = (clip.video_title_for_youtube_short || `Clip ${idx + 1}`).slice(0, 100);
  const cap = (captionText || title).slice(0, 2200);

  const perPlatformContent = {};
  if (perPlatformCaptions?.tiktok) perPlatformContent.tiktok = perPlatformCaptions.tiktok.slice(0, 2200);
  if (perPlatformCaptions?.instagram) perPlatformContent.instagram = perPlatformCaptions.instagram.slice(0, 2200);
  if (perPlatformCaptions?.youtube) perPlatformContent.youtube = perPlatformCaptions.youtube.slice(0, 2200);
  if (perPlatformCaptions?.youtube_title) {
    perPlatformContent.youtube_title = perPlatformCaptions.youtube_title.slice(0, 100);
  }

  const firstComment = (publishDefaults.first_comment || '').trim();
  const useCover = publishDefaults.use_cover_thumbnail !== false;
  const shareToFeed = publishDefaults.instagram_share_to_feed !== false;

  return {
    title,
    caption: cap,
    platforms: targets,
    schedule_mode: schedule ? 'auto' : 'now',
    ...(schedule ? { start_date: localDatePlus(batchPos) } : {}),
    timezone: zernio?.timezone || 'Europe/Rome',
    first_comment: firstComment || undefined,
    use_cover_thumbnail: useCover,
    instagram_share_to_feed: shareToFeed,
    ...(youtubeTags?.length ? { youtube_tags: youtubeTags } : {}),
    ...(Object.keys(perPlatformContent).length ? { per_platform_content: perPlatformContent } : {}),
    tiktok_settings: plats.tiktok && accounts.tiktok ? {
      privacy_level: 'PUBLIC_TO_EVERYONE',
      allow_comment: true,
      allow_duet: true,
      allow_stitch: true,
      content_preview_confirmed: true,
      express_consent_given: true,
    } : undefined,
    ...(anyCompose ? {
      compose_first: true,
      toggles,
      hook_params: toggles.hook ? hookParams : {},
      subtitle_params: toggles.subtitles ? subtitleParams : {},
      logo_params: toggles.logo ? logoParams : {},
      grade_params: toggles.grade ? gradeParams : {},
      drop_ranges: toggles.smartcut ? (clipState?.dropRanges || []) : [],
    } : {}),
  };
}

export function captionAIPlatform(plats) {
  const count = ['tiktok', 'ig', 'yt'].filter((k) => plats[k]).length;
  return count > 1 ? 'all' : primaryPublishPlatform(plats);
}
