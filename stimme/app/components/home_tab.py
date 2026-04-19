import flet as ft
import os
import threading
from app.components.input_panel import InputPanel
from app.components.output_panel import OutputPanel
from app.components.center_panel import CenterPanel
from app.components.history_view import HistoryView
from app.components.loading_screen import LoadingScreen
from app.contexts.workspace import WorkspaceManager
from app.contexts.settings import SettingsManager
from app.services.translation_service import TranslationService
from app.theme import Colors, Fonts
from app.components.img_icon import ImgIcon
from app.services.pdf_import import PDFImportService
from app.constants import ERROR_NO_TEXT, SUCCESS_TRANSLATION, HTML_TEMPLATE

class HomeTab:
    def __init__(self, page: ft.Page, workspace: WorkspaceManager, settings: SettingsManager):
        self.page = page
        self.workspace = workspace
        self.settings = settings
        
        # Initialize translation service
        self.translation_service = TranslationService(settings)
        
        self.input_panel = InputPanel(workspace)
        self.output_panel = OutputPanel()
        
        # Create sidebar and center panel with cross-references for syncing
        self.sidebar = None  # Will be set by shell
        self.shell = None    # Will be set by shell
        self.center_panel = CenterPanel(page, settings, sidebar=None)
        
        self.history_view = HistoryView(page)
        
        # Track if we have a translation
        self.has_translation = False
        
        # Check OCR availability on startup
        self.ocr_available = self._check_ocr_availability()
        
        # Create scroll icon for history button
        self.scroll_icon = ImgIcon("icon-scroll.png", 24, 24)
        
        self.translate_btn = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.icons.TRANSLATE, size=20),
                    ft.Text(
                        "Translate",
                        font_family=Fonts.FRAKTUR,
                        size=16,
                        weight=ft.FontWeight.BOLD
                    )
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER
            ),
            on_click=self.on_translate,
            bgcolor=Colors.GOLD,
            color=Colors.BACKGROUND,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6)
            ),
            height=36
        )
        
        self.upload_btn = ft.OutlinedButton(
            text="Upload",
            on_click=self.on_upload,
            icon=ft.icons.UPLOAD_FILE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
                side=ft.BorderSide(1, Colors.DIVIDER)
            ),
            height=36
        )
        
        self.export_btn = ft.OutlinedButton(
            text="Export",
            on_click=self.on_export,
            icon=ft.icons.DOWNLOAD,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
                side=ft.BorderSide(1, Colors.DIVIDER)
            ),
            height=36
        )
        
        self.history_btn = ft.TextButton(
            content=ft.Row(
                controls=[
                    self.scroll_icon.build(),
                    ft.Text("History", size=14)
                ],
                spacing=8
            ),
            on_click=self.on_history,
            height=36
        )
        
        # File picker
        self.file_picker = ft.FilePicker(
            on_result=self.on_file_picked
        )
        self.page.overlay.append(self.file_picker)
        
        self.loading = False
        self.current_pdf_file = None
        
        # Loading screen for file processing
        self.loading_screen = LoadingScreen(page)
        self.processing_cancelled = False
        self.processing_thread = None
        self.processing_result = None  # Store result from background thread
        self.processing_timer = None   # Timer to check for completion
        
        # Resizable panels state
        self.left_width = 0.5  # 50% initially
        self.is_dragging = False
        self.drag_start_x = 0
        
    def on_pan_start(self, e: ft.DragStartEvent):
        """Handle drag start"""
        self.is_dragging = True
        self.drag_start_x = e.global_x
    
    def on_pan_update(self, e: ft.DragUpdateEvent):
        """Handle drag update"""
        if not self.is_dragging:
            return
        
        # Calculate new width based on drag delta
        container_width = self.page.window_width - 288  # Subtract sidebar width
        delta_x = e.global_x - self.drag_start_x
        delta_percent = delta_x / container_width
        
        new_width = self.left_width + delta_percent
        # Clamp between 30% and 70%
        new_width = max(0.3, min(0.7, new_width))
        
        self.left_width = new_width
        self.drag_start_x = e.global_x
        
        # Rebuild the content area
        self.rebuild_content()
    
    def on_pan_end(self, e: ft.DragEndEvent):
        """Handle drag end"""
        self.is_dragging = False
    
    def rebuild_content(self):
        """Rebuild the content area with new panel sizes"""
        # This will be called by the parent to update the layout
        self.page.update()
    
    def on_translate(self, e):
        """Handle translate button click"""
        print("TRANSLATE: Button clicked!")  # Debug
        
        text = self.input_panel.get_text()
        print(f"TRANSLATE: Input text length: {len(text)}")  # Debug
        
        if not text.strip():
            self.show_error(ERROR_NO_TEXT)
            return
        
        # Check API key
        has_key = self.settings.has_api_key()
        print(f"🔑 TRANSLATE: Has API key: {has_key}")  # Debug
        
        if not has_key:
            self.show_error("API key is missing. Please configure it in the sidebar.")
            return
        
        # Check internet connectivity
        print(" TRANSLATE: Checking internet connectivity...")  # Debug
        from app.utils.network import check_internet_connection
        
        if not check_internet_connection():
            print("❌ TRANSLATE: No internet connection")  # Debug
            self.show_error("No internet connection detected. Translation requires an active internet connection to reach the Anthropic API. Please check your network and try again.")
            return
        
        print("✅ TRANSLATE: Internet connection confirmed")  # Debug
        print(f"TRANSLATE: Shell reference exists: {hasattr(self, 'shell') and self.shell is not None}")  # Debug
        
        # Set loading state
        self.loading = True
        self.translate_btn.disabled = True
        self.translate_btn.text = "Translating..."
        self.translate_btn.icon = ft.icons.HOURGLASS_EMPTY
        self.page.update()
        
        try:
            print("🧠 TRANSLATE: Calling translation service...")  # Debug
            # Call the translation service synchronously
            success, translation, commentary, metrics = self.translation_service.translate_sync(text)
            print(f"✅ TRANSLATE: Translation result - success: {success}")  # Debug
            
            if success:
                print(" TRANSLATE: Translation successful, adding result...")  # Debug
                # Add translation result to workspace and create new tab
                if hasattr(self, 'shell') and self.shell:
                    print("  TRANSLATE: Calling shell.add_translation_result...")  # Debug
                    self.shell.add_translation_result(
                        source_text=text,
                        translation=translation,
                        commentary=commentary,
                        metrics=metrics
                    )
                    print("✅ TRANSLATE: Shell method completed")  # Debug
                else:
                    print("  TRANSLATE: No shell reference, using fallback...")  # Debug
                    # Fallback: show in output panel (old behavior)
                    self.output_panel.set_translation(
                        translation=translation,
                        model=metrics.get("model_used", "Unknown") if metrics else "Unknown",
                        commentary=commentary,
                        metrics=metrics
                    )
                    self.has_translation = True
                    self.rebuild_workspace()
                
                # Also set commentary in center panel for the Commentary tab
                if commentary:
                    self.center_panel.set_commentary(commentary)
                
                self.show_success(SUCCESS_TRANSLATION)
                
            else:
                print(f"❌ TRANSLATE: Translation failed: {translation}")  # Debug
                # Show error from translation service
                self.show_error(translation)  # translation contains error message
                
        except Exception as ex:
            print(f" TRANSLATE: Exception occurred: {ex}")  # Debug
            import traceback
            traceback.print_exc()
            self.show_error(f"Translation failed: {str(ex)}")
        
        finally:
            print(" TRANSLATE: Resetting loading state...")  # Debug
            # Reset loading state
            self.loading = False
            self.translate_btn.disabled = False
            self.translate_btn.text = "Translate"
            self.translate_btn.icon = ft.icons.TRANSLATE
            self.page.update()
            print("✅ TRANSLATE: Process complete")  # Debug
    
    def on_upload(self, e):
        """Handle file upload"""
        self.file_picker.pick_files(
            dialog_title="Select file to upload",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf", "txt", "md", "png", "jpg", "jpeg", "tiff", "bmp"]
        )
    
    def on_file_picked(self, e: ft.FilePickerResultEvent):
        """Handle file picker result"""
        print(f" FILE_PICKER: File picker result received")  # Debug
        
        if not e.files:
            print("❌ FILE_PICKER: No files selected")  # Debug
            return
        
        file = e.files[0]
        file_path = file.path
        file_name = file.name
        
        print(f" FILE_PICKER: Selected file: {file_name}")  # Debug
        print(f" FILE_PICKER: File path: {file_path}")  # Debug
        
        try:
            if not PDFImportService.is_supported_file(file_name):
                print(f"❌ FILE_PICKER: Unsupported file type: {file_name}")  # Debug
                self.show_error("Unsupported file type. Please select .pdf, .txt, .md, or image files (.png, .jpg, .jpeg, .tiff, .bmp).")
                return
            
            print(f"✅ FILE_PICKER: File type supported")  # Debug
            
            # Check if there's already text in the input panel (prevent multiple uploads)
            existing_text = self.input_panel.get_text()
            if existing_text and existing_text.strip():
                print(f"FILE_PICKER: Text already exists in input panel ({len(existing_text)} chars)")  # Debug
                print("FILE_PICKER: Showing error message to user")  # Debug
                self.show_error(
                    "Text already exists in the input panel. Please translate the current text or clear it before uploading a new file."
                )
                print("FILE_PICKER: Error message displayed, returning")  # Debug
                return
            
            print(f"✅ FILE_PICKER: Input panel is clear, proceeding with upload")  # Debug
            
            # For text files, process immediately without loading screen
            if file_name.lower().endswith(('.txt', '.md')):
                print(f" FILE_PICKER: Processing text file")  # Debug
                text = PDFImportService.read_text_file(file_path)
                
                if not text.strip():
                    self.show_error("No text found in the file.")
                    return
                
                self.input_panel.set_text(text)
                self.show_success(f"Loaded {file_name}")
                self.page.update()
                return
            
            # For PDF and image files, use loading screen and background processing
            self.processing_cancelled = False
            
            # Clear any existing PDF from center panel before processing new one
            if file_name.lower().endswith('.pdf'):
                print("FILE_PICKER: Clearing previous PDF from center panel")  # Debug
                self.center_panel.clear_pdf()
                self.current_pdf_file = None
            
            # Show loading screen with cancel support
            if file_name.lower().endswith('.pdf'):
                title = "Processing PDF"
                self.current_pdf_file = file_name
            else:
                title = "Processing Image"
                self.current_pdf_file = None
            
            self.loading_screen.show(title, cancel_callback=self.cancel_processing)
            
            # Start background processing
            self.processing_thread = threading.Thread(
                target=self._process_file_background,
                args=(file_path, file_name),
                daemon=True
            )
            self.processing_thread.start()
            
            # Start timer to check for completion
            self._start_processing_timer()
            
        except Exception as ex:
            print(f" FILE_PICKER: Exception occurred: {ex}")  # Debug
            import traceback
            traceback.print_exc()
            self.show_error(f"Upload failed: {str(ex)}")
    
    def cancel_processing(self):
        """Cancel ongoing file processing"""
        print(" FILE_PROCESSING: Cancellation requested")
        self.processing_cancelled = True
        
        # Cancel OCR processing if active
        try:
            import sys
            from pathlib import Path
            sys.path.append(str(Path(__file__).parent.parent.parent / "programs"))
            from ocr_engine import OCREngine
            
            # Create a temporary OCR instance to cancel processing
            ocr = OCREngine()
            ocr.cancel_processing()
            print("✅ FILE_PROCESSING: OCR cancellation requested")
        except Exception as e:
            print(f"  FILE_PROCESSING: Could not cancel OCR: {e}")
    
    def _start_processing_timer(self):
        """Start timer to check for processing completion"""
        import time
        
        def check_completion():
            try:
                if self.processing_result is not None:
                    # Processing completed, handle result
                    result = self.processing_result
                    self.processing_result = None  # Clear result
                    
                    if self.processing_timer:
                        self.processing_timer.cancel()
                        self.processing_timer = None
                    
                    # Handle the result on main thread
                    self._handle_processing_complete(
                        result.get('text'),
                        result.get('file_name'), 
                        result.get('file_path'),  # Pass file path
                        result.get('error_message'),
                        result.get('cancelled', False)
                    )
                    return
                
                # Check if thread is still alive
                if self.processing_thread and not self.processing_thread.is_alive():
                    # Thread died without setting result - this is an error
                    if self.processing_timer:
                        self.processing_timer.cancel()
                        self.processing_timer = None
                    
                    self._handle_processing_complete(None, None, None, "Processing failed unexpectedly")
                    return
                
                # Continue checking
                if not self.processing_cancelled:
                    self.processing_timer = threading.Timer(0.1, check_completion)
                    self.processing_timer.start()
                    
            except Exception as e:
                print(f" TIMER: Error in completion check: {e}")
                if self.processing_timer:
                    self.processing_timer.cancel()
                    self.processing_timer = None
                self._handle_processing_complete(None, None, None, f"Timer error: {str(e)}")
        
        self.processing_timer = threading.Timer(0.1, check_completion)
        self.processing_timer.start()
    
    def _process_file_background(self, file_path: str, file_name: str):
        """Process file in background thread"""
        try:
            print(f" FILE_PROCESSING: Starting background processing for {file_name}")
            
            def progress_callback(message, progress):
                """Update loading screen progress"""
                if not self.processing_cancelled:
                    print(f" PROGRESS: {message} ({progress}%)")
                    try:
                        self.loading_screen.update_progress(message, progress)
                    except Exception as e:
                        print(f"  PROGRESS: Error updating progress: {e}")
            
            def cancel_callback():
                """Check if processing should be cancelled"""
                cancelled = self.processing_cancelled
                if cancelled:
                    print(" FILE_PROCESSING: Cancel callback triggered")
                return cancelled
            
            # Extract text based on file type
            if file_name.lower().endswith('.pdf'):
                text = PDFImportService.extract_pdf_text(
                    file_path, 
                    progress_callback=progress_callback,
                    cancel_callback=cancel_callback
                )
            elif file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                text = PDFImportService.extract_image_text(
                    file_path,
                    progress_callback=progress_callback,
                    cancel_callback=cancel_callback
                )
            else:
                text = PDFImportService.read_text_file(file_path)
            
            # Check if cancelled during processing
            if self.processing_cancelled:
                print(" FILE_PROCESSING: Processing was cancelled")
                self.processing_result = {
                    'text': None,
                    'file_name': None,
                    'file_path': None,
                    'error_message': "Processing cancelled",
                    'cancelled': True
                }
                return
            
            print(f" FILE_PROCESSING: Extracted text length: {len(text) if text else 0}")
            
            if not text.strip():
                print("❌ FILE_PROCESSING: No text found in file")
                self.processing_result = {
                    'text': None,
                    'file_name': None,
                    'file_path': None,
                    'error_message': "No text found in the file.",
                    'cancelled': False
                }
                return
            
            # Success - store result for main thread
            print("✅ FILE_PROCESSING: Processing completed successfully, storing result...")
            self.processing_result = {
                'text': text,
                'file_name': file_name,
                'file_path': file_path,  # Store the file path for PDF viewer
                'error_message': None,
                'cancelled': False
            }
            
        except Exception as ex:
            print(f" FILE_PROCESSING: Exception in background thread: {ex}")
            import traceback
            traceback.print_exc()
            
            if "cancelled" in str(ex).lower():
                print(" FILE_PROCESSING: Exception indicates cancellation")
                self.processing_result = {
                    'text': None,
                    'file_name': None,
                    'file_path': None,
                    'error_message': "Processing cancelled",
                    'cancelled': True
                }
            else:
                print(f"❌ FILE_PROCESSING: Exception indicates error: {str(ex)}")
                self.processing_result = {
                    'text': None,
                    'file_name': None,
                    'file_path': None,
                    'error_message': f"Upload failed: {str(ex)}",
                    'cancelled': False
                }
    
    def _handle_processing_complete(self, text: str, file_name: str, file_path: str, error_message: str, cancelled: bool = False):
        """Handle completion of file processing on main thread"""
        print(" FILE_PROCESSING: Starting UI update...")
        
        try:
            # Hide loading screen first
            if hasattr(self, 'loading_screen') and self.loading_screen:
                print(" FILE_PROCESSING: Hiding loading screen...")
                self.loading_screen.hide()
                print("✅ FILE_PROCESSING: Loading screen hidden")
            
            if cancelled:
                print(" FILE_PROCESSING: Processing was cancelled by user")
                # Don't show error for user-initiated cancellation
                return
            
            if error_message:
                print(f"❌ FILE_PROCESSING: Showing error: {error_message}")
                self.show_error(error_message)
                return
            
            # Success case
            print(f"✅ FILE_PROCESSING: Setting text in input panel")
            self.input_panel.set_text(text)
            
            # If PDF, set it in center panel with file path
            if file_name and file_name.lower().endswith('.pdf') and file_path:
                print(f" FILE_PROCESSING: Setting PDF in center panel: {file_name} at {file_path}")
                self.center_panel.set_pdf_file(file_name, file_path)
                self.current_pdf_file = file_name
                print(f"✅ FILE_PROCESSING: PDF viewer initialized")
            elif file_name:
                self.current_pdf_file = file_name if file_name.lower().endswith('.pdf') else None
                print(f"✅ FILE_PROCESSING: File name set: {file_name}")
            
            self.show_success(f"Loaded {file_name}")
            self.page.update()
            print(f"✅ FILE_PROCESSING: UI update completed")
            
        except Exception as e:
            print(f" FILE_PROCESSING: Error updating UI: {e}")
            import traceback
            traceback.print_exc()
            # Ensure loading screen is hidden even if there's an error
            if hasattr(self, 'loading_screen') and self.loading_screen:
                try:
                    self.loading_screen.hide()
                except:
                    pass
            self.show_error(f"Error updating interface: {str(e)}")
    
    def on_export(self, e):
        """Handle export - show dialog to select translations and format"""
        print(" EXPORT: Export button clicked")  # Debug
        
        # Check if there are any translations to export
        if not self.workspace.has_translations():
            self.show_error("No translations available to export. Please translate some text first to create exportable content.")
            return
        
        # Check if workspace has translation tabs
        if not hasattr(self.workspace, 'translation_tabs') or not self.workspace.translation_tabs:
            self.show_error("No translation tabs found. Please complete a translation first.")
            return
        
        # Show export dialog
        self.show_export_dialog()
    
    def show_export_dialog(self):
        """Show dialog for selecting translations and export format"""
        from app.services.export_service import ExportService
        
        export_service = ExportService(self.settings)
        translations = self.workspace.translation_tabs
        
        # Create checkboxes for each translation
        translation_checkboxes = []
        for i, trans in enumerate(translations):
            checkbox = ft.Checkbox(
                label=f"{trans['source_preview']} ({trans['timestamp'].strftime('%Y-%m-%d %H:%M')})",
                value=True,  # Default to selected
                data=i  # Store index
            )
            translation_checkboxes.append(checkbox)
        
        # Format selection
        format_dropdown = ft.Dropdown(
            options=[
                ft.dropdown.Option("txt", "Plain Text (.txt)"),
                ft.dropdown.Option("html", "HTML (.html)"),
                ft.dropdown.Option("markdown", "Markdown (.md)")
            ],
            value="txt",
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            width=200
        )
        
        # Export type selection
        export_type_radio = ft.RadioGroup(
            content=ft.Column([
                ft.Radio(value="single", label="Export each translation separately"),
                ft.Radio(value="combined", label="Export all selected translations in one file")
            ]),
            value="single"
        )
        
        def on_export_selected(dialog_e):
            print(" EXPORT: Processing export request")  # Debug
            
            # Get selected translations
            selected_indices = []
            for checkbox in translation_checkboxes:
                if checkbox.value:
                    selected_indices.append(checkbox.data)
            
            if not selected_indices:
                self.show_error("Please select at least one translation to export.")
                return
            
            selected_translations = [translations[i] for i in selected_indices]
            format_type = format_dropdown.value
            export_type = export_type_radio.value
            
            print(f" EXPORT: Selected {len(selected_translations)} translations, format: {format_type}, type: {export_type}")  # Debug
            
            try:
                if export_type == "single":
                    # Export each translation separately
                    exported_files = []
                    for trans in selected_translations:
                        success, result = export_service.export_single_translation(trans, format_type)
                        if success:
                            exported_files.append(result)
                        else:
                            self.show_error(f"Export failed: {result}")
                            return
                    
                    # Show success message
                    export_dir = export_service.get_export_directory()
                    self.show_success(f"Exported {len(exported_files)} files to {export_dir}")
                    
                else:
                    # Export all translations to one file
                    success, result = export_service.export_multiple_translations(selected_translations, format_type)
                    if success:
                        self.show_success(f"Exported combined file: {os.path.basename(result)}")
                    else:
                        self.show_error(f"Export failed: {result}")
                
            except Exception as ex:
                print(f" EXPORT: Exception: {ex}")  # Debug
                self.show_error(f"Export failed: {str(ex)}")
            
            # Close dialog
            export_dialog.open = False
            self.page.update()
        
        # Create export dialog
        export_dialog = ft.AlertDialog(
            title=ft.Text(
                "Export Translations",
                font_family=Fonts.HEADER,
                weight=ft.FontWeight.W_600,
                size=18,
                color=Colors.FOREGROUND
            ),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        "Select translations to export:",
                        font_family=Fonts.SERIF,
                        size=14,
                        weight="bold",
                        color=Colors.INK_MUTED
                    ),
                    ft.Container(
                        content=ft.Column(
                            controls=translation_checkboxes,
                            spacing=8,
                            scroll=ft.ScrollMode.AUTO
                        ),
                        height=200,
                        bgcolor=Colors.SURFACE,
                        border=ft.border.all(1, Colors.DIVIDER),
                        border_radius=6,
                        padding=ft.padding.all(12)
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        "Export format:",
                        font_family=Fonts.SERIF,
                        size=14,
                        weight="bold",
                        color=Colors.INK_MUTED
                    ),
                    format_dropdown,
                    ft.Container(height=10),
                    ft.Text(
                        "Export type:",
                        font_family=Fonts.SERIF,
                        size=14,
                        weight="bold",
                        color=Colors.INK_MUTED
                    ),
                    export_type_radio,
                    ft.Container(height=10),
                    ft.Container(
                        content=ft.Column([
                            ft.Text(
                                "Export destination:",
                                font_family=Fonts.SERIF,
                                size=12,
                                weight="bold",
                                color=Colors.INK_MUTED
                            ),
                            ft.Text(
                                export_service.get_export_directory(),
                                font_family=Fonts.MONO,
                                size=11,
                                color=Colors.INK_MUTED,
                                selectable=True
                            )
                        ], spacing=4),
                        bgcolor=Colors.SURFACE,
                        border=ft.border.all(1, Colors.DIVIDER),
                        border_radius=6,
                        padding=ft.padding.all(12)
                    )
                ], spacing=8),
                width=500,
                height=500,
                bgcolor=Colors.SURFACE,
                border=ft.border.all(1, Colors.DIVIDER),
                border_radius=6,
                padding=ft.padding.all(16)
            ),
            actions=[
                ft.TextButton(
                    "Cancel", 
                    on_click=lambda e: self.close_dialog(export_dialog),
                    style=ft.ButtonStyle(color=Colors.INK_MUTED)
                ),
                ft.ElevatedButton(
                    "Export",
                    on_click=on_export_selected,
                    bgcolor=Colors.GOLD,
                    color=Colors.BACKGROUND,
                    icon=ft.icons.DOWNLOAD,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=6)
                    )
                )
            ],
            bgcolor=Colors.BACKGROUND,
            shape=ft.RoundedRectangleBorder(radius=12)
        )
        
        self.page.dialog = export_dialog
        export_dialog.open = True
        self.page.update()
    
    def _check_ocr_availability(self):
        """Check if OCR is available and show installation instructions if not"""
        try:
            import sys
            import os
            # Add programs directory to path
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            programs_path = os.path.join(base_dir, "programs")
            if programs_path not in sys.path:
                sys.path.append(programs_path)
            
            from ocr_engine import OCREngine
            ocr = OCREngine()
            
            if ocr.is_available():
                print("✅ HOME: OCR is available")
                return True
            else:
                print("⚠️  HOME: OCR not available, will show installation instructions")
                self._show_ocr_installation_dialog(ocr)
                return False
                
        except Exception as e:
            print(f"⚠️  HOME: Error checking OCR availability: {e}")
            return False
    
    def _show_ocr_installation_dialog(self, ocr_engine):
        """Show OCR installation instructions dialog"""
        instructions = ocr_engine.get_installation_instructions()
        
        if not instructions["instructions"]:
            return  # No missing components
        
        # Build instruction content
        instruction_controls = []
        
        instruction_controls.append(
            ft.Text(
                "OCR Features Require Additional Software",
                size=18,
                weight="bold",
                color=Colors.FOREGROUND,
                font_family=Fonts.HEADER
            )
        )
        
        instruction_controls.append(
            ft.Text(
                f"To use PDF scanning and OCR features on {instructions['system']}, please install:",
                size=14,
                color=Colors.INK_MUTED,
                font_family=Fonts.SERIF
            )
        )
        
        for instruction in instructions["instructions"]:
            instruction_controls.append(ft.Divider(color=Colors.DIVIDER))
            
            instruction_controls.append(
                ft.Text(
                    f"📦 {instruction['component']}",
                    size=16,
                    weight="bold",
                    color=Colors.GOLD
                )
            )
            
            instruction_controls.append(
                ft.Text(
                    instruction["description"],
                    size=13,
                    color=Colors.INK_MUTED,
                    font_family=Fonts.SERIF
                )
            )
            
            if "command" in instruction:
                instruction_controls.append(
                    ft.Container(
                        content=ft.Text(
                            instruction["command"],
                            size=12,
                            color=Colors.FOREGROUND,
                            font_family=Fonts.MONO,
                            selectable=True
                        ),
                        bgcolor=Colors.BACKGROUND,
                        padding=ft.padding.all(12),
                        border_radius=6,
                        border=ft.border.all(1, Colors.DIVIDER)
                    )
                )
            
            if "url" in instruction:
                instruction_controls.append(
                    ft.Text(
                        f"Download: {instruction['url']}",
                        size=12,
                        color=Colors.GOLD,
                        font_family=Fonts.MONO,
                        selectable=True
                    )
                )
        
        instruction_controls.append(ft.Divider(color=Colors.DIVIDER))
        instruction_controls.append(
            ft.Text(
                "Note: Translation features will work without OCR. You can still translate text directly.",
                size=12,
                color=Colors.INK_MUTED,
                italic=True,
                font_family=Fonts.SERIF
            )
        )
        
        # Create dialog
        def close_dialog(e):
            dialog.open = False
            self.page.update()
        
        dialog = ft.AlertDialog(
            modal=False,  # Allow user to continue using the app
            title=ft.Row(
                controls=[
                    ft.Icon(ft.icons.INFO, color=Colors.GOLD, size=24),
                    ft.Text(
                        "Setup Required",
                        font_family=Fonts.HEADER,
                        weight=ft.FontWeight.W_600,
                        color=Colors.FOREGROUND
                    )
                ],
                spacing=12
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=instruction_controls,
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO
                ),
                width=600,
                height=400
            ),
            actions=[
                ft.TextButton(
                    "Continue Without OCR",
                    on_click=close_dialog,
                    style=ft.ButtonStyle(color=Colors.INK_MUTED)
                ),
                ft.ElevatedButton(
                    "Got It",
                    on_click=close_dialog,
                    bgcolor=Colors.GOLD,
                    color=Colors.BACKGROUND
                )
            ],
            bgcolor=Colors.SURFACE,
        )
        
        # Show dialog after a short delay to let the app load first
        def show_delayed():
            import time
            time.sleep(2)  # Wait 2 seconds
            self.page.dialog = dialog
            dialog.open = True
            self.page.update()
        
        import threading
        threading.Thread(target=show_delayed, daemon=True).start()

    def on_history(self, e):
        """Handle history view"""
        self.history_view.show()
    
    def show_error(self, message: str):
        """Show error message"""
        # Use banner instead of SnackBar for Python 3.9 compatibility
        banner = ft.Banner(
            bgcolor=Colors.DESTRUCTIVE,
            leading=ft.Icon(ft.icons.ERROR, color=Colors.FOREGROUND, size=40),
            content=ft.Text(message, color=Colors.FOREGROUND),
            actions=[
                ft.TextButton("Close", on_click=lambda e: self.close_banner())
            ]
        )
        self.page.banner = banner
        banner.open = True
        self.page.update()
    
    def show_success(self, message: str):
        """Show success message"""
        banner = ft.Banner(
            bgcolor=Colors.SUCCESS,
            leading=ft.Icon(ft.icons.CHECK_CIRCLE, color=Colors.FOREGROUND, size=40),
            content=ft.Text(message, color=Colors.FOREGROUND),
            actions=[
                ft.TextButton("Close", on_click=lambda e: self.close_banner())
            ]
        )
        self.page.banner = banner
        banner.open = True
        self.page.update()
    
    def show_info(self, message: str):
        """Show info message"""
        banner = ft.Banner(
            bgcolor=Colors.SURFACE,
            leading=ft.Icon(ft.icons.INFO, color=Colors.GOLD, size=40),
            content=ft.Text(
                message, 
                color=Colors.FOREGROUND,
                weight=ft.FontWeight.W_500
            ),
            actions=[
                ft.TextButton(
                    "Close", 
                    on_click=lambda e: self.close_banner(),
                    style=ft.ButtonStyle(color=Colors.GOLD)
                )
            ]
        )
        self.page.banner = banner
        banner.open = True
        self.page.update()
    
    def close_banner(self):
        """Close the banner"""
        if self.page.banner:
            self.page.banner.open = False
            self.page.update()
    
    def rebuild_workspace(self):
        """Rebuild workspace panel to show either center panel or output panel"""
        # This will be called when switching between states
        pass
    
    def build(self):
        """Build home tab layout"""
        # Toolbar with proper spacing and layout
        toolbar = ft.Container(
            content=ft.Row(
                controls=[
                    self.translate_btn,
                    self.upload_btn,
                    self.export_btn,
                    ft.Container(expand=True),  # Spacer
                    self.history_btn
                ],
                spacing=8
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            bgcolor=Colors.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER))
        )
        
        # Drag handle for resizing
        drag_handle = ft.GestureDetector(
            content=ft.Container(
                width=5,
                bgcolor="transparent",
                content=ft.Container(
                    width=1,
                    bgcolor=Colors.DIVIDER,
                    margin=ft.margin.symmetric(horizontal=2)
                ),
                on_hover=lambda e: self.on_hover_handle(e, drag_handle)
            ),
            on_pan_start=self.on_pan_start,
            on_pan_update=self.on_pan_update,
            on_pan_end=self.on_pan_end,
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN
        )
        
        # Workspace panel - show center panel or output panel based on state
        workspace_content = self.output_panel.build() if self.has_translation else self.center_panel.build()
        
        # Two-column layout with resizable panels and drag handle
        content = ft.Row(
            controls=[
                ft.Container(
                    content=self.input_panel.build(),
                    expand=int(self.left_width * 10)
                ),
                drag_handle,  # Add the drag handle between panels
                ft.Container(
                    content=workspace_content,
                    expand=int((1 - self.left_width) * 10)
                )
            ],
            spacing=0,
            expand=True
        )
        
        return ft.Column(
            controls=[
                toolbar,
                content,
            ],
            expand=True,
            spacing=0
        )
    
    def cleanup(self):
        """Cleanup resources"""
        print(" HOME_TAB: Cleanup called")
        
        # Cancel any ongoing file processing
        if hasattr(self, 'processing_cancelled'):
            self.processing_cancelled = True
            print(" HOME_TAB: File processing cancellation requested")
        
        # Cancel processing timer
        if hasattr(self, 'processing_timer') and self.processing_timer:
            try:
                self.processing_timer.cancel()
                self.processing_timer = None
                print("✅ HOME_TAB: Processing timer cancelled")
            except Exception as e:
                print(f"  HOME_TAB: Could not cancel processing timer: {e}")
        
        # Cancel OCR processing
        try:
            import sys
            from pathlib import Path
            sys.path.append(str(Path(__file__).parent.parent.parent / "programs"))
            from ocr_engine import OCREngine
            
            # Create a temporary OCR instance to cancel processing
            ocr = OCREngine()
            ocr.cancel_processing()
            print("✅ HOME_TAB: OCR cancellation requested")
        except Exception as e:
            print(f"  HOME_TAB: Could not cancel OCR: {e}")
        
        # Hide loading screen if active
        if hasattr(self, 'loading_screen') and self.loading_screen:
            try:
                self.loading_screen.hide()
                print("✅ HOME_TAB: Loading screen hidden")
            except Exception as e:
                print(f"  HOME_TAB: Could not hide loading screen: {e}")
        
        # Wait for processing thread to complete (with timeout)
        if hasattr(self, 'processing_thread') and self.processing_thread and self.processing_thread.is_alive():
            try:
                print(" HOME_TAB: Waiting for processing thread to complete...")
                self.processing_thread.join(timeout=2.0)  # Wait max 2 seconds
                if self.processing_thread.is_alive():
                    print("  HOME_TAB: Processing thread did not complete in time")
                else:
                    print("✅ HOME_TAB: Processing thread completed")
            except Exception as e:
                print(f"  HOME_TAB: Error waiting for processing thread: {e}")
        
        # Cleanup translation service
        if hasattr(self, 'translation_service'):
            try:
                self.translation_service.cleanup()
                print("✅ HOME_TAB: Translation service cleaned up")
            except Exception as e:
                print(f"  HOME_TAB: Error cleaning up translation service: {e}")
        
        print("✅ HOME_TAB: Cleanup completed")
    
    def on_hover_handle(self, e, handle):
        """Handle hover effect on drag handle"""
        if e.data == "true":
            handle.content.content.bgcolor = Colors.GOLD
            handle.content.content.opacity = 0.8
        else:
            handle.content.content.bgcolor = Colors.DIVIDER
            handle.content.content.opacity = 1.0
        self.page.update()