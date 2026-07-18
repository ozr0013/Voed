import { toBlob } from "html-to-image";

// Capture the live editor region (#editor-capture) as a PNG, downscaled to
// ~maxWidth px wide, so the planner/verifier receive a real image of the
// current screen. This is the evidence for gate 2 (live screen understanding).
export async function captureEditor(maxWidth = 1280): Promise<Blob> {
  const node = document.getElementById("editor-capture");
  if (!node) throw new Error("Editor region not found");

  const raw = await toBlob(node, { cacheBust: true, pixelRatio: 1, backgroundColor: "#0b0e14" });
  if (!raw) throw new Error("Screen capture failed");
  return downscale(raw, maxWidth);
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
