# ÆHub — AeSouls Digital Hub

> **ÆHub** is a futuristic **Holographic / Bento Grid** digital dashboard designed to centralize intelligent services, academic synchronization, and multimedia utilities inside a modern, reactive, and highly modular ecosystem.

The architecture is fully decoupled:

* ⚡ **High-performance asynchronous backend** built with **Python + FastAPI**
* 🧩 **Reactive frontend** powered by **Next.js + React + TypeScript**

The platform provides:

* 🌦️ Real-time weather telemetry
* 🎓 Secure academic data synchronization through assisted browser automation
* 🎵 High-fidelity MP3 extraction and conversion
* 🌙 Dynamic Dark / Light mode interface with futuristic UI design

---

# 🏗️ System Architecture

ÆHub is divided into two independent macro-modules communicating through **REST APIs**.

---

# ⚙️ Technology Stack

## 🔹 Backend — API Server

| Technology                | Description                                |
| ------------------------- | ------------------------------------------ |
| **FastAPI**               | Asynchronous framework for API management  |
| **Uvicorn**               | High-performance ASGI server               |
| **Playwright (Chromium)** | Browser automation for SPID authentication |
| **yt-dlp**                | Audio extraction from web sources          |
| **FFmpeg**                | High-quality MP3 conversion                |
| **Pydantic**              | Typed HTTP payload validation              |

---

## 🔹 Frontend — Dashboard UI

| Technology          | Description                      |
| ------------------- | -------------------------------- |
| **Next.js 16**      | React framework using App Router |
| **React 19**        | Reactive UI rendering            |
| **TypeScript**      | Advanced static typing           |
| **Tailwind CSS v4** | Utility-first styling framework  |
| **Radix UI**        | Accessible UI primitives         |
| **Lucide React**    | Dynamic vector icon library      |

---

# 🧠 Core Features

## 🌦️ Atmosphere — Local Weather System

A reactive weather widget that periodically fetches data from **Open-Meteo APIs** including:

* Current temperature
* Daily minimum / maximum
* Feels-like temperature
* Humidity
* Atmospheric pressure
* Wind speed
* Rain prediction indicators

Automatic refresh every **30 seconds**.

---

## 🎓 Academic — University Synchronization

An intelligent synchronization system for the **Infostud / Phoenix** student portal.

### Features:

* SPID login through a real Chromium browser
* Automatic authenticated session detection
* Academic graph parsing
* Automatic extraction of:

  * 📊 Weighted GPA
  * 🎯 Earned credits (CFU)
  * ✅ Passed exams

Data is persisted locally through server-side cache storage.

---

## 🎵 MP3 Sync — Media Extraction Engine

Advanced audio extraction and conversion module.

### Pipeline:

1. Automatic media search
2. Original audio stream extraction
3. FFmpeg conversion
4. MP3 encoding at **320kbps**
5. ID3 metadata injection
6. Direct client-side download

### UI States:

* `idle`
* `searching`
* `downloading`
* `done`

---

## 🧩 Core Orchestrator

Diagnostic section enhanced with:

* Animated CSS spectrum analyzer
* API traffic simulation
* Pulse network effects
* Real-time server status indicators

---

## 🌙 Theme Controller

Dark / Light mode management system featuring:

* Instant theme switching
* Theme persistence
* Temporary CSS transition disabling
* Flicker-free theme transitions

---

# 🔌 API Endpoints

Backend runs by default on:

```txt
http://127.0.0.1:3002
```

---

# 🔹 Core Routes

| Method | Endpoint | Description      |
| ------ | -------- | ---------------- |
| `GET`  | `/`      | Server heartbeat |

### Response:

```json
{
  "status": "Online"
}
```

---

# 🎓 Academic Module — `/api/academic`

## `GET /status`

Checks local session validity using:

```txt
academic_cache.json
```

---

## `POST /login`

Launches Chromium in non-headless mode and waits for:

1. Manual SPID login
2. Navigation to `#/grafico`

Then:

* captures the DOM
* extracts academic data
* stores local cache

### Extracted Data:

* Weighted GPA
* Earned credits (CFU)
* Passed exams

---

## `POST /logout`

Deletes:

```txt
academic_cache.json
```

Immediately invalidating the session.

---

# 🎵 Media Module — `/api/media`

## `POST /download`

### Payload:

```json
{
  "query": "Artist - Title"
}
```

### Process:

* automatic search
* audio extraction
* MP3 320kbps conversion
* downloadable binary response

### Response Headers:

```txt
Content-Disposition: attachment
```

---

# 📦 Local Installation

# 🔧 Requirements

Make sure the following are installed:

* Python **3.10+**
* Node.js **18+**
* npm / yarn / pnpm
* FFmpeg configured inside the system `PATH`

---

# 🚀 Backend Setup

## 1. Enter backend directory

```bash
cd backend
```

---

## 2. Install Python dependencies

```bash
pip install fastapi uvicorn yt_dlp playwright pydantic
```

---

## 3. Install Chromium for Playwright

```bash
playwright install chromium
```

---

## 4. Start the server

```bash
python main.py
```

Backend available at:

```txt
http://127.0.0.1:3002
```

---

# 💻 Frontend Setup

## 1. Enter frontend directory

```bash
cd frontend
```

---

## 2. Install dependencies

```bash
npm install
```

---

## 3. Start Next.js

```bash
npm run dev
```

Frontend available at:

```txt
http://localhost:2003
```

---

# 🧬 Design Philosophy

ÆHub adopts a visual language inspired by:

* **Holographic UI**
* **Glassmorphism**
* **Bento Grid Layouts**
* **Soft Neon Glow**
* **Reactive Motion Systems**

The interface is designed to simulate an advanced digital control center while maintaining:

* high performance
* readability
* modularity
* fluid animations

---

# 📁 Project Structure

```txt
ÆHub/
│
├── backend/
│   ├── routers/
│   ├── services/
│   ├── cache/
│   ├── main.py
│   └── academic_cache.json
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── public/
│   └── styles/
│
└── README.md
```

---

# 🔮 Future Roadmap

* 🔐 Native account system
* ☁️ Multi-device cloud sync
* 📊 Advanced academic analytics
* 🤖 Integrated AI assistant
* 🎧 Real-time audio streaming
* 📱 Progressive Web App (PWA)
* 🛰️ WebSocket telemetry system

---

# 📜 License

This project is under copyright.

---

# 👤 Author

**AeSouls**
