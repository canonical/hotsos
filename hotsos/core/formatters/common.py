import yaml


class HOTSOSDumper(yaml.Dumper):  # pylint: disable=too-many-ancestors
    """ Custom yaml dumper that preserves order. """
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def represent_dict_preserve_order(self, data):
        """ Represent a dict preserving its key insertion order. """
        return self.represent_dict(data.items())


def yaml_dump(data):
    """
    This is our version of yaml.dump but ensuring the format/style that we
    want.
    """
    HOTSOSDumper.add_representer(
        dict,
        HOTSOSDumper.represent_dict_preserve_order)
    return yaml.dump(data, Dumper=HOTSOSDumper,
                     default_flow_style=False).rstrip("\n")
