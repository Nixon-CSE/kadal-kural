// The heavy 3D scenes load lazily; the layout warms them while the browser is idle.
export const loadHeroScene = () => import("@/components/three/HeroScene");
export const loadBars3D = () => import("@/components/three/Bars3D");
export const loadVoiceOrb = () => import("@/components/desk/VoiceOrb");

export const PAGE_LOADERS = [loadHeroScene, loadBars3D, loadVoiceOrb];
