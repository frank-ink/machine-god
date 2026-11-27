def order(graph):
    pending = {task: set(dependencies) for task, dependencies in graph.items()}
    for dependencies in graph.values():
        for name in dependencies:
            pending.setdefault(name, set())
    result = []
    while pending:
        ready = [name for name, dependencies in pending.items() if not dependencies]
        if not ready:
            raise ValueError("cycle")
        name = min(ready)
        del pending[name]
        result.append(name)
        for dependencies in pending.values():
            dependencies.discard(name)
    return result
