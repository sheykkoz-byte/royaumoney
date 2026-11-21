"use client";

// The voice orb from prototype/index.html: 7,000 particles on a sphere that swell with the
// real audio level (microphone) or with the spoken words (Jarvis).
import { useEffect, useRef } from "react";
import * as THREE from "three";

export type OrbMode = "idle" | "listen" | "think" | "speak";

export type OrbSignals = { mode: OrbMode; mic: number; spike: number };

export default function Orb({ signals }: { signals: React.MutableRefObject<OrbSignals> }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.z = 4.2;

    const N = 7000;
    const pos = new Float32Array(N * 3);
    const rnd = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), th = i * 2.399963;
      pos[i * 3] = Math.cos(th) * r; pos[i * 3 + 1] = y; pos[i * 3 + 2] = Math.sin(th) * r;
      rnd[i] = Math.random();
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aRnd", new THREE.BufferAttribute(rnd, 1));
    const uni = { uTime: { value: 0 }, uAmp: { value: 0 }, uMode: { value: 0 } };
    const mat = new THREE.ShaderMaterial({
      uniforms: uni, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: `
        uniform float uTime; uniform float uAmp; attribute float aRnd; varying float vGlow; varying float vY;
        float n3(vec3 p){ return sin(p.x*3.1+uTime*1.1)*sin(p.y*3.7+uTime*1.3)*sin(p.z*2.9+uTime*.9); }
        void main(){
          vec3 p = position;
          float n = n3(p*1.4) + .5*n3(p*3.2+4.);
          float d = .04 + n*(.05 + uAmp*.38) + aRnd*uAmp*.08;
          p *= 1. + d;
          vGlow = .45 + n*.5 + uAmp*.6; vY = position.y;
          vec4 mv = modelViewMatrix*vec4(p,1.);
          gl_PointSize = (1.6 + aRnd*1.8 + uAmp*2.2) * (3.2/ -mv.z) * 1.6;
          gl_Position = projectionMatrix*mv;
        }`,
      fragmentShader: `
        uniform float uMode; varying float vGlow; varying float vY;
        void main(){
          float d = length(gl_PointCoord-.5); if(d>.5) discard;
          float a = smoothstep(.5,0.,d);
          vec3 violet = vec3(.55,.48,1.), cyan = vec3(.37,.88,1.), pink = vec3(.95,.45,1.);
          vec3 c = mix(violet, cyan, smoothstep(-1.,1.,vY));
          c = mix(c, pink, clamp(uMode,0.,1.)*.25*(1.-vY));
          gl_FragColor = vec4(c*vGlow, a*.85);
        }`,
    });
    const sphere = new THREE.Points(geo, mat);
    scene.add(sphere);

    const cv = document.createElement("canvas");
    cv.width = cv.height = 128;
    const g = cv.getContext("2d")!;
    const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, "rgba(200,190,255,.9)"); gr.addColorStop(0.3, "rgba(130,110,255,.35)"); gr.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
    const core = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(cv), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    core.scale.set(2.2, 2.2, 1);
    scene.add(core);

    const rings: THREE.Mesh[] = [];
    ([[1.55, 0.0025, 0.35], [1.75, 0.0015, 0.18], [1.95, 0.002, 0.1]] as const).forEach(([r, w, o], i) => {
      const m = new THREE.Mesh(
        new THREE.RingGeometry(r, r + w * 6, 160, 1, 0, Math.PI * (1.2 + i * 0.35)),
        new THREE.MeshBasicMaterial({ color: i % 2 ? 0x5fe1ff : 0x8b7cff, transparent: true, opacity: o, side: THREE.DoubleSide }),
      );
      m.rotation.x = 1.15 + i * 0.12; m.rotation.y = i * 0.4;
      scene.add(m); rings.push(m);
    });

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = w / Math.max(h, 1);
      camera.position.z = w < 520 ? 5.2 : 4.2;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    const clock = new THREE.Clock();
    let level = 0, raf = 0;
    const loop = () => {
      const t = clock.getElapsedTime();
      const s = signals.current;
      let target: number;
      if (s.mode === "listen") target = Math.min(1, s.mic * 4.5);
      else if (s.mode === "speak") {
        s.spike *= 0.9;
        target = Math.min(1, 0.22 + 0.28 * Math.abs(Math.sin(t * 7.3)) * Math.abs(Math.sin(t * 2.1 + 1)) + s.spike);
      } else if (s.mode === "think") target = 0.18 + 0.08 * Math.sin(t * 6);
      else target = 0.04 + 0.03 * Math.sin(t * 1.4);
      level += (target - level) * (target > level ? 0.35 : 0.08);
      uni.uTime.value = t; uni.uAmp.value = level;
      uni.uMode.value += ((s.mode === "speak" ? 1 : 0) - uni.uMode.value) * 0.05;
      sphere.rotation.y = t * 0.12; sphere.rotation.x = Math.sin(t * 0.2) * 0.15;
      const sc = 1 + level * 0.12; sphere.scale.set(sc, sc, sc);
      (core.material as THREE.SpriteMaterial).opacity = 0.55 + level * 0.6;
      core.scale.setScalar(2.2 + level * 1.1);
      rings.forEach((r, i) => {
        r.rotation.z = t * (i % 2 ? -0.25 : 0.18) * (1 + level * 2);
        (r.material as THREE.MeshBasicMaterial).opacity = [0.35, 0.18, 0.1][i] + level * 0.3;
      });
      renderer.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    loop();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      geo.dispose();
      mat.dispose();
      el.removeChild(renderer.domElement);
    };
  }, [signals]);

  return <div ref={host} className="orb" aria-hidden />;
}
