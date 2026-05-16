import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex.api.ai_api import TranslateMetrics
from humex.api.metrics_api import MonitorDiscoveryAPI, OperatorDiscoveryAPI


if __name__ == "__main__":
    translator = TranslateMetrics()
    requirement = \
    """
    Highway lane change acceptance
    When ego requests lane change at speed ≥ 15 m/s, it must
    only execute if predicted rear-vehicle TTC in target lane ≥ 3.0 s and front gap ≥ 20 m,
    complete lane boundary crossing within ≤ 4.0 s after acceptance,
    keep lateral jerk ≤ 1.5 m/s³,
    and ensure minimum lateral clearance to any vehicle ≥ 1.0 m throughout maneuver.
    """


    result = translator.translate(requirement, save_visualization=True)
    print(result)
