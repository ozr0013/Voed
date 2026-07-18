import { toBlob } from "html-to-image";

// Capture the live editor region (#editor-capture) as a PNG, downscaled to
// ~maxWidth px wide, so the planner/verifier receive a real image of the
// current screen. This is the evidence for gate 2 (live screen understanding).
export async function captureEditor(maxWidth = 1280): Promise<Blob> {
  const node = document.getElementById("editor-capture");
  if (!node) throw new Error("Editor region not found");

  // html-to-image hangs trying to serialize live <video> elements. Snapshot the
  // current frame onto a <canvas> overlay (same-origin, so no taint) and skip the
  // <video> during capture. The agent still sees the preview frame plus the full
  // timeline, clips, playhead, and panels.
  const overlays: HTMLCanvasElement[] = [];
  for (const v of Array.from(node.querySelectorAll("video"))) {
    try {
      const rect = v.getBoundingClientRect();
      const parentRect = node.getBoundingClientRect();
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(rect.width));
      canvas.height = Math.max(1, Math.round(rect.height));
      const ctx = canvas.getContext("2d");
      if (ctx && v.readyState >= 2) ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
      Object.assign(canvas.style, {
        position: "absolute",
        left: `${rect.left - parentRect.left}px`,
        top: `${rect.top - parentRect.top}px`,
        width: `${rect.width}px`,
        height: `${rect.height}px`,
        zIndex: "50",
      });
      node.appendChild(canvas);
      overlays.push(canvas);
    } catch {
      /* ignore a frame we couldn't draw */
    }
  }

  try {
    const rawP = toBlob(node, {
      cacheBust: false,
      pixelRatio: 1,
      backgroundColor: "#0b0e14",
      filter: (n) => !(n instanceof HTMLElement && n.tagName === "VIDEO"),
    });
    const raw = await withTimeout(rawP, 15000, "html-to-image toBlob");
    if (!raw) throw new Error("Screen capture failed");
    return await downscale(raw, maxWidth);
  } finally {
    overlays.forEach((c) => c.remove());
  }
}

function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  return Promise.race([
    p,
    new Promise<T>((_, reject) =>
      setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms),
    ),
  ]);
}

async function downscale(blob: Blob, maxWidth: number): Promise<Blob> {
  const bitmap = await createImageBitmap(blob);
  if (bitmap.width <= maxWidth) return blob;

  const scale = maxWidth / bitmap.width;
  const w = Math.round(bitmap.width * scale);
  const h = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("downscale failed"))),
      "image/png",
    ),
  );
}
