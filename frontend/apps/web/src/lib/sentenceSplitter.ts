/**
 * Sentence splitting utility for bilingual translation.
 *
 * Handles English, Chinese, and mixed-language content.
 * Splits text into sentences while preserving punctuation.
 */

// Minimum sentence length to avoid trivially short fragments (e.g. "Dr.", "U.S.")
const MIN_SENTENCE_LENGTH = 10

/**
 * Split text into sentences.
 *
 * Handles:
 * - English: split after . ! ? followed by whitespace
 * - Chinese: split after 。！？；
 * - Mixed: combined regex
 * - Merges very short fragments with the previous sentence
 */
export function splitIntoSentences(text: string): string[] {
  if (!text.trim()) return []

  // Split on sentence-ending punctuation:
  // - English: .!? followed by whitespace
  // - Chinese: 。！？； (no whitespace needed)
  const parts = text.split(/(?<=[.!?])\s+|(?<=[。！？；])/)

  const sentences: string[] = []
  for (const part of parts) {
    const trimmed = part.trim()
    if (!trimmed) continue

    if (sentences.length > 0 && trimmed.length < MIN_SENTENCE_LENGTH) {
      // Merge short fragment with previous sentence
      sentences[sentences.length - 1] += ' ' + trimmed
    } else {
      sentences.push(trimmed)
    }
  }

  return sentences
}
