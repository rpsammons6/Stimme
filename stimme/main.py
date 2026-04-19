import flet as ft
import threading
import time
import os
from app.shell import AppShell
from app.theme import Colors, Fonts
from app.components.loading_screen import LoadingScreen

# Set BASE_DIR as anchor for all paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Global flag to track model loading
models_loaded = False
loading_screen = None

def preload_models():
    """Preload ML models in background to avoid cold start delays"""
    global models_loaded, loading_screen
    
    print("🔄 MAIN: Starting model preloading...")
    
    try:
        # Import and initialize the brain (this loads the models)
        import sys
        programs_path = os.path.join(BASE_DIR, "programs")
        sys.path.append(programs_path)
        
        if loading_screen:
            loading_screen.update_progress("Loading sentence transformer...", 25)
        
        from brain import TranslationBrain
        
        print("  MAIN: Loading sentence transformer model...")
        
        if loading_screen:
            loading_screen.update_progress("Initializing translation brain...", 50)
        
        brain = TranslationBrain()  # This loads SentenceTransformer and BERT
        
        if loading_screen:
            loading_screen.update_progress("Models loaded successfully!", 100)
        
        print("✅ MAIN: Models preloaded successfully")
        
        models_loaded = True
        
    except Exception as e:
        print(f"⚠️  MAIN: Model preloading failed: {e}")
        if loading_screen:
            loading_screen.update_progress("Model loading failed, continuing...", 100)
        models_loaded = True  # Set to True anyway to not block the UI

def main(page: ft.Page):
    global loading_screen, models_loaded
    
    page.title = "Stimme"
    
    print(" MAIN: Starting Stimme app...")  # Debug
    print(f"  MAIN: Window size will be 1200x800")  # Debug
    
    # Use new window API with more reasonable default size
    page.window.min_width = 900
    page.window.min_height = 600
    page.window.width = 1200
    page.window.height = 800
    
    page.theme_mode = ft.ThemeMode.DARK
    
    # Set exact color scheme from CSS
    page.bgcolor = Colors.BACKGROUND
    
    # Configure fonts - using local TTF files
    page.fonts = {
        "CormorantGaramond": "/CormorantGaramond-Regular.ttf",
        "UnifrakturCook-Bold": "/UnifrakturCook-Bold.ttf",
        "Lexend": "/Lexend[wght].ttf"
    }
    
    # Set window icon to shortcut logo
    page.window.icon = "/Shortcut-Logo.png"
    
    # Create custom theme with our exact colors
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=Colors.PRIMARY,
            on_primary=Colors.PRIMARY_FOREGROUND,
            secondary=Colors.SECONDARY,
            on_secondary=Colors.SECONDARY_FOREGROUND,
            background=Colors.BACKGROUND,
            on_background=Colors.FOREGROUND,
            surface=Colors.SURFACE,
            on_surface=Colors.FOREGROUND,
            error=Colors.DESTRUCTIVE,
            on_error=Colors.DESTRUCTIVE_FOREGROUND,
            outline=Colors.BORDER,
            shadow=Colors.BACKGROUND,
            inverse_surface=Colors.FOREGROUND,
            inverse_primary=Colors.BACKGROUND,
        ),
        font_family="CormorantGaramond",  # Use Cormorant Garamond as default
        use_material3=True
    )
    
    # Disable padding
    page.padding = 0
    page.spacing = 0
    
    # Show loading screen while models load
    loading_screen = LoadingScreen(page)
    loading_screen.show("Loading translation models...")
    
    # Start model preloading in background
    if not models_loaded:
        threading.Thread(target=preload_models, daemon=True).start()
    
    # Wait for models to load or timeout after 15 seconds
    def check_models_loaded():
        start_time = time.time()
        while not models_loaded and (time.time() - start_time) < 15:
            time.sleep(0.1)
        
        # Hide loading screen and show main app
        if loading_screen:
            loading_screen.hide()
        
        # Create and show main app
        app_shell = AppShell(page)
        print("  MAIN: AppShell created")  # Debug
        print(f" MAIN: Home tab has shell reference: {hasattr(app_shell.home_tab, 'shell')}")  # Debug
        
        # Set up window close handling
        setup_window_close_handling(page, app_shell)
        
        page.add(app_shell.build())
        print("✅ MAIN: App shell added to page")  # Debug
        page.update()
    
    # Start app initialization in background
    threading.Thread(target=check_models_loaded, daemon=True).start()

def setup_window_close_handling(page: ft.Page, app_shell: AppShell):
    """Handle window close event with confirmation"""
    def on_window_event(e):
        if e.data == "close":
            print(" MAIN: Window close event triggered")  # Debug
            
            # Check if there's unsaved content using workspace manager
            has_content = app_shell.workspace.has_unsaved_content(
                pdf_file=app_shell.home_tab.center_panel.pdf_file
            )
            
            print(f" MAIN: Has unsaved content: {has_content}")  # Debug
            
            if has_content:
                print("  MAIN: Unsaved content detected, showing confirmation dialog")  # Debug
                show_exit_confirmation(page, app_shell)
            else:
                print("✅ MAIN: No unsaved content, allowing exit")  # Debug
                page.window.destroy()
    
    # Set the window event handler
    page.window.on_event = on_window_event
    page.window.prevent_close = True  # Prevent default close behavior

def show_exit_confirmation(page: ft.Page, app_shell: AppShell):
    """Show confirmation dialog before exiting with unsaved content"""
    
    def on_confirm_exit(e):
        print("✅ MAIN: User confirmed exit")  # Debug
        exit_dialog.open = False
        page.update()
        # Cleanup resources
        app_shell.home_tab.cleanup()
        page.window.destroy()
    
    def on_cancel_exit(e):
        print("❌ MAIN: User cancelled exit")  # Debug
        exit_dialog.open = False
        page.update()
    
    exit_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(
            "Confirm Exit",
            font_family=Fonts.HEADER,
            weight=ft.FontWeight.W_600,
            size=18,
            color=Colors.FOREGROUND
        ),
        content=ft.Text(
            "You have unsaved content (text or loaded PDF). Are you sure you want to exit?",
            font_family=Fonts.SERIF,
            size=14,
            color=Colors.INK_MUTED
        ),
        actions=[
            ft.TextButton(
                "Cancel",
                on_click=on_cancel_exit,
                style=ft.ButtonStyle(
                    color=Colors.INK_MUTED
                )
            ),
            ft.ElevatedButton(
                "Exit",
                on_click=on_confirm_exit,
                bgcolor=Colors.DESTRUCTIVE,  # Keep red for exit
                color=Colors.FOREGROUND,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=6)
                )
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        bgcolor=Colors.BACKGROUND,
        shape=ft.RoundedRectangleBorder(radius=12)
    )
    
    page.dialog = exit_dialog
    exit_dialog.open = True
    page.update()

if __name__ == "__main__":
    # Set assets directory using BASE_DIR for cross-platform compatibility
    assets_dir = os.path.join(BASE_DIR, "app", "assets")
    ft.app(target=main, assets_dir=assets_dir)