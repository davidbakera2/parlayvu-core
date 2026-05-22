from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import initialize_database, session_scope
from app.demo_seed import seed_ramair_demo


def main() -> None:
    load_dotenv()
    initialize_database()
    with session_scope() as session:
        result = seed_ramair_demo(session)

    print("RamAir demo project seeded.")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
