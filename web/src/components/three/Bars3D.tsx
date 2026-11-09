import { ContactShadows, Environment, Html, Lightformer, OrbitControls, RoundedBox } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

import { SceneCanvas } from "./SceneCanvas";

export interface Bar3D {
  label: string;
  value: number;
  color: string;
  display: string;
}

function Bar({ bar, x, max, reduced }: { bar: Bar3D; x: number; max: number; reduced: boolean }) {
  const group = useRef<THREE.Group>(null);
  const target = max > 0 ? 0.15 + (bar.value / max) * 2.6 : 0.15;
  useFrame((_, dt) => {
    if (!group.current) return;
    group.current.scale.y = reduced ? target : THREE.MathUtils.damp(group.current.scale.y, target, 4, dt);
  });
  return (
    <group position={[x, 0, 0]}>
      <group ref={group} scale={[1, 0.01, 1]}>
        <RoundedBox args={[0.8, 1, 0.8]} radius={0.08} smoothness={4} position={[0, 0.5, 0]}>
          <meshStandardMaterial color={bar.color} roughness={0.3} metalness={0.05} />
        </RoundedBox>
      </group>
      <Html position={[0, target + 0.35, 0]} center distanceFactor={7} zIndexRange={[10, 0]}>
        <div className="rounded-full bg-white/90 px-2 py-0.5 text-xs font-extrabold whitespace-nowrap text-ink shadow">{bar.display}</div>
      </Html>
      <Html position={[0, -0.25, 0.6]} center distanceFactor={7} zIndexRange={[10, 0]}>
        <div className="text-xs font-semibold whitespace-nowrap text-muted-foreground">{bar.label}</div>
      </Html>
    </group>
  );
}

export default function Bars3D({ bars, reduced }: { bars: Bar3D[]; reduced: boolean }) {
  const max = Math.max(0, ...bars.map((b) => b.value));
  const gap = 1.25;
  const start = -((bars.length - 1) * gap) / 2;
  return (
    <SceneCanvas className="absolute inset-0" camera={{ position: [3.2, 3.4, 6.2], fov: 36 }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[4, 7, 5]} intensity={1.4} />
      <group position={[0, -1.2, 0]}>
        <mesh rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[bars.length * gap + 1.5, 3]} />
          <meshStandardMaterial color="#f4f8ee" roughness={0.9} />
        </mesh>
        {bars.map((b, i) => <Bar key={b.label} bar={b} x={start + i * gap} max={max} reduced={reduced} />)}
        <ContactShadows frames={1} position={[0, 0.01, 0]} opacity={0.25} scale={10} blur={2} far={3} />
      </group>
      <OrbitControls enablePan={false} enableZoom={false} autoRotate={!reduced} autoRotateSpeed={0.6} minPolarAngle={0.6} maxPolarAngle={1.35} />
      <Environment resolution={128} frames={1}>
        <Lightformer form="rect" intensity={2} position={[0, 5, -3]} scale={[8, 3, 1]} />
        <Lightformer form="rect" intensity={1.2} position={[-4, 2, 3]} scale={[3, 5, 1]} rotation-y={Math.PI / 2} />
      </Environment>
    </SceneCanvas>
  );
}
