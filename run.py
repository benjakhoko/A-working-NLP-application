"""Development entry point.

Run with:  python run.py
"""
from __future__ import annotations

import os

from backend import create_app

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=app.config["DEBUG"])
