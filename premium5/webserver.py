import os
import json
import http.server
import threading

from premium5.emulator import Emulator, Listing, emulator_thread


WEB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=WEB_ROOT, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path == '/events':
            self.handle_sse()
            return
        super().do_GET()

    def do_POST(self):
        if self.path == '/command':
            self.handle_command()
            return
        self.send_error(404)

    def handle_sse(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        emulator = self.server.emulator
        try:
            while True:
                with emulator.state_changed:
                    emulator.state_changed.wait(timeout=0.1)
                    data = json.dumps(emulator.get_state())
                self.wfile.write(('data: %s\n\n' % data).encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            pass

    def handle_command(self):
        length = int(self.headers['Content-Length'])
        body = self.rfile.read(length)
        cmd = json.loads(body)

        emulator = self.server.emulator
        with emulator.lock:
            emulator.handle_command(cmd)
            emulator.state_changed.notify_all()

        self.send_response(204)
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

    def log_request(self, code='-', size='-'):
        if self.path == '/events':
            return
        super().log_request(code, size)


def serve(emulator, port=8080):
    httpd = http.server.ThreadingHTTPServer(('', port), Handler)
    httpd.emulator = emulator

    emu_thread = threading.Thread(target=emulator_thread, args=(emulator,), daemon=True)
    emu_thread.start()

    print("Premium 5 emulator")
    print("  http://localhost:%d" % port)

    httpd.serve_forever()
