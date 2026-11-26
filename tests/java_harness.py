"""Compile and run generated Java against real WPILib jars, without Gradle.

Looks for a Maven-layout folder with WPILib and JUnit jars: $WPILIB_MAVEN, else ~/wpilib/<year>/maven (installed
by the WPILib installer). Looks for javac in $JAVA_HOME, else the WPILib JDK, else PATH. Tests skip if either is
missing; CI provides both (.github/workflows/ci.yml).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
ARTIFACTS = [
    "edu/wpi/first/wpimath/wpimath-java",
    "edu/wpi/first/wpiunits/wpiunits-java",
    "edu/wpi/first/wpiutil/wpiutil-java",
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
OPTIONAL = {"us/hebi/quickbuf/quickbuf-runtime"}
AKIT = "org/littletonrobotics/akit/akit-java"
ROBOT_ARTIFACTS = [
    "edu/wpi/first/wpilibj/wpilibj-java",
    "edu/wpi/first/wpilibNewCommands/wpilibNewCommands-java",
    "edu/wpi/first/hal/hal-java",
    "edu/wpi/first/ntcore/ntcore-java",
]


def maven_root() -> Path | None:
    env = os.environ.get("WPILIB_MAVEN")
    if env and Path(env).is_dir():
        return Path(env)
    for year in ("2027", "2026"):
        p = Path.home() / "wpilib" / year / "maven"
        if p.is_dir():
            return p
    return None


def _version_key(v: str):
    return [int(x) if x.isdigit() else x for x in v.replace("-", ".").split(".")]


def classpath(root: Path, extra: list[str] | None = None) -> list[Path] | None:
    jars = []
    for art in ARTIFACTS + (extra or []):
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


def jdk_bin() -> Path | None:
    for base in [os.environ.get("JAVA_HOME"), *(str(Path.home() / "wpilib" / y / "jdk") for y in ("2027", "2026"))]:
        if base and (Path(base) / "bin" / "javac").exists():
            return Path(base) / "bin"
    javac = shutil.which("javac")
    return Path(javac).parent if javac else None


def akit_jar(root: Path) -> Path | None:
    """AdvantageKit's jar, if the Maven folder has it (scripts/fetch-java-deps.py adds it; the WPILib installer does not)."""
    jars = classpath(root, [AKIT])
    return jars[-1] if jars and jars[-1].parent.parent.name == "akit-java" else None


def available() -> bool:
    root = maven_root()
    return root is not None and classpath(root) is not None and jdk_bin() is not None


def compile_and_test(java: str, test: str, package: str, workdir: Path) -> subprocess.CompletedProcess:
    """Compile RobotModel + RobotModelTest + the runner, then run the test class. Returns the run's result."""
    jars = classpath(maven_root())  # type: ignore[arg-type]
    bin_ = jdk_bin()
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
    java: str, templates: dict[str, str], package: str, vis_package: str, workdir: Path
) -> subprocess.CompletedProcess:
    """Compile RobotModel plus the hand-owned templates against WPILib command-based jars (compile only).

    Uses AdvantageKit's real Logger when its jar is in the Maven folder. Otherwise, a compile-only stand-in, unless
    CAD2ASCOPE_REQUIRE_JAVA is set (CI), where a missing AdvantageKit jar is an error.
    """
    root = maven_root()
    jars = classpath(root, ROBOT_ARTIFACTS)  # type: ignore[arg-type]
    if jars is None:
        raise RuntimeError("WPILib command-based jars not found")
    akit = akit_jar(root)  # type: ignore[arg-type]
    if akit is None and os.environ.get("CAD2ASCOPE_REQUIRE_JAVA"):
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
            str(jdk_bin() / "javac"),
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
