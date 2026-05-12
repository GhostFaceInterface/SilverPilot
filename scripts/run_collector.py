from pathlib import Path
import sys

api_path = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(api_path))

from app.collectors.runner import main  # noqa: E402


if __name__ == "__main__":
    main()
