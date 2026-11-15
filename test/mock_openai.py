"""Tiny OpenAI-compatible mock used by the end-to-end test.

Returns a deterministic lead score so workflow logic can be tested without an API key.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = json.loads(body["messages"][-1]["content"])
        hot = user.get("business_email") and user.get("budget")
        result = {
            "score": 86 if hot else 22,
            "tier": "hot" if hot else "cold",
            "need": "AI support chatbot",
            "reasoning": "Business email with a clear budget." if hot else "Free email and no budget.",
            "next_step": "Book a discovery call this week." if hot else "Add to nurture list.",
        }
        resp = {"choices": [{"message": {"role": "assistant", "content": json.dumps(result)}}]}
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 18999), Handler).serve_forever()
