import { create } from "zustand";

// ==============================================================================
// WEATHER TYPE
// ==============================================================================
export interface WeatherData {
    city: string;
    temperature: string;
    condition: string;
    tempMax: string;
    tempMin: string;
    wind: string;
    humidity: string;
    feelsLike: string;
    sunrise: string;
    pressure: string;
    willRain: boolean;
}

// ==============================================================================
// GLOBAL STATE INTERFACE
// ==============================================================================
interface AppState {
    weatherData: WeatherData | null;
    setWeatherData: (data: WeatherData) => void;

    mediaConverterStatus: string;
    setMediaConverterStatus: (status: string) => void;

    musicPlayerData: string;
    setMusicPlayerData: (data: string) => void;

    academicData: string;
    setAcademicData: (data: string) => void;
}

// ==============================================================================
// STORE
// ==============================================================================
export const useAppStore = create<AppState>((set) => ({
    weatherData: null,
    setWeatherData: (data) => set({ weatherData: data }),

    mediaConverterStatus: "Converter idle.",
    setMediaConverterStatus: (status) => set({ mediaConverterStatus: status }),

    musicPlayerData: "No audio track currently playing.",
    setMusicPlayerData: (data) => set({ musicPlayerData: data }),

    academicData: "Academic module standby. No active research queries.",
    setAcademicData: (data) => set({ academicData: data }),
}));