/**
 * Parse cloud ASR retry / fallback lines from streamed pipeline logs.
 * Returns a user-facing status object for the processing banner.
 *
 * @param {string[]} logs
 * @returns {null | { kind: 'retry' | 'fallback', provider: string, attempt?: number, max?: number, waitSec?: number, message: string }}
 */
export function parseTranscriptionRetryStatus(logs = []) {
  if (!logs?.length) return null;

  for (let i = logs.length - 1; i >= 0; i -= 1) {
    const line = String(logs[i] || '');

    const retry = line.match(
      /🔁\s*(Deepgram|ElevenLabs)\s+retry\s+(\d+)\/(\d+).*(?:in|waiting)\s+([\d.]+)s/i,
    );
    if (retry) {
      return {
        kind: 'retry',
        provider: retry[1],
        attempt: Number(retry[2]),
        max: Number(retry[3]),
        waitSec: Number(retry[4]),
        message: `${retry[1]} hit a network hiccup — retry ${retry[2]}/${retry[3]} in ${retry[4]}s. Please wait; the job is still running.`,
      };
    }

    if (/trying ElevenLabs Scribe as fallback/i.test(line)) {
      return {
        kind: 'fallback',
        provider: 'ElevenLabs',
        message: 'Deepgram failed — switching to ElevenLabs Scribe…',
      };
    }
    if (/trying Deepgram as fallback/i.test(line)) {
      return {
        kind: 'fallback',
        provider: 'Deepgram',
        message: 'ElevenLabs failed — switching to Deepgram…',
      };
    }
    if (/Cloud transcription unavailable — falling back to Faster-Whisper/i.test(line)) {
      return {
        kind: 'fallback',
        provider: 'Whisper',
        message: 'Cloud transcription unavailable — falling back to local Whisper (slower on CPU).',
      };
    }
  }

  return null;
}
