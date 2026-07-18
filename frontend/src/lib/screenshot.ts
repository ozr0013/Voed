import html2canvas from "html2canvas";

// Capture the live editor region (#editor-capture) as a PNG, downscaled to
// ~maxWidth px wide, so the planner/verifier receive a real image of the current
// screen. This is the evidence for gate 2 (live screen understanding).
//
// We use html2canvas (paints the DOM straight to a canvas) rather than
// html-to-image, because the latter round-trips through an SVG <img> whose
// onload never fires in some automated Chromium builds, hanging the capture.
export async function captureEditor(maxWidth = 1280): Promise<Blob> {
  const node = document.getElementById("editor-capture");
  if (!node) throw new Error("Editor region not found");

  // Snapshot each <video>'s current frame onto a <canvas> overlay (same-origin,
  // no taint). html2canvas renders <canvas> reliably but not <video>, so we skip
  // the video and let the overlay show the preview frame.
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
      canvas.setAttribute("data-capture-overlay", "1");
      node.appendChild(canvas);
      overlays.push(canvas);
    } catch {
      /* ignore a frame we couldn't draw */
    }
  }

  try {
    const rendered = await withTimeout(
      html2canvas(node, {
        backgroundColor: "#000000",
        scale: 1,
        logging: false,
        useCORS: true,
        ignoreElements: (el) => el.tagName === "VIDEO",
      }),
      20000,
      "html2canvas",
    );
    return await canvasToBlob(downscaleCanvas(rendered, maxWidth));
  } finally {
    overlays.forEach((c) => c.remove());
  }
}

function downscaleCanvas(src: HTMLCanvasElement, maxWidth: number): HTMLCanvasElement {
  if (src.width <= maxWidth) return src;
  const scale = maxWidth / src.width;
  const out = document.createElement("canvas");
  out.width = Math.round(src.width * scale);
  out.height = Math.round(src.height * scale);
  out.getContext("2d")!.drawImage(src, 0, 0, out.width, out.height);
  return out;
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("canvas.toBlob returned null"))),
      "image/png",
    ),
  );
}

function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  return Promise.race([
    p,
    new Promise<T>((_, reject) =>
      setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms),
    ),
  ]);
}
