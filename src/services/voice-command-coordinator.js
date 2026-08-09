class VoiceCommandCoordinator {
  constructor(options) {
    this.transcribe = options.transcribe;
    this.routeIntent = options.routeIntent;
    this.onRoute = options.onRoute;
    this.onClarify = options.onClarify;
    this.transcriptThreshold = options.transcriptThreshold ?? 0.52;
    this.intentThreshold = options.intentThreshold ?? 0.68;
    this.current = null;
    this.processing = false;
  }

  start(sessionId) {
    this.current = {
      id: String(sessionId),
      queue: [],
      routed: false,
      timedOut: false
    };
    return this.current;
  }

  cancel() {
    this.current = null;
  }

  enqueue(event) {
    const session = this.current;
    if (
      !session
      || session.routed
      || String(event?.session_id || '') !== session.id
      || event?.encoding !== 'pcm_s16le'
      || typeof event?.audio !== 'string'
    ) return false;
    if (session.queue.length >= 2) session.queue.shift();
    session.queue.push(event);
    void this.#drain(session);
    return true;
  }

  timeout(sessionId) {
    const session = this.current;
    if (!session || session.routed || String(sessionId || '') !== session.id) return false;
    session.timedOut = true;
    if (!this.processing && session.queue.length === 0) {
      this.#clarify(session, '', null, 'timeout');
    }
    return true;
  }

  #clarify(session, transcript, route, reason = '') {
    if (this.current !== session || session.routed) return;
    this.current = null;
    this.onClarify({ transcript, route, reason, sessionId: session.id });
  }

  async #drain(session) {
    if (this.processing) return;
    this.processing = true;
    try {
      while (this.current === session && !session.routed && session.queue.length) {
        const event = session.queue.shift();
        let transcript;
        try {
          transcript = await this.transcribe(event);
        } catch {
          if (event.phase === 'follow-up') this.#clarify(session, '', null, 'low-confidence');
          continue;
        }
        if (this.current !== session || session.routed) break;
        const route = this.routeIntent(transcript.text);
        const transcriptConfidence = Number(transcript.confidence) || 0;
        if (
          transcriptConfidence >= this.transcriptThreshold
          && route.intent
          && !route.ambiguous
          && route.confidence >= this.intentThreshold
        ) {
          session.routed = true;
          this.current = null;
          this.onRoute({
            intent: route.intent,
            text: transcript.text,
            confidence: Math.min(transcriptConfidence, route.confidence),
            sessionId: session.id
          });
          break;
        }
        const containedCommand = Boolean(route.commandText && route.commandText.length >= 2);
        if (event.phase === 'follow-up' || containedCommand) {
          this.#clarify(
            session,
            transcript.text,
            route,
            transcriptConfidence < this.transcriptThreshold ? 'low-confidence' : ''
          );
        }
      }
    } finally {
      this.processing = false;
      const pending = this.current;
      if (pending?.queue.length) {
        void this.#drain(pending);
      } else if (pending === session && session.timedOut && !session.routed) {
        this.#clarify(session, '', null, 'timeout');
      }
    }
  }
}

module.exports = { VoiceCommandCoordinator };
