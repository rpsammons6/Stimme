import flet as ft
from app.contexts.settings import SettingsManager
from app.theme import Colors, Fonts
from app.components.img_icon import ImgIcon
from app.components.pdf_viewer import PDFViewer

class CenterPanel:
    """Tabbed workspace panel shown BEFORE translation"""
    
    def __init__(self, page: ft.Page, settings: SettingsManager, sidebar=None):
        self.page = page
        self.settings = settings
        self.sidebar = sidebar  # Reference to sidebar for syncing
        
        # Icons
        self.quill_icon = ImgIcon("icon-quill.png", 28, 28)
        self.book_icon = ImgIcon("icon-book.png", 28, 28)
        self.sun_welcome_icon = ImgIcon("sun-welcome.png", 28, 28)  # Add welcome icon
        
        # Current tab
        self.current_tab = 0
        
        # PDF state and viewer
        self.pdf_file = None
        self.pdf_path = None  # Store the actual file path
        self.pdf_viewer = PDFViewer(page)
        
        # Commentary state
        self.commentary = None
        
        # Thematic focus textarea (synced with sidebar)
        self.thematic_focus = ft.TextField(
            multiline=True,
            min_lines=15,
            max_lines=20,
            value=settings.get_thematic_focus(),
            on_change=self.on_thematic_focus_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            hint_text="e.g. Render in a theological register, preserving Lutheran cadence. Favor archaic English where the German is elevated…",
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED,
                italic=True,
                size=15,
                font_family=Fonts.SERIF
            ),
            text_style=ft.TextStyle(
                size=15,
                font_family=Fonts.SERIF,
                italic=True
            ),
            content_padding=ft.padding.all(16)
        )
        
        # Datasets
        self.datasets_container = ft.Column(spacing=8)
        
        self.add_dataset_btn = ft.IconButton(
            icon=ft.icons.ADD,
            icon_color=Colors.FOREGROUND,
            icon_size=20,
            bgcolor=Colors.SURFACE_RAISED,
            on_click=self.on_add_button_click,  # Use custom handler
            width=44,
            height=44,
            style=ft.ButtonStyle(
                padding=ft.padding.all(0)
            ),
            tooltip="Select datasets from lancedb_vectors folder"
        )
        
        # Build tabs
        self.tabs = None
        self.rebuild_tabs()
    
    def on_thematic_focus_change(self, e):
        """Sync thematic focus with settings"""
        new_value = self.thematic_focus.value
        self.settings.set_thematic_focus(new_value)
        # Sync with sidebar if available (prevent circular updates)
        if self.sidebar and self.sidebar.thematic_focus.value != new_value:
            self.sidebar.thematic_focus.value = new_value
            self.page.update()
    
    def update_thematic_focus(self, value: str):
        """Update thematic focus from external source (e.g., sidebar)"""
        if self.thematic_focus.value != value:
            self.thematic_focus.value = value
            # No page.update() here to prevent circular updates
    
    def on_add_button_click(self, e):
        """Handle add button click - show dataset file picker"""
        print(f" CENTER_PANEL: Add button clicked - showing dataset picker")  # Debug
        
        # Scan lancedb_vectors folder for CSV files
        import os
        from pathlib import Path
        
        lancedb_path = Path(__file__).parent.parent.parent / "lancedb_vectors"
        print(f" CENTER_PANEL: Scanning folder: {lancedb_path}")  # Debug
        
        available_datasets = []
        if lancedb_path.exists():
            for file in lancedb_path.glob("*.csv"):
                dataset_name = file.stem  # filename without extension
                available_datasets.append(dataset_name)
                print(f" CENTER_PANEL: Found dataset: {dataset_name}")  # Debug
        
        if not available_datasets:
            print(f"  CENTER_PANEL: No CSV files found in lancedb_vectors folder")  # Debug
            # Show info dialog
            info_dialog = ft.AlertDialog(
                title=ft.Text(
                    "No Datasets Available",
                    font_family=Fonts.HEADER,
                    weight=ft.FontWeight.W_600,
                    color=Colors.FOREGROUND
                ),
                content=ft.Text(
                    f"No CSV files found in the lancedb_vectors folder.\n\n"
                    f"To add datasets:\n"
                    f"1. Place CSV files in: {lancedb_path}\n"
                    f"2. Click the + button to select them",
                    font_family=Fonts.SERIF,
                    color=Colors.INK_MUTED
                ),
                actions=[
                    ft.ElevatedButton(
                        "OK", 
                        on_click=lambda e: self.close_dialog(info_dialog),
                        bgcolor=Colors.GOLD,
                        color=Colors.BACKGROUND,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=6)
                        )
                    )
                ],
                bgcolor=Colors.BACKGROUND,
                shape=ft.RoundedRectangleBorder(radius=12)
            )
            self.page.dialog = info_dialog
            info_dialog.open = True
            self.page.update()
            return
        
        # Get currently active datasets
        current_datasets = set(self.settings.get_datasets())
        print(f" CENTER_PANEL: Current active datasets: {current_datasets}")  # Debug
        
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
            print(f" CENTER_PANEL: Applying dataset selection")  # Debug
            
            # Get selected datasets
            selected_datasets = []
            for checkbox in dataset_checkboxes:
                if checkbox.value:
                    selected_datasets.append(checkbox.data)
                    print(f"✅ CENTER_PANEL: Selected: {checkbox.data}")  # Debug
            
            # Update settings with selected datasets
            self.settings.settings["datasets"] = selected_datasets
            self.settings.save_settings()
            print(f" CENTER_PANEL: Saved datasets: {selected_datasets}")  # Debug
            
            # Update displays
            self.rebuild_tabs()
            if self.sidebar:
                self.sidebar.update_datasets_display()
            
            # Close dialog
            picker_dialog.open = False
            self.page.update()
        
        # Create dataset picker dialog
        picker_dialog = ft.AlertDialog(
            title=ft.Text(
                "Select Datasets",
                font_family=Fonts.HEADER,
                weight=ft.FontWeight.W_600,
                color=Colors.FOREGROUND
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Select which datasets to activate:",
                            size=14,
                            color=Colors.INK_MUTED,
                            font_family=Fonts.SERIF
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
                height=300,
                bgcolor=Colors.SURFACE,
                border=ft.border.all(1, Colors.DIVIDER),
                border_radius=6,
                padding=ft.padding.all(16)
            ),
            actions=[
                ft.TextButton(
                    "Cancel", 
                    on_click=lambda e: self.close_dialog(picker_dialog),
                    style=ft.ButtonStyle(color=Colors.INK_MUTED)
                ),
                ft.ElevatedButton(
                    "Apply", 
                    on_click=on_apply_selection,
                    bgcolor=Colors.GOLD,
                    color=Colors.BACKGROUND,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=6)
                    )
                )
            ],
            bgcolor=Colors.BACKGROUND,
            shape=ft.RoundedRectangleBorder(radius=12)
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
        print(f" CENTER_PANEL: Dataset input changed to: '{self.current_dataset_input}'")  # Debug
    
    def add_dataset(self, e):
        """Add new dataset"""
        print(f" CENTER_PANEL: add_dataset called")  # Debug
        
        # Use the stored input value or try to get from field
        dataset_name = self.current_dataset_input or self.new_dataset_field.value
        print(f" CENTER_PANEL: Dataset name: '{dataset_name}'")  # Debug
        
        if dataset_name and dataset_name.strip():
            print(f"✅ CENTER_PANEL: Valid dataset name: '{dataset_name.strip()}'")  # Debug
            
            # Check current datasets before adding
            current_datasets = self.settings.get_datasets()
            print(f" CENTER_PANEL: Current datasets: {current_datasets}")  # Debug
            
            self.settings.add_dataset(dataset_name.strip())
            
            # Check datasets after adding
            updated_datasets = self.settings.get_datasets()
            print(f" CENTER_PANEL: Updated datasets: {updated_datasets}")  # Debug
            
            # Clear both the field and stored value
            self.new_dataset_field.value = ""
            self.current_dataset_input = ""
            print(f" CENTER_PANEL: Field and input cleared")  # Debug
            
            self.rebuild_tabs()  # Rebuild tabs to update datasets tab
            print(f" CENTER_PANEL: Tabs rebuilt")  # Debug
            
            # Sync with sidebar if available
            if self.sidebar:
                print(f" CENTER_PANEL: Syncing with sidebar")  # Debug
                self.sidebar.update_datasets_display()
            else:
                print(f"  CENTER_PANEL: No sidebar reference")  # Debug
            
            self.page.update()
            print(f"✅ CENTER_PANEL: Page updated")  # Debug
        else:
            print(f"❌ CENTER_PANEL: Invalid dataset name: '{dataset_name}'")  # Debug
    
    def remove_dataset(self, dataset_name):
        """Remove dataset"""
        def _remove(e):
            self.settings.remove_dataset(dataset_name)
            self.rebuild_tabs()  # Rebuild tabs to update datasets tab
            # Sync with sidebar if available
            if self.sidebar:
                self.sidebar.update_datasets_display()
            self.page.update()
        return _remove
    
    def update_datasets_display(self):
        """Update the datasets display"""
        self.datasets_container.controls.clear()
        
        datasets = self.settings.get_datasets()
        if not datasets:
            self.datasets_container.controls.append(
                ft.Text(
                    "None active.",
                    size=14,
                    color=Colors.INK_MUTED,
                    italic=True,
                    font_family=Fonts.SERIF
                )
            )
        else:
            # Create badges in a wrapping row
            badges_row = ft.Row(controls=[], wrap=True, spacing=8, run_spacing=8)
            for dataset in datasets:
                badge = ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                dataset,
                                size=13,
                                color=Colors.INK
                            ),
                            ft.IconButton(
                                icon=ft.icons.CLOSE,
                                icon_size=14,
                                icon_color=Colors.INK_MUTED,
                                on_click=self.remove_dataset(dataset),
                                width=24,
                                height=24,
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
                    padding=ft.padding.only(left=12, right=4, top=6, bottom=6)
                )
                badges_row.controls.append(badge)
            self.datasets_container.controls.append(badges_row)
    
    def set_commentary(self, commentary: str):
        """Set commentary and rebuild tabs"""
        self.commentary = commentary
        self.rebuild_tabs()
    
    def set_pdf_file(self, pdf_file, pdf_path=None):
        """Set PDF file and rebuild tabs"""
        self.pdf_file = pdf_file
        self.pdf_path = pdf_path
        if pdf_path:
            self.pdf_viewer.load_pdf(pdf_path, pdf_file)
        self.rebuild_tabs()
        self.page.update()  # Force UI update
    
    def clear_pdf(self):
        """Clear PDF file and rebuild tabs"""
        self.pdf_file = None
        self.pdf_path = None
        self.pdf_viewer.cleanup()
        self.rebuild_tabs()
        self.page.update()  # Force UI update
    
    def rebuild_tabs(self):
        """Rebuild tabs based on current state"""
        # Create content for each tab type
        welcome_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Image(
                            src="/stimme-s.png",
                            width=192,
                            height=192,
                            fit=ft.ImageFit.CONTAIN,
                            opacity=0.9
                        ),
                        alignment=ft.alignment.center,
                        padding=ft.padding.only(bottom=16)
                    ),
                    ft.Container(
                        content=ft.Text(
                            "A scholarly workbench for the careful rendering of German into English.\nEnter or upload a passage to begin.",
                            size=15,
                            color=Colors.INK_MUTED,
                            text_align=ft.TextAlign.CENTER,
                            italic=True,
                            font_family=Fonts.SERIF
                        ),
                        width=420,
                        padding=ft.padding.symmetric(horizontal=32)
                    ),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Container(
                                    content=ft.Container(
                                        bgcolor=Colors.GOLD,
                                        height=1,
                                        opacity=0.4
                                    ),
                                    expand=True
                                ),
                                ft.Text(
                                    "✦",
                                    size=16,
                                    color=Colors.GOLD,
                                    opacity=0.7
                                ),
                                ft.Container(
                                    content=ft.Container(
                                        bgcolor=Colors.GOLD,
                                        height=1,
                                        opacity=0.4
                                    ),
                                    expand=True
                                )
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=16
                        ),
                        width=128,
                        margin=ft.margin.only(top=32, bottom=16)
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=0
            ),
            alignment=ft.alignment.center,
            expand=True
        )
        
        # Thematic Focus content
        focus_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            self.quill_icon.build(),
                            ft.Text(
                                "Thematic Focus",
                                size=24,
                                font_family=Fonts.HEADER,
                                weight=ft.FontWeight.W_600
                            )
                        ],
                        spacing=8
                    ),
                    ft.Text(
                        "Guide the translator's voice — register, theological inflection, period diction, scholarly emphasis.",
                        size=14,
                        color=Colors.INK_MUTED,
                        italic=True,
                        font_family=Fonts.SERIF
                    ),
                    ft.Container(
                        content=self.thematic_focus,
                        expand=True
                    ),
                    ft.Text(
                        "Saved automatically. Mirrors the sidebar field.",
                        size=11,
                        color=Colors.INK_MUTED,
                        font_family=Fonts.SERIF
                    )
                ],
                spacing=16,
                expand=True
            ),
            padding=ft.padding.all(32),
            expand=True
        )
        
        # Datasets content
        self.update_datasets_display()
        datasets_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            self.book_icon.build(),
                            ft.Text(
                                "Datasets",
                                size=24,
                                font_family=Fonts.HEADER,
                                weight=ft.FontWeight.W_600
                            )
                        ],
                        spacing=8
                    ),
                    ft.Text(
                        "Lexicons, idiom registers, and reference corpora consulted during translation.",
                        size=14,
                        color=Colors.INK_MUTED,
                        italic=True,
                        font_family=Fonts.SERIF
                    ),
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Text(
                                    "ACTIVE",
                                    size=11,
                                    font_family=Fonts.HEADER,
                                    weight=ft.FontWeight.W_700,
                                    color=Colors.INK_MUTED
                                ),
                                self.datasets_container,
                                ft.Container(
                                    content=self.add_dataset_btn,
                                    alignment=ft.alignment.center_left
                                )
                            ],
                            spacing=12
                        ),
                        bgcolor=Colors.SURFACE,
                        border=ft.border.all(1, Colors.DIVIDER),
                        border_radius=6,
                        padding=ft.padding.all(16)
                    ),
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Text(
                                    "PREVIEW",
                                    size=11,
                                    font_family=Fonts.HEADER,
                                    weight=ft.FontWeight.W_700,
                                    color=Colors.INK_MUTED
                                ),
                                ft.Text(
                                    "Dataset previews will be available in a future release. Active datasets above are passed to the translator.",
                                    size=14,
                                    color=Colors.INK_MUTED,
                                    italic=True,
                                    font_family=Fonts.SERIF
                                )
                            ],
                            spacing=8
                        ),
                        bgcolor=Colors.SURFACE,
                        border=ft.border.all(1, Colors.DIVIDER),
                        border_radius=6,
                        padding=ft.padding.all(16)
                    )
                ],
                spacing=16,
                expand=True
            ),
            padding=ft.padding.all(32),
            expand=True
        )
        
        # Create custom tabs with icons
        tab_headers = []
        tab_contents = []
        
        # Welcome tab (only if no PDF)
        if not self.pdf_file:
            welcome_header = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Image(
                            src="/sun-welcome.png",
                            width=16,
                            height=16,
                            fit=ft.ImageFit.CONTAIN
                        ),
                        ft.Text("Welcome", size=14, font_family=Fonts.SERIF)
                    ],
                    spacing=6,
                    alignment=ft.MainAxisAlignment.CENTER
                ),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                bgcolor=Colors.SURFACE if self.current_tab != 0 else Colors.BACKGROUND,
                border_radius=ft.border_radius.only(top_left=6, top_right=6),
                on_click=lambda e: self.switch_tab(0)
            )
            tab_headers.append(welcome_header)
            tab_contents.append(welcome_content)
        
        # PDF tab (only if PDF is loaded)
        if self.pdf_file:
            pdf_header = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.icons.PICTURE_AS_PDF, size=16),
                        ft.Text("PDF", size=14, font_family=Fonts.SERIF)
                    ],
                    spacing=6,
                    alignment=ft.MainAxisAlignment.CENTER
                ),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                bgcolor=Colors.SURFACE if self.current_tab != (1 if not self.pdf_file else 0) else Colors.BACKGROUND,
                border_radius=ft.border_radius.only(top_left=6, top_right=6),
                on_click=lambda e: self.switch_tab(1 if not self.pdf_file else 0)
            )
            tab_headers.append(pdf_header)
            tab_contents.append(self.pdf_viewer.build())
        
        # Commentary tab (only if Scholar Mode is on)
        if self.settings.get_scholar_mode():
            commentary_idx = len(tab_headers)
            commentary_header = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Image(
                            src="/icon-quill.png",
                            width=16,
                            height=16,
                            fit=ft.ImageFit.CONTAIN
                        ),
                        ft.Text("Commentary", size=14, font_family=Fonts.SERIF)
                    ],
                    spacing=6,
                    alignment=ft.MainAxisAlignment.CENTER
                ),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                bgcolor=Colors.SURFACE if self.current_tab != commentary_idx else Colors.BACKGROUND,
                border_radius=ft.border_radius.only(top_left=6, top_right=6),
                on_click=lambda e: self.switch_tab(commentary_idx)
            )
            tab_headers.append(commentary_header)
            
            if self.commentary:
                commentary_content = ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Container(
                                content=ft.Row(
                                    controls=[
                                        ft.Container(
                                            content=ft.Container(
                                                bgcolor=Colors.GOLD,
                                                height=1,
                                                opacity=0.4
                                            ),
                                            expand=True
                                        ),
                                        ft.Text(
                                            "❦ Philological Commentary ❦",
                                            size=14,
                                            color=Colors.GOLD,
                                            font_family=Fonts.SERIF,
                                            opacity=0.9
                                        ),
                                        ft.Container(
                                            content=ft.Container(
                                                bgcolor=Colors.GOLD,
                                                height=1,
                                                opacity=0.4
                                            ),
                                            expand=True
                                        )
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=16
                                ),
                                margin=ft.margin.only(bottom=24)
                            ),
                            ft.Markdown(
                                value=self.commentary,
                                selectable=True,
                                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                                code_theme="monokai"
                            )
                        ],
                        scroll=ft.ScrollMode.HIDDEN
                    ),
                    padding=ft.padding.all(32),
                    expand=True
                )
            else:
                commentary_content = ft.Container(
                    content=ft.Text(
                        "Commentary will appear here after a translation with Scholar Mode enabled.",
                        size=14,
                        color=Colors.INK_MUTED,
                        text_align=ft.TextAlign.CENTER,
                        italic=True,
                        font_family=Fonts.SERIF
                    ),
                    alignment=ft.alignment.center,
                    expand=True,
                    padding=ft.padding.all(32)
                )
            tab_contents.append(commentary_content)
        
        # Thematic Focus tab (always visible)
        focus_idx = len(tab_headers)
        focus_header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.icons.PALETTE, size=16),
                    ft.Text("Thematic Focus", size=14, font_family=Fonts.SERIF)
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            bgcolor=Colors.SURFACE if self.current_tab != focus_idx else Colors.BACKGROUND,
            border_radius=ft.border_radius.only(top_left=6, top_right=6),
            on_click=lambda e: self.switch_tab(focus_idx)
        )
        tab_headers.append(focus_header)
        tab_contents.append(focus_content)
        
        # Datasets tab (always visible)
        datasets_idx = len(tab_headers)
        datasets_header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Image(
                        src="/icon-book.png",
                        width=16,
                        height=16,
                        fit=ft.ImageFit.CONTAIN
                    ),
                    ft.Text("Datasets", size=14, font_family=Fonts.SERIF)
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            bgcolor=Colors.SURFACE if self.current_tab != datasets_idx else Colors.BACKGROUND,
            border_radius=ft.border_radius.only(top_left=6, top_right=6),
            on_click=lambda e: self.switch_tab(datasets_idx)
        )
        tab_headers.append(datasets_header)
        tab_contents.append(datasets_content)
        
        # Create custom tab system
        custom_tabs = ft.Column(
            controls=[
                # Tab headers
                ft.Container(
                    content=ft.Row(
                        controls=tab_headers,
                        spacing=2
                    ),
                    bgcolor=Colors.SURFACE,
                    padding=ft.padding.only(left=8, top=4)
                ),
                # Active tab content
                ft.Container(
                    content=tab_contents[self.current_tab] if tab_contents else ft.Container(),
                    expand=True
                )
            ],
            spacing=0,
            expand=True
        )
        
        # Update the tabs reference
        self.tabs = custom_tabs
        
        # Update container content if it exists (after build() has been called)
        if hasattr(self, 'container'):
            self.container.content = self.tabs
    
    def switch_tab(self, index: int):
        """Switch to a specific tab"""
        self.current_tab = index
        self.rebuild_tabs()
        self.page.update()
    
    def on_tab_change(self, e):
        """Handle tab change"""
        self.current_tab = e.control.selected_index
    
    def build(self):
        """Build the center panel with proper scrolling"""
        # Store container reference so we can update it
        self.container = ft.Container(
            content=self.tabs,
            expand=True,
            bgcolor=Colors.BACKGROUND  # Match main background
        )
        return self.container
