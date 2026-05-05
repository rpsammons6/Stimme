import flet as ft
import threading
import traceback
import os
from pathlib import Path
from app.shell import AppShell
from app.theme import Colors, Fonts
from app.components.shared.loading_screen import LoadingScreen
from app.services.configuration_service import ConfigurationService

# Set BASE_DIR as anchor for all paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Global reference for loading screen
loading_screen = None

def main(page: ft.Page):
    global loading_screen
    
    page.title = "Stimme"
    page.window.min_width = 1000
    page.window.min_height = 700
    page.window.width = 1000
    page.window.height = 700
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = Colors.BACKGROUND
    page.padding = 0
    page.spacing = 0

    # Registration of fonts
    page.fonts = {
        "CormorantGaramond": "/CormorantGaramond-Regular.ttf",
        "UnifrakturCook-Bold": "/UnifrakturCook-Bold.ttf",
        "JetBrains Mono": "/JetBrainsMono-Regular.ttf"
    }

    # Custom theme setup
    page.theme = ft.Theme(
        font_family="CormorantGaramond",
        use_material3=True,
        color_scheme=ft.ColorScheme(
            primary=Colors.GOLD,
            surface=Colors.SURFACE,
            background=Colors.BACKGROUND,
        ),
        splash_color=ft.Colors.TRANSPARENT,
    )
    
    # 1. Show the Loading Screen immediately
    loading_screen = LoadingScreen(page)
    loading_screen.show("Consulting the archives...", fullpage=True)
    
    # 2. Transition to Shell
    def initialize_app():
        try:
            # Apply theme from persisted settings BEFORE creating AppShell,
            # so every component initializes with the correct palette.
            theme_mode = ConfigurationService.get_early_theme(Path(BASE_DIR))
            Colors.apply(theme_mode)
            page.theme_mode = ft.ThemeMode.DARK if theme_mode == "dark" else ft.ThemeMode.LIGHT
            page.bgcolor = Colors.BACKGROUND
            page.theme = ft.Theme(
                font_family="CormorantGaramond",
                use_material3=True,
                color_scheme=ft.ColorScheme(
                    primary=Colors.GOLD,
                    surface=Colors.SURFACE,
                    background=Colors.BACKGROUND,
                ),
                splash_color=ft.Colors.TRANSPARENT,
            )
            
            # Create the AppShell — all components now init with correct colors
            app_shell = AppShell(page)
            
            # Mount the UI before recovery dialogs so the shell is visible
            page.add(app_shell.build())
            page.update()
            
            # Hide loading screen after AppShell is built and mounted
            if loading_screen:
                loading_screen.hide()
            
            # Check for session recovery
            state_service = app_shell.state_service
            recovery_data = state_service.check_recovery()
            
            if recovery_data:
                # Use threading.Event to wait for user's dialog choice
                decision_event = threading.Event()
                user_accepted = [False]  # mutable container for closure
                
                def on_accept(e):
                    user_accepted[0] = True
                    decision_event.set()
                    app_shell.bus.close_dialog()
                
                def on_decline(e):
                    user_accepted[0] = False
                    decision_event.set()
                    app_shell.bus.close_dialog()
                
                recovery_dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Session Recovery", font_family=Fonts.HEADER, color=Colors.GOLD),
                    content=ft.Text(
                        "Resume your previous session?",
                        font_family=Fonts.SERIF,
                        size=14,
                        color=Colors.FOREGROUND,
                    ),
                    actions=[
                        ft.TextButton(
                            content=ft.Text("Discard", font_family=Fonts.FRAKTUR),
                            on_click=on_decline,
                        ),
                        ft.ElevatedButton(
                            content=ft.Text("Resume", font_family=Fonts.FRAKTUR, weight="bold"),
                            on_click=on_accept,
                            bgcolor=Colors.GOLD,
                            color=Colors.BACKGROUND,
                        ),
                    ],
                    bgcolor=Colors.SURFACE,
                )
                
                # Show dialog via EventBus (thread-safe)
                app_shell.bus.show_dialog(recovery_dialog)
                
                # Wait for user decision
                decision_event.wait()
                
                if user_accepted[0]:
                    # Apply recovery: replace state and rebuild
                    restored_state = state_service.apply_recovery(recovery_data)
                    app_shell.state = restored_state
                    # Update StateService's internal reference to the new state
                    state_service._state = restored_state
                    app_shell.rebuild_tabs()
                else:
                    state_service.discard_recovery()
            
            # Check for glossary journal recovery
            if app_shell.glossary_journal.has_entries():
                glossary_decision_event = threading.Event()
                glossary_accepted = [False]
                
                def on_glossary_accept(e):
                    glossary_accepted[0] = True
                    glossary_decision_event.set()
                    app_shell.bus.close_dialog()
                
                def on_glossary_decline(e):
                    glossary_accepted[0] = False
                    glossary_decision_event.set()
                    app_shell.bus.close_dialog()
                
                glossary_recovery_dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Glossary Recovery", font_family=Fonts.HEADER, color=Colors.GOLD),
                    content=ft.Text(
                        "Unsaved glossary changes from your last session were found. Apply them?",
                        font_family=Fonts.SERIF,
                        size=14,
                        color=Colors.FOREGROUND,
                    ),
                    actions=[
                        ft.TextButton(
                            content=ft.Text("Discard", font_family=Fonts.FRAKTUR),
                            on_click=on_glossary_decline,
                        ),
                        ft.ElevatedButton(
                            content=ft.Text("Apply", font_family=Fonts.FRAKTUR, weight="bold"),
                            on_click=on_glossary_accept,
                            bgcolor=Colors.GOLD,
                            color=Colors.BACKGROUND,
                        ),
                    ],
                    bgcolor=Colors.SURFACE,
                )
                
                app_shell.bus.show_dialog(glossary_recovery_dialog)
                glossary_decision_event.wait()
                
                if glossary_accepted[0]:
                    entries = app_shell.glossary_journal.read_entries()
                    app_shell.glossary_manager.apply_journal_recovery(entries)
                else:
                    app_shell.glossary_journal.reset()
            
            # Start periodic auto-saves
            state_service.start()
            
            # Setup the close handling
            setup_window_close_handling(page, app_shell)
            
            print("✅ MAIN: App initialized successfully")
        except Exception as e:
            print(f"❌ MAIN: Fatal error during initialization: {e}")
            traceback.print_exc()
            # Show a minimal error state so the user knows something went wrong
            try:
                if loading_screen:
                    loading_screen.hide()
                page.add(ft.Text(
                    f"Stimme failed to start: {e}\nCheck the terminal for details.",
                    color="red", size=16
                ))
                page.update()
            except Exception:
                pass

    threading.Thread(target=initialize_app, daemon=True).start()

def setup_window_close_handling(page: ft.Page, app_shell: AppShell):
    """Intercepts the 'X' button to check for unsaved work"""
    
    def on_window_event(e):
        if e.data == "close":
            try:
                if app_shell.state.has_unsaved_content:
                    if app_shell.state.has_dirty_glossaries:
                        show_glossary_exit_dialog(page, app_shell)
                    else:
                        show_session_exit_dialog(page, app_shell)
                else:
                    _safe_exit(page, app_shell)
            except Exception as ex:
                print(f"⚠️  MAIN: Error in close handler: {ex}")
                _safe_exit(page, app_shell)
    
    page.window.on_event = on_window_event
    page.window.prevent_close = True


def _safe_exit(page: ft.Page, app_shell: AppShell):
    """Clean up resources and destroy the window."""
    try:
        app_shell.home_tab.cleanup()
    except Exception:
        pass
    
    try:
        app_shell.home_tab.translation_service.cleanup()
    except Exception:
        pass
    
    # Stop the auto-save timer and delete the snapshot (clean shutdown)
    try:
        app_shell.state_service.stop(clean_exit=True)
    except Exception:
        pass
    
    try:
        page.window.destroy()
    except (AssertionError, Exception):
        # Flet's internal update can fail during teardown — just force quit
        os._exit(0)


def show_glossary_exit_dialog(page: ft.Page, app_shell: AppShell):
    """Three-button dialog when glossaries have unsaved changes."""
    count = app_shell.get_dirty_glossary_count()
    msg = f"You have {count} unsaved glossar{'y' if count == 1 else 'ies'}. Save before exiting?"

    def on_stay(e):
        try:
            dialog.open = False
            page.update()
        except Exception:
            pass

    def on_discard(e):
        _safe_exit(page, app_shell)

    def on_save_exit(e):
        success, error = app_shell.save_all_dirty_glossaries()
        if success:
            # Also save session state (best-effort)
            try:
                app_shell.state_service.save_snapshot()
            except Exception:
                pass
            _safe_exit(page, app_shell)
        else:
            dialog.open = False
            page.update()
            app_shell.bus.show_banner(error, is_error=True)

    # Close any existing dialog first to prevent stomping
    try:
        if page.dialog and hasattr(page.dialog, 'open'):
            page.dialog.open = False
            page.update()
    except Exception:
        pass

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Unsaved Glossaries", font_family=Fonts.HEADER),
        content=ft.Text(msg, font_family=Fonts.SERIF, size=14),
        actions=[
            ft.TextButton("Stay", on_click=on_stay),
            ft.TextButton("Discard & Exit", on_click=on_discard),
            ft.ElevatedButton(
                "Save & Exit",
                on_click=on_save_exit,
                bgcolor=Colors.GOLD,
                color=Colors.BACKGROUND,
            ),
        ],
    )
    page.dialog = dialog
    dialog.open = True
    page.update()


def show_session_exit_dialog(page: ft.Page, app_shell: AppShell):
    """Three-button dialog when only text/PDF is unsaved (no dirty glossaries)."""
    msg = "You have unsaved text or a PDF loaded. Save your session before exiting?"

    def on_stay(e):
        try:
            dialog.open = False
            page.update()
        except Exception:
            pass

    def on_discard(e):
        _safe_exit(page, app_shell)

    def on_save_session_exit(e):
        try:
            app_shell.state_service.save_snapshot()
        except Exception:
            pass  # Best-effort; don't block exit for session save failure
        _safe_exit(page, app_shell)

    # Close any existing dialog first to prevent stomping
    try:
        if page.dialog and hasattr(page.dialog, 'open'):
            page.dialog.open = False
            page.update()
    except Exception:
        pass

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Unsaved Work", font_family=Fonts.HEADER),
        content=ft.Text(msg, font_family=Fonts.SERIF, size=14),
        actions=[
            ft.TextButton("Stay", on_click=on_stay),
            ft.TextButton("Discard & Exit", on_click=on_discard),
            ft.ElevatedButton(
                "Save Session & Exit",
                on_click=on_save_session_exit,
                bgcolor=Colors.GOLD,
                color=Colors.BACKGROUND,
            ),
        ],
    )
    page.dialog = dialog
    dialog.open = True
    page.update()

# This part ensures the app runs when main.py is executed
if __name__ == "__main__":
    # Define where the logos and fonts are stored
    assets_dir = os.path.join(BASE_DIR, "app", "assets")
    ft.app(target=main, assets_dir=assets_dir)