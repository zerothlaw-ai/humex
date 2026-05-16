import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from humex.api.core_apis import TranslateMetrics
from humex.api.core_apis import MonitorDiscoveryAPI, OperatorDiscoveryAPI

if __name__ == "__main__":
    print('testing')

    tm = TranslateMetrics()
    result = tm.translate(
        'When a pedestrian is detected, the car must decelerate within 0.5 seconds and stay below 10 m/s within 2 seconds',
        save_yaml=True,
        save_visualization=True
    )
    print(result)

    # d = MonitorDiscoveryAPI()
    # res = d.get_monitors_info()
    # print(res)

