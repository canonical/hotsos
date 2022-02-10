import datetime
import os

from charmhelpers.core import hookenv

from charms.reactive import hook
from charms.reactive import RelationBase
from charms.reactive import scopes


class NrpeExternalMasterProvides(RelationBase):
    scope = scopes.GLOBAL

    @hook('{provides:nrpe-external-master}-relation-{joined,changed}')
    def changed_nrpe(self):
        self.set_state('{relation_name}.available')

    @hook('{provides:nrpe-external-master}-relation-{broken,departed}')
    def broken_nrpe(self):
        self.remove_state('{relation_name}.available')

    def add_check(self, args, name=None, description=None, context=None,
                  servicegroups=None, unit=None):
        nagios_files = self.get_local('nagios.check.files', [])

        if not unit:
            unit = hookenv.local_unit()
        unit = unit.replace('/', '-')
        context = self.get_remote('nagios_host_context', context)
        host_name = self.get_remote('nagios_hostname',
                                    '%s-%s' % (context, unit))

        check_tmpl = """
#---------------------------------------------------
# This file is Juju managed
#---------------------------------------------------
command[%(check_name)s]=%(check_args)s
"""
        service_tmpl = """
#---------------------------------------------------
# This file is Juju managed
#---------------------------------------------------
define service {
    use                             active-service
    host_name                       %(host_name)s
    service_description             %(description)s
    check_command                   check_nrpe!%(check_name)s
    servicegroups                   %(servicegroups)s
}
"""
        check_filename = "/etc/nagios/nrpe.d/check_%s.cfg" % (name)
        with open(check_filename, "w") as fh:
            fh.write(check_tmpl % {
                'check_args': ' '.join(args),
                'check_name': name,
            })
        nagios_files.append(check_filename)

        service_filename = "/var/lib/nagios/export/service__%s_%s.cfg" % (
                           unit, name)
        with open(service_filename, "w") as fh:
            fh.write(service_tmpl % {
                'servicegroups': servicegroups or context,
                'context': context,
                'description': description,
                'check_name': name,
                'host_name': host_name,
                'unit_name': unit,
            })
        nagios_files.append(service_filename)

        self.set_local('nagios.check.files', nagios_files)

    def removed(self):
        files = self.get_local('nagios.check.files', [])
        for f in files:
            try:
                os.unlink(f)
            except Exception as e:
                hookenv.log("failed to remove %s: %s" % (f, e))
        self.set_local('nagios.check.files', [])
        self.remove_state('{relation_name}.removed')

    def added(self):
        self.updated()

    def updated(self):
        relation_info = {
            'timestamp': datetime.datetime.now().isoformat(),
        }
        self.set_remote(**relation_info)
