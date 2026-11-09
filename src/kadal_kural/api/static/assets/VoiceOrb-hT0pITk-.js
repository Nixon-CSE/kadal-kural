import{r,j as s}from"./index-DlbLW2Ka.js";import{g as F,h as I,a as _,M as R,i as k,u as S,_ as w,b as O,V,j as T,k as L,S as G,E as D,L as P,C as N}from"./SceneCanvas-DBaKU3Jm.js";import{F as $,M as B}from"./Float-Ce8Favkt.js";const H=()=>parseInt(F.replace(/\D+/g,"")),J=H();class U extends L{constructor(){super({uniforms:{time:{value:0},pixelRatio:{value:1}},vertexShader:`
        uniform float pixelRatio;
        uniform float time;
        attribute float size;  
        attribute float speed;  
        attribute float opacity;
        attribute vec3 noise;
        attribute vec3 color;
        varying vec3 vColor;
        varying float vOpacity;

        void main() {
          vec4 modelPosition = modelMatrix * vec4(position, 1.0);
          modelPosition.y += sin(time * speed + modelPosition.x * noise.x * 100.0) * 0.2;
          modelPosition.z += cos(time * speed + modelPosition.x * noise.y * 100.0) * 0.2;
          modelPosition.x += cos(time * speed + modelPosition.x * noise.z * 100.0) * 0.2;
          vec4 viewPosition = viewMatrix * modelPosition;
          vec4 projectionPostion = projectionMatrix * viewPosition;
          gl_Position = projectionPostion;
          gl_PointSize = size * 25. * pixelRatio;
          gl_PointSize *= (1.0 / - viewPosition.z);
          vColor = color;
          vOpacity = opacity;
        }
      `,fragmentShader:`
        varying vec3 vColor;
        varying float vOpacity;
        void main() {
          float distanceToCenter = distance(gl_PointCoord, vec2(0.5));
          float strength = 0.05 / distanceToCenter - 0.1;
          gl_FragColor = vec4(vColor, strength * vOpacity);
          #include <tonemapping_fragment>
          #include <${J>=154?"colorspace_fragment":"encodings_fragment"}>
        }
      `})}get time(){return this.uniforms.time.value}set time(t){this.uniforms.time.value=t}get pixelRatio(){return this.uniforms.pixelRatio.value}set pixelRatio(t){this.uniforms.pixelRatio.value=t}}const E=e=>e&&e.constructor===Float32Array,W=e=>[e.r,e.g,e.b],z=e=>e instanceof O||e instanceof V||e instanceof T,C=e=>Array.isArray(e)?e:z(e)?e.toArray():[e,e,e];function x(e,t,l){return r.useMemo(()=>{if(t!==void 0){if(E(t))return t;if(t instanceof k){const i=Array.from({length:e*3},()=>W(t)).flat();return Float32Array.from(i)}else if(z(t)||Array.isArray(t)){const i=Array.from({length:e*3},()=>C(t)).flat();return Float32Array.from(i)}return Float32Array.from({length:e},()=>t)}return Float32Array.from({length:e},l)},[t])}const q=r.forwardRef(({noise:e=1,count:t=100,speed:l=1,opacity:i=1,scale:p=1,size:n,color:a,children:c,...g},h)=>{r.useMemo(()=>I({SparklesImplMaterial:U}),[]);const u=r.useRef(null),f=_(m=>m.viewport.dpr),o=C(p),d=r.useMemo(()=>Float32Array.from(Array.from({length:t},()=>o.map(R.randFloatSpread)).flat()),[t,...o]),j=x(t,n,Math.random),A=x(t,i),y=x(t,l),b=x(t*3,e),M=x(a===void 0?t*3:t,E(a)?a:new k(a),()=>1);return S(m=>{u.current&&u.current.material&&(u.current.material.time=m.clock.elapsedTime)}),r.useImperativeHandle(h,()=>u.current,[]),r.createElement("points",w({key:`particle-${t}-${JSON.stringify(p)}`},g,{ref:u}),r.createElement("bufferGeometry",null,r.createElement("bufferAttribute",{attach:"attributes-position",args:[d,3]}),r.createElement("bufferAttribute",{attach:"attributes-size",args:[j,1]}),r.createElement("bufferAttribute",{attach:"attributes-opacity",args:[A,1]}),r.createElement("bufferAttribute",{attach:"attributes-speed",args:[y,1]}),r.createElement("bufferAttribute",{attach:"attributes-color",args:[M,3]}),r.createElement("bufferAttribute",{attach:"attributes-noise",args:[b,3]})),c||r.createElement("sparklesImplMaterial",{transparent:!0,pixelRatio:f,depthWrite:!1}))}),v={idle:"#b5f23d",connecting:"#d9f99d",listening:"#a3e635",thinking:"#e4f76b",speaking:"#9be22d",error:"#e05252",lime:"#b5f23d",hold:"#e05252",ask:"#f0b93a"};function K({mode:e,tone:t,level:l,reduced:i}){const p=r.useRef(null),n=r.useRef(null),a=r.useRef(null),c=r.useRef(null),g=r.useRef(0),h=r.useMemo(()=>new k,[]);return S((u,f)=>{var b;const o=u.clock.elapsedTime;g.current+=(l.current-g.current)*Math.min(1,f*12);const d=i?0:g.current,j=e==="speaking"?Math.sin(o*9)*.035:e==="thinking"?Math.sin(o*4)*.02:Math.sin(o*1.6)*.012,A=1+d*.28+(i?0:j);if((b=p.current)==null||b.scale.setScalar(A),n.current){const M=e==="thinking"?.42:e==="listening"?.32:e==="speaking"?.36:.24;n.current.distort=R.damp(n.current.distort,i?.15:M+d*.45,6,f),n.current.speed=e==="thinking"?4:e==="idle"?1.2:2.4,h.set(t!=="lime"&&e!=="listening"&&e!=="thinking"?v[t]:v[e]);const m=1-Math.exp(-f*5);n.current.color.lerp(h,m),n.current.emissive.lerp(h,m),n.current.emissiveIntensity=.28+d*.5}const y=i?0:e==="thinking"?1.8:e==="listening"?.9:.35;a.current&&(a.current.rotation.z+=f*y,a.current.rotation.x=1.15+Math.sin(o*.6)*.08),c.current&&(c.current.rotation.z-=f*y*.7,c.current.rotation.y=.5+Math.cos(o*.5)*.1)}),s.jsxs("group",{children:[s.jsxs($,{speed:i?0:1.6,rotationIntensity:.25,floatIntensity:.6,children:[s.jsxs("mesh",{ref:p,castShadow:!0,children:[s.jsx("icosahedronGeometry",{args:[1,32]}),s.jsx(B,{ref:n,color:v.idle,emissive:v.idle,emissiveIntensity:.28,roughness:.14,metalness:.05,clearcoat:1,clearcoatRoughness:.12,distort:.24,speed:1.2})]}),s.jsxs("mesh",{ref:a,children:[s.jsx("torusGeometry",{args:[1.32,.01,16,160]}),s.jsx("meshStandardMaterial",{color:"#4d7c0f",roughness:.35,metalness:.5})]}),s.jsxs("mesh",{ref:c,children:[s.jsx("torusGeometry",{args:[1.48,.006,16,160]}),s.jsx("meshStandardMaterial",{color:"#84cc16",roughness:.3,metalness:.3,transparent:!0,opacity:.65})]})]}),!i&&s.jsx(q,{count:18,scale:[3.6,3,2.6],size:2.4,speed:.35,color:"#84cc16",opacity:.7}),s.jsx(N,{frames:1,position:[0,-1.55,0],opacity:.35,scale:6,blur:2.6,far:3,color:"#0f1d14"})]})}function Z(e){const{className:t,...l}=e;return s.jsxs(G,{className:t,fps:45,"aria-hidden":"true",camera:{position:[0,.15,5.4],fov:40},children:[s.jsx("ambientLight",{intensity:.55}),s.jsx("directionalLight",{position:[3,4,3],intensity:1.4}),s.jsx(K,{...l}),s.jsxs(D,{resolution:128,frames:1,children:[s.jsx(P,{form:"rect",intensity:2.4,position:[0,4,-3],scale:[8,3,1]}),s.jsx(P,{form:"rect",intensity:1.4,position:[-4,1,2],scale:[3,6,1],"rotation-y":Math.PI/2}),s.jsx(P,{form:"ring",intensity:1.8,color:"#d9f99d",position:[4,2,2],scale:2})]})]})}export{Z as VoiceOrb};
