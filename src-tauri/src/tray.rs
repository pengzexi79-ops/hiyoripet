use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager,
};

pub fn build_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let show_pet = MenuItem::with_id(app, "show_pet", "显示宠物", true, None::<&str>)?;
    let hide_pet = MenuItem::with_id(app, "hide_pet", "隐藏宠物", true, None::<&str>)?;
    let quit_i = MenuItem::with_id(app, "quit", "退出日和桌宠", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_pet, &hide_pet, &quit_i])?;

    let _tray = TrayIconBuilder::with_id("main-tray")
        .icon(app.default_window_icon().unwrap().clone())
        .tooltip("日和桌宠")
        .menu(&menu)
        .on_menu_event(|tray, event| {
            let app = tray.app_handle();
            match event.id.as_ref() {
                "quit" => app.exit(0),
                "show_pet" => {
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.show();
                        let _ = w.unminimize();
                        let _ = w.set_always_on_top(true);
                        let _ = w.set_focus();
                        let _ = w.emit("pet-opened", ());
                    }
                }
                "hide_pet" => {
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.emit("pet-hidden", ());
                        let _ = w.hide();
                    }
                }
                _ => {}
            }
        })
        .build(app)?;

    Ok(())
}
