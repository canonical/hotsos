from hotsos.core.plugins.maas import MAASChecks


class MAASSummary(MAASChecks):
    """ Implementation of MAAS summary. """
    summary_part_index = 0

    # REMINDER: common entries are implemented in the SummaryBase base class
    #           and only application plugin specific customisations are
    #           implemented here. We use the get_min_available_entry_index() to
    #           ensure that additional entries don't clobber existing ones but
    #           conversely can also replace them by re-using their indices.

    # No custom entries defined here yet so currently relying on the defaults.
