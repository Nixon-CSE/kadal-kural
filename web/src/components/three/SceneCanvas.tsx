import { PerformanceMonitor } from "@react-three/drei";
import { Canvas, useThree, type CanvasProps } from "@react-three/fiber";
import { useEffect, useRef, useState } from "react";

/** Drives a demand-mode canvas at a fixed frame rate instead of the display's refresh rate. */
function FpsDriver({ fps }: { fps: number }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    const id = window.setInterval(() => invalidate(), 1000 / fps);
    return () => window.clearInterval(id);
  }, [fps, invalidate]);
  return null;
}

/**
 * A Canvas that only renders while it is on screen and the tab is visible, and lowers its pixel
 * density when the frame rate drops. Off-screen or hidden, it costs nothing. Frames are capped at
 * `fps` (a 120 Hz display would otherwise re-render a slow floating scene 120 times a second).
 */
export function SceneCanvas({ children, className, fps = 30, maxDpr = 1.5, ...props }: CanvasProps & { className?: string; fps?: number; maxDpr?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const [onScreen, setOnScreen] = useState(true);
  const [tabVisible, setTabVisible] = useState(() => document.visibilityState === "visible");
  const [dpr, setDpr] = useState(maxDpr);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setOnScreen(entry.isIntersecting), { rootMargin: "120px" });
    io.observe(el);
    const onVis = () => setTabVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onVis);
    return () => { io.disconnect(); document.removeEventListener("visibilitychange", onVis); };
  }, []);

  return (
    <div ref={host} className={className}>
      <Canvas
        dpr={dpr}
        frameloop={onScreen && tabVisible ? "demand" : "never"}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        {...props}
      >
        {onScreen && tabVisible && <FpsDriver fps={fps} />}
        <PerformanceMonitor onDecline={() => setDpr(1)} onIncline={() => setDpr(maxDpr)} flipflops={3} />
        {children}
      </Canvas>
    </div>
  );
}
