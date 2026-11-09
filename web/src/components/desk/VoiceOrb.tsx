import { ContactShadows, Environment, Float, Lightformer, MeshDistortMaterial, Sparkles } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, type MutableRefObject } from "react";
import * as THREE from "three";

import type { Mode } from "@/hooks/useDesk";

import { SceneCanvas } from "../three/SceneCanvas";

export type OrbTone = "lime" | "hold" | "ask";

const PALETTE: Record<Mode | OrbTone, string> = {
  idle: "#b5f23d",
  connecting: "#d9f99d",
  listening: "#a3e635",
  thinking: "#e4f76b",
  speaking: "#9be22d",
  error: "#e05252",
  lime: "#b5f23d",
  hold: "#e05252",
  ask: "#f0b93a",
};

interface OrbProps {
  mode: Mode;
  tone: OrbTone;
  level: MutableRefObject<number>;
  reduced: boolean;
}

function Orb({ mode, tone, level, reduced }: OrbProps) {
  const mesh = useRef<THREE.Mesh>(null);
  const mat = useRef<THREE.MeshPhysicalMaterial & { distort: number; speed: number }>(null);
  const ringA = useRef<THREE.Mesh>(null);
  const ringB = useRef<THREE.Mesh>(null);
  const smooth = useRef(0);
  const target = useMemo(() => new THREE.Color(), []);

  useFrame((state, dt) => {
    const t = state.clock.elapsedTime;
    smooth.current += (level.current - smooth.current) * Math.min(1, dt * 12);
    const lvl = reduced ? 0 : smooth.current;

    const pulse =
      mode === "speaking" ? Math.sin(t * 9) * 0.035 : mode === "thinking" ? Math.sin(t * 4) * 0.02 : Math.sin(t * 1.6) * 0.012;
    const s = 1 + lvl * 0.28 + (reduced ? 0 : pulse);
    mesh.current?.scale.setScalar(s);

    if (mat.current) {
      const baseDistort = mode === "thinking" ? 0.42 : mode === "listening" ? 0.32 : mode === "speaking" ? 0.36 : 0.24;
      mat.current.distort = THREE.MathUtils.damp(mat.current.distort, reduced ? 0.15 : baseDistort + lvl * 0.45, 6, dt);
      mat.current.speed = mode === "thinking" ? 4 : mode === "idle" ? 1.2 : 2.4;
      target.set(tone !== "lime" && mode !== "listening" && mode !== "thinking" ? PALETTE[tone] : PALETTE[mode]);
      const k = 1 - Math.exp(-dt * 5); // frame-rate independent: settles in ~0.6 s at any fps
      mat.current.color.lerp(target, k);
      mat.current.emissive.lerp(target, k);
      mat.current.emissiveIntensity = 0.28 + lvl * 0.5;
    }
    const spin = reduced ? 0 : mode === "thinking" ? 1.8 : mode === "listening" ? 0.9 : 0.35;
    if (ringA.current) { ringA.current.rotation.z += dt * spin; ringA.current.rotation.x = 1.15 + Math.sin(t * 0.6) * 0.08; }
    if (ringB.current) { ringB.current.rotation.z -= dt * spin * 0.7; ringB.current.rotation.y = 0.5 + Math.cos(t * 0.5) * 0.1; }
  });

  return (
    <group>
      <Float speed={reduced ? 0 : 1.6} rotationIntensity={0.25} floatIntensity={0.6}>
        <mesh ref={mesh} castShadow>
          <icosahedronGeometry args={[1, 32]} />
          <MeshDistortMaterial
            ref={mat as never}
            color={PALETTE.idle}
            emissive={PALETTE.idle}
            emissiveIntensity={0.28}
            roughness={0.14}
            metalness={0.05}
            clearcoat={1}
            clearcoatRoughness={0.12}
            distort={0.24}
            speed={1.2}
          />
        </mesh>
        <mesh ref={ringA}>
          <torusGeometry args={[1.32, 0.01, 16, 160]} />
          <meshStandardMaterial color="#4d7c0f" roughness={0.35} metalness={0.5} />
        </mesh>
        <mesh ref={ringB}>
          <torusGeometry args={[1.48, 0.006, 16, 160]} />
          <meshStandardMaterial color="#84cc16" roughness={0.3} metalness={0.3} transparent opacity={0.65} />
        </mesh>
      </Float>
      {!reduced && <Sparkles count={18} scale={[3.6, 3, 2.6]} size={2.4} speed={0.35} color="#84cc16" opacity={0.7} />}
      <ContactShadows frames={1} position={[0, -1.55, 0]} opacity={0.35} scale={6} blur={2.6} far={3} color="#0f1d14" />
    </group>
  );
}

export function VoiceOrb(props: OrbProps & { className?: string }) {
  const { className, ...orb } = props;
  return (
    <SceneCanvas className={className} fps={45} aria-hidden="true" camera={{ position: [0, 0.15, 5.4], fov: 40 }}>
        <ambientLight intensity={0.55} />
        <directionalLight position={[3, 4, 3]} intensity={1.4} />
        <Orb {...orb} />
        {/* Studio lighting built from light panels: no HDR download, works offline. */}
        <Environment resolution={128} frames={1}>
          <Lightformer form="rect" intensity={2.4} position={[0, 4, -3]} scale={[8, 3, 1]} />
          <Lightformer form="rect" intensity={1.4} position={[-4, 1, 2]} scale={[3, 6, 1]} rotation-y={Math.PI / 2} />
          <Lightformer form="ring" intensity={1.8} color="#d9f99d" position={[4, 2, 2]} scale={2} />
        </Environment>
    </SceneCanvas>
  );
}
