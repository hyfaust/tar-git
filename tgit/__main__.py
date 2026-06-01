"""Allow ``python -m tgit``."""
from .cli import main
import sys

sys.exit(main())
