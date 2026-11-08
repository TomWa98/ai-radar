"""Load local configuration from a ``.env`` file into the process environment.

The components keep reading ``os.environ``; this module only fills it. Values
that are already set always win, so a real environment (shell, Docker) is never
changed by a file.
"""

from pathlib import Path

from dotenv import load_dotenv

# The repository root in a source checkout, independent of the working
# directory. An installed package finds no file here and uses the environment.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def load_env_file(path: Path | None = None) -> bool:
    """Add variables from ``path`` (default ``ENV_FILE``) that are not yet set.

    A missing file is not an error. Returns whether any variable was found.
    ``$`` stays literal, so a secret cannot be altered by variable expansion.
    """
    return load_dotenv(path or ENV_FILE, override=False, interpolate=False)
