import flet as ft
import threading
import time
import os
import sys
from pathlib import Path
from app.shell import AppShell
from app.theme import Colors, Fonts, UI
from app.components.shared.loading_screen import LoadingScreen

# Set BASE_DIR as anchor for all paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Global flags to track state
models_loaded = False
loading_screen = None

def preload_models():
    """Preload ML models in background to avoid cold start delays.
    
    NOTE: Disabled — the LLMBackendRouter lazily initializes TranslationBrain
    on first translate() call, so preloading here just creates a throwaway
    instance that wastes RAM and startup time.
    """
    global models_loaded
    models_loaded = True

def main(page: ft.Page):
    global loading_screen, models_loaded
    
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
        )
    )
    
    # 1. Show the Loading Screen immediately
    loading_screen = LoadingScreen(page)
    loading_screen.show("Consulting the archives...", fullpage=True)
    
    # 2. Start preloading models
    if not models_loaded:
        threading.Thread(target=preload_models, daemon=True).start()
    
    # 3. Transition to Shell
    def initialize_app():
        try:
            start_time = time.time()
            # Wait for models or 15s timeout
            while not models_loaded and (time.time() - start_time) < 15:
                time.sleep(0.2)
            
            if loading_screen:
                loading_screen.hide()
            
            # Create the AppShell
            app_shell = AppShell(page)
            
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
                    glossary_paths_checked = {}
                    
                    for entry in entries:
                        glossary_path = entry.glossary_path
                        
                        # Cache path existence checks
                        if glossary_path not in glossary_paths_checked:
                            glossary_paths_checked[glossary_path] = Path(glossary_path).exists()
                        
                        if not glossary_paths_checked[glossary_path]:
                            app_shell.bus.show_banner(
                                f"Error: Glossary not found at {glossary_path}",
                                is_error=True,
                            )
                            continue
                        
                        if entry.operation == "add":
                            term_data = entry.term_data
                            app_shell.glossary_manager.add_term(
                                german=term_data.get("german", ""),
                                english=term_data.get("english", ""),
                                context_target=term_data.get("context_target", ""),
                                field_tag=term_data.get("field_tag", ""),
                                nuance_note=term_data.get("nuance_note", ""),
                            )
                        elif entry.operation == "remove":
                            term_data = entry.term_data
                            app_shell.glossary_manager.remove_term(
                                german=term_data.get("german", ""),
                            )
                    
                    # Save glossary and reset journal after applying all entries
                    app_shell.glossary_manager.save()
                    app_shell.glossary_journal.reset()
                else:
                    app_shell.glossary_journal.reset()
            
            # Start periodic auto-saves
            state_service.start()
            
            # Setup the close handling
            setup_window_close_handling(page, app_shell)
            
            # Add the Shell build to the page
            page.add(app_shell.build())
            page.update()
            print("✅ MAIN: App initialized successfully")
        except Exception as e:
            print(f"❌ MAIN: Fatal error during initialization: {e}")
            import traceback
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
                # Check centralized state for unsaved content
                if app_shell.state.has_unsaved_content:
                    show_exit_confirmation(page, app_shell)
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
        import os
        os._exit(0)


def show_exit_confirmation(page: ft.Page, app_shell: AppShell):
    """Displays the final warning dialog"""
    
    def on_stay(e):
        try:
            exit_dialog.open = False
            page.update()
        except Exception:
            pass
    
    def on_confirm_exit(e):
        # Don't bother closing the dialog cleanly — just exit immediately
        _safe_exit(page, app_shell)
    
    # Close any existing dialog first to prevent stomping
    try:
        if page.dialog and hasattr(page.dialog, 'open'):
            page.dialog.open = False
            page.update()
    except Exception:
        pass
    
    exit_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Unsaved Work", font_family=Fonts.HEADER),
        content=ft.Text(
            "You have unsaved text or a PDF loaded. Exit anyway?",
            font_family=Fonts.SERIF,
            size=14,
        ),
        actions=[
            ft.TextButton("Stay", on_click=on_stay),
            ft.ElevatedButton(
                "Exit Stimme",
                on_click=on_confirm_exit,
                bgcolor=Colors.DESTRUCTIVE,
                color=Colors.FOREGROUND,
            ),
        ],
    )
    page.dialog = exit_dialog
    exit_dialog.open = True
    page.update()

# This part ensures the app runs when main.py is executed
if __name__ == "__main__":
    # Define where the logos and fonts are stored
    assets_dir = os.path.join(BASE_DIR, "app", "assets")
    ft.app(target=main, assets_dir=assets_dir)