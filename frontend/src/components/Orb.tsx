"use client";

// Jarvis's orb. Layers, back to front:
//   halo · plasma core (noise-displaced, fresnel rim, white-hot centre) · particle shell
//   (flow field; orbits while thinking) · voice spectrum ring · HUD rings (ticks, arcs,
//   labels) · shockwaves on each scene cue — through a bloom pass.
// It reacts to the frequency bands of the real sound (lib/audio.ts): lows swell the core,
// highs make the shell sparkle. Each state has its palette and motion.
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { bands } from "@/lib/audio";

export type OrbMode = "idle" | "listen" | "think" | "speak";

// `voice`: real loudness of Jarvis's audio (0–1), or −1 when the voice gives no audio level.
// `cue`: incremented when a scene action starts (a shockwave leaves the orb).
export type OrbSignals = { mode: OrbMode; mic: number; spike: number; voice: number; cue: number };

type Palette = [THREE.Color, THREE.Color, THREE.Color]; // body, rim/highlight, deep
const PALETTES: Record<OrbMode, Palette> = {
  idle: [new THREE.Color(0.55, 0.47, 1.0), new THREE.Color(0.37, 0.86, 1.0), new THREE.Color(0.2, 0.14, 0.62)],
  listen: [new THREE.Color(0.3, 0.86, 1.0), new THREE.Color(0.45, 1.0, 0.9), new THREE.Color(0.1, 0.3, 0.75)],
  think: [new THREE.Color(1.0, 0.72, 0.32), new THREE.Color(1.0, 0.9, 0.6), new THREE.Color(0.55, 0.28, 0.75)],
  speak: [new THREE.Color(0.66, 0.52, 1.0), new THREE.Color(0.78, 0.96, 1.0), new THREE.Color(0.85, 0.35, 1.0)],
};

// Ashima / Stefan Gustavson 3D simplex noise (MIT)
const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1./289.))*289.;}
vec4 mod289(vec4 x){return x-floor(x*(1./289.))*289.;}
vec4 permute(vec4 x){return mod289(((x*34.)+1.)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1./6.,1./3.); const vec4 D=vec4(0.,.5,1.,2.);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));
  float n_=.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.+1.; vec4 s1=floor(b1)*2.+1.; vec4 sh=-step(h,vec4(0.));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.); m=m*m;
  return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

const CORE_VS = /* glsl */ `
uniform float uTime, uLow, uAmp;
varying vec3 vN; varying vec3 vView; varying float vD;
${NOISE}
void main(){
  vec3 p = position;
  float n = snoise(p*1.7 + vec3(0., uTime*.35, 0.))*.65 + snoise(p*4.2 - uTime*.55)*.3;
  p += normal * n * (.035 + uLow*.2 + uAmp*.07);
  vD = n;
  vN = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(p, 1.);
  vView = -mv.xyz;
  gl_Position = projectionMatrix * mv;
}`;

const CORE_FS = /* glsl */ `
uniform vec3 uC1, uC2, uC3; uniform float uAmp, uTime;
varying vec3 vN; varying vec3 vView; varying float vD;
void main(){
  float f = 1. - abs(dot(normalize(vN), normalize(vView)));
  float rim = pow(f, 2.4);
  float inner = pow(1. - f, 4.) * (.1 + uAmp*.42);
  float veins = smoothstep(.25, .95, vD) * (.35 + uAmp*.8);
  vec3 col = mix(uC3*.35, uC1*.75, .5 + .5*vD);
  col += uC2 * rim * 1.15 + vec3(1.) * pow(f, 8.) * .25;
  col += mix(uC1, vec3(1.), .5) * inner + uC2 * veins * .3;
  gl_FragColor = vec4(col, clamp(.08 + rim*.7 + inner*.45 + veins*.12, 0., 1.));
}`;

const SHELL_VS = /* glsl */ `
uniform float uTime, uAmp, uHigh, uLow, uThink, uPx, uSpeed;
attribute vec3 aRnd; attribute vec4 aOrbit;
varying float vGlow; varying float vY; varying float vTw;
${NOISE}
mat3 rotX(float a){float c=cos(a),s=sin(a);return mat3(1.,0.,0.,0.,c,s,0.,-s,c);}
mat3 rotZ(float a){float c=cos(a),s=sin(a);return mat3(c,s,0.,-s,c,0.,0.,0.,1.);}
void main(){
  float t = uTime * uSpeed;
  vec3 p = position;
  vec3 q = p*1.3 + t*.18;
  vec3 flow = vec3(snoise(q), snoise(q + 17.1), snoise(q + 31.7));
  p += flow * (.045 + uAmp*.2);
  float bulge = snoise(position*2.1 + t*.6);
  p *= 1.06 + bulge*(.025 + uLow*.2) + aRnd.z*uAmp*.05;
  // thinking: particles leave the shell for inclined orbits
  float ang = aOrbit.z + t * aOrbit.w;
  vec3 o = rotZ(aRnd.x*6.2831) * rotX(aOrbit.y) * vec3(cos(ang), 0., sin(ang)) * aOrbit.x;
  float k = clamp(uThink*1.7 - aRnd.y*.7, 0., 1.);
  p = mix(p, o, k*k*(3.-2.*k));
  vec4 mv = modelViewMatrix * vec4(p, 1.);
  vTw = pow(.5 + .5*sin(t*(2.5 + aRnd.x*6.) + aRnd.y*40.), 10.) * (.2 + uHigh*1.3);
  vGlow = .26 + bulge*.2 + uAmp*.18 + vTw*.7;
  vY = position.y;
  gl_PointSize = (1.0 + aRnd.z*1.5 + uHigh*1.1 + vTw*1.4) * uPx / -mv.z;
  gl_Position = projectionMatrix * mv;
}`;

const SHELL_FS = /* glsl */ `
uniform vec3 uC1, uC2, uC3;
varying float vGlow; varying float vY; varying float vTw;
void main(){
  float d = length(gl_PointCoord - .5); if (d > .5) discard;
  float a = smoothstep(.5, 0., d);
  vec3 c = mix(uC1, uC2, smoothstep(-1., 1., vY));
  c = mix(c, uC3, .18*(1. - vY)) + vec3(vTw*.6);
  gl_FragColor = vec4(c * vGlow, a * .75);
}`;

const FIT_RADIUS = 2.2;

// Last pass: alpha from brightness, so the canvas is transparent where there is no light
// and glows over the page (premultiplied: rgb + page × (1 − a)).
const LIGHT_ALPHA = {
  uniforms: { tDiffuse: { value: null } },
  vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }",
  fragmentShader: `uniform sampler2D tDiffuse; varying vec2 vUv;
    void main(){ vec3 c = texture2D(tDiffuse, vUv).rgb; float a = clamp(max(c.r, max(c.g, c.b)), 0., 1.);
      gl_FragColor = vec4(min(c, vec3(a)), a); }`,
};
const add = { transparent: true, depthWrite: false, blending: THREE.AdditiveBlending } as const;

// ---- HUD textures (drawn once on a canvas) --------------------------------------------------
function hudTexture(draw: (g: CanvasRenderingContext2D, s: number) => void, size = 1024) {
  const cv = document.createElement("canvas");
  cv.width = cv.height = size;
  const g = cv.getContext("2d")!;
  g.translate(size / 2, size / 2);
  g.strokeStyle = g.fillStyle = "#fff";
  draw(g, size / 2);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

const TICKS = (g: CanvasRenderingContext2D, r: number) => {
  for (let i = 0; i < 180; i++) {
    const a = (i / 180) * Math.PI * 2, long = i % 15 === 0, mid = i % 5 === 0;
    const r0 = r * (long ? 0.9 : mid ? 0.935 : 0.95);
    g.globalAlpha = long ? 0.95 : mid ? 0.6 : 0.32;
    g.lineWidth = long ? 3 : 1.6;
    g.beginPath(); g.moveTo(Math.cos(a) * r0, Math.sin(a) * r0);
    g.lineTo(Math.cos(a) * r * 0.975, Math.sin(a) * r * 0.975); g.stroke();
  }
  g.globalAlpha = 0.5; g.lineWidth = 1.2;
  g.beginPath(); g.arc(0, 0, r * 0.985, 0, Math.PI * 2); g.stroke();
};

const ARCS = (g: CanvasRenderingContext2D, r: number) => {
  const arcs: [number, number, number, number][] = [ // start, length, width, alpha
    [0.1, 1.1, 10, 0.85], [1.5, 0.35, 10, 0.55], [2.2, 1.6, 4, 0.7], [4.05, 0.5, 10, 0.85],
    [4.8, 1.05, 3, 0.45],
  ];
  for (const [s, l, w, a] of arcs) {
    g.globalAlpha = a; g.lineWidth = w; g.lineCap = "butt";
    g.beginPath(); g.arc(0, 0, r * 0.9, s, s + l); g.stroke();
  }
  // bracket marks
  g.globalAlpha = 0.9; g.lineWidth = 3;
  for (const a of [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2]) {
    g.beginPath(); g.arc(0, 0, r * 0.97, a - 0.06, a + 0.06); g.stroke();
  }
};

const LABELS = (g: CanvasRenderingContext2D, r: number) => {
  g.font = `500 ${Math.round(r * 0.034)}px "JetBrains Mono", ui-monospace, monospace`;
  g.textAlign = "center"; g.textBaseline = "middle";
  const words = ["ROYAUMONEY", "LIQUIDITÀ", "REGIME", "MERCATO", "SCENARIO", "INVALIDAZIONE"];
  words.forEach((w, i) => {
    const a = (i / words.length) * Math.PI * 2;
    g.save(); g.rotate(a); g.globalAlpha = 0.55;
    g.fillText(w, 0, -r * 0.93);
    g.restore();
  });
  g.globalAlpha = 0.35; g.lineWidth = 1.2; g.setLineDash([2, 9]);
  g.beginPath(); g.arc(0, 0, r * 0.86, 0, Math.PI * 2); g.stroke();
  g.setLineDash([]);
};

const RADIAL = (g: CanvasRenderingContext2D, r: number) => {
  const gr = g.createRadialGradient(0, 0, 0, 0, 0, r);
  gr.addColorStop(0, "rgba(255,255,255,.5)"); gr.addColorStop(0.25, "rgba(255,255,255,.14)");
  gr.addColorStop(0.6, "rgba(255,255,255,.03)"); gr.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = gr; g.fillRect(-r, -r, 2 * r, 2 * r);
};

export default function Orb({ signals }: { signals: React.MutableRefObject<OrbSignals> }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current!;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const small = el.clientWidth < 520;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, premultipliedAlpha: true, powerPreference: "high-performance" });
    const dpr = Math.min(window.devicePixelRatio, small ? 1.5 : 1.75);
    renderer.setPixelRatio(dpr);
    renderer.setClearColor(0x000000, 0);
    el.appendChild(renderer.domElement);
    // the edge fades so no frame is ever visible
    Object.assign(renderer.domElement.style, {
      maskImage: "radial-gradient(closest-side, #000 78%, transparent 100%)",
      webkitMaskImage: "radial-gradient(closest-side, #000 78%, transparent 100%)",
    });

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    let dist = 4.6;
    camera.position.z = dist;
    const root = new THREE.Group();
    scene.add(root);

    const col = { c1: new THREE.Color(), c2: new THREE.Color(), c3: new THREE.Color() };
    [col.c1, col.c2, col.c3].forEach((c, i) => c.copy(PALETTES.idle[i]));
    const shared = { uC1: { value: col.c1 }, uC2: { value: col.c2 }, uC3: { value: col.c3 } };
    const u = {
      uTime: { value: 0 }, uAmp: { value: 0 }, uLow: { value: 0 }, uHigh: { value: 0 },
      uThink: { value: 0 }, uPx: { value: 1 }, uSpeed: { value: reduced ? 0.35 : 1 }, ...shared,
    };

    // halo
    const radial = hudTexture(RADIAL, 256);
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: radial, color: col.c1, ...add, opacity: 0.55 }));
    halo.scale.setScalar(3.2);
    root.add(halo);

    // plasma core
    const coreGeo = new THREE.IcosahedronGeometry(0.62, 48);
    const coreMat = new THREE.ShaderMaterial({ uniforms: u, vertexShader: CORE_VS, fragmentShader: CORE_FS, ...add });
    const core = new THREE.Mesh(coreGeo, coreMat);
    root.add(core);

    // particle shell
    const N = small ? 5000 : 9000;
    const pos = new Float32Array(N * 3), rnd = new Float32Array(N * 3), orbit = new Float32Array(N * 4);
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), th = i * 2.399963;
      pos.set([Math.cos(th) * r, y, Math.sin(th) * r], i * 3);
      rnd.set([Math.random(), Math.random(), Math.random()], i * 3);
      const ring = Math.floor(Math.random() * 4);
      orbit.set([1.05 + ring * 0.13 + Math.random() * 0.05, 0.35 + ring * 0.45, Math.random() * 6.283,
        (0.35 + Math.random() * 0.3) * (ring % 2 ? -1 : 1)], i * 4);
    }
    const shellGeo = new THREE.BufferGeometry();
    shellGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    shellGeo.setAttribute("aRnd", new THREE.BufferAttribute(rnd, 3));
    shellGeo.setAttribute("aOrbit", new THREE.BufferAttribute(orbit, 4));
    const shellMat = new THREE.ShaderMaterial({ uniforms: u, vertexShader: SHELL_VS, fragmentShader: SHELL_FS, ...add });
    const shell = new THREE.Points(shellGeo, shellMat);
    root.add(shell);

    // HUD: tilted rings that turn at different speeds
    const hud = new THREE.Group();
    hud.rotation.x = -0.32;
    root.add(hud);
    const hudMats: THREE.MeshBasicMaterial[] = [];
    const ring = (tex: THREE.Texture, size: number, opacity: number) => {
      const m = new THREE.MeshBasicMaterial({ map: tex, color: col.c2, ...add, opacity, side: THREE.DoubleSide });
      hudMats.push(m);
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), m);
      hud.add(mesh);
      return mesh;
    };
    const textures = [hudTexture(TICKS), hudTexture(ARCS), hudTexture(LABELS)];
    const rTicks = ring(textures[0], 3.5, 0.45);
    const rArcs = ring(textures[1], 3.0, 0.55);
    const rLabels = ring(textures[2], 4.05, 0.5);

    // voice spectrum ring: radial bars whose length follows the sound
    const BARS = 120;
    const barPos = new Float32Array(BARS * 6);
    const barGeo = new THREE.BufferGeometry();
    barGeo.setAttribute("position", new THREE.BufferAttribute(barPos, 3));
    const barMat = new THREE.LineBasicMaterial({ color: col.c2, ...add, opacity: 0.75 });
    const bars = new THREE.LineSegments(barGeo, barMat);
    hud.add(bars);
    const barSeed = Array.from({ length: BARS }, () => Math.random());

    // shockwaves on scene cues
    const waves = Array.from({ length: 4 }, () => {
      const m = new THREE.MeshBasicMaterial({ color: col.c2, ...add, opacity: 0, side: THREE.DoubleSide });
      const w = new THREE.Mesh(new THREE.RingGeometry(0.98, 1, 128), m);
      w.userData.t = -1;
      hud.add(w);
      return w;
    });
    let lastCue = signals.current.cue, nextWave = 0;

    // bloom
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.55, 0.45, 0.12);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());
    composer.addPass(new ShaderPass(LIGHT_ALPHA));

    const resize = () => {
      const w = Math.max(el.clientWidth, 1), h = Math.max(el.clientHeight, 1);
      renderer.setSize(w, h, false);
      composer.setSize(w, h);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = w / h;
      // distance at which the HUD (radius ≈ 2.1) fits the shorter side
      dist = FIT_RADIUS / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / Math.min(1, camera.aspect);
      camera.position.z = dist;
      camera.updateProjectionMatrix();
      u.uPx.value = (dpr * Math.min(w, h)) / 330 * (dist / 4.6);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    const mouse = { x: 0, y: 0 };
    const onMove = (e: PointerEvent) => {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener("pointermove", onMove);

    const clock = new THREE.Clock();
    let level = 0, low = 0, high = 0, raf = 0, think = 0;
    const loop = () => {
      const dt = Math.min(clock.getDelta(), 0.05);
      const t = clock.elapsedTime;
      const s = signals.current;
      // target loudness by state (real sound when there is an analyser)
      let target: number;
      if (s.mode === "listen") target = Math.min(1, s.mic * 4.5);
      else if (s.mode === "speak" && s.voice >= 0) target = Math.min(0.8, 0.1 + s.voice * 2.2);
      else if (s.mode === "speak") {
        s.spike *= 0.9;
        target = Math.min(1, 0.22 + 0.28 * Math.abs(Math.sin(t * 7.3)) * Math.abs(Math.sin(t * 2.1 + 1)) + s.spike);
      } else if (s.mode === "think") target = 0.2 + 0.07 * Math.sin(t * 5);
      else target = 0.05 + 0.03 * Math.sin(t * 1.3);
      level += (target - level) * (target > level ? 0.3 : 0.07);
      const hasBands = bands.level > 0.001;
      const tl = hasBands ? Math.min(1, bands.low * 2.2) : level * 0.8;
      const th = hasBands ? Math.min(1, bands.high * 4) : (s.mode === "speak" ? s.spike : 0) * 0.8;
      low += (tl - low) * 0.25; high += (th - high) * 0.3;
      think += ((s.mode === "think" ? 1 : 0) - think) * (s.mode === "think" ? 0.025 : 0.06);

      // palette follows the state
      const pal = PALETTES[s.mode];
      col.c1.lerp(pal[0], 0.04); col.c2.lerp(pal[1], 0.04); col.c3.lerp(pal[2], 0.04);

      u.uTime.value = t; u.uAmp.value = level; u.uLow.value = low; u.uHigh.value = high;
      u.uThink.value = think;

      const sp = reduced ? 0.3 : 1;
      shell.rotation.y = t * 0.1 * sp + think * t * 0.25 * sp;
      core.rotation.y = -t * 0.15 * sp; core.rotation.x = Math.sin(t * 0.3) * 0.2;
      core.scale.setScalar(1 + level * 0.07 + low * 0.06);
      halo.scale.setScalar(2.7 + level * 0.9);
      (halo.material as THREE.SpriteMaterial).opacity = 0.22 + level * 0.3;

      rTicks.rotation.z = t * 0.05 * sp;
      rArcs.rotation.z = -t * (0.12 + level * 0.5 + think * 0.6) * sp;
      rLabels.rotation.z = t * 0.025 * sp;
      hudMats[0].opacity = 0.32 + level * 0.3;
      hudMats[1].opacity = 0.4 + level * 0.45 + think * 0.25;
      hudMats[2].opacity = 0.32 + think * 0.3;
      hud.rotation.z = Math.sin(t * 0.15) * 0.05;

      // spectrum bars
      for (let i = 0; i < BARS; i++) {
        const a = (i / BARS) * Math.PI * 2 + t * 0.08 * sp;
        const wave = 0.5 + 0.5 * Math.sin(a * 3 + t * 4) * Math.sin(a * 5 - t * 3);
        const amp = (low * 0.6 + high * 0.8 * barSeed[i] + level * 0.5) * wave;
        const r0 = 1.22, r1 = r0 + 0.02 + amp * 0.32;
        barPos.set([Math.cos(a) * r0, Math.sin(a) * r0, 0, Math.cos(a) * r1, Math.sin(a) * r1, 0], i * 6);
      }
      barGeo.attributes.position.needsUpdate = true;
      barMat.opacity = 0.25 + level * 0.7;

      // shockwaves
      if (s.cue !== lastCue) {
        lastCue = s.cue;
        waves[nextWave].userData.t = 0;
        nextWave = (nextWave + 1) % waves.length;
      }
      for (const w of waves) {
        if (w.userData.t < 0) continue;
        w.userData.t += dt / 1.3;
        const k = w.userData.t;
        if (k >= 1) { w.userData.t = -1; (w.material as THREE.MeshBasicMaterial).opacity = 0; continue; }
        w.scale.setScalar(0.7 + k * 1.6);
        (w.material as THREE.MeshBasicMaterial).opacity = (1 - k) * 0.85;
      }

      // light parallax with the pointer
      camera.position.x += (mouse.x * 0.35 - camera.position.x) * 0.04;
      camera.position.y += (-mouse.y * 0.25 - camera.position.y) * 0.04;
      camera.lookAt(0, 0, 0);

      bloom.strength = 0.5 + level * 0.45;
      composer.render();
      raf = requestAnimationFrame(loop);
    };
    loop();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onMove);
      composer.dispose();
      renderer.dispose();
      [coreGeo, shellGeo, barGeo].forEach((g) => g.dispose());
      [coreMat, shellMat, barMat, ...hudMats].forEach((m) => m.dispose());
      [radial, ...textures].forEach((x) => x.dispose());
      waves.forEach((w) => { w.geometry.dispose(); (w.material as THREE.Material).dispose(); });
      el.removeChild(renderer.domElement);
    };
  }, [signals]);

  return <div ref={host} className="orb" aria-hidden />;
}
