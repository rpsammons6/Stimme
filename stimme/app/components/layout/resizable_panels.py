import flet as ft
from app.theme import Colors

class ResizablePanels:
    """A resizable panel container with drag handles"""
    
    def __init__(self, left_panel, right_panel, initial_left_width: float = 0.5):
        self.left_panel = left_panel
        self.right_panel = right_panel
        self.left_width = initial_left_width
        self.right_width = 1.0 - initial_left_width
        self.is_dragging = False
        self.container_width = 1000  # Default width
        
        # Create drag handle
        self.drag_handle = ft.GestureDetector(
            content=ft.Container(
                width=4,
                bgcolor=Colors.DIVIDER,
                border_radius=2,
                content=ft.Container(
                    width=1,
                    bgcolor=Colors.GOLD,
                    margin=ft.margin.symmetric(horizontal=1.5)
                )
            ),
            on_pan_start=self.on_drag_start,
            on_pan_update=self.on_drag_update,
            on_pan_end=self.on_drag_end,
            drag_interval=10
        )
        
        # Hover effect for drag handle
        self.drag_handle_container = ft.Container(
            content=self.drag_handle,
            width=8,
            padding=ft.padding.symmetric(horizontal=2),
            on_hover=self.on_hover_handle
        )
    
    def on_hover_handle(self, e):
        """Handle hover effect on drag handle"""
        if e.data == "true":
            self.drag_handle.content.bgcolor = Colors.GOLD
        else:
            self.drag_handle.content.bgcolor = Colors.DIVIDER
        e.page.update()
    
    def on_drag_start(self, e):
        """Start dragging"""
        self.is_dragging = True
        e.page.update()
    
    def on_drag_update(self, e):
        """Update panel sizes during drag"""
        if not self.is_dragging:
            return
        
        # Calculate new width based on drag position
        delta_x = e.delta_x
        width_change = delta_x / self.container_width
        
        new_left_width = max(0.2, min(0.8, self.left_width + width_change))
        self.left_width = new_left_width
        self.right_width = 1.0 - new_left_width
        
        # Update the layout
        self.update_layout()
        e.page.update()
    
    def on_drag_end(self, e):
        """End dragging"""
        self.is_dragging = False
        e.page.update()
    
    def update_layout(self):
        """Update the panel layout"""
        # This will be called by the parent to update sizes
        pass
    
    def build(self, container_width: int = 1000):
        """Build the resizable panels"""
        self.container_width = container_width
        
        return ft.Row(
            controls=[
                ft.Container(
                    content=self.left_panel,
                    expand=int(self.left_width * 10),  # Convert to integer ratio
                ),
                self.drag_handle_container,
                ft.Container(
                    content=self.right_panel,
                    expand=int(self.right_width * 10),  # Convert to integer ratio
                )
            ],
            spacing=0,
            expand=True
        )