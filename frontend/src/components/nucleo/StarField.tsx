/**
 * @file frontend/src/components/nucleo/StarField.tsx
 * @description The sky behind every page: stars in three slow layers, a
 * faint nebula and, now and then, a shooting star. Still under
 * prefers-reduced-motion.
 */
"use client";

import { useEffect, useRef } from "react";

interface Star {
    x: number;
    y: number;
    layer: 0 | 1 | 2;
    r: number;
    a: number;
    twinkle: number;
    phase: number;
    warm: boolean;
}

const DRIFT = [1.2, 2.4, 4]; // px per second, per layer
const STAR_COLORS = ["#c9d8ff", "#c9d8ff", "#ffffff"];

function rgb(hex: string): [number, number, number] {
    const n = parseInt(hex.replace("#", ""), 16);
    return [n >> 16, (n >> 8) & 255, n & 255];
}

export default function StarField() {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext("2d");
        if (!canvas || !ctx) {
            return;
        }

        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const css = getComputedStyle(document.documentElement);
        const token = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;

        let width = 0;
        let height = 0;
        let stars: Star[] = [];
        let nebula: HTMLCanvasElement | null = null;

        const build = () => {
            const dpr = Math.min(2, window.devicePixelRatio || 1);
            width = window.innerWidth;
            height = window.innerHeight;
            canvas.width = Math.round(width * dpr);
            canvas.height = Math.round(height * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

            const count = Math.min(460, Math.round((width * height) / 4200));
            stars = Array.from({ length: count }, () => {
                const layer: Star["layer"] = Math.random() < 0.7 ? 0 : Math.random() < 0.75 ? 1 : 2;
                return {
                    x: Math.random(),
                    y: Math.random(),
                    layer,
                    r: [0.45, 0.8, 1.25][layer] * (0.7 + Math.random() * 0.6),
                    a: [0.35, 0.55, 0.85][layer] * (0.6 + Math.random() * 0.4),
                    twinkle: 0.6 + Math.random() * 2.2,
                    phase: Math.random() * Math.PI * 2,
                    warm: Math.random() < 0.08,
                };
            });

            nebula = document.createElement("canvas");
            nebula.width = Math.max(1, Math.round(width / 2));
            nebula.height = Math.max(1, Math.round(height / 2));
            const nc = nebula.getContext("2d");
            if (nc) {
                const blue = rgb(token("--nebula", "#3b4fd0"));
                const violet = rgb(token("--violet", "#6a4bc4"));
                const clouds: [number, number, number, [number, number, number], number][] = [
                    [0.78, 0.22, 0.55, blue, 0.1],
                    [0.18, 0.78, 0.5, violet, 0.08],
                    [0.5, 0.5, 0.35, blue, 0.05],
                ];
                for (const [x, y, r, c, a] of clouds) {
                    const g = nc.createRadialGradient(
                        x * nebula.width,
                        y * nebula.height,
                        0,
                        x * nebula.width,
                        y * nebula.height,
                        r * Math.max(nebula.width, nebula.height),
                    );
                    g.addColorStop(0, `rgba(${c[0]},${c[1]},${c[2]},${a})`);
                    g.addColorStop(1, "rgba(0,0,0,0)");
                    nc.fillStyle = g;
                    nc.fillRect(0, 0, nebula.width, nebula.height);
                }
            }
        };

        build();
        window.addEventListener("resize", build);

        let t = 0;
        let last = performance.now();
        let frame = 0;
        let nextShoot = 6;
        let shoot: { x: number; y: number; angle: number; life: number } | null = null;

        const draw = (now: number) => {
            const dt = Math.min(0.05, (now - last) / 1000);
            last = now;
            t += dt;

            ctx.clearRect(0, 0, width, height);
            if (nebula) {
                ctx.drawImage(nebula, 0, 0, width, height);
            }

            const drift = reduce ? 0 : t;
            for (const star of stars) {
                const x = (((star.x * width - drift * DRIFT[star.layer]) % width) + width) % width;
                ctx.globalAlpha = reduce ? star.a : star.a * (0.65 + 0.35 * Math.sin(t * star.twinkle + star.phase));
                ctx.fillStyle = star.warm ? "#ffe2b8" : STAR_COLORS[star.layer];
                ctx.beginPath();
                ctx.arc(x, star.y * height, star.r, 0, Math.PI * 2);
                ctx.fill();
            }

            if (!reduce) {
                if (!shoot && t > nextShoot) {
                    shoot = {
                        x: width * (0.15 + Math.random() * 0.7),
                        y: height * (0.05 + Math.random() * 0.3),
                        angle: 0.45 + Math.random() * 0.25,
                        life: 1,
                    };
                    nextShoot = t + 14 + Math.random() * 20;
                }
                if (shoot) {
                    shoot.life -= dt * 1.1;
                    const progress = 1 - shoot.life;
                    const length = 120;
                    const hx = shoot.x + Math.cos(shoot.angle) * progress * 420;
                    const hy = shoot.y + Math.sin(shoot.angle) * progress * 420;
                    const tx = hx - Math.cos(shoot.angle) * length;
                    const ty = hy - Math.sin(shoot.angle) * length;
                    const g = ctx.createLinearGradient(tx, ty, hx, hy);
                    g.addColorStop(0, "rgba(201,216,255,0)");
                    g.addColorStop(1, `rgba(220,230,255,${Math.max(0, shoot.life) * 0.8})`);
                    ctx.globalAlpha = 1;
                    ctx.strokeStyle = g;
                    ctx.lineWidth = 1.2;
                    ctx.beginPath();
                    ctx.moveTo(tx, ty);
                    ctx.lineTo(hx, hy);
                    ctx.stroke();
                    if (shoot.life <= 0) {
                        shoot = null;
                    }
                }
            }

            ctx.globalAlpha = 1;
            frame = requestAnimationFrame(draw);
        };

        frame = requestAnimationFrame(draw);

        return () => {
            cancelAnimationFrame(frame);
            window.removeEventListener("resize", build);
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            aria-hidden="true"
            className="pointer-events-none fixed inset-0 z-0 h-full w-full"
        />
    );
}
