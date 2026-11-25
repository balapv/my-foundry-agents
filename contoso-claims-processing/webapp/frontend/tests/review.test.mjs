import { test } from "node:test";
import assert from "node:assert/strict";

import { ApiError, ReviewController, httpApi } from "../lib/review.js";

// A scripted fake of the Claims Review backend.
function fakeApi({ polls = 1, failSend, failTurn } = {}) {
  const calls = [];
  let sessions = 0;
  let turns = 0;
  const pending = new Map();
  return {
    calls,
    createReview: async (claimId) => {
      calls.push(["createReview", claimId]);
      sessions += 1;
      return { sessionId: `s${sessions}`, claimId };
    },
    send: async (sessionId, text) => {
      calls.push(["send", sessionId, text]);
      if (failSend) throw failSend;
      turns += 1;
      const turnId = `t${turns}`;
      pending.set(turnId, polls);
      return { turnId, prompt: text, status: "running", stage: "verifying", elapsedSeconds: 0 };
    },
    turn: async (sessionId, turnId) => {
      calls.push(["turn", sessionId, turnId]);
      if (failTurn) throw failTurn;
      const left = pending.get(turnId) - 1;
      pending.set(turnId, left);
      if (left > 0) return { turnId, status: "running", stage: "reviewing", elapsedSeconds: 1 };
      return { turnId, status: "completed", answer: `answer to ${turnId}`, elapsedSeconds: 2 };
    },
    endReview: async (sessionId) => {
      calls.push(["endReview", sessionId]);
      return null;
    },
  };
}

const noSleep = async () => {};

test("the first message creates one review session; follow-ups reuse it", async () => {
  const api = fakeApi({ polls: 2 });
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: noSleep });
  const first = await review.send("  Review this claim and tell me what I should do next.  ");
  assert.equal(first.status, "completed");
  await review.send("Show me why you flagged the headlamp.");
  assert.deepEqual(api.calls.filter((c) => c[0] === "createReview"), [["createReview", "CLM-10482"]]);
  assert.deepEqual(api.calls.filter((c) => c[0] === "send").map((c) => c[1]), ["s1", "s1"]);
  assert.equal(api.calls.filter((c) => c[0] === "send")[0][2], "Review this claim and tell me what I should do next.");
  assert.deepEqual(review.turns.map((t) => [t.turnId, t.status]), [["t1", "completed"], ["t2", "completed"]]);
  assert.equal(review.firstTurnId, "t1");
  assert.ok(review.started);
  assert.equal(review.busy, false);
});

test("empty messages and messages sent while busy are ignored", async () => {
  const api = fakeApi();
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: noSleep });
  assert.equal(await review.send("   "), null);
  const running = review.send("first");
  assert.equal(await review.send("second"), null);
  await running;
  assert.deepEqual(api.calls.filter((c) => c[0] === "send").map((c) => c[2]), ["first"]);
});

test("progress updates are published while the agent works", async () => {
  const stages = [];
  const api = fakeApi({ polls: 3 });
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: noSleep, onChange: (r) => stages.push(r.turns.at(-1)?.stage ?? r.turns.at(-1)?.status) });
  await review.send("Review this claim.");
  assert.deepEqual([...new Set(stages)], ["queued", "verifying", "reviewing", "completed"]);
  assert.equal(review.turns[0].status, "completed");
});

test("reset ends the review and the next message starts a clean one", async () => {
  const api = fakeApi();
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: noSleep });
  await review.send("first review");
  await review.reset();
  assert.deepEqual(review.turns, []);
  assert.equal(review.started, false);
  await review.send("second review");
  assert.deepEqual(api.calls.filter((c) => c[0] !== "turn"), [
    ["createReview", "CLM-10482"], ["send", "s1", "first review"], ["endReview", "s1"],
    ["createReview", "CLM-10482"], ["send", "s2", "second review"],
  ]);
});

test("a reset during a running turn discards that turn's late results", async () => {
  const api = fakeApi({ polls: 5 });
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: () => gate });
  const running = review.send("slow review");
  await new Promise((resolve) => setImmediate(resolve));
  await review.reset();
  release();
  assert.equal(await running, null);
  assert.deepEqual(review.turns, []);
  assert.equal(review.busy, false);
  assert.ok(!api.calls.some((c) => c[0] === "turn"));
});

test("a reset still succeeds when the server has already forgotten the review", async () => {
  const api = fakeApi();
  api.endReview = async () => { throw new ApiError(404, "gone"); };
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: noSleep });
  await review.send("first");
  await review.reset();
  assert.equal(review.sessionId, null);
});

test("server errors are shown with the server's friendly message", async () => {
  const error = { code: "evidence_validation", message: "The claim evidence package could not be verified.", reference: "CR-ABC123", retry: "none" };
  const api = fakeApi({ failSend: new ApiError(409, error.message, error) });
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: noSleep });
  assert.equal(await review.send("Review this claim."), null);
  assert.equal(review.turns[0].status, "failed");
  assert.deepEqual(review.turns[0].error, error);
  assert.equal(review.busy, false);
});

test("an expired review asks the adjuster to start a new review", async () => {
  const api = fakeApi({ failTurn: new ApiError(404, "Not Found") });
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: noSleep });
  await review.send("Review this claim.");
  assert.equal(review.turns[0].error.code, "session_ended");
  assert.equal(review.turns[0].error.retry, "new_review");
});

test("retrying a failed first message starts over in a clean review", async () => {
  const api = fakeApi({ failSend: new ApiError(502, "x", { code: "agent_error", message: "x", retry: "retry" }) });
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: noSleep });
  await review.send("Review this claim.");
  api.calls.length = 0;
  const realSend = fakeApi().send;
  api.send = async (sessionId, text) => { api.calls.push(["send", sessionId, text]); return realSend(sessionId, text); };
  await review.retry();
  assert.deepEqual(api.calls.filter((c) => c[0] !== "turn").map((c) => c[0]), ["endReview", "createReview", "send"]);
  assert.equal(review.turns.length, 1);
});

test("retrying a failed follow-up resends it in the same review", async () => {
  const api = fakeApi();
  const review = new ReviewController({ api, claimId: "CLM-10482", sleep: noSleep });
  await review.send("first");
  const send = api.send;
  api.send = async () => { throw new ApiError(502, "x", { code: "agent_error", message: "x", retry: "retry" }); };
  await review.send("follow-up");
  assert.equal(review.turns.at(-1).status, "failed");
  api.send = send;
  await review.retry();
  assert.deepEqual(review.turns.map((t) => t.status), ["completed", "completed"]);
  assert.deepEqual(api.calls.filter((c) => c[0] === "createReview").length, 1);
});

test("the HTTP client maps responses and connection failures", async () => {
  const responses = [
    { status: 201, ok: true, json: async () => ({ sessionId: "s1" }) },
    { status: 409, ok: false, json: async () => ({ error: { code: "busy", message: "Wait for the current answer." } }) },
    { status: 204, ok: true, json: async () => { throw new Error("no body"); } },
  ];
  const seen = [];
  const api = httpApi(async (url, init) => { seen.push([init.method, url]); return responses.shift(); });
  assert.deepEqual(await api.createReview("CLM-10482"), { sessionId: "s1" });
  await assert.rejects(api.send("s/1", "hi"), (e) => e.status === 409 && e.error.code === "busy" && e.message === "Wait for the current answer.");
  assert.equal(await api.endReview("s1"), null);
  assert.deepEqual(seen, [["POST", "/api/reviews"], ["POST", "/api/reviews/s%2F1/messages"], ["DELETE", "/api/reviews/s1"]]);
  const offline = httpApi(async () => { throw new TypeError("fetch failed"); });
  await assert.rejects(offline.about(), (e) => e.status === 0 && e.error.code === "connection" && !/fetch failed/.test(e.message));
});
