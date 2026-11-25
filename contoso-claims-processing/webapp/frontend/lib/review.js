// Review conversation controller: one backend review session (one Foundry conversation) per review.
// The API and timer are injected so the controller can be tested without a browser or network.

export class ApiError extends Error {
  constructor(status, message, error) {
    super(message);
    this.status = status;
    this.error = error ?? null;
  }
}

const CONNECTION_ERROR = {
  code: "connection",
  message: "The Claims Review service could not be reached. Check that it is running, then try again.",
  retry: "retry",
};

export function httpApi(fetchImpl = globalThis.fetch.bind(globalThis)) {
  async function call(method, url, body) {
    let response;
    try {
      response = await fetchImpl(url, {
        method,
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
        cache: "no-store",
      });
    } catch {
      throw new ApiError(0, CONNECTION_ERROR.message, CONNECTION_ERROR);
    }
    if (response.status === 204) return null;
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (!response.ok) {
      const detail = typeof payload?.detail === "string" ? payload.detail : null;
      throw new ApiError(response.status, payload?.error?.message ?? detail ?? `Request failed (${response.status}).`, payload?.error);
    }
    return payload;
  }
  return {
    about: () => call("GET", "/api/about"),
    claim: (claimId) => call("GET", `/api/claims/${encodeURIComponent(claimId)}`),
    createReview: (claimId) => call("POST", "/api/reviews", { claimId }),
    send: (sessionId, text) => call("POST", `/api/reviews/${encodeURIComponent(sessionId)}/messages`, { text }),
    turn: (sessionId, turnId) => call("GET", `/api/reviews/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(turnId)}`),
    endReview: (sessionId) => call("DELETE", `/api/reviews/${encodeURIComponent(sessionId)}`),
  };
}

const ENDED = {
  code: "session_ended",
  message: "This review is no longer available. Start a new review to continue.",
  retry: "new_review",
};

export class ReviewController {
  constructor({ api, claimId, onChange = () => {}, sleep, pollMs = 1000 }) {
    this.api = api;
    this.claimId = claimId;
    this.onChange = onChange;
    this.sleep = sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    this.pollMs = pollMs;
    this.sessionId = null;
    this.turns = [];
    this.busy = false;
    this.generation = 0; // increments on reset so stale polls are ignored
  }

  get firstTurnId() {
    return this.turns.find((t) => t.status === "completed")?.turnId ?? this.turns[0]?.turnId ?? null;
  }

  get started() {
    return this.turns.some((t) => t.status === "completed");
  }

  emit() {
    this.onChange(this);
  }

  async send(text) {
    const prompt = String(text ?? "").trim();
    if (!prompt || this.busy) return null;
    const generation = this.generation;
    this.busy = true;
    const placeholder = { turnId: `local-${this.turns.length + 1}`, prompt, status: "running", stage: "queued", elapsedSeconds: 0 };
    this.turns.push(placeholder);
    this.emit();
    try {
      if (!this.sessionId) this.sessionId = (await this.api.createReview(this.claimId)).sessionId;
      if (generation !== this.generation) return null;
      let turn = await this.api.send(this.sessionId, prompt);
      this.replace(placeholder.turnId, turn);
      while (turn.status === "running") {
        await this.sleep(this.pollMs);
        if (generation !== this.generation) return null;
        turn = await this.api.turn(this.sessionId, turn.turnId);
        if (generation !== this.generation) return null;
        this.replace(turn.turnId, turn);
      }
      return turn;
    } catch (err) {
      if (generation !== this.generation) return null;
      const error = err?.status === 404 && this.sessionId ? ENDED : err?.error ?? {
        code: "request",
        message: err?.message || "The request could not be completed.",
        retry: "retry",
      };
      const current = this.turns[this.turns.length - 1];
      this.replace(current.turnId, { ...current, status: "failed", error });
      return null;
    } finally {
      if (generation === this.generation) {
        this.busy = false;
        this.emit();
      }
    }
  }

  replace(turnId, turn) {
    const i = this.turns.findIndex((t) => t.turnId === turnId);
    if (i >= 0) this.turns[i] = turn;
    else this.turns.push(turn);
    this.emit();
  }

  // Re-sends the last failed prompt. A failed first message is retried in a clean review.
  async retry() {
    const last = this.turns[this.turns.length - 1];
    if (!last || last.status !== "failed" || this.busy) return null;
    if (!this.started) {
      await this.reset();
      return this.send(last.prompt);
    }
    this.turns.pop();
    return this.send(last.prompt);
  }

  // Ends this review and starts a clean one. Only the local review session is discarded.
  async reset() {
    this.generation += 1;
    const old = this.sessionId;
    this.sessionId = null;
    this.turns = [];
    this.busy = false;
    this.emit();
    if (old) {
      try {
        await this.api.endReview(old);
      } catch {
        // The server forgets idle reviews on its own; a failed clean-up must not block a new review.
      }
    }
  }
}
