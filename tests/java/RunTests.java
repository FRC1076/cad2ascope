// Minimal JUnit 5 runner, so generated tests can run without Gradle: java RunTests <fully.qualified.TestClass>
import static org.junit.platform.engine.discovery.DiscoverySelectors.selectClass;

import java.io.PrintWriter;
import org.junit.platform.launcher.Launcher;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;
import org.junit.platform.launcher.listeners.SummaryGeneratingListener;
import org.junit.platform.launcher.listeners.TestExecutionSummary;

public class RunTests {
  public static void main(String[] args) throws Exception {
    LauncherDiscoveryRequest request =
        LauncherDiscoveryRequestBuilder.request().selectors(selectClass(Class.forName(args[0]))).build();
    Launcher launcher = LauncherFactory.create();
    SummaryGeneratingListener listener = new SummaryGeneratingListener();
    launcher.execute(request, listener);
    TestExecutionSummary summary = listener.getSummary();
    PrintWriter out = new PrintWriter(System.out, true);
    out.println("tests found " + summary.getTestsFoundCount() + ", passed " + summary.getTestsSucceededCount()
        + ", failed " + summary.getTotalFailureCount());
    summary.printFailuresTo(out, 25);
    System.exit(summary.getTotalFailureCount() == 0 && summary.getTestsSucceededCount() > 0 ? 0 : 1);
  }
}
