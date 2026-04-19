import flet as ft
from app.theme import Colors, Fonts
import tempfile
import os
import base64
from typing import Optional, List
from pathlib import Path

class PDFViewer:
    """PDF viewer component that renders PDF pages as images"""
    
    def __init__(self, page: ft.Page):
        self.page = page
        self.pdf_path: Optional[str] = None
        self.pdf_name: Optional[str] = None
        self.current_page = 0
        self.total_pages = 0
        self.page_images: List[str] = []  # Base64 encoded images
        self.zoom_level = 1.0
        self.temp_dir = None
        
        # Controls
        self.page_display = ft.Text("", size=12, color=Colors.INK_MUTED)
        self.prev_btn = ft.IconButton(
            icon=ft.icons.ARROW_BACK,
            on_click=self.prev_page,
            disabled=True
        )
        self.next_btn = ft.IconButton(
            icon=ft.icons.ARROW_FORWARD,
            on_click=self.next_page,
            disabled=True
        )
        self.zoom_in_btn = ft.IconButton(
            icon=ft.icons.ZOOM_IN,
            on_click=self.zoom_in
        )
        self.zoom_out_btn = ft.IconButton(
            icon=ft.icons.ZOOM_OUT,
            on_click=self.zoom_out
        )
        self.zoom_reset_btn = ft.IconButton(
            icon=ft.icons.CENTER_FOCUS_STRONG,
            on_click=self.zoom_reset,
            tooltip="Reset zoom"
        )
        
        self.image_container = ft.Container(
            content=ft.Text(
                "No PDF loaded",
                size=14,
                color=Colors.INK_MUTED,
                text_align=ft.TextAlign.CENTER
            ),
            alignment=ft.alignment.center,
            expand=True
        )
        
        # Add keyboard event handler to page
        self.page.on_keyboard_event = self.on_keyboard_event
    
    def load_pdf(self, pdf_path: str, pdf_name: str):
        """Load a PDF file and convert pages to images"""
        print(f" PDF_VIEWER: Loading PDF: {pdf_name}")
        
        try:
            # Try pypdfium2 first (faster)
            self._load_with_pypdfium2(pdf_path, pdf_name)
        except ImportError:
            print(" PDF_VIEWER: pypdfium2 not available, falling back to pdf2image")
            try:
                self._load_with_pdf2image(pdf_path, pdf_name)
            except ImportError:
                print(" PDF_VIEWER: pdf2image not available, showing placeholder")
                self._show_placeholder(pdf_name)
        except Exception as e:
            print(f" PDF_VIEWER: Error loading PDF: {e}")
            self._show_error(f"Error loading PDF: {str(e)}")
    
    def _load_with_pypdfium2(self, pdf_path: str, pdf_name: str):
        """Load PDF using pypdfium2 (preferred method)"""
        import pypdfium2 as pdfium
        
        self.pdf_path = pdf_path
        self.pdf_name = pdf_name
        self.page_images = []
        
        # Open PDF
        pdf = pdfium.PdfDocument(pdf_path)
        self.total_pages = len(pdf)
        
        print(f" PDF_VIEWER: PDF has {self.total_pages} pages")
        
        # Convert first few pages to images (lazy loading for performance)
        pages_to_load = min(3, self.total_pages)  # Load first 3 pages initially
        
        for i in range(pages_to_load):
            page = pdf.get_page(i)
            # Render at 150 DPI for good quality
            pil_image = page.render(scale=2.0).to_pil()
            
            # Convert to base64 for Flet
            import io
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            self.page_images.append(img_base64)
        
        # Load remaining pages lazily
        for i in range(pages_to_load, self.total_pages):
            self.page_images.append(None)  # Placeholder for lazy loading
        
        pdf.close()
        
        self.current_page = 0
        self._update_display()
        print(f"✅ PDF_VIEWER: PDF loaded successfully with pypdfium2")
    
    def _load_with_pdf2image(self, pdf_path: str, pdf_name: str):
        """Load PDF using pdf2image (fallback method)"""
        from pdf2image import convert_from_path
        
        self.pdf_path = pdf_path
        self.pdf_name = pdf_name
        self.page_images = []
        
        print(f" PDF_VIEWER: Converting PDF to images...")
        
        # Convert first few pages only for performance
        images = convert_from_path(pdf_path, first_page=1, last_page=3, dpi=150)
        
        for img in images:
            # Convert to base64 for Flet
            import io
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            self.page_images.append(img_base64)
        
        # Get total page count
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                self.total_pages = len(pdf_reader.pages)
        except:
            self.total_pages = len(images)
        
        # Add placeholders for remaining pages
        for i in range(len(images), self.total_pages):
            self.page_images.append(None)
        
        self.current_page = 0
        self._update_display()
        print(f"✅ PDF_VIEWER: PDF loaded successfully with pdf2image")
    
    def _load_page_lazy(self, page_num: int):
        """Lazy load a specific page if not already loaded"""
        if page_num >= len(self.page_images) or self.page_images[page_num] is not None:
            return
        
        try:
            # Try pypdfium2 first
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(self.pdf_path)
            page = pdf.get_page(page_num)
            pil_image = page.render(scale=2.0).to_pil()
            pdf.close()
        except ImportError:
            # Fallback to pdf2image
            from pdf2image import convert_from_path
            images = convert_from_path(
                self.pdf_path, 
                first_page=page_num + 1, 
                last_page=page_num + 1, 
                dpi=150
            )
            pil_image = images[0] if images else None
        
        if pil_image:
            import io
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            self.page_images[page_num] = img_base64
    
    def _show_placeholder(self, pdf_name: str):
        """Show placeholder when PDF libraries are not available"""
        self.image_container.content = ft.Column(
            controls=[
                ft.Icon(ft.icons.PICTURE_AS_PDF, size=64, color=Colors.INK_MUTED),
                ft.Text(
                    f"PDF: {pdf_name}",
                    size=16,
                    color=Colors.FOREGROUND,
                    weight="bold"
                ),
                ft.Text(
                    "PDF rendering requires pypdfium2 or pdf2image",
                    size=14,
                    color=Colors.INK_MUTED,
                    text_align=ft.TextAlign.CENTER
                ),
                ft.Text(
                    "Text extraction is working - check the input panel",
                    size=12,
                    color=Colors.INK_MUTED,
                    italic=True
                )
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER
        )
        self.page_display.value = ""
        self._update_buttons()
    
    def _show_error(self, error_msg: str):
        """Show error message"""
        self.image_container.content = ft.Column(
            controls=[
                ft.Icon(ft.icons.ERROR, size=48, color=Colors.DESTRUCTIVE),
                ft.Text(
                    "PDF Loading Error",
                    size=16,
                    color=Colors.DESTRUCTIVE,
                    weight="bold"
                ),
                ft.Text(
                    error_msg,
                    size=14,
                    color=Colors.INK_MUTED,
                    text_align=ft.TextAlign.CENTER
                )
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER
        )
        self.page_display.value = ""
        self._update_buttons()
    
    def _update_display(self):
        """Update the current page display"""
        if not self.page_images or self.current_page >= len(self.page_images):
            return
        
        # Lazy load current page if needed
        if self.page_images[self.current_page] is None:
            self._load_page_lazy(self.current_page)
        
        if self.page_images[self.current_page]:
            # Calculate display size based on zoom
            width = int(600 * self.zoom_level)
            
            # Create image with gesture detector for swipe support
            image = ft.Image(
                src_base64=self.page_images[self.current_page],
                width=width,
                fit=ft.ImageFit.CONTAIN
            )
            
            # Wrap in gesture detector for swipe navigation
            self.image_container.content = ft.GestureDetector(
                content=image,
                on_horizontal_drag_end=self.on_swipe,
                drag_interval=50
            )
        else:
            self.image_container.content = ft.Text(
                f"Loading page {self.current_page + 1}...",
                size=14,
                color=Colors.INK_MUTED
            )
        
        self.page_display.value = f"Page {self.current_page + 1} of {self.total_pages}"
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states"""
        self.prev_btn.disabled = self.current_page <= 0
        self.next_btn.disabled = self.current_page >= self.total_pages - 1
        self.page.update()
    
    def on_keyboard_event(self, e: ft.KeyboardEvent):
        """Handle keyboard events for navigation"""
        if not self.page_images or self.total_pages <= 1:
            return
        
        if e.key == "Arrow Left" and e.shift == False and e.ctrl == False and e.alt == False:
            self.prev_page(None)
        elif e.key == "Arrow Right" and e.shift == False and e.ctrl == False and e.alt == False:
            self.next_page(None)
        elif e.key == "Arrow Up" and e.shift == False and e.ctrl == False and e.alt == False:
            self.prev_page(None)
        elif e.key == "Arrow Down" and e.shift == False and e.ctrl == False and e.alt == False:
            self.next_page(None)
    
    def prev_page(self, e):
        """Go to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_display()
    
    def next_page(self, e):
        """Go to next page"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_display()
    
    def on_swipe(self, e: ft.DragEndEvent):
        """Handle swipe gestures for navigation"""
        if not self.page_images or self.total_pages <= 1:
            return
        
        # Swipe left = next page, swipe right = previous page
        if e.velocity_x < -500:  # Swipe left (negative velocity)
            self.next_page(None)
        elif e.velocity_x > 500:  # Swipe right (positive velocity)
            self.prev_page(None)
    
    def zoom_in(self, e):
        """Zoom in"""
        self.zoom_level = min(3.0, self.zoom_level * 1.25)
        self._update_display()
    
    def zoom_out(self, e):
        """Zoom out"""
        self.zoom_level = max(0.3, self.zoom_level / 1.25)
        self._update_display()
    
    def zoom_reset(self, e):
        """Reset zoom to 100%"""
        self.zoom_level = 1.0
        self._update_display()
    
    def build(self):
        """Build the PDF viewer component"""
        # Toolbar
        toolbar = ft.Row(
            controls=[
                self.prev_btn,
                self.next_btn,
                ft.VerticalDivider(width=1),
                self.zoom_out_btn,
                self.zoom_reset_btn,
                self.zoom_in_btn,
                ft.Container(expand=True),
                self.page_display
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.START
        )
        
        # Main content with scrolling
        content = ft.Container(
            content=self.image_container,
            expand=True,
            alignment=ft.alignment.top_center,
            padding=ft.padding.all(16)
        )
        
        return ft.Column(
            controls=[
                ft.Container(
                    content=toolbar,
                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                    bgcolor=Colors.SURFACE,
                    border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER))
                ),
                ft.Container(
                    content=content,
                    expand=True,
                    bgcolor=Colors.BACKGROUND
                )
            ],
            spacing=0,
            expand=True
        )
    
    def cleanup(self):
        """Cleanup temporary files"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)