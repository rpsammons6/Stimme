import flet as ft
from app.contexts.settings import SettingsManager
from app.theme import Colors, Fonts
from app.components.img_icon import ImgIcon
from app.constants import AVAILABLE_MODELS

class Sidebar:
    def __init__(self, page: ft.Page, settings: SettingsManager, center_panel=None):
        self.page = page
        self.settings = settings
        self.center_panel = center_panel  # Reference to center panel for syncing
        
        # Create icons with asset names
        self.monk_icon = ImgIcon("icon-monk.png", 28, 28)
        self.quill_icon = ImgIcon("icon-quill.png", 28, 28)
        self.book_icon = ImgIcon("icon-book.png", 28, 28)
        self.key_icon = ImgIcon("icon-key.png", 28, 28)
        self.scroll_icon = ImgIcon("icon-scroll.png", 28, 28)
        
        # Export directory field
        self.export_directory_field = ft.TextField(
            value=settings.get_export_directory(),
            on_change=self.on_export_directory_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            hint_text="Choose export destination…",
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED,
                size=11,
                font_family=Fonts.SERIF
            ),
            text_style=ft.TextStyle(
                size=11,
                font_family=Fonts.SERIF
            ),
            text_size=11,
            content_padding=ft.padding.all(10),
            read_only=True  # Make it read-only, user clicks browse button
        )
        
        self.browse_export_btn = ft.IconButton(
            icon=ft.icons.FOLDER_OPEN,
            icon_color=Colors.FOREGROUND,
            icon_size=16,
            bgcolor=Colors.SURFACE_RAISED,
            on_click=self.on_browse_export_directory,
            width=32,
            height=32,
            style=ft.ButtonStyle(
                padding=ft.padding.all(0)
            ),
            tooltip="Browse for export directory"
        )
        
        self.model_dropdown = ft.Dropdown(
            options=[
                ft.dropdown.Option(model["id"], model["display"]) 
                for model in AVAILABLE_MODELS
            ],
            on_change=self.on_model_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            value=settings.get_model(),
            text_size=14,
            height=48,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8)
        )
        
        self.scholar_mode_switch = ft.Switch(
            value=settings.get_scholar_mode(),
            on_change=self.on_scholar_mode_change,
            active_color=Colors.GOLD
        )
        
        self.thematic_focus = ft.TextField(
            multiline=True,
            min_lines=2,
            max_lines=3,
            value=settings.get_thematic_focus(),
            on_change=self.on_thematic_focus_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            hint_text="e.g. theological, archaic register…",
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED,
                italic=True,
                size=13,
                font_family=Fonts.SERIF
            ),
            text_style=ft.TextStyle(
                size=13,
                font_family=Fonts.SERIF,
                italic=True
            ),
            text_size=13,
            content_padding=ft.padding.all(12)
        )
        
        self.api_key_field = ft.TextField(
            password=True,
            value=settings.get_api_key() if settings.get_remember_api_key() else "",
            on_change=self.on_api_key_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            hint_text="sk-ant-…",
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED,
                size=11,
                font_family=Fonts.MONO
            ),
            text_style=ft.TextStyle(
                size=11,
                font_family=Fonts.MONO
            ),
            text_size=11,
            content_padding=ft.padding.all(10)
        )
        
        # Remember API key toggle
        self.remember_api_key_switch = ft.Switch(
            value=settings.get_remember_api_key(),
            on_change=self.on_remember_api_key_change,
            active_color=Colors.GOLD
        )
        
        # Datasets
        self.datasets_container = ft.Column(spacing=6)
        
        self.add_dataset_btn = ft.IconButton(
            icon=ft.icons.ADD,
            icon_color=Colors.FOREGROUND,
            icon_size=20,
            bgcolor=Colors.SURFACE_RAISED,
            on_click=self.on_add_button_click,  # Use custom handler
            width=36,
            height=36,
            style=ft.ButtonStyle(
                padding=ft.padding.all(0)
            ),
            tooltip="Select datasets from lancedb_vectors folder"
        )
        
        # API Keys collapsible state
        self.keys_open = False
        self.keys_content = ft.Column(
            controls=[
                self.api_key_field,
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                "Remember API key",
                                size=11,
                                color=Colors.FOREGROUND
                            ),
                            ft.Container(expand=True),
                            self.remember_api_key_switch
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    padding=ft.padding.symmetric(vertical=4)
                ),
                ft.Text(
                    "API key is stored locally only. Uncheck to forget on app close.",
                    size=10,
                    color=Colors.INK_MUTED,
                    italic=True
                ),
            ],
            spacing=8,
            visible=False
        )
        
        # API key status indicator
        self.api_status_icon = ft.Icon(
            ft.icons.ERROR if not settings.has_api_key() else ft.icons.CHECK_CIRCLE,
            size=16,
            color=Colors.DESTRUCTIVE if not settings.has_api_key() else Colors.SUCCESS
        )
        
        self.keys_chevron = ft.Icon(
            ft.icons.KEYBOARD_ARROW_DOWN,
            size=14,
            color=Colors.INK_MUTED
        )
    
    def on_model_change(self, e):
        """Handle model selection change"""
        if self.model_dropdown.value:
            self.settings.set_model(self.model_dropdown.value)
    
    def on_scholar_mode_change(self, e):
        """Handle scholar mode toggle"""
        self.settings.set_scholar_mode(self.scholar_mode_switch.value)
    
    def on_thematic_focus_change(self, e):
        """Handle thematic focus change"""
        new_value = self.thematic_focus.value
        self.settings.set_thematic_focus(new_value)
        # Sync with center panel if available (prevent circular updates)
        if self.center_panel and self.center_panel.thematic_focus.value != new_value:
            self.center_panel.thematic_focus.value = new_value
            self.page.update()
    
    def update_thematic_focus(self, value: str):
        """Update thematic focus from external source (e.g., center panel)"""
        if self.thematic_focus.value != value:
            self.thematic_focus.value = value
            # No page.update() here to prevent circular updates
    
    def on_api_key_change(self, e):
        """Handle API key change"""
        self.settings.set_api_key(self.api_key_field.value)
        # Update status icon
        has_key = self.settings.has_api_key()
        self.api_status_icon.name = ft.icons.CHECK_CIRCLE if has_key else ft.icons.ERROR
        self.api_status_icon.color = Colors.SUCCESS if has_key else Colors.DESTRUCTIVE
        self.page.update()
    
    def on_remember_api_key_change(self, e):
        """Handle remember API key toggle"""
        remember = self.remember_api_key_switch.value
        self.settings.set_remember_api_key(remember)
        if not remember:
            # Clear the field if user chooses not to remember
            self.api_key_field.value = ""
            self.page.update()
    
    def on_export_directory_change(self, e):
        """Handle export directory change"""
        self.settings.set_export_directory(self.export_directory_field.value)
    
    def on_browse_export_directory(self, e):
        """Handle browse export directory button click"""
        # Create a directory picker dialog
        def on_directory_selected(selected_dir):
            if selected_dir:
                self.export_directory_field.value = selected_dir
                self.settings.set_export_directory(selected_dir)
                self.page.update()
        
        # For now, show a simple dialog to enter path
        # In a full implementation, you'd use a proper directory picker
        directory_dialog = ft.AlertDialog(
            title=ft.Text(
                "Set Export Directory",
                font_family=Fonts.HEADER,
                weight=ft.FontWeight.W_500
            ),
            content=ft.Column([
                ft.Text(
                    "Enter the directory path where translations should be exported:",
                    font_family=Fonts.SERIF,
                    size=13
                ),
                ft.TextField(
                    value=self.settings.get_export_directory(),
                    hint_text="e.g., /Users/username/Documents/Stimme Exports",
                    width=400,
                    bgcolor=Colors.SURFACE,
                    border_color=Colors.DIVIDER,
                    color=Colors.FOREGROUND,
                    text_style=ft.TextStyle(
                        size=12,
                        font_family=Fonts.MONO
                    )
                )
            ], spacing=10, width=400, height=120),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close_dialog(directory_dialog)),
                ft.ElevatedButton(
                    "Set Directory",
                    on_click=lambda e: self.set_export_directory(directory_dialog),
                    bgcolor=Colors.GOLD,
                    color=Colors.BACKGROUND
                )
            ]
        )
        
        self.page.dialog = directory_dialog
        directory_dialog.open = True
        self.page.update()
    
    def set_export_directory(self, dialog):
        """Set the export directory from dialog"""
        text_field = dialog.content.controls[1]  # Get the text field
        new_directory = text_field.value
        
        if new_directory and new_directory.strip():
            # Create directory if it doesn't exist
            import os
            try:
                os.makedirs(new_directory, exist_ok=True)
                self.export_directory_field.value = new_directory
                self.settings.set_export_directory(new_directory)
                dialog.open = False
                self.page.update()
            except Exception as ex:
                # Show error
                error_dialog = ft.AlertDialog(
                    title=ft.Text("Error"),
                    content=ft.Text(f"Could not create directory: {str(ex)}"),
                    actions=[ft.TextButton("OK", on_click=lambda e: self.close_dialog(error_dialog))]
                )
                self.page.dialog = error_dialog
                error_dialog.open = True
                self.page.update()
    
    def on_add_button_click(self, e):
        """Handle add button click - show dataset file picker"""
        print(f" SIDEBAR: Add button clicked - showing dataset picker")  # Debug
        
        # Scan lancedb_vectors folder for CSV files
        import os
        from pathlib import Path
        
        lancedb_path = Path(__file__).parent.parent.parent / "lancedb_vectors"
        print(f" SIDEBAR: Scanning folder: {lancedb_path}")  # Debug
        
        available_datasets = []
        if lancedb_path.exists():
            for file in lancedb_path.glob("*.csv"):
                dataset_name = file.stem  # filename without extension
                available_datasets.append(dataset_name)
                print(f" SIDEBAR: Found dataset: {dataset_name}")  # Debug
        
        if not available_datasets:
            print(f"  SIDEBAR: No CSV files found in lancedb_vectors folder")  # Debug
            # Show info dialog
            info_dialog = ft.AlertDialog(
                title=ft.Text("No Datasets Available"),
                content=ft.Text(
                    f"No CSV files found in the lancedb_vectors folder.\n\n"
                    f"To add datasets:\n"
                    f"1. Place CSV files in: {lancedb_path}\n"
                    f"2. Click the + button to select them"
                ),
                actions=[ft.TextButton("OK", on_click=lambda e: self.close_dialog(info_dialog))]
            )
            self.page.dialog = info_dialog
            info_dialog.open = True
            self.page.update()
            return
        
        # Get currently active datasets
        current_datasets = set(self.settings.get_datasets())
        print(f" SIDEBAR: Current active datasets: {current_datasets}")  # Debug
        
        # Create checkboxes for each available dataset
        dataset_checkboxes = []
        for dataset in available_datasets:
            is_active = dataset in current_datasets
            checkbox = ft.Checkbox(
                label=dataset,
                value=is_active,
                data=dataset  # Store dataset name in data property
            )
            dataset_checkboxes.append(checkbox)
        
        def on_apply_selection(dialog_e):
            print(f" SIDEBAR: Applying dataset selection")  # Debug
            
            # Get selected datasets
            selected_datasets = []
            for checkbox in dataset_checkboxes:
                if checkbox.value:
                    selected_datasets.append(checkbox.data)
                    print(f"✅ SIDEBAR: Selected: {checkbox.data}")  # Debug
            
            # Update settings with selected datasets
            self.settings.settings["datasets"] = selected_datasets
            self.settings.save_settings()
            print(f" SIDEBAR: Saved datasets: {selected_datasets}")  # Debug
            
            # Update displays
            self.update_datasets_display()
            if self.center_panel:
                self.center_panel.update_datasets_display()
            
            # Close dialog
            picker_dialog.open = False
            self.page.update()
        
        # Create dataset picker dialog
        picker_dialog = ft.AlertDialog(
            title=ft.Text("Select Datasets"),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Select which datasets to activate:",
                            size=14,
                            color=Colors.INK_MUTED
                        ),
                        ft.Container(height=8),
                        ft.Column(
                            controls=dataset_checkboxes,
                            spacing=8,
                            scroll=ft.ScrollMode.AUTO
                        )
                    ],
                    spacing=8
                ),
                width=400,
                height=300
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close_dialog(picker_dialog)),
                ft.TextButton("Apply", on_click=on_apply_selection)
            ]
        )
        
        self.page.dialog = picker_dialog
        picker_dialog.open = True
        self.page.update()
    
    def close_dialog(self, dialog):
        """Close dialog helper"""
        dialog.open = False
        self.page.update()
    
    def on_dataset_input_change(self, e):
        """Handle dataset input change"""
        self.current_dataset_input = e.control.value
        print(f" SIDEBAR: Dataset input changed to: '{self.current_dataset_input}'")  # Debug
    
    def add_dataset(self, e):
        """Add new dataset"""
        print(f" SIDEBAR: add_dataset called")  # Debug
        print(f" SIDEBAR: Event type: {type(e)}")  # Debug
        print(f" SIDEBAR: Event control: {type(e.control) if hasattr(e, 'control') else 'No control'}")  # Debug
        
        # Try multiple ways to get the dataset name
        dataset_name = None
        
        # Method 1: From stored input
        if hasattr(self, 'current_dataset_input') and self.current_dataset_input:
            dataset_name = self.current_dataset_input
            print(f" SIDEBAR: Got from stored input: '{dataset_name}'")  # Debug
        
        # Method 2: From event control (if it's a text field submit)
        elif hasattr(e, 'control') and hasattr(e.control, 'value') and e.control.value:
            dataset_name = e.control.value
            print(f" SIDEBAR: Got from event control: '{dataset_name}'")  # Debug
        
        # Method 3: From field directly
        elif self.new_dataset_field.value:
            dataset_name = self.new_dataset_field.value
            print(f" SIDEBAR: Got from field directly: '{dataset_name}'")  # Debug
        
        # Method 4: Force page update and try again
        else:
            print(f" SIDEBAR: Forcing page update and retrying...")  # Debug
            self.page.update()
            dataset_name = self.new_dataset_field.value
            print(f" SIDEBAR: Got after page update: '{dataset_name}'")  # Debug
        
        print(f" SIDEBAR: Final dataset name: '{dataset_name}'")  # Debug
        
        if dataset_name and dataset_name.strip():
            print(f"✅ SIDEBAR: Valid dataset name: '{dataset_name.strip()}'")  # Debug
            
            # Check current datasets before adding
            current_datasets = self.settings.get_datasets()
            print(f" SIDEBAR: Current datasets: {current_datasets}")  # Debug
            
            self.settings.add_dataset(dataset_name.strip())
            
            # Check datasets after adding
            updated_datasets = self.settings.get_datasets()
            print(f" SIDEBAR: Updated datasets: {updated_datasets}")  # Debug
            
            # Clear both the field and stored value
            self.new_dataset_field.value = ""
            if hasattr(self, 'current_dataset_input'):
                self.current_dataset_input = ""
            print(f" SIDEBAR: Field and input cleared")  # Debug
            
            self.update_datasets_display()
            print(f" SIDEBAR: Display updated")  # Debug
            
            # Sync with center panel if available
            if self.center_panel:
                print(f" SIDEBAR: Syncing with center panel")  # Debug
                self.center_panel.update_datasets_display()
            else:
                print(f"  SIDEBAR: No center panel reference")  # Debug
            
            self.page.update()
            print(f"✅ SIDEBAR: Page updated")  # Debug
        else:
            print(f"❌ SIDEBAR: Invalid dataset name: '{dataset_name}'")  # Debug
            # Let's also check what's actually in the text field
            print(f" SIDEBAR: Text field value debug: '{self.new_dataset_field.value}'")  # Debug
            print(f" SIDEBAR: Text field object: {self.new_dataset_field}")  # Debug
    
    def remove_dataset(self, dataset_name):
        """Remove dataset"""
        def _remove(e):
            self.settings.remove_dataset(dataset_name)
            self.update_datasets_display()
            # Sync with center panel if available
            if self.center_panel:
                self.center_panel.update_datasets_display()
            self.page.update()
        return _remove
    
    def toggle_keys(self, e):
        """Toggle API keys section"""
        self.keys_open = not self.keys_open
        self.keys_chevron.name = ft.icons.KEYBOARD_ARROW_UP if self.keys_open else ft.icons.KEYBOARD_ARROW_DOWN
        self.keys_content.visible = self.keys_open
        self.page.update()
    
    def update_datasets_display(self):
        """Update the datasets display"""
        print(f" SIDEBAR: update_datasets_display called")  # Debug
        
        self.datasets_container.controls.clear()
        print(f" SIDEBAR: Container cleared")  # Debug
        
        datasets = self.settings.get_datasets()
        print(f" SIDEBAR: Retrieved datasets: {datasets}")  # Debug
        
        if not datasets:
            print(f" SIDEBAR: No datasets, showing empty message")  # Debug
            self.datasets_container.controls.append(
                ft.Text(
                    "No datasets active.",
                    size=11,
                    color=Colors.INK_MUTED,
                    italic=True
                )
            )
        else:
            print(f" SIDEBAR: Creating {len(datasets)} dataset badges")  # Debug
            # Create badges in a wrapping row
            badges_row = ft.Row(controls=[], wrap=True, spacing=6, run_spacing=6)
            for dataset in datasets:
                print(f"🏷️  SIDEBAR: Creating badge for: '{dataset}'")  # Debug
                badge = ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                dataset,
                                size=12,
                                color=Colors.INK
                            ),
                            ft.IconButton(
                                icon=ft.icons.CLOSE,
                                icon_size=12,
                                icon_color=Colors.INK_MUTED,
                                on_click=self.remove_dataset(dataset),
                                width=20,
                                height=20,
                                style=ft.ButtonStyle(
                                    padding=ft.padding.all(0)
                                )
                            )
                        ],
                        spacing=4,
                        tight=True
                    ),
                    bgcolor=Colors.SURFACE_RAISED,
                    border=ft.border.all(1, Colors.DIVIDER),
                    border_radius=4,
                    padding=ft.padding.only(left=10, right=4, top=4, bottom=4)
                )
                badges_row.controls.append(badge)
            self.datasets_container.controls.append(badges_row)
            print(f"✅ SIDEBAR: Added badges row with {len(badges_row.controls)} badges")  # Debug
    
    def build(self):
        """Build sidebar"""
        self.update_datasets_display()
        
        # Logo using asset path - moved up with reduced top padding
        logo_container = ft.Container(
            content=ft.Image(
                src="/stimme-logo.png",
                width=160,
                height=100,
                fit=ft.ImageFit.CONTAIN
            ),
            alignment=ft.alignment.center,
            padding=ft.padding.only(top=12, bottom=16)  # Reduced from top=24, bottom=24
        )
        
        return ft.Container(
            content=ft.Column(
                controls=[
                    logo_container,
                    
                    # Model section
                    self._section_header("MODEL", self.monk_icon),
                    self.model_dropdown,
                    
                    ft.Container(height=16),  # Reduced from 24
                    
                    # Scholar mode section
                    self._section_header("SCHOLAR MODE", self.quill_icon),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Philological commentary",
                                            size=13,
                                            color=Colors.FOREGROUND
                                        ),
                                        ft.Text(
                                            "Annotate the translation",
                                            size=11,
                                            color=Colors.INK_MUTED
                                        )
                                    ],
                                    spacing=2,
                                    expand=True
                                ),
                                self.scholar_mode_switch
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        ),
                        bgcolor=Colors.SURFACE,
                        border=ft.border.all(1, Colors.DIVIDER),
                        border_radius=6,
                        padding=ft.padding.all(12)
                    ),
                    
                    ft.Container(height=16),  # Reduced from 24
                    
                    # Thematic focus section
                    self._section_header("THEMATIC FOCUS"),
                    self.thematic_focus,
                    
                    ft.Container(height=16),  # Reduced from 24
                    
                    # Datasets section
                    self._section_header("DATASETS", self.book_icon),
                    self.datasets_container,
                    ft.Container(
                        content=self.add_dataset_btn,
                        alignment=ft.alignment.center_left
                    ),
                    
                    ft.Container(height=16),  # Reduced from 32
                    
                    # Export Directory section
                    self._section_header("EXPORT DIRECTORY", self.scroll_icon),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Container(
                                    content=self.export_directory_field,
                                    expand=True
                                ),
                                self.browse_export_btn
                            ],
                            spacing=8
                        ),
                        bgcolor=Colors.SURFACE,
                        border=ft.border.all(1, Colors.DIVIDER),
                        border_radius=6,
                        padding=ft.padding.all(12)
                    ),
                    
                    ft.Container(height=16),  # Reduced from 32
                    
                    # API Keys section (collapsible) - fixed height container to prevent layout shift
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.GestureDetector(
                                    content=ft.Row(
                                        controls=[
                                            self.key_icon.build(),
                                            ft.Text(
                                                "API KEYS",
                                                size=10,
                                                font_family=Fonts.HEADER,
                                                weight=ft.FontWeight.W_700,
                                                color=Colors.INK_MUTED
                                            ),
                                            ft.Container(expand=True),
                                            self.api_status_icon,
                                            self.keys_chevron
                                        ],
                                        spacing=8
                                    ),
                                    on_tap=self.toggle_keys,
                                    mouse_cursor=ft.MouseCursor.CLICK
                                ),
                                ft.Container(
                                    content=self.keys_content,
                                    padding=ft.padding.only(top=12)
                                )
                            ],
                            spacing=0
                        ),
                        padding=ft.padding.only(top=12, bottom=20)
                    ),
                ],
                spacing=8,
                scroll=ft.ScrollMode.HIDDEN  # Hide scrollbar but maintain scroll functionality
            ),
            padding=ft.padding.all(20),
            width=288,
            bgcolor=Colors.SIDEBAR_BG,
            border=ft.border.only(left=ft.BorderSide(1, Colors.DIVIDER)),
            expand=True  # Allow the container to expand and handle overflow
        )
    
    def _section_header(self, title: str, icon=None):
        """Create a section header"""
        controls = []
        if icon:
            controls.append(icon.build())
        controls.append(
            ft.Text(
                title,
                size=10,
                font_family=Fonts.HEADER,
                weight=ft.FontWeight.W_700,
                color=Colors.INK_MUTED
            )
        )
        
        return ft.Container(
            content=ft.Row(
                controls=controls,
                spacing=8
            ),
            padding=ft.padding.only(bottom=8)
        )