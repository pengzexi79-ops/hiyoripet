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
        use windows::Win32::Foundation::RECT;
        use windows::Win32::Graphics::Gdi::{ExtCreateRegion, SetWindowRgn, RDH_RECTANGLES, RGNDATA, RGNDATAHEADER};

        let hwnd = window.hwnd().map_err(|error| error.to_string())?;
        // 一次性用 RGNDATA 批量建区域：旧实现逐矩形 CombineRgn 是 O(n^2) GDI 操作，
        // 矩形多时会卡死主线程（连点/缩放崩溃根因之一）。
        let items: Vec<RECT> = rects
            .into_iter()
            .filter(|rect| rect.width > 0 && rect.height > 0)
            .map(|rect| RECT {
                left: rect.x,
                top: rect.y,
                right: rect.x.saturating_add(rect.width),
                bottom: rect.y.saturating_add(rect.height),
            })
            .collect();
        if items.is_empty() {
            return Err("桌宠命中区域为空，已保留上一次有效区域".to_string());
        }
        let bound = RECT {
            left: items.iter().map(|item| item.left).min().unwrap_or(0),
            top: items.iter().map(|item| item.top).min().unwrap_or(0),
            right: items.iter().map(|item| item.right).max().unwrap_or(0),
            bottom: items.iter().map(|item| item.bottom).max().unwrap_or(0),
        };
        let header = RGNDATAHEADER {
            dwSize: core::mem::size_of::<RGNDATAHEADER>() as u32,
            iType: RDH_RECTANGLES,
            nCount: items.len() as u32,
            nRgnSize: (items.len() * core::mem::size_of::<RECT>()) as u32,
            rcBound: bound,
        };
        let mut bytes: Vec<u8> =
            Vec::with_capacity(core::mem::size_of::<RGNDATAHEADER>() + items.len() * core::mem::size_of::<RECT>());
        bytes.extend_from_slice(unsafe {
            core::slice::from_raw_parts(core::ptr::addr_of!(header).cast::<u8>(), core::mem::size_of::<RGNDATAHEADER>())
        });
        bytes.extend_from_slice(unsafe {
            core::slice::from_raw_parts(items.as_ptr().cast::<u8>(), items.len() * core::mem::size_of::<RECT>())
        });
        let region = unsafe { ExtCreateRegion(None, bytes.len() as u32, bytes.as_ptr().cast::<RGNDATA>()) };
        if region.is_invalid() {
            return Err("创建桌宠命中区域失败".to_string());
        }
        let result = unsafe { SetWindowRgn(hwnd, Some(region), true) };
        if result == 0 {
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
