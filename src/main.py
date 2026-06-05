"""Entrypoint: run gateway (8000) or admin panel (8888).

Production requires at minimum:
  SESSION_SECRET, ADMIN_SECRET, ALLOW_INSECURE_DEFAULTS=0
Local dev may set ALLOW_INSECURE_DEFAULTS=1 until secrets are configured.
"""

import argparse
import logging

import uvicorn

from .config import ADMIN_HOST, ADMIN_PORT, GATEWAY_HOST, GATEWAY_PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="EPS orchestrator services")
    parser.add_argument(
        "service",
        choices=("gateway", "admin", "both"),
        nargs="?",
        default="gateway",
        help="gateway=public API :8000, admin=localhost panel :8888",
    )
    args = parser.parse_args()

    if args.service == "gateway":
        uvicorn.run(
            "src.gateway:app",
            host=GATEWAY_HOST,
            port=GATEWAY_PORT,
            reload=False,
        )
    elif args.service == "admin":
        uvicorn.run(
            "src.admin:app",
            host=ADMIN_HOST,
            port=ADMIN_PORT,
            reload=False,
        )
    else:
        import multiprocessing

        def run_gateway() -> None:
            uvicorn.run(
                "src.gateway:app",
                host=GATEWAY_HOST,
                port=GATEWAY_PORT,
                reload=False,
            )

        def run_admin() -> None:
            uvicorn.run(
                "src.admin:app",
                host=ADMIN_HOST,
                port=ADMIN_PORT,
                reload=False,
            )

        procs = [
            multiprocessing.Process(target=run_gateway, daemon=True),
            multiprocessing.Process(target=run_admin, daemon=True),
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join()


if __name__ == "__main__":
    main()
