from pathlib import Path
import sys

api_path = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(api_path))

from app.services.seed import seed_development_data  # noqa: E402


def main() -> None:
    seed_development_data()


if __name__ == "__main__":
    main()
