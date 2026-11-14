import { useEffect, useRef } from "react";

const STAR_COUNT_PER_MEGAPIXEL = 260;
// A few stars are bright enough to carry a soft halo. They give the sky some depth.
const BRIGHT_STAR_COUNT_PER_MEGAPIXEL = 7;
// Star colours run from blue-white through white to a warm white, like the real sky.
const TINTS = ["214, 226, 255", "226, 234, 255", "244, 246, 255", "255, 240, 222"];

/** Small deterministic random generator, so the sky looks the same on every visit. */
function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A static star field drawn once per resize. It sits behind the transparent map canvas. */
export function Stars() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;

    const draw = () => {
      const dpr = Math.min(window.devicePixelRatio, 2);
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);

      const random = mulberry32(20261112);
      const megapixels = (w * h) / 1_000_000;
      const count = Math.round(megapixels * STAR_COUNT_PER_MEGAPIXEL);
      for (let i = 0; i < count; i++) {
        const x = random() * w;
        const y = random() * h;
        const magnitude = random() ** 3; // most stars are faint, a few are bright
        const radius = 0.35 + magnitude * 0.9;
        const alpha = 0.18 + magnitude * 0.7;
        ctx.fillStyle = `rgba(226, 234, 255, ${alpha.toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fill();
      }

      const bright = Math.max(3, Math.round(megapixels * BRIGHT_STAR_COUNT_PER_MEGAPIXEL));
      for (let i = 0; i < bright; i++) {
        const x = random() * w;
        const y = random() * h;
        const tint = TINTS[Math.floor(random() * TINTS.length)];
        const reach = 3.5 + random() * 3.5;
        const halo = ctx.createRadialGradient(x, y, 0, x, y, reach);
        halo.addColorStop(0, `rgba(${tint}, 0.42)`);
        halo.addColorStop(1, `rgba(${tint}, 0)`);
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(x, y, reach, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = `rgba(${tint}, 0.95)`;
        ctx.beginPath();
        ctx.arc(x, y, 0.9 + random() * 0.4, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  return <canvas ref={ref} className="stars absolute inset-0 h-full w-full" aria-hidden="true" />;
}
