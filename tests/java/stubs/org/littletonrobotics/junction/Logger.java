// Compile-only stand-in for AdvantageKit's Logger, so the RobotVisualizer template can be compiled without the
// AdvantageKit vendordep. Only the method the template calls is declared. Used only when the AdvantageKit jar is
// missing locally; CI compiles against the real akit-java (scripts/fetch-java-deps.py).
package org.littletonrobotics.junction;

import edu.wpi.first.math.geometry.Pose3d;

public final class Logger {
  private Logger() {}

  public static void recordOutput(String key, Pose3d... value) {}
}
