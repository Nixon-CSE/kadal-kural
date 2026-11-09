import{R,u as g,_ as b,c as E,M as z,e as F,d as I,b as _,V,f as T,g as j,S as k}from"./Lightformer-CWANNdKH.js";import{r}from"./index-u4K41RJZ.js";const D=()=>parseInt(R.replace(/\D+/g,"")),O=D();var $=`#define GLSLIFY 1
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}float snoise(vec3 v){const vec2 C=vec2(1.0/6.0,1.0/3.0);const vec4 D=vec4(0.0,0.5,1.0,2.0);vec3 i=floor(v+dot(v,C.yyy));vec3 x0=v-i+dot(i,C.xxx);vec3 g=step(x0.yzx,x0.xyz);vec3 l=1.0-g;vec3 i1=min(g.xyz,l.zxy);vec3 i2=max(g.xyz,l.zxy);vec3 x1=x0-i1+C.xxx;vec3 x2=x0-i2+C.yyy;vec3 x3=x0-D.yyy;i=mod289(i);vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));float n_=0.142857142857;vec3 ns=n_*D.wyz-D.xzx;vec4 j=p-49.0*floor(p*ns.z*ns.z);vec4 x_=floor(j*ns.z);vec4 y_=floor(j-7.0*x_);vec4 x=x_*ns.x+ns.yyyy;vec4 y=y_*ns.x+ns.yyyy;vec4 h=1.0-abs(x)-abs(y);vec4 b0=vec4(x.xy,y.xy);vec4 b1=vec4(x.zw,y.zw);vec4 s0=floor(b0)*2.0+1.0;vec4 s1=floor(b1)*2.0+1.0;vec4 sh=-step(h,vec4(0.0));vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);m=m*m;return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));}`;class L extends E{constructor(e={}){super(e),this.setValues(e),this._time={value:0},this._distort={value:.4},this._radius={value:1}}onBeforeCompile(e){e.uniforms.time=this._time,e.uniforms.radius=this._radius,e.uniforms.distort=this._distort,e.vertexShader=`
      uniform float time;
      uniform float radius;
      uniform float distort;
      ${$}
      ${e.vertexShader}
    `,e.vertexShader=e.vertexShader.replace("#include <begin_vertex>",`
        float updateTime = time / 50.0;
        float noise = snoise(vec3(position / 2.0 + updateTime * 5.0));
        vec3 transformed = vec3(position * (noise * pow(distort, 2.0) + radius));
        `)}get time(){return this._time.value}set time(e){this._time.value=e}get distort(){return this._distort.value}set distort(e){this._distort.value=e}get radius(){return this._radius.value}set radius(e){this._radius.value=e}}const U=r.forwardRef(({speed:t=1,...e},o)=>{const[i]=r.useState(()=>new L);return g(n=>i&&(i.time=n.clock.elapsedTime*t)),r.createElement("primitive",b({object:i,ref:o,attach:"material"},e))}),B=r.forwardRef(({children:t,enabled:e=!0,speed:o=1,rotationIntensity:i=1,floatIntensity:n=1,floatingRange:c=[-.1,.1],autoInvalidate:l=!1,...d},y)=>{const a=r.useRef(null);r.useImperativeHandle(y,()=>a.current,[]);const s=r.useRef(Math.random()*1e4);return g(p=>{var u,v;if(!e||o===0)return;l&&p.invalidate();const m=s.current+p.clock.elapsedTime;a.current.rotation.x=Math.cos(m/4*o)/8*i,a.current.rotation.y=Math.sin(m/4*o)/8*i,a.current.rotation.z=Math.sin(m/4*o)/20*i;let f=Math.sin(m/4*o)/10;f=z.mapLinear(f,-.1,.1,(u=c==null?void 0:c[0])!==null&&u!==void 0?u:-.1,(v=c==null?void 0:c[1])!==null&&v!==void 0?v:.1),a.current.position.y=f*n,a.current.updateMatrix()}),r.createElement("group",d,r.createElement("group",{ref:a,matrixAutoUpdate:!1},t))});class q extends k{constructor(){super({uniforms:{time:{value:0},pixelRatio:{value:1}},vertexShader:`
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
          #include <${O>=154?"colorspace_fragment":"encodings_fragment"}>
        }
      `})}get time(){return this.uniforms.time.value}set time(e){this.uniforms.time.value=e}get pixelRatio(){return this.uniforms.pixelRatio.value}set pixelRatio(e){this.uniforms.pixelRatio.value=e}}const A=t=>t&&t.constructor===Float32Array,G=t=>[t.r,t.g,t.b],w=t=>t instanceof V||t instanceof T||t instanceof j,M=t=>Array.isArray(t)?t:w(t)?t.toArray():[t,t,t];function x(t,e,o){return r.useMemo(()=>{if(e!==void 0){if(A(e))return e;if(e instanceof _){const i=Array.from({length:t*3},()=>G(e)).flat();return Float32Array.from(i)}else if(w(e)||Array.isArray(e)){const i=Array.from({length:t*3},()=>M(e)).flat();return Float32Array.from(i)}return Float32Array.from({length:t},()=>e)}return Float32Array.from({length:t},o)},[e])}const J=r.forwardRef(({noise:t=1,count:e=100,speed:o=1,opacity:i=1,scale:n=1,size:c,color:l,children:d,...y},a)=>{r.useMemo(()=>F({SparklesImplMaterial:q}),[]);const s=r.useRef(null),p=I(h=>h.viewport.dpr),u=M(n),v=r.useMemo(()=>Float32Array.from(Array.from({length:e},()=>u.map(z.randFloatSpread)).flat()),[e,...u]),m=x(e,c,Math.random),f=x(e,i),P=x(e,o),S=x(e*3,t),C=x(l===void 0?e*3:e,A(l)?l:new _(l),()=>1);return g(h=>{s.current&&s.current.material&&(s.current.material.time=h.clock.elapsedTime)}),r.useImperativeHandle(a,()=>s.current,[]),r.createElement("points",b({key:`particle-${e}-${JSON.stringify(n)}`},y,{ref:s}),r.createElement("bufferGeometry",null,r.createElement("bufferAttribute",{attach:"attributes-position",args:[v,3]}),r.createElement("bufferAttribute",{attach:"attributes-size",args:[m,1]}),r.createElement("bufferAttribute",{attach:"attributes-opacity",args:[f,1]}),r.createElement("bufferAttribute",{attach:"attributes-speed",args:[P,1]}),r.createElement("bufferAttribute",{attach:"attributes-color",args:[C,3]}),r.createElement("bufferAttribute",{attach:"attributes-noise",args:[S,3]})),d||r.createElement("sparklesImplMaterial",{transparent:!0,pixelRatio:p,depthWrite:!1}))});export{B as F,U as M,J as S};
