# heml.py
# Run: python heml.py
# Starts a server on port 8082 for the new NTPC Chhattisgarh Demand Forecast Dashboard
# and automatically opens it in the browser.

import http.server
import socketserver
import webbrowser
import os

PORT = 8082
DIRECTORY = "dashboard"

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

if __name__ == "__main__":
    print(f"\n========================================================")
    print(f"Starting NTPC Dashboard Server...")
    print(f"URL: http://127.0.0.1:{PORT}/heml.html")
    print(f"========================================================\n")
    
    # Auto-open the specific dashboard html page
    webbrowser.open(f"http://127.0.0.1:{PORT}/heml.html")
    
    # Run the server
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down NTPC Dashboard server.")
