//! ÆHub desktop shell (roadmap M14, ADR-020).
//!
//! The window is a plain web page over the local engine: this process starts
//! `backend/desktop.py` (bundled Python, Postgres and frontend), waits for its
//! `{"event": "ready", "url": ...}` line on stdout and points the window at
//! that one-time launch URL. The page gets no Tauri IPC (no capabilities),
//! and the window may only navigate inside the engine's own origin.
//!
//! Closing the app closes the engine's stdin: the engine stops the API and
//! Postgres by itself. If it does not within 30 seconds it is killed.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use serde::Deserialize;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};

const STOP_TIMEOUT: Duration = Duration::from_secs(30);

/// Origin of the engine once it is ready: the only place the window may go.
static ENGINE_ORIGIN: OnceLock<String> = OnceLock::new();
/// Set when the app is closing, so the engine's exit is not an error.
static STOPPING: AtomicBool = AtomicBool::new(false);

#[derive(Deserialize)]
struct EngineEvent {
    event: String,
    url: Option<String>,
    port: Option<u16>,
    message: Option<String>,
}

struct Engine {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
}

fn log_file(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_log_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("engine.log"))
}

fn start_engine(app: &AppHandle) -> Result<Child, String> {
    let resources = app
        .path()
        .resource_dir()
        .map_err(|e| e.to_string())?
        .join("resources");
    let log = std::fs::File::create(log_file(app)?).map_err(|e| e.to_string())?;

    let mut command = Command::new(resources.join("python").join("python.exe"));
    command
        // Isolated mode: no PYTHONPATH, no user site-packages.
        .arg("-I")
        .arg(resources.join("backend").join("desktop.py"))
        .arg("--pg-bin")
        .arg(resources.join("postgres").join("bin"))
        .arg("--frontend-dir")
        .arg(resources.join("frontend"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::from(log));

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    command
        .spawn()
        .map_err(|e| format!("Cannot start the ÆHub engine: {e}"))
}

fn stop_engine(app: &AppHandle) {
    STOPPING.store(true, Ordering::SeqCst);

    let Some(engine) = app.try_state::<Engine>() else {
        return;
    };

    // EOF on stdin is the engine's signal to shut down.
    drop(engine.stdin.lock().unwrap().take());

    if let Some(mut child) = engine.child.lock().unwrap().take() {
        let deadline = Instant::now() + STOP_TIMEOUT;

        while Instant::now() < deadline {
            match child.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) => std::thread::sleep(Duration::from_millis(200)),
                Err(_) => break,
            }
        }

        let _ = child.kill();
        let _ = child.wait();
    }
}

fn fail(app: &AppHandle, message: &str) {
    let log = log_file(app)
        .map(|path| path.display().to_string())
        .unwrap_or_default();

    app.dialog()
        .message(format!("{message}\n\nDetails: {log}"))
        .title("ÆHub")
        .kind(MessageDialogKind::Error)
        .blocking_show();

    stop_engine(app);
    app.exit(1);
}

fn navigation_allowed(url: &Url) -> bool {
    // The start page is bundled (tauri://localhost, http://tauri.localhost on Windows).
    if url.scheme() == "tauri" || url.host_str() == Some("tauri.localhost") {
        return true;
    }

    ENGINE_ORIGIN
        .get()
        .is_some_and(|origin| url.origin().ascii_serialization() == *origin)
}

/// Read the engine's events and open the app when it is ready.
fn follow_engine(app: AppHandle, stdout: ChildStdout) {
    let mut opened = false;

    for line in BufReader::new(stdout).lines() {
        let Ok(line) = line else { break };
        let Ok(event) = serde_json::from_str::<EngineEvent>(&line) else {
            continue;
        };

        match event.event.as_str() {
            "ready" => {
                let (Some(url), Some(port)) = (event.url, event.port) else {
                    continue;
                };
                let _ = ENGINE_ORIGIN.set(format!("http://127.0.0.1:{port}"));

                let target = match url.parse::<Url>() {
                    Ok(target) if navigation_allowed(&target) => target,
                    _ => {
                        fail(&app, "The ÆHub engine announced an unexpected address.");
                        return;
                    }
                };

                if let Some(window) = app.get_webview_window("main") {
                    if window.navigate(target).is_ok() {
                        opened = true;
                    }
                }
            }
            "error" => {
                let message = event.message.unwrap_or_default();
                fail(&app, &format!("ÆHub could not start: {message}"));
                return;
            }
            _ => {}
        }
    }

    if !STOPPING.load(Ordering::SeqCst) {
        let message = if opened {
            "The ÆHub engine stopped. The app will close."
        } else {
            "The ÆHub engine stopped before it was ready."
        };
        fail(&app, message);
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("ÆHub")
                .inner_size(1280.0, 800.0)
                .min_inner_size(800.0, 600.0)
                .on_navigation(navigation_allowed)
                .build()?;

            let handle = app.handle().clone();

            match start_engine(&handle) {
                Ok(mut child) => {
                    let stdout = child.stdout.take().expect("engine stdout is piped");
                    let stdin = child.stdin.take();
                    app.manage(Engine {
                        child: Mutex::new(Some(child)),
                        stdin: Mutex::new(stdin),
                    });
                    std::thread::spawn(move || follow_engine(handle, stdout));
                }
                Err(message) => {
                    std::thread::spawn(move || fail(&handle, &message));
                }
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the ÆHub app")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_engine(app);
            }
        });
}
