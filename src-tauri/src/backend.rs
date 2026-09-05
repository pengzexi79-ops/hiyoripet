use std::{
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
use tauri::{App, AppHandle, Manager};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

pub struct BackendProcess(Mutex<Option<Child>>);

fn executable_path(app: &App) -> Result<PathBuf, String> {
    let bundled = app
        .path()
        .resource_dir()
        .map_err(|error| error.to_string())?
        .join("backend")
        .join("pet-backend.exe");
    if bundled.is_file() {
        return Ok(bundled);
    }
    #[cfg(debug_assertions)]
    {
        let local = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("resources")
            .join("backend")
            .join("pet-backend.exe");
        if local.is_file() {
            return Ok(local);
        }
    }
    Err(format!("backend sidecar not found: {}", bundled.display()))
}

fn spawn(app: &App) -> Result<Child, String> {
    let executable = executable_path(app)?;
    let mut command = Command::new(executable);
    command
        .env("PET_PARENT_PID", std::process::id().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);
    command.spawn().map_err(|error| error.to_string())
}

pub fn launch(app: &App) -> BackendProcess {
    let child = match spawn(app) {
        Ok(child) => Some(child),
        Err(error) => {
            eprintln!("failed to launch pet backend: {error}");
            None
        }
    };
    BackendProcess(Mutex::new(child))
}

pub fn shutdown(app: &AppHandle) {
    let state = app.state::<BackendProcess>();
    let Ok(mut guard) = state.0.lock() else {
        return;
    };
    let Some(mut child) = guard.take() else {
        return;
    };

    #[cfg(windows)]
    {
        let taskkill = std::env::var_os("SystemRoot")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(r"C:\Windows"))
            .join("System32")
            .join("taskkill.exe");
        if Command::new(taskkill)
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|status| status.success())
        {
            let _ = child.wait();
            return;
        }
    }

    let _ = child.kill();
    let _ = child.wait();
}
