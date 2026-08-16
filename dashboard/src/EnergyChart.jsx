import { useEffect, useRef } from "react";

const W = 560;
const H = 160;
const PAD = 6;

export default function EnergyChart({ history }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, W, H);

    const pts = history.slice(-60);
    if (pts.length < 2) {
      ctx.fillStyle = "#5f6b78";
      ctx.font = "12px sans-serif";
      ctx.fillText("Waiting for predictions\u2026", PAD + 2, H / 2);
      return;
    }

    const min = Math.min(...pts.map((p) => p.pred)) * 0.9;
    const max = Math.max(...pts.map((p) => p.pred)) * 1.1;
    const span = max - min || 1;

    ctx.strokeStyle = "#1c232b";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 3; i++) {
      const y = PAD + (i / 3) * (H - PAD * 2);
      ctx.beginPath();
      ctx.moveTo(PAD, y);
      ctx.lineTo(W - PAD, y);
      ctx.stroke();
    }

    ctx.strokeStyle = "#58a6ff";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    pts.forEach((p, i) => {
      const x = PAD + (i / (pts.length - 1)) * (W - PAD * 2);
      const y = PAD + (1 - (p.pred - min) / span) * (H - PAD * 2);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    const last = pts[pts.length - 1];
    const lx = W - PAD;
    const ly = PAD + (1 - (last.pred - min) / span) * (H - PAD * 2);
    ctx.fillStyle = "#3fb950";
    ctx.beginPath();
    ctx.arc(lx, ly, 3, 0, Math.PI * 2);
    ctx.fill();
  }, [history]);

  return (
    <canvas ref={canvasRef} width={W} height={H} aria-label="Historical predicted consumption chart" />
  );
}