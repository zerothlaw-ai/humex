from humex.metrics.dag.dag import MetricDAG


if __name__ == "__main__":
    dag = MetricDAG()
    dag.load_from_yaml('../data/dag_cfg/simple_speed_compliance.yaml')
    dag.visualize()
