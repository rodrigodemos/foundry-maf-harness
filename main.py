"""Code-deploy entry point for the Foundry hosted agent (azure.yaml codeConfiguration.entryPoint).

The platform runs `python main.py`. We ensure src/ is importable, then delegate to the package's
server (which serves the Foundry Responses protocol on :8088 via the harness agent).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from maf_orchestrator.server import main  # noqa: E402

if __name__ == "__main__":
    main()
