"""
Network utility functions for checking internet connectivity
"""

import socket
import urllib.request
import urllib.error

def check_internet_connection(timeout: int = 5) -> bool:
    """
    Check if there's an active internet connection.
    
    Args:
        timeout: Timeout in seconds for the connection test
        
    Returns:
        True if internet connection is available, False otherwise
    """
    try:
        # Try to connect to Google's DNS server
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except (socket.error, OSError):
        pass
    
    try:
        # Fallback: try to make an HTTP request to a reliable service
        urllib.request.urlopen("https://www.google.com", timeout=timeout)
        return True
    except (urllib.error.URLError, socket.timeout):
        pass
    
    return False

def check_anthropic_api_connectivity(timeout: int = 10) -> bool:
    """
    Check if Anthropic API is reachable.
    
    Args:
        timeout: Timeout in seconds for the connection test
        
    Returns:
        True if Anthropic API is reachable, False otherwise
    """
    try:
        # Try to connect to Anthropic's API endpoint
        urllib.request.urlopen("https://api.anthropic.com", timeout=timeout)
        return True
    except (urllib.error.URLError, socket.timeout):
        return False