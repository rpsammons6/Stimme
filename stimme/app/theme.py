# Stimme Color Scheme - extracted from CSS
# All colors converted from HSL to hex (removing green tints)

class Colors:
    # Base colors from CSS (HSL to Hex conversions)
    BACKGROUND = "#2D232E"          # hsl(290 8% 16%) - Shadow Grey
    FOREGROUND = "#E0DDCF"          # hsl(47 23% 84%) - Bone
    SURFACE = "#38313A"             # hsl(285 4% 21%) - slightly lifted
    SURFACE_RAISED = "#474448"      # hsl(285 4% 27%) - Gunmetal
    
    # Primary (Parchment)
    PRIMARY = "#F1F0EA"             # hsl(50 18% 93%) - Parchment
    PRIMARY_FOREGROUND = "#2D232E"  # hsl(290 8% 16%) - Shadow Grey ink
    
    # Secondary (Taupe)
    SECONDARY = "#534B52"           # hsl(290 6% 31%) - Taupe
    SECONDARY_FOREGROUND = "#E0DDCF" # hsl(47 23% 84%)
    
    # Muted
    MUTED = "#39323A"               # hsl(290 5% 22%)
    MUTED_FOREGROUND = "#ACA49D"    # hsl(47 10% 65%)
    
    # Accent
    ACCENT = "#E0DDCF"              # hsl(47 23% 84%) - Bone
    ACCENT_FOREGROUND = "#2D232E"   # hsl(290 8% 16%)
    
    # Semantic colors
    INK = "#F1F0EA"                 # hsl(50 18% 93%) - Parchment for prose
    INK_MUTED = "#ACA49D"           # hsl(47 10% 65%) - dimmed
    GOLD = "#F1F0EA"                # hsl(50 18% 93%) - Parchment accent
    GOLD_DEEP = "#534B52"           # hsl(290 6% 31%) - Taupe
    
    # Borders and inputs
    BORDER = "#4A444A"              # hsl(290 5% 28%)
    INPUT = "#433D42"               # hsl(290 5% 26%)
    DIVIDER = "#433D42"             # hsl(290 5% 26%)
    RING = "#EBE9E0"                # hsl(50 18% 86%)
    
    # Sidebar specific
    SIDEBAR_BG = "#211C22"          # hsl(290 9% 13%) - deepest Shadow Grey
    SIDEBAR_FG = "#D4CFC6"          # hsl(47 20% 80%)
    SIDEBAR_PRIMARY = "#F1F0EA"     # hsl(50 18% 93%)
    SIDEBAR_PRIMARY_FG = "#2D232E"  # hsl(290 8% 16%)
    SIDEBAR_ACCENT = "#38313A"      # hsl(285 4% 21%)
    SIDEBAR_ACCENT_FG = "#E0DDCF"   # hsl(47 23% 84%)
    SIDEBAR_BORDER = "#39323A"      # hsl(290 5% 22%)
    SIDEBAR_RING = "#EBE9E0"        # hsl(50 18% 86%)
    
    # Status colors
    DESTRUCTIVE = "#FF4D84"         # hsl(339 100% 65%)
    DESTRUCTIVE_FOREGROUND = "#F7F6F3" # hsl(50 18% 96%)
    WARNING = "#F1A355"             # hsl(26 85% 64%)
    WARNING_FOREGROUND = "#1F1A1C"  # hsl(290 8% 12%)
    SUCCESS = "#F1F0EA"             # Using parchment instead of green
    SUCCESS_FOREGROUND = "#2D232E"

class Fonts:
    SERIF = "CormorantGaramond"
    MONO = "JetBrains Mono"
    FRAKTUR = "UnifrakturCook-Bold"     # For Translate button
    HEADER = "Lexend"                   # For headers