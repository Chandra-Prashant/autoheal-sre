import argparse
import json
import os
import shutil

ROOT = os.path.join(os.path.dirname(__file__), "..")
SAMPLE_REPO = os.path.join(ROOT, "evals", "bugs", "sample_repo")
DEFINITIONS = os.path.join(ROOT, "evals", "bugs", "definitions.json")
OUT_ROOT = os.path.join(ROOT, "evals", "bugs", "seeded")


def load_definitions() -> list[dict]:
    with open(DEFINITIONS) as f:
        return json.load(f)


def seed(bug: dict) -> str:
    dest = os.path.join(OUT_ROOT, bug["id"])
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(SAMPLE_REPO, dest)

    target = os.path.join(dest, bug["file"])
    with open(target) as f:
        src = f.read()

    count = src.count(bug["find"])
    if count != 1:
        raise ValueError(f"{bug['id']}: expected exactly 1 match for find-string in {bug['file']}, found {count}")

    with open(target, "w") as f:
        f.write(src.replace(bug["find"], bug["replace"]))

    return dest


def main():
    parser = argparse.ArgumentParser(description="seed known bugs into evals/bugs/seeded/<bug-id>")
    parser.add_argument("--bug", help="seed a single bug id, default: seed all")
    args = parser.parse_args()

    bugs = load_definitions()
    if args.bug:
        bugs = [b for b in bugs if b["id"] == args.bug]
        if not bugs:
            raise SystemExit(f"no bug with id {args.bug!r}")

    for bug in bugs:
        dest = seed(bug)
        print(f"seeded {bug['id']} -> {dest}")


if __name__ == "__main__":
    main()
