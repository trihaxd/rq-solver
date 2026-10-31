"""Entry point for hosting the (r, Q) solver on a public web host.

    python server.py

Binds 0.0.0.0 on $PORT (default 8000), which is what Render, Koyeb, Railway,
Hugging Face Spaces etc. expect. Excel export is returned to the browser as a
download instead of being saved on the server disk.
"""

import os

from webapp import make_server


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    httpd = make_server("0.0.0.0", port, quiet=False, download_exports=True)
    print(f"(r, Q) solver listening on 0.0.0.0:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
