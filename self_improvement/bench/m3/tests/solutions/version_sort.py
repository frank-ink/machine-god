def version_sort(versions):
    def key(version):
        components = [int(part) for part in version.split(".")]
        while components and components[-1] == 0:
            components.pop()
        return tuple(components)
    return sorted(versions, key=key)
