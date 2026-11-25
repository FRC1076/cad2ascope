// Template written once by `cad2ascope init`. The software subteam owns this file after that.
// RobotModel is GENERATED; do not edit it. Only the two recordOutput calls depend on the
// logging library, so switching to WPILib Telemetry for 2027 changes only those lines.

package frc.robot.visualization;

import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.robot.generated.RobotModel;
import frc.robot.generated.RobotModel.Signal;
import java.util.Arrays;
import org.littletonrobotics.junction.Logger;

/** Collects mechanism positions from subsystems and logs 3D component poses for AdvantageScope. */
public class RobotVisualizer extends SubsystemBase {
  private final double[] measured = new double[Signal.values().length];
  private final double[] setpoints = new double[Signal.values().length];

  /** Measured position in SI units (meters or radians), with the robot code's zero. */
  public void set(Signal signal, double value) {
    measured[signal.ordinal()] = value;
  }

  /** Target position in SI units. Drawn as a ghost robot in AdvantageScope. */
  public void setSetpoint(Signal signal, double value) {
    setpoints[signal.ordinal()] = value;
  }

  @Override
  public void periodic() {
    Logger.recordOutput("RobotModel/Measured", RobotModel.componentPoses(Arrays.copyOf(measured, measured.length)));
    Logger.recordOutput("RobotModel/Setpoint", RobotModel.componentPoses(Arrays.copyOf(setpoints, setpoints.length)));
  }
}
