import argparse
import importlib.metadata as metadata
import re
import sys
from dataclasses import dataclass
from pathlib import Path


NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


@dataclass
class RequirementStatus:
    raw_line: str
    package_name: str
    installed_version: str | None

    @property
    def is_satisfied(self) -> bool:
        return self.installed_version is not None


def canonicalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def extract_package_name(requirement_line: str) -> str | None:
    line = requirement_line.split("#", 1)[0].strip()
    if not line:
        return None
    match = NAME_RE.match(line)
    if not match:
        return None
    return match.group(1)


def read_requirements(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def scan_requirements(lines: list[str]) -> list[RequirementStatus]:
    installed = {
        canonicalize_name(dist.metadata["Name"]): dist.version
        for dist in metadata.distributions()
        if dist.metadata["Name"]
    }

    statuses: list[RequirementStatus] = []
    for raw_line in lines:
        package_name = extract_package_name(raw_line)
        if package_name is None:
            continue
        installed_version = installed.get(canonicalize_name(package_name))
        statuses.append(
            RequirementStatus(
                raw_line=raw_line.strip(),
                package_name=package_name,
                installed_version=installed_version,
            )
        )
    return statuses


def write_missing_requirements(path: Path, statuses: list[RequirementStatus]) -> None:
    missing_lines = [status.raw_line for status in statuses if not status.is_satisfied]
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(missing_lines)
    if missing_lines:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare overlay requirements against the current Python environment."
    )
    parser.add_argument(
        "--requirements",
        default="requirements-overlay.txt",
        help="Path to the overlay requirements file.",
    )
    parser.add_argument(
        "--write-missing",
        help="Optional path to write the subset of missing requirements.",
    )
    args = parser.parse_args()

    req_path = Path(args.requirements)
    if not req_path.exists():
        print(f"ERROR: Requirements file not found: {req_path}", file=sys.stderr)
        return 1

    statuses = scan_requirements(read_requirements(req_path))

    print("Overlay requirement scan")
    print(f"Interpreter: {sys.executable}")
    print(f"Requirements: {req_path}")
    print()

    if not statuses:
        print("No package requirements found.")
    else:
        print("Satisfied by fixed environment:")
        satisfied = [status for status in statuses if status.is_satisfied]
        if satisfied:
            for status in satisfied:
                print(f"  OK   {status.package_name} ({status.installed_version})")
        else:
            print("  None")

        print()
        print("Missing and must be shipped in overlay:")
        missing = [status for status in statuses if not status.is_satisfied]
        if missing:
            for status in missing:
                print(f"  ADD  {status.raw_line}")
        else:
            print("  None")

    if args.write_missing:
        out_path = Path(args.write_missing)
        write_missing_requirements(out_path, statuses)
        print()
        print(f"Wrote missing requirements to: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
