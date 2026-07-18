// The plan->act->verify agent loop, driven from the browser so every planner /
// verifier call sees a REAL screenshot of the live editor. Each iteration:
//   capture screen -> POST /step (plan + act) -> re-render timeline ->
//   capture screen -> POST /verify -> speak progress -> repeat until done.
import { captureEditor } from "./screenshot";
import { speak } from "./voice";

export interface StepEvent {
  index: number;
  label: string;
  status: "running" | "done" | "failed";
  thought?: string;
  plan?: string[];
  expectedResult?: string;
  observed?: string;
  shotIn?: string;
  shotOut?: string;
}

export interface RunCallbacks {
  onStatus: (s: string) => void;
  onStep: (e: StepEvent) => void;
  onSeek?: (t: number) => void;
  refetchProject: () => Promise<void>;
  shouldCancel: () => boolean;
}

const MAX_STEPS = 12;

function labelFor(step: any): string {
  const a = step.action ?? {};
  if (step.summary) return step.summary;
  if (a.name === "cut_range") return `Cut ${a.start_s ?? 0}s–${a.end_s ?? "?"}s`;
  if (a.name === "trim") return `Trim to ${a.start_s ?? 0}s–${a.end_s ?? "?"}s`;
  if (a.name === "mute_range") return `Mute ${a.start_s ?? 0}s–${a.end_s ?? "?"}s`;
  return a.name ?? "step";
}

// Stream one plan+act step over SSE. `onEvent` fires for live reasoning events
// ({type:"step_start"} / {type:"thought"}); resolves with the final "done" payload.
async function streamStep(
  projectId: number,
  goal: string,
  shot: Blob,
  runId: number | null,
  onEvent: (ev: any) => void,
): Promise<any> {
  const form = new FormData();
  form.append("project_id", String(projectId));
  form.append("goal", goal);
  form.append("screenshot", shot, "editor.png");
  if (runId != null) form.append("run_id", String(runId));

  const r = await fetch("/api/agent/step", { method: "POST", credentials: "include", body: form });
  if (!r.ok || !r.body) {
    throw new Error((await r.json().catch(() => ({}))).detail ?? "Planner step failed");
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let done: any = null;

  for (;;) {
    const { value, done: readerDone } = await reader.read();
    if (readerDone) break;
    buf += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 2);
      if (!raw.startsWith("data:")) continue;
      const ev = JSON.parse(raw.slice(5).trim());
      if (ev.type === "done") done = ev;
      else if (ev.type === "error") throw new Error(ev.message ?? "Agent error");
      else onEvent(ev);
    }
  }
  if (!done) throw new Error("Agent stream ended without a result");
  return done;
}

async function postVerify(runId: number, stepId: number, shot: Blob): Promise<any> {
  const form = new FormData();
  form.append("run_id", String(runId));
  form.append("step_id", String(stepId));
  form.append("screenshot", shot, "editor.png");
  const r = await fetch("/api/agent/verify", { method: "POST", credentials: "include", body: form });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "Verify failed");
  return r.json();
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function runAgent(
  projectId: number,
  goal: string,
  cb: RunCallbacks,
): Promise<void> {
  // Sub-second acknowledgment before any inference starts.
  speak(`On it. ${goal}`);
  let runId: number | null = null;

  for (let i = 0; i < MAX_STEPS; i++) {
    if (cb.shouldCancel()) {
      cb.onStatus("cancelled");
      await speak("Okay, stopped.");
      return;
    }

    cb.onStatus("looking at the screen…");
    const shot = await captureEditor();
    let step: any;
    try {
      cb.onStatus("thinking…");
      step = await streamStep(projectId, goal, shot, runId, (ev) => {
        if (ev.type === "step_start") {
          cb.onStep({
            index: ev.step_index,
            label: "Thinking…",
            status: "running",
            shotIn: ev.screenshot_in_url,
          });
        } else if (ev.type === "thought") {
          // Live reasoning: merges into the step's thought as tokens arrive.
          cb.onStep({ index: ev.step_index, label: "Thinking…", status: "running", thought: ev.text });
        }
      });
    } catch (e) {
      cb.onStatus("error");
      await speak(String((e as Error).message ?? e));
      return;
    }
    runId = step.run_id;
    const idx = step.step_index ?? i;

    cb.onStep({
      index: idx,
      label: labelFor(step),
      status: "running",
      thought: step.thought,
      plan: step.plan,
      expectedResult: step.expected_result,
      shotIn: step.screenshot_in_url,
    });

    if (step.status === "complete") {
      cb.onStep({ index: idx, label: "Done", status: "done", observed: step.message });
      cb.onStatus("complete");
      await speak(step.message || "Done.");
      return;
    }
    if (step.status === "failed") {
      cb.onStep({ index: idx, label: labelFor(step), status: "failed", observed: step.message });
      cb.onStatus("failed");
      await speak(step.message || "I couldn't complete that.");
      return;
    }
    if (step.status === "ask") {
      cb.onStatus("waiting for you");
      await speak(step.question); // spoken yes/no handling arrives in a later milestone
      return;
    }
    if (step.status === "error") {
      cb.onStep({ index: idx, label: labelFor(step), status: "failed", observed: step.message });
      await speak(`That didn't work: ${step.message}`);
      return;
    }

    // status === "acted": a real edit happened. Re-render the timeline, then
    // re-capture and verify against the expected result.
    if (step.seek_to != null && cb.onSeek) cb.onSeek(step.seek_to);
    await cb.refetchProject();
    await sleep(400); // let the DOM repaint before the verification screenshot

    if (cb.shouldCancel()) {
      cb.onStatus("cancelled");
      await speak("Okay, stopped.");
      return;
    }

    cb.onStatus("checking the result…");
    const shot2 = await captureEditor();
    let ver: any;
    try {
      ver = await postVerify(runId!, step.step_id, shot2);
    } catch (e) {
      cb.onStatus("error");
      await speak(String((e as Error).message ?? e));
      return;
    }

    cb.onStep({
      index: idx,
      label: labelFor(step),
      status: ver.success ? "done" : "failed",
      thought: step.thought,
      plan: step.plan,
      expectedResult: step.expected_result,
      observed: ver.observed,
      shotIn: step.screenshot_in_url,
      shotOut: ver.screenshot_out_url,
    });

    await speak(step.summary || ver.observed || "Done.");
    // On verify failure we still loop: the planner reassesses the new screenshot.
    // (Explicit retry / re-plan / stuck detection arrive in a later milestone.)
  }

  cb.onStatus("stopped");
  await speak("I reached the step limit.");
}
