import flet as ft
from app.components.sidebar import Sidebar
from app.components.home_tab import HomeTab
from app.components.translation_result_tab import TranslationResultTab
from app.contexts.workspace import WorkspaceManager
from app.contexts.settings import SettingsManager
from app.theme import Colors, Fonts

class AppShell:
    def __init__(self, page: ft.Page):
        print("🏗️  SHELL: Initializing AppShell...")  # Debug
        self.page = page
        self.workspace = WorkspaceManager()
        self.settings = SettingsManager()
        
        print("🏠 SHELL: Creating HomeTab...")  # Debug
        self.home_tab = HomeTab(self.page, self.workspace, self.settings)
        
        print("📋 SHELL: Creating Sidebar...")  # Debug
        # Pass center_panel reference to sidebar for syncing
        self.sidebar = Sidebar(self.page, self.settings, self.home_tab.center_panel)
        
        print("🔗 SHELL: Setting up references...")  # Debug
        # Set sidebar reference in center_panel for bidirectional sync
        self.home_tab.center_panel.sidebar = self.sidebar
        # Also set sidebar reference in home_tab for access
        self.home_tab.sidebar = self.sidebar
        
        # Set shell reference in home_tab so it can trigger tab updates
        self.home_tab.shell = self
        print(f"✅ SHELL: Shell reference set in home_tab: {self.home_tab.shell is self}")  # Debug
        
        # Current tab controls - initialize with proper structure
        self.tab_bar_row = ft.Row(controls=[], spacing=4, scroll=ft.ScrollMode.AUTO)
        self.tab_bar_container = ft.Container(
            content=self.tab_bar_row,
            padding=ft.padding.only(left=8, top=4),
            bgcolor=Colors.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
            height=44
        )
        self.content_container = ft.Container(expand=True)
        self.main_layout = None  # Store reference to main layout
        
        self.rebuild_tabs()
    
    def rebuild_tabs(self):
        """Rebuild the tab bar and content based on workspace state"""
        print(f"🔄 SHELL: rebuild_tabs called")  # Debug
        print(f"📊 SHELL: Workspace has {self.workspace.get_translation_count()} translations")  # Debug
        print(f"🎯 SHELL: Active index: {self.workspace.active_translation_index}")  # Debug
        
        tabs = []
        
        # Always have Home tab
        is_home_active = not self.workspace.has_translations() or self.workspace.active_translation_index == -1
        print(f"🏠 SHELL: Home tab active: {is_home_active}")  # Debug
        
        home_tab_control = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.icons.HOME, size=16, color=Colors.GOLD if is_home_active else Colors.INK_MUTED),
                    ft.Text(
                        "Home",
                        size=13,
                        color=Colors.INK if is_home_active else Colors.INK_MUTED,
                        weight="w500" if is_home_active else "normal"
                    ),
                ],
                spacing=8
            ),
            bgcolor=Colors.BACKGROUND if is_home_active else Colors.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(2, Colors.GOLD if is_home_active else "transparent")),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            border_radius=ft.border_radius.only(top_left=6, top_right=6),
            on_click=lambda e: self.switch_to_home()
        )
        tabs.append(home_tab_control)
        
        # Add translation tabs
        for i, translation_data in enumerate(self.workspace.translation_tabs):
            is_active = i == self.workspace.active_translation_index
            print(f"📝 SHELL: Creating translation tab {i}: '{translation_data['source_preview']}', active: {is_active}")  # Debug
            
            tab_control = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.icons.TRANSLATE, size=16, color=Colors.GOLD if is_active else Colors.INK_MUTED),
                        ft.Text(
                            translation_data["source_preview"],
                            size=13,
                            color=Colors.INK if is_active else Colors.INK_MUTED,
                            weight="w500" if is_active else "normal"
                        ),
                        ft.IconButton(
                            icon=ft.icons.CLOSE,
                            icon_size=14,
                            icon_color=Colors.INK_MUTED,
                            on_click=lambda e, idx=i: self.close_translation_tab(idx),
                            width=20,
                            height=20,
                            style=ft.ButtonStyle(padding=ft.padding.all(0))
                        )
                    ],
                    spacing=8
                ),
                bgcolor=Colors.BACKGROUND if is_active else Colors.SURFACE,
                border=ft.border.only(bottom=ft.BorderSide(2, Colors.GOLD if is_active else "transparent")),
                padding=ft.padding.symmetric(horizontal=16, vertical=10),
                border_radius=ft.border_radius.only(top_left=6, top_right=6),
                on_click=lambda e, idx=i: self.switch_to_translation(idx)
            )
            tabs.append(tab_control)
        
        print(f"🏗️  SHELL: Created {len(tabs)} tabs total")  # Debug
        
        # Update tab bar row controls directly
        self.tab_bar_row.controls.clear()
        self.tab_bar_row.controls.extend(tabs)
        print("📋 SHELL: Tab bar updated")  # Debug
        
        # Update content based on active state
        if self.workspace.active_translation_index == -1 or not self.workspace.has_translations():
            print("🏠 SHELL: Showing home tab content")  # Debug
            self.content_container.content = self.home_tab.build()
        else:
            print(f"📖 SHELL: Showing translation tab {self.workspace.active_translation_index}")  # Debug
            active_translation = self.workspace.get_active_translation()
            if active_translation:
                translation_tab = TranslationResultTab(active_translation)
                self.content_container.content = translation_tab.build()
        
        # Force page update
        print("🔄 SHELL: Calling page.update()...")  # Debug
        self.page.update()
        print("✅ SHELL: Page updated successfully")  # Debug
    
    def switch_to_home(self):
        """Switch to home tab"""
        self.workspace.set_active_translation(-1)
        self.rebuild_tabs()
    
    def switch_to_translation(self, index: int):
        """Switch to translation tab"""
        self.workspace.set_active_translation(index)
        self.rebuild_tabs()
    
    def close_translation_tab(self, index: int):
        """Close a translation tab"""
        self.workspace.close_translation_tab(index)
        self.rebuild_tabs()
    
    def add_translation_result(self, source_text: str, translation: str, commentary: str = None, metrics: dict = None):
        """Add a new translation result and switch to it"""
        print(f"🏗️  SHELL: add_translation_result called")  # Debug
        print(f"📝 SHELL: Source text: '{source_text[:50]}...'")  # Debug
        
        self.workspace.add_translation(source_text, translation, commentary, metrics)
        print(f"📊 SHELL: Workspace now has {self.workspace.get_translation_count()} translations")  # Debug
        print(f"🎯 SHELL: Active index: {self.workspace.active_translation_index}")  # Debug
        
        print("🔄 SHELL: Calling rebuild_tabs...")  # Debug
        self.rebuild_tabs()
        print("✅ SHELL: rebuild_tabs completed")  # Debug
    
    def build(self):
        """Build the main shell layout"""
        print("🏗️  SHELL: build() method called")  # Debug
        
        # Initialize tabs first
        self.rebuild_tabs()
        
        # Main content area with tab bar at the top
        main_content = ft.Column(
            controls=[
                self.tab_bar_container,  # Use the persistent container
                self.content_container,  # Use the persistent container
            ],
            expand=True,
            spacing=0
        )
        
        print("🏗️  SHELL: Main content structure created")  # Debug
        
        # Sidebar with band-aid color fix - wrap in column with matching color containers
        sidebar_with_fix = ft.Column(
            controls=[
                # Top band-aid - matches sidebar background
                ft.Container(
                    height=0,
                    bgcolor=Colors.SIDEBAR_BG,
                    expand=False
                ),
                # Actual sidebar
                self.sidebar.build(),
                # Bottom band-aid - matches sidebar background
                ft.Container(
                    height=0,
                    bgcolor=Colors.SIDEBAR_BG,
                    expand=False
                )
            ],
            spacing=0,
            expand=True
        )
        
        # Layout: Row with main content and sidebar as separate full-height columns
        layout = ft.Row(
            controls=[
                ft.Container(
                    content=main_content,
                    expand=True
                ),
                ft.Container(
                    content=sidebar_with_fix,
                    bgcolor=Colors.SIDEBAR_BG,  # Band-aid: ensure entire column is sidebar color
                    width=288
                )
            ],
            expand=True,
            spacing=0
        )
        
        print("✅ SHELL: Layout structure completed")  # Debug
        return layout