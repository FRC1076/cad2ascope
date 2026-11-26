"""Compile and run generated Java against real WPILib jars, without Gradle.

Each WPILib year has its own jars and JDK:
- 2026: a Maven-layout folder in $WPILIB_MAVEN, else ~/wpilib/2026/maven (installed by the WPILib installer); javac
  from $JAVA_HOME, else ~/wpilib/2026/jdk, else PATH.
- 2027: $WPILIB_MAVEN_2027, else ~/wpilib/2027/maven; javac from $JAVA_HOME_2027, else ~/wpilib/2027/jdk. WPILib
  2027 needs Java 25.
`scripts/fetch-java-deps.py <folder> [--wpilib 2027]` fills such a folder. Tests for a year skip if its jars or JDK
are missing, unless CAD2ASCOPE_REQUIRE_JAVA (2026) or CAD2ASCOPE_REQUIRE_JAVA_2027 is set, as in CI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
YEARS = (2026, 2027)
COMMON = [
    "org/ejml/ejml-core",
    "org/ejml/ejml-ddense",
    "org/ejml/ejml-simple",
    "com/fasterxml/jackson/core/jackson-annotations",
    "com/fasterxml/jackson/core/jackson-core",
    "com/fasterxml/jackson/core/jackson-databind",
    "us/hebi/quickbuf/quickbuf-runtime",
    "org/junit/jupiter/junit-jupiter-api",
    "org/junit/jupiter/junit-jupiter-engine",
    "org/junit/platform/junit-platform-commons",
    "org/junit/platform/junit-platform-engine",
    "org/junit/platform/junit-platform-launcher",
    "org/opentest4j/opentest4j",
    "org/apiguardian/apiguardian-api",
]
ARTIFACTS = {
    2026: [
        "edu/wpi/first/wpimath/wpimath-java",
        "edu/wpi/first/wpiunits/wpiunits-java",
        "edu/wpi/first/wpiutil/wpiutil-java",
        *COMMON,
    ],
    2027: [
        "org/wpilib/wpimath/wpimath-java",
        "org/wpilib/wpiunits/wpiunits-java",
        "org/wpilib/wpiutil/wpiutil-java",
        *COMMON,
    ],
}
OPTIONAL = {"us/hebi/quickbuf/quickbuf-runtime"}
AKIT = "org/littletonrobotics/akit/akit-java"
ROBOT_ARTIFACTS = {
    2026: [
        "edu/wpi/first/wpilibj/wpilibj-java",
        "edu/wpi/first/wpilibNewCommands/wpilibNewCommands-java",
        "edu/wpi/first/hal/hal-java",
        "edu/wpi/first/ntcore/ntcore-java",
    ],
    2027: [
        "org/wpilib/wpilibj/wpilibj-java",
        "org/wpilib/commandsv2/commandsv2-java",
        "org/wpilib/tunables/tunables-java",  # Command implements org.wpilib.tunable.ComplexTunable
        "org/wpilib/hal/hal-java",
        "org/wpilib/ntcore/ntcore-java",
        "org/wpilib/datalog/datalog-java",
        "org/wpilib/telemetry/telemetry-java",
    ],
}


def _suffix(year: int) -> str:
    return "" if year == 2026 else f"_{year}"


def required(year: int = 2026) -> bool:
    """CI sets CAD2ASCOPE_REQUIRE_JAVA (2026) and CAD2ASCOPE_REQUIRE_JAVA_2027, so a missing JDK or jar fails."""
    return bool(os.environ.get(f"CAD2ASCOPE_REQUIRE_JAVA{_suffix(year)}"))


def maven_root(year: int = 2026) -> Path | None:
    env = os.environ.get(f"WPILIB_MAVEN{_suffix(year)}")
    if env and Path(env).is_dir():
        return Path(env)
    p = Path.home() / "wpilib" / str(year) / "maven"
    return p if p.is_dir() else None


def _version_key(v: str):
    return [int(x) if x.isdigit() else x for x in v.replace("-", ".").split(".")]


def classpath(root: Path, extra: list[str] | None = None, year: int = 2026) -> list[Path] | None:
    jars = []
    for art in ARTIFACTS[year] + (extra or []):
        d = root / art
        versions = sorted((v.name for v in d.iterdir() if v.is_dir()), key=_version_key) if d.is_dir() else []
        jar = None
        for v in reversed(versions):
            cand = d / v / f"{d.name}-{v}.jar"
            if cand.is_file():
                jar = cand
                break
        if jar is None:
            if art in OPTIONAL:
                continue
            return None
        jars.append(jar)
    return jars


def jdk_bin(year: int = 2026) -> Path | None:
    for base in [os.environ.get(f"JAVA_HOME{_suffix(year)}"), str(Path.home() / "wpilib" / str(year) / "jdk")]:
        if base and (Path(base) / "bin" / "javac").exists():
            return Path(base) / "bin"
    if year != 2026:
        return None  # the default javac on PATH is too old for WPILib 2027's Java 25 class files
    javac = shutil.which("javac")
    return Path(javac).parent if javac else None


def akit_jar(root: Path, year: int = 2026) -> Path | None:
    """AdvantageKit's jar, if the Maven folder has it (scripts/fetch-java-deps.py adds it; the WPILib installer does not)."""
    jars = classpath(root, [AKIT], year)
    return jars[-1] if jars and jars[-1].parent.parent.name == "akit-java" else None


def available(year: int = 2026) -> bool:
    root = maven_root(year)
    return root is not None and classpath(root, year=year) is not None and jdk_bin(year) is not None


def compile_and_test(
    java: str, test: str, package: str, workdir: Path, year: int = 2026
) -> subprocess.CompletedProcess:
    """Compile RobotModel + RobotModelTest + the runner, then run the test class. Returns the run's result."""
    jars = classpath(maven_root(year), year=year)  # type: ignore[arg-type]
    bin_ = jdk_bin(year)
    pkg_dir = workdir / "src" / Path(*package.split("."))
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "RobotModel.java").write_text(java)
    (pkg_dir / "RobotModelTest.java").write_text(test)
    out = workdir / "classes"
    out.mkdir(exist_ok=True)
    cp = os.pathsep.join(str(j) for j in jars)
    sources = [
        str(pkg_dir / "RobotModel.java"),
        str(pkg_dir / "RobotModelTest.java"),
        str(HERE / "java" / "RunTests.java"),
    ]
    javac = subprocess.run(
        [str(bin_ / "javac"), "-Xlint:all", "-Werror", "-d", str(out), "-cp", cp, *sources],
        capture_output=True,
        text=True,
    )
    if javac.returncode != 0:
        return javac
    return subprocess.run(
        [str(bin_ / "java"), "-cp", os.pathsep.join([str(out), cp]), "RunTests", f"{package}.RobotModelTest"],
        capture_output=True,
        text=True,
        timeout=300,
    )


def compile_robot_code(
    java: str, templates: dict[str, str], package: str, vis_package: str, workdir: Path, year: int = 2026
) -> subprocess.CompletedProcess:
    """Compile RobotModel plus the hand-owned templates against WPILib command-based jars (compile only).

    Uses AdvantageKit's real Logger when its jar is in the Maven folder. Otherwise, a compile-only stand-in, unless
    CAD2ASCOPE_REQUIRE_JAVA is set (CI), where a missing AdvantageKit jar is an error.
    """
    root = maven_root(year)
    jars = classpath(root, ROBOT_ARTIFACTS[year], year)  # type: ignore[arg-type]
    if jars is None:
        raise RuntimeError(f"WPILib {year} command-based jars not found")
    akit = akit_jar(root, year)  # type: ignore[arg-type]
    if akit is None and required(year):
        raise RuntimeError("AdvantageKit jar not found; run scripts/fetch-java-deps.py into $WPILIB_MAVEN")
    src = workdir / "src"
    gen = src / Path(*package.split("."))
    vis = src / Path(*vis_package.split("."))
    gen.mkdir(parents=True, exist_ok=True)
    vis.mkdir(parents=True, exist_ok=True)
    (gen / "RobotModel.java").write_text(java)
    files = [gen / "RobotModel.java"]
    for name, text in templates.items():
        (vis / name).write_text(text)
        files.append(vis / name)
    stub = HERE / "java" / "stubs" / "org" / "littletonrobotics" / "junction" / "Logger.java"
    if akit is not None:
        jars.append(akit)
    out = workdir / "classes"
    out.mkdir(exist_ok=True)
    cp = os.pathsep.join(str(j) for j in jars)
    return subprocess.run(
        [
            str(jdk_bin(year) / "javac"),
            "-Xlint:all",
            "-Xlint:-processing",
            "-Xlint:-classfile",  # wpilibNewCommands references an annotation jar the offline repo lacks
            "-Werror",
            "-d",
            str(out),
            "-cp",
            cp,
            *map(str, files),
            *([] if akit is not None else [str(stub)]),
        ],
        capture_output=True,
        text=True,
    )
