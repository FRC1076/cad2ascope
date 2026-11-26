"""Download the WPILib, AdvantageKit and JUnit jars the generated-Java tests need, into a Maven-layout folder.

    python scripts/fetch-java-deps.py <folder>      then   WPILIB_MAVEN=<folder> uv run pytest

Used by CI, where the WPILib installer is not available. Versions match the WPILib 2026.2.1 installer's offline
Maven repository. Each jar is checked against the .sha1 file its repository publishes.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import requests  # carries its own CA bundle; urllib in uv's macOS Python has none

WPILIB = "https://frcmaven.wpi.edu/artifactory/release"
CENTRAL = "https://repo1.maven.org/maven2"
AKIT = "https://frcmaven.wpi.edu/artifactory/littletonrobotics-mvn-release"  # from AdvantageKit's vendordep
WPI_VERSION = "2026.2.1"
JARS = [
    (WPILIB, "edu.wpi.first.wpimath", "wpimath-java", WPI_VERSION),
    (WPILIB, "edu.wpi.first.wpiunits", "wpiunits-java", WPI_VERSION),
    (WPILIB, "edu.wpi.first.wpiutil", "wpiutil-java", WPI_VERSION),
    (WPILIB, "edu.wpi.first.wpilibj", "wpilibj-java", WPI_VERSION),
    (WPILIB, "edu.wpi.first.wpilibNewCommands", "wpilibNewCommands-java", WPI_VERSION),
    (WPILIB, "edu.wpi.first.hal", "hal-java", WPI_VERSION),
    (WPILIB, "edu.wpi.first.ntcore", "ntcore-java", WPI_VERSION),
    (AKIT, "org.littletonrobotics.akit", "akit-java", "26.0.2"),  # FRC 1076's 2026 robot code uses this
    (CENTRAL, "org.ejml", "ejml-core", "0.44.0"),
    (CENTRAL, "org.ejml", "ejml-ddense", "0.44.0"),
    (CENTRAL, "org.ejml", "ejml-simple", "0.44.0"),
    (CENTRAL, "com.fasterxml.jackson.core", "jackson-annotations", "2.19.2"),
    (CENTRAL, "com.fasterxml.jackson.core", "jackson-core", "2.19.2"),
    (CENTRAL, "com.fasterxml.jackson.core", "jackson-databind", "2.19.2"),
    (CENTRAL, "us.hebi.quickbuf", "quickbuf-runtime", "1.4"),
    (CENTRAL, "org.junit.jupiter", "junit-jupiter-api", "5.10.1"),
    (CENTRAL, "org.junit.jupiter", "junit-jupiter-engine", "5.10.1"),
    (CENTRAL, "org.junit.platform", "junit-platform-commons", "1.10.1"),
    (CENTRAL, "org.junit.platform", "junit-platform-engine", "1.10.1"),
    (CENTRAL, "org.junit.platform", "junit-platform-launcher", "1.10.1"),
    (CENTRAL, "org.opentest4j", "opentest4j", "1.3.0"),
    (CENTRAL, "org.apiguardian", "apiguardian-api", "1.1.2"),
]


def fetch(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def main(dest: Path) -> int:
    for repo, group, artifact, version in JARS:
        rel = Path(*group.split("."), artifact, version, f"{artifact}-{version}.jar")
        out = dest / rel
        if out.is_file():
            continue
        url = f"{repo}/{rel.as_posix()}"
        data = fetch(url)
        expected = fetch(url + ".sha1").decode().split()[0].strip()
        actual = hashlib.sha1(data).hexdigest()  # noqa: S324 (Maven's published checksum format)
        if actual != expected:
            print(f"checksum mismatch for {url}", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"fetched {rel.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
