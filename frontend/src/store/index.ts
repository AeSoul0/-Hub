/**
 * @file frontend/src/store/index.ts
 * @description Implements index.ts.
 * 
 * This module manages the frontend logic for UI components.
 * Core interfaces: WeatherData, AppState.
 */
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

    musicPlayerData: string;
    setMusicPlayerData: (data: string) => void;}

// ==============================================================================
// STORE
// ==============================================================================
export const useAppStore = create<AppState>((set) => ({
    weatherData: null,
    setWeatherData: (data) => set({ weatherData: data }),

    musicPlayerData: "No audio track currently playing.",
    setMusicPlayerData: (data) => set({ musicPlayerData: data }),}));
