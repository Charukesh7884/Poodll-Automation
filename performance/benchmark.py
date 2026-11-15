import time
from config import Config


class BenchmarkTracker:
    """
    Measures and generates detailed performance and timing reports
    for Moodle Playwright automation runs.
    """

    def __init__(self):
        self.start_total = time.perf_counter()
        self.timers: dict[str, float] = {}
        self.durations: dict[str, float] = {}
        self.activity_times: list[dict] = []
        self.retries = 0
        self.failures = 0
        self.fixed_sleeps = 0

    def start_timer(self, name: str):
        """Starts a named stopwatch."""
        self.timers[name] = time.perf_counter()

    def stop_timer(self, name: str) -> float:
        """Stops a named stopwatch and records the elapsed time."""
        if name in self.timers:
            elapsed = time.perf_counter() - self.timers[name]
            self.durations[name] = self.durations.get(name, 0.0) + elapsed
            return elapsed
        return 0.0

    def record_activity(self, title: str, duration: float, success: bool = True):
        """Records the execution duration and outcome of a specific activity."""
        self.activity_times.append({
            "title": title,
            "duration": duration,
            "success": success
        })
        if not success:
            self.failures += 1

    def record_retry(self):
        """Increments the retry counter."""
        self.retries += 1

    def print_report(self, router=None):
        """Prints the standardized MOODLE PERFORMANCE REPORT to stdout."""
        if not Config.BENCHMARK:
            return

        total_elapsed = time.perf_counter() - self.start_total

        auth_time = self.durations.get("auth", 0.0)
        dash_time = self.durations.get("dashboard", 0.0)
        course_time = self.durations.get("course_discovery", 0.0)
        act_disc_time = self.durations.get("activity_discovery", 0.0)

        act_count = len(self.activity_times)
        act_durations = [a["duration"] for a in self.activity_times]

        act_avg = sum(act_durations) / act_count if act_count > 0 else 0.0
        act_fastest = min(act_durations) if act_durations else 0.0
        act_slowest = max(act_durations) if act_durations else 0.0

        net_requests = router.total_requests if router else 0
        net_blocked = router.blocked_requests if router else 0

        print()
        print("=" * 45)
        print("       MOODLE PERFORMANCE REPORT")
        print("=" * 45)
        print(f"Authentication restore   {auth_time:8.2f} sec")
        if dash_time > 0:
            print(f"Dashboard navigation     {dash_time:8.2f} sec")
        if course_time > 0:
            print(f"Course discovery         {course_time:8.2f} sec")
        if act_disc_time > 0:
            print(f"Activity discovery       {act_disc_time:8.2f} sec")

        print()
        print(f"Activities processed:    {act_count:>8}")
        if act_count > 0:
            print()
            print(f"Activity average:        {act_avg:8.2f} sec")
            print(f"Fastest activity:        {act_fastest:8.2f} sec")
            print(f"Slowest activity:        {act_slowest:8.2f} sec")

        print()
        print(f"Network requests:        {net_requests:>8}")
        print(f"Blocked requests:        {net_blocked:>8}")

        print()
        print(f"Fixed sleeps:            {self.fixed_sleeps:>8}")
        print(f"Timeout retries:         {self.retries:>8}")
        print(f"Failures:                {self.failures:>8}")

        print("-" * 45)
        print(f"TOTAL TIME:              {total_elapsed:8.2f} sec")
        print("=" * 45)
        print()
