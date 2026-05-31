"use client";

import { useEffect, useState } from "react";
import {
    Cloud,
    Umbrella,
    Thermometer,
    Wind,
    ThermometerSun,
    Droplets,
    Sunrise,
    Gauge
} from "lucide-react";

import BentoWidget from "./BentoWidget";
import { useAppStore, WeatherData } from "../store/index";

export default function WeatherWidget() {
    const setWeatherData = useAppStore((state) => state.setWeatherData);

    const [weather, setWeather] = useState<WeatherData | null>(null);

    useEffect(() => {
        async function fetchWeather() {
            try {
                const res = await fetch(
                    "https://api.open-meteo.com/v1/forecast?latitude=41.9028&longitude=12.4964&current=temperature_2m,relative_humidity_2m,apparent_temperature,surface_pressure,weather_code,wind_speed_10m&hourly=weather_code&daily=temperature_2m_max,temperature_2m_min,sunrise&timezone=auto"
                );

                const data = await res.json();

                const getCondition = (code: number) => {
                    if (code >= 1 && code <= 3) return "Cloudy";
                    if (code >= 45 && code <= 48) return "Fog";
                    if (code >= 51 && code <= 67) return "Rain";
                    if (code >= 71 && code <= 77) return "Snow";
                    if (code >= 95) return "Thunderstorm";
                    return "Clear";
                };

                const condition = getCondition(data.current.weather_code);

                const currentHour = new Date().getHours();
                const startIndex = data.hourly.time.findIndex(
                    (t: string) => new Date(t).getHours() === currentHour
                );

                let rainExpected = false;

                if (startIndex !== -1) {
                    for (let i = 1; i <= 4; i++) {
                        const code = data.hourly.weather_code[startIndex + i];
                        if ((code >= 51 && code <= 67) || (code >= 80 && code <= 99)) {
                            rainExpected = true;
                            break;
                        }
                    }
                }

                const sunriseTime = new Date(
                    data.daily.sunrise[0]
                ).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit"
                });

                const weatherState: WeatherData = {
                    city: "Rome",
                    temperature: `${Math.round(data.current.temperature_2m)}°`,
                    condition,
                    tempMax: `${Math.round(data.daily.temperature_2m_max[0])}°`,
                    tempMin: `${Math.round(data.daily.temperature_2m_min[0])}°`,
                    wind: `${Math.round(data.current.wind_speed_10m)} km/h`,
                    humidity: `${data.current.relative_humidity_2m}%`,
                    feelsLike: `${Math.round(data.current.apparent_temperature)}°`,
                    pressure: `${Math.round(data.current.surface_pressure)} hPa`,
                    sunrise: sunriseTime,
                    willRain: rainExpected
                };

                setWeather(weatherState);
                setWeatherData(weatherState); // 🔥 ORA OGGETTO COMPLETO
            } catch (err) {
                console.error("Telemetry fetch fault:", err);
            }
        }

        fetchWeather();
        const interval = setInterval(fetchWeather, 30000);

        return () => clearInterval(interval);
    }, [setWeatherData]);

    return (
        <BentoWidget
            title="Atmosphere"
            icon={Cloud}
            colorKey="cyan"
            colSpan={2}
            textSize="text-6xl"
            isLoading={!weather}
            mainText={weather?.temperature}
            subTextLeft={weather?.city}
            subTextRight={weather?.condition}
        >
            {weather && (
                <div className="w-full mt-auto relative">
                    {weather.willRain && (
                        <div className="absolute -top-12 right-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-[9px] font-bold uppercase tracking-widest text-cyan-600 dark:text-cyan-400 animate-pulse">
                            <Umbrella className="w-3 h-3" />
                            Rain Expected
                        </div>
                    )}

                    <div className="pt-4 mt-3 border-t grid grid-cols-3 gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-cyan-600/70">
                        <div className="flex flex-col gap-3">
                            <span className="flex items-center gap-2">
                                <Thermometer className="w-3.5 h-3.5" />
                                {weather.tempMin}/{weather.tempMax}
                            </span>
                            <span className="flex items-center gap-2">
                                <Wind className="w-3.5 h-3.5" />
                                {weather.wind}
                            </span>
                        </div>

                        <div className="flex flex-col gap-3">
                            <span className="flex items-center gap-2">
                                <ThermometerSun className="w-3.5 h-3.5" />
                                Feels {weather.feelsLike}
                            </span>
                            <span className="flex items-center gap-2">
                                <Droplets className="w-3.5 h-3.5" />
                                {weather.humidity}
                            </span>
                        </div>

                        <div className="flex flex-col gap-3">
                            <span className="flex items-center gap-2">
                                <Sunrise className="w-3.5 h-3.5" />
                                {weather.sunrise}
                            </span>
                            <span className="flex items-center gap-2">
                                <Gauge className="w-3.5 h-3.5" />
                                {weather.pressure}
                            </span>
                        </div>
                    </div>
                </div>
            )}
        </BentoWidget>
    );
}