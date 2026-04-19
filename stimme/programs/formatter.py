import markdown
from pathlib import Path
import sys

# Add the app directory to the path for imports
sys.path.append(str(Path(__file__).parent.parent))

try:
    from app.constants import HTML_TEMPLATE
except ImportError:
    # Fallback if constants not available
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ background-color: #0a0a0a; color: #e8e6e3; font-family: 'Cormorant Garamond', Georgia, serif; }}
            h1, h2, h3 {{ color: #d4af37; }}
            strong {{ color: #d4af37; }}
        </style>
    </head>
    <body>
        {content}
    </body>
    </html>
    """

def get_styled_html(translation, commentary=None):
    """Returns the HTML string with proper dark mode styling."""
    
    # Convert markdown to HTML
    trans_html = markdown.markdown(translation, extensions=['extra', 'codehilite'])
    
    # Build content
    content = trans_html
    
    if commentary:
        # Add ornamental divider
        divider = '''
        <div class="divider">
            <span>❦ Philological Commentary ❦</span>
        </div>
        '''
        commentary_html = markdown.markdown(commentary, extensions=['extra', 'codehilite'])
        content += divider + commentary_html
    
    # Use the HTML template from constants
    return HTML_TEMPLATE.format(content=content)