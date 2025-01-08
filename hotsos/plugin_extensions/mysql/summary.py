from hotsos.core.plugins.mysql import MySQLChecks


class MySQLSummary(MySQLChecks):
    """ Implementation of MySQL summary. """
    summary_part_index = 0

    # REMINDER: Common entries are implemented in
    #           plugintools.ApplicationSummaryBase. Only customisations are
    #           implemented here. See
    #           plugintools.get_min_available_entry_index() for an explanation
    #           on how entry indices are managed.

    # NOTE: no custom entries defined here yet so plugin will only use
    #       defaults.
