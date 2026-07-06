/** Pick the best existing social caption from pipeline metadata. */
export function defaultClipCaption(clip, platform = 'tiktok') {
  if (!clip) return '';
  if (platform === 'instagram') {
    return clip.video_description_for_instagram || clip.video_description_for_tiktok || '';
  }
  if (platform === 'youtube') {
    return clip.video_description_for_tiktok || clip.video_title_for_youtube_short || '';
  }
  return clip.video_description_for_tiktok || clip.tiktok_caption || clip.video_title_for_youtube_short || '';
}

/** Primary enabled publish platform for caption style. */
export function primaryPublishPlatform(plats) {
  if (plats?.tiktok) return 'tiktok';
  if (plats?.ig) return 'instagram';
  if (plats?.yt) return 'youtube';
  return 'tiktok';
}

/** Caption text for a platform from a caption-ai response. */
export function captionFromAIResult(result, platform) {
  if (!result) return '';
  if (platform === 'instagram') return result.instagram || result.caption || '';
  if (platform === 'youtube') return result.youtube || result.caption || '';
  return result.tiktok || result.caption || '';
}

/** Map caption-ai "all" response to per-platform captions + YouTube tags. */
export function captionsFromAIAll(result) {
  if (!result) return { captions: {}, youtubeTags: [] };
  return {
    captions: {
      tiktok: result.tiktok || result.caption || '',
      instagram: result.instagram || result.caption || '',
      youtube: result.youtube || result.caption || '',
      youtube_title: result.youtube_title || '',
    },
    youtubeTags: (result.hashtags || [])
      .map((t) => String(t || '').trim().replace(/^#+/, ''))
      .filter(Boolean),
  };
}
