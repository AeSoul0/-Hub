/**
 * @file frontend/src/components/nucleo/Orb.tsx
 * @description The sphere at the centre of the Nucleo (F1).
 *
 * A dotted Fibonacci sphere on a 2D canvas, after the thinking-orbs idea
 * (MIT): each mode moves it differently. Listening rolls a wave through
 * its rings with the microphone level, speaking swells it with the reply's
 * level, thinking adds orbits, a tool call sweeps a scan meridian, an
 * approval turns it amber inside a dashed ring, and every subagent is a
 * small moon. Every event leaves a spark towards the log.
 */
"use client";

import { useEffect, useRef } from "react";

import type { Moon, OrbMode } from "@/lib/nucleo/engine";

interface Params {
    spin: number;
    listen: number;
    speak: number;
    think: number;
    scan: number;
    approve: number;
    scale: number;
    glow: number;
}

const MODES: Record<OrbMode, Params> = {
    idle: { spin: 0.14, listen: 0, speak: 0, think: 0, scan: 0, approve: 0, scale: 1, glow: 0.25 },
    listening: { spin: 0.08, listen: 1, speak: 0, think: 0, scan: 0, approve: 0, scale: 1.04, glow: 0.7 },
    thinking: { spin: 0.55, listen: 0, speak: 0, think: 1, scan: 0, approve: 0, scale: 0.97, glow: 0.55 },
    tool: { spin: 0.32, listen: 0, speak: 0, think: 0.45, scan: 1, approve: 0, scale: 1, glow: 0.6 },
    approval: { spin: 0.04, listen: 0, speak: 0, think: 0, scan: 0, approve: 1, scale: 0.9, glow: 0.35 },
    speaking: { spin: 0.2, listen: 0, speak: 1, think: 0, scan: 0, approve: 0, scale: 1.02, glow: 0.8 },
};

const N = 1300;
const MINI = 90;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

// Fibonacci lattice: x, y, z, latitude, seed (seeded, so renders repeat).
function lattice(count: number, stride: number): Float32Array {
    const points = new Float32Array(count * stride);
    let seed = 7;
    for (let i = 0; i < count; i++) {
        const y = 1 - (2 * (i + 0.5)) / count;
        const r = Math.sqrt(1 - y * y);
        const phi = i * GOLDEN;
        seed = (seed * 16807) % 2147483647;
        points.set([Math.cos(phi) * r, y, Math.sin(phi) * r, Math.asin(y), seed / 2147483647].slice(0, stride), i * stride);
    }
    return points;
}

function rgb(hex: string): [number, number, number] {
    const n = parseInt(hex.replace("#", ""), 16);
    return [n >> 16, (n >> 8) & 255, n & 255];
}

const wrap = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));

interface Satellite {
    id: string;
    label: string;
    a0: number;
    speed: number;
    tilt: number;
    life: number;
    dying: boolean;
    spin: number;
}

interface Spark {
    a: number;
    d: number;
    v: number;
    life: number;
    amber: boolean;
}

export interface OrbProps {
    mode: OrbMode;
    moons: Moon[];
    /** Current audio level, 0..1 (microphone or reply). */
    level: () => number;
    /** Increment to send a spark towards the log; `amber` for approvals. */
    spark: { count: number; amber: boolean };
}

export default function Orb({ mode, moons, level, spark }: OrbProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const latest = useRef({ mode, moons, level, spark });

    useEffect(() => {
        latest.current = { mode, moons, level, spark };
    });

    useEffect(() => {
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext("2d");
        if (!canvas || !ctx) {
            return;
        }

        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const css = getComputedStyle(document.documentElement);
        const token = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
        const COLORS = [token("--ink", "#dce6ff"), token("--ice", "#8fb8ff"), token("--amber", "#f2b54c")];
        const VOID = token("--void", "#030714");
        const ICE = rgb(COLORS[1]);
        const AMBER = rgb(COLORS[2]);
        const MONO = token("--font-code", "monospace");

        const P = lattice(N, 5);
        const M = lattice(MINI, 3);

        let width = 0;
        let height = 0;
        const resize = () => {
            const rect = canvas.getBoundingClientRect();
            const dpr = Math.min(2, window.devicePixelRatio || 1);
            width = rect.width;
            height = rect.height;
            canvas.width = Math.max(1, Math.round(width * dpr));
            canvas.height = Math.max(1, Math.round(height * dpr));
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        };
        const observer = new ResizeObserver(resize);
        observer.observe(canvas);
        resize();

        const S: Params = { ...MODES[latest.current.mode] };
        const sats: Satellite[] = [];
        const sparks: Spark[] = [];
        let sparkSeen = latest.current.spark.count;
        let t = 0;
        let rot = 0;
        let lvl = 0;
        let last = performance.now();
        let frame = 0;

        const syncMoons = (moonList: Moon[]) => {
            for (const moon of moonList) {
                if (!sats.some((sat) => sat.id === moon.id && !sat.dying)) {
                    const previous = sats[sats.length - 1];
                    sats.push({
                        id: moon.id,
                        label: moon.label,
                        a0: previous ? previous.a0 + Math.PI : Math.random() * Math.PI * 2,
                        speed: 0.3 + Math.random() * 0.15,
                        tilt: (sats.length % 2 ? -1 : 1) * (0.75 + Math.random() * 0.3),
                        life: 0,
                        dying: false,
                        spin: 0,
                    });
                }
            }
            for (const sat of sats) {
                if (!moonList.some((moon) => moon.id === sat.id)) {
                    sat.dying = true;
                }
            }
        };

        const draw = (now: number) => {
            const dt = Math.min(0.05, (now - last) / 1000);
            last = now;
            const speed = reduce ? 0.35 : 1;
            t += dt * speed;

            const props = latest.current;
            const target = MODES[props.mode];
            const k = 1 - Math.exp(-dt * 3.5);
            for (const key of Object.keys(S) as (keyof Params)[]) {
                S[key] += (target[key] - S[key]) * k;
            }
            const wantLevel = props.mode === "listening" || props.mode === "speaking" ? props.level() : 0;
            lvl += (wantLevel - lvl) * (1 - Math.exp(-dt * 16));
            rot += dt * S.spin * speed;
            syncMoons(props.moons);
            if (props.spark.count !== sparkSeen) {
                sparkSeen = props.spark.count;
                sparks.push({ a: (Math.random() - 0.5) * 0.9, d: 1.05, v: 1.6 + Math.random(), life: 1, amber: props.spark.amber });
            }

            ctx.clearRect(0, 0, width, height);
            const cx = width / 2;
            const cy = height * 0.47;
            const R = Math.min(width, height) * 0.29 * S.scale * (1 + 0.018 * Math.sin(t * 1.2));
            const dotBase = Math.max(0.75, R / 165);

            // halo
            const halo = S.approve > 0.5 ? AMBER : ICE;
            const g = ctx.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * 2);
            g.addColorStop(0, `rgba(${halo[0]},${halo[1]},${halo[2]},${0.05 + 0.08 * S.glow + 0.14 * lvl})`);
            g.addColorStop(1, "rgba(0,0,0,0)");
            ctx.fillStyle = g;
            ctx.fillRect(0, 0, width, height);

            // bearing ring: a tick every 6°, a long one every 30°
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(-rot * 0.15);
            ctx.strokeStyle = COLORS[0];
            ctx.globalAlpha = 0.12;
            ctx.lineWidth = 1;
            ctx.beginPath();
            const rr = R * 1.42;
            for (let i = 0; i < 60; i++) {
                const a = (i / 60) * Math.PI * 2;
                const l = i % 5 === 0 ? 9 : 4;
                ctx.moveTo(Math.cos(a) * rr, Math.sin(a) * rr);
                ctx.lineTo(Math.cos(a) * (rr + l), Math.sin(a) * (rr + l));
            }
            ctx.stroke();
            ctx.restore();
            ctx.globalAlpha = 1;

            // approval ring
            if (S.approve > 0.02) {
                ctx.save();
                ctx.translate(cx, cy);
                ctx.strokeStyle = COLORS[2];
                ctx.lineWidth = 1;
                ctx.globalAlpha = S.approve * (0.45 + 0.35 * Math.sin(t * 4));
                ctx.setLineDash([2, 7]);
                ctx.lineDashOffset = -t * 18;
                ctx.beginPath();
                ctx.arc(0, 0, R * 1.22, 0, Math.PI * 2);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.globalAlpha = S.approve * 0.5;
                ctx.beginPath();
                ctx.arc(0, 0, R * 1.22, -Math.PI / 2, -Math.PI / 2 + ((t * 0.6) % 1) * Math.PI * 2);
                ctx.stroke();
                ctx.restore();
                ctx.globalAlpha = 1;
            }

            // dots go into 3 colours x 6 alpha buckets, one fill each
            const buckets = () => Array.from({ length: 18 }, () => new Path2D());
            const flush = (B: Path2D[]) => {
                for (let c = 0; c < 3; c++) {
                    ctx.fillStyle = COLORS[c];
                    for (let al = 0; al < 6; al++) {
                        ctx.globalAlpha = (al + 0.6) / 6;
                        ctx.fill(B[c * 6 + al]);
                    }
                }
                ctx.globalAlpha = 1;
            };
            const put = (B: Path2D[], c: number, a: number, x: number, y: number, r: number) => {
                const al = Math.max(0, Math.min(5, Math.floor(a * 6)));
                B[c * 6 + al].moveTo(x + r, y);
                B[c * 6 + al].arc(x, y, r, 0, Math.PI * 2);
            };

            const B = buckets();
            const tilt = 0.36 + 0.05 * Math.sin(t * 0.3);
            const ct = Math.cos(tilt);
            const st = Math.sin(tilt);
            const cr = Math.cos(rot);
            const sr = Math.sin(rot);
            const scanAngle = wrap(t * 1.7);
            for (let i = 0; i < N; i++) {
                const o = i * 5;
                const lat = P[o + 3];
                const seed = P[o + 4];
                let d = 1;
                d += S.listen * lvl * 0.2 * Math.sin(lat * 7 - t * 6.5);
                d += S.speak * lvl * (0.09 + 0.08 * Math.sin(seed * 40 + t * 9));
                d += S.think * 0.03 * Math.sin(seed * 60 + t * 4);
                const x = P[o] * d;
                const y = P[o + 1] * d;
                const z = P[o + 2] * d;
                const x1 = x * cr + z * sr;
                const z1 = -x * sr + z * cr;
                const y1 = y * ct - z1 * st;
                const z2 = y * st + z1 * ct;
                const depth = (z2 / d + 1) / 2;
                let a = 0.06 + 0.94 * depth * depth;
                let c = 0;
                if (S.scan > 0.05 && depth > 0.35 && Math.abs(wrap(Math.atan2(x1, z2) - scanAngle)) < 0.28 * S.scan) {
                    c = 1;
                    a = Math.min(1, a + 0.35);
                }
                if (S.approve > 0.05 && seed < S.approve * 0.55) {
                    c = 2;
                }
                put(B, c, a, cx + x1 * R, cy + y1 * R, (0.45 + 1.2 * depth) * dotBase);
            }

            // thinking: three tilted orbits
            if (S.think > 0.03) {
                for (let j = 0; j < 3; j++) {
                    const ta = 0.9 + j * 0.7;
                    const ca = Math.cos(ta);
                    const sa = Math.sin(ta);
                    const tz = j * 2.1;
                    const cz = Math.cos(tz);
                    const sz = Math.sin(tz);
                    for (let q = 0; q < 46; q += 3) {
                        const ang = (q / 46) * Math.PI * 2 + t * (0.7 + j * 0.25) * (j % 2 ? -1 : 1);
                        const x = Math.cos(ang) * 1.3;
                        const z = Math.sin(ang) * 1.3;
                        const y2 = -z * sa;
                        const z2 = z * ca;
                        const x3 = x * cz - y2 * sz;
                        const y3 = x * sz + y2 * cz;
                        const depth = (z2 / 1.3 + 1) / 2;
                        put(B, 1, S.think * (0.15 + 0.85 * depth), cx + x3 * R, cy + y3 * R, (0.6 + depth) * dotBase);
                    }
                }
            }
            flush(B);

            // moons: one per subagent, drawn over the sphere
            ctx.lineWidth = 1;
            for (let s = sats.length - 1; s >= 0; s--) {
                const sat = sats[s];
                sat.life += ((sat.dying ? 0 : 1) - sat.life) * Math.min(1, dt * 3);
                if (sat.dying && sat.life < 0.02) {
                    sats.splice(s, 1);
                    continue;
                }
                sat.spin += dt * 1.2;
                const ang = sat.a0 + t * sat.speed;
                const ox = Math.cos(ang) * 1.75;
                const oy = Math.sin(ang) * sat.tilt;
                const sx = cx + ox * R;
                const sy = cy + oy * R;
                const radius = R * 0.17 * sat.life;
                const norm = Math.hypot(ox, oy) || 1;

                ctx.strokeStyle = `rgba(${ICE[0]},${ICE[1]},${ICE[2]},${0.2 * sat.life})`;
                ctx.setLineDash([1, 4]);
                ctx.beginPath();
                ctx.moveTo(cx + (ox / norm) * R * 1.02, cy + (oy / norm) * R * 1.02);
                ctx.lineTo(sx, sy);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.strokeStyle = `rgba(${ICE[0]},${ICE[1]},${ICE[2]},${0.45 * sat.life})`;
                ctx.beginPath();
                ctx.arc(sx, sy, radius * 1.45, t * 2, t * 2 + Math.PI * 1.4);
                ctx.stroke();

                ctx.fillStyle = VOID;
                ctx.globalAlpha = 0.85 * sat.life;
                ctx.beginPath();
                ctx.arc(sx, sy, radius * 1.1, 0, Math.PI * 2);
                ctx.fill();
                ctx.globalAlpha = 1;

                const MB = buckets();
                const c1 = Math.cos(sat.spin);
                const s1 = Math.sin(sat.spin);
                for (let i = 0; i < MINI; i++) {
                    const mx = M[i * 3];
                    const my = M[i * 3 + 1];
                    const mz = M[i * 3 + 2];
                    const x1 = mx * c1 + mz * s1;
                    const depth = (-mx * s1 + mz * c1 + 1) / 2;
                    put(MB, 1, sat.life * (0.15 + 0.85 * depth), sx + x1 * radius, sy + my * radius, (0.5 + 0.8 * depth) * dotBase);
                }
                flush(MB);

                ctx.globalAlpha = 0.75 * sat.life;
                ctx.fillStyle = COLORS[0];
                ctx.font = `10px ${MONO}`;
                ctx.textAlign = "center";
                ctx.fillText(sat.label, Math.max(90, Math.min(width - 90, sx)), sy + radius * 1.45 + 16);
                ctx.textAlign = "left";
                ctx.globalAlpha = 1;
            }

            // sparks: an event leaves the core towards the log
            for (let i = sparks.length - 1; i >= 0; i--) {
                const p = sparks[i];
                p.d += dt * p.v;
                p.life -= dt * 0.9;
                if (p.life <= 0 || cx + Math.cos(p.a) * p.d * R > width) {
                    sparks.splice(i, 1);
                    continue;
                }
                const color = p.amber ? AMBER : ICE;
                const x0 = cx + Math.cos(p.a) * (p.d - 0.35) * R;
                const y0 = cy + Math.sin(p.a) * (p.d - 0.35) * R;
                const x1 = cx + Math.cos(p.a) * p.d * R;
                const y1 = cy + Math.sin(p.a) * p.d * R;
                const trail = ctx.createLinearGradient(x0, y0, x1, y1);
                trail.addColorStop(0, "rgba(0,0,0,0)");
                trail.addColorStop(1, `rgba(${color[0]},${color[1]},${color[2]},${p.life})`);
                ctx.strokeStyle = trail;
                ctx.lineWidth = 1.2;
                ctx.beginPath();
                ctx.moveTo(x0, y0);
                ctx.lineTo(x1, y1);
                ctx.stroke();
            }

            frame = requestAnimationFrame(draw);
        };

        frame = requestAnimationFrame(draw);

        return () => {
            cancelAnimationFrame(frame);
            observer.disconnect();
        };
    }, []);

    return <canvas ref={canvasRef} aria-hidden="true" className="absolute inset-0 block h-full w-full" />;
}
