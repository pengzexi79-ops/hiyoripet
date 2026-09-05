mod backend;
mod tray;

use serde::Deserialize;
use tauri::{Emitter, Manager, WebviewWindow};

#[derive(Debug, Deserialize)]
struct HitRegionRect {
    x: i32,
    y: i32,
    width: i32,
    height: i32,
}

/// Restrict the native HWND hit-test region to opaque pet pixels. Transparent
/// pixels are outside the region and are therefore passed to the desktop.
#[tauri::command]
fn set_hit_region(window: WebviewWindow, rects: Vec<HitRegionRect>) -> Result<(), String> {
    #[cfg(windows)]
    {
        use windows::Win32::Graphics::Gdi::{CombineRgn, CreateRectRgn, DeleteObject, HGDIOBJ, RGN_OR, SetWindowRgn};

        let hwnd = window.hwnd().map_err(|error| error.to_string())?;
        let region = unsafe { CreateRectRgn(0, 0, 0, 0) };
        if region.is_invalid() {
            return Err("创建桌宠命中区域失败".to_string());
        }
        let mut count = 0;
        for rect in rects {
            if rect.width <= 0 || rect.height <= 0 {
                continue;
            }
            let next = unsafe {
                CreateRectRgn(rect.x, rect.y, rect.x.saturating_add(rect.width), rect.y.saturating_add(rect.height))
            };
            if next.is_invalid() {
                let _ = unsafe { DeleteObject(HGDIOBJ(region.0)) };
                return Err("创建桌宠命中片段失败".to_string());
            }
            unsafe {
                CombineRgn(Some(region), Some(region), Some(next), RGN_OR);
                let _ = DeleteObject(HGDIOBJ(next.0));
            }
            count += 1;
        }
        if count == 0 {
            let _ = unsafe { DeleteObject(HGDIOBJ(region.0)) };
            return Err("桌宠命中区域为空，已保留上一次有效区域".to_string());
        }
        let result = unsafe { SetWindowRgn(hwnd, Some(region), true) };
        if result == 0 {
            let _ = unsafe { DeleteObject(HGDIOBJ(region.0)) };
            return Err("应用桌宠命中区域失败".to_string());
        }
        // SetWindowRgn transfers ownership of region to Windows on success.
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = (window, rects);
        Ok(())
    }
}


#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_always_on_top(true);
                let _ = window.set_focus();
                let _ = window.emit("pet-opened", ());
            }
        }))
        .invoke_handler(tauri::generate_handler![set_hit_region])
        .setup(|app| {
            app.manage(backend::launch(app));
            tray::build_tray(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Hiyori Pet");

    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            backend::shutdown(app_handle);
        }
    });
}
