import time

from humex.metrics.metric_trace import MetricTrace
from humex.metrics.monitors import monitor_mapping
from humex.utils.data_loader import DataLoader


class MonitorEvaluator(object):
    def __init__(self, scenario, logs=None):
        self.scenario = scenario
        self.monitors = dict()  # {monitor_name: monitor_object}
        self.results = dict()   # {monitor_name: MetricTrace}
        self.logs = logs

    def _log(self, msg):
        print(msg)
        if self.logs is not None:
            self.logs.append(msg)

    def add(self, name, params=None):
        if name not in monitor_mapping:
            raise ValueError(f'Monitor: {name} not found!')
        if name not in self.monitors:
            if params:
                self.monitors[name] = monitor_mapping[name](self.scenario, params=params)
            else:
                self.monitors[name] = monitor_mapping[name](self.scenario)
            params_str = f" (params: {', '.join(f'{k}={v}' for k, v in params.items())})" if params else ""
            self._log(f"Registering monitor: {name}{params_str}")

    def run(self):
        """Run all monitors on scenario frames.

        Returns:
            dict: {monitor_name: MetricTrace} mapping results
        """
        num_frames = len(self.scenario.frames)
        self._log(f"Running {len(self.monitors)} monitors over {num_frames} frames...")
        start_time = time.time()

        for ts, frame in self.scenario.frames.items():
            for name, monitor in self.monitors.items():
                monitor.run(frame)

        # Collect MetricTrace output from each monitor
        for name, monitor in self.monitors.items():
            self.results[name] = monitor.output()

        elapsed = time.time() - start_time
        self._log(f"Monitor evaluation complete: {len(self.monitors)} monitors, {num_frames} frames, {elapsed:.3f}s")

        return self.results

    def get_result(self, name) -> MetricTrace:
        """Get monitor result as MetricTrace.

        Args:
            name (str): Monitor name

        Returns:
            MetricTrace: Monitor evaluation results
        """
        return self.results[name]

    def eval_monitor(self, name) -> MetricTrace:
        """Get monitor evaluation results for analyzer usage.

        Args:
            name (str): Monitor name

        Returns:
            MetricTrace: Monitor evaluation results with timestamps and values
        """
        return self.results[name]


if __name__=='__main__':
    scenario = DataLoader().load('collision')
    x = MonitorEvaluator(scenario)
    x.add('ego_speed')
    results = x.run()
    print(results)
    # results = x.run('ego_out_of_map')
    # print(results)
