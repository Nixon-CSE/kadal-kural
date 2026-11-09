import { ContactShadows, Environment, Float, Lightformer, MeshDistortMaterial, RoundedBox } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

import { SceneCanvas } from "./SceneCanvas";

/** A white ledger slip with a lime status edge: the product's unit of work, as an object. */
function Slip({ position, rotation, tone = "#b5f23d", scale = 1 }: { position: [number, number, number]; rotation: [number, number, number]; tone?: string; scale?: number }) {
  return (
    <Float speed={1.4} rotationIntensity={0.6} floatIntensity={0.9}>
      <group position={position} rotation={rotation} scale={scale}>
        <RoundedBox args={[1.5, 0.95, 0.06]} radius={0.06} smoothness={2}>
          <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.35} roughness={0.4} />
        </RoundedBox>
        <RoundedBox args={[0.08, 0.95, 0.07]} radius={0.03} position={[-0.71, 0, 0.005]}>
          <meshStandardMaterial color={tone} emissive={tone} emissiveIntensity={0.25} roughness={0.3} />
        </RoundedBox>
        {[0.25, 0.05, -0.15].map((y, i) => (
          <mesh key={y} position={[0.05 - i * 0.08, y, 0.035]}>
            <boxGeometry args={[i === 0 ? 1.0 : 0.8 - i * 0.12, 0.07, 0.005]} />
            <meshStandardMaterial color={i === 0 ? "#0f1d14" : "#c9d4c1"} roughness={0.8} />
          </mesh>
        ))}
        <mesh position={[0.45, -0.3, 0.035]}>
          <boxGeometry args={[0.38, 0.14, 0.005]} />
          <meshStandardMaterial color={tone} roughness={0.4} />
        </mesh>
      </group>
    </Float>
  );
}

function Rig({ reduced }: { reduced: boolean }) {
  useFrame((state) => {
    if (reduced) return;
    const { camera, pointer } = state;
    camera.position.x = THREE.MathUtils.damp(camera.position.x, pointer.x * 0.9, 3, 1 / 60);
    camera.position.y = THREE.MathUtils.damp(camera.position.y, 0.3 + pointer.y * 0.5, 3, 1 / 60);
    camera.lookAt(0, 0, 0);
  });
  return null;
}

function Core({ reduced }: { reduced: boolean }) {
  const ring = useRef<THREE.Mesh>(null);
  const ring2 = useRef<THREE.Mesh>(null);
  useFrame((state, dt) => {
    if (reduced) return;
    if (ring.current) ring.current.rotation.z += dt * 0.4;
    if (ring2.current) ring2.current.rotation.z -= dt * 0.25;
    void state;
  });
  return (
    <Float speed={reduced ? 0 : 1.2} floatIntensity={0.5}>
      <mesh>
        <icosahedronGeometry args={[1.05, 32]} />
        <MeshDistortMaterial color="#b5f23d" emissive="#a3e635" emissiveIntensity={0.25} roughness={0.12} metalness={0.05} clearcoat={1} clearcoatRoughness={0.1} distort={reduced ? 0.15 : 0.3} speed={reduced ? 0 : 1.6} />
      </mesh>
      <mesh ref={ring} rotation={[1.2, 0.2, 0]}>
        <torusGeometry args={[1.5, 0.012, 16, 180]} />
        <meshStandardMaterial color="#4d7c0f" metalness={0.5} roughness={0.3} />
      </mesh>
      <mesh ref={ring2} rotation={[1.45, -0.4, 0]}>
        <torusGeometry args={[1.75, 0.007, 16, 180]} />
        <meshStandardMaterial color="#84cc16" transparent opacity={0.6} />
      </mesh>
    </Float>
  );
}

export default function HeroScene({ reduced }: { reduced: boolean }) {
  return (
    <SceneCanvas className="absolute inset-0" maxDpr={1.25} camera={{ position: [0, 0.3, 8.2], fov: 38 }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[4, 6, 4]} intensity={1.5} />
      <Rig reduced={reduced} />
      <Core reduced={reduced} />
      <Slip position={[-2.7, 1.1, -0.6]} rotation={[0.1, 0.5, -0.12]} />
      <Slip position={[2.6, 0.9, -0.4]} rotation={[-0.05, -0.55, 0.1]} tone="#e05252" scale={0.9} />
      <Slip position={[2.3, -1.25, 0.4]} rotation={[0.2, -0.35, -0.08]} tone="#f0b93a" scale={0.8} />
      <Slip position={[-2.4, -1.2, 0.3]} rotation={[-0.15, 0.4, 0.14]} scale={0.85} />
      <ContactShadows frames={1} position={[0, -2.4, 0]} opacity={0.3} scale={12} blur={2.8} far={4} color="#0f1d14" />
      <Environment resolution={128} frames={1}>
        <Lightformer form="rect" intensity={2.4} position={[0, 5, -4]} scale={[10, 3, 1]} />
        <Lightformer form="rect" intensity={1.5} position={[-5, 1, 2]} scale={[3, 7, 1]} rotation-y={Math.PI / 2} />
        <Lightformer form="ring" intensity={2} color="#d9f99d" position={[5, 2, 2]} scale={2.5} />
      </Environment>
    </SceneCanvas>
  );
}
