"""Run the whole test suite: `./.venv/bin/python -m tests` (from the project root).

Each test module is run in its own subprocess so their monkeypatching of shared
module state stays isolated (the same isolation as running each file alone).
Exits non-zero if any module fails.
"""

import pkgutil
import subprocess
import sys

import tests

failed = []
for mod in sorted(pkgutil.iter_modules(tests.__path__), key=lambda m: m.name):
    if not mod.name.startswith("test_"):
        continue
    print(f"\n### {mod.name}")
    result = subprocess.run([sys.executable, "-m", f"tests.{mod.name}"])
    if result.returncode != 0:
        failed.append(mod.name)

print("\n" + "=" * 40)
if failed:
    print("FAILED modules: " + ", ".join(failed))
else:
    print("All test modules passed.")
raise SystemExit(1 if failed else 0)
