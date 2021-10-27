#!/usr/bin/python

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = '''
---
module: service_catalog
short_description: Manage OTC Service Catalog
extends_documentation_fragment: opentelekomcloud.cloud.otc
author: "Artem Goncharov (@gtema)"
description:
   - Maintain Service Catalog.
options:
    data:
        description: Path to the data file
        required: true
        type: dict
    target_env:
        description: Environment name from the data file
        required: true
        type: str
    skip_delete:
        description: Whether delete operations should be skipped
        type: bool
        default: true
    limit_services:
        description: Limit modification to the provided service types
        type: list
        elements: str
        default: []
'''


RETURN = '''
actions:
    description: List of actions
    type: list
    returned: Always
'''

EXAMPLES = '''
'''


from urllib.parse import urlparse

import openstack

from ansible_collections.opentelekomcloud.cloud.plugins.module_utils.otc import OTCModule


def urljoin(*args):
    """A custom version of urljoin that simply joins strings into a path.

    The real urljoin takes into account web semantics like when joining a url
    like /path this should be joined to http://host/path as it is an anchored
    link. We generally won't care about that in client.
    """
    return '/'.join(str(a or '').strip('/') for a in args)


class SCModule(OTCModule):
    argument_spec = dict(
        data=dict(type='dict', required=True),
        target_env=dict(type='str', required=True),
        skip_delete=dict(type='bool', default=True),
        limit_services=dict(type='list', elements='str', default=[])
    )
    module_kwargs = dict(
        supports_check_mode=True
    )

    def _update_service(self, existing, name, description, is_enabled):
        _url = urljoin(
            self.identity_ext_base,
            'OS-CATALOG', 'services'
        )
        return self.conn.identity._update(
            openstack.identity.v3.service.Service,
            existing,
            base_path=_url,
            name=name, description=description, is_enabled=is_enabled
        )

    def _create_service(self, srv_type, name, description, is_enabled):
        _url = urljoin(
            self.identity_ext_base, 'OS-CATALOG', 'services')
        return self.conn.identity._create(
            openstack.identity.v3.service.Service,
            base_path=_url,
            type=srv_type, name=name, description=description,
            is_enabled=is_enabled
        )

    def _delete_service(self, current):
        _url = urljoin(
            self.identity_ext_base,
            'OS-CATALOG', 'services', current.id
        )
        self.conn.identity.delete(_url)

    def _update_endpoint(self, current, url, is_enabled=True):
        _url = urljoin(
            self.identity_ext_base,
            'OS-CATALOG'
        )
        return self.conn.identity._update(
            openstack.identity.v3.endpoint.Endpoint,
            current,
            base_path=_url,
            url=url, is_enabled=is_enabled
        )

    def _create_endpoint(
        self,
        service_id, interface, url, region_id=None, is_enabled=True
    ):
        _url = urljoin(
            self.identity_ext_base,
            'OS-CATALOG', 'endpoints',
        )
        return self.conn.identity._create(
            openstack.identity.v3.endpoint.Endpoint,
            base_path=_url,
            service_id=service_id, interface=interface, region_id=region_id,
            url=url, is_enabled=is_enabled
        )

    def _delete_endpoint(self, current):
        _url = urljoin(
            self.identity_ext_base,
            'OS-CATALOG', current.id
        )
        self.conn.identity.delete(_url)

    def _is_srv_update_necessary(self, current, name, description, is_enabled):
        if current.name != name:
            return True
        if current.description != description:
            return True
        if current.is_enabled != is_enabled:
            return True
        return False

    def _is_ep_update_necessary(self, current, url, is_enabled=True):
        if current.url != url:
            return True
        if current.is_enabled != is_enabled:
            return True
        return False

    def run(self):
        changed = False
        target_env = self.params['target_env']
        skip_delete = self.params['skip_delete']
        limit_services = self.params['limit_services']
        identity_url = self.conn.identity.get_endpoint_data().url
        parsed_domain = urlparse(identity_url)
        log = []
        self.identity_ext_base = \
            f'{parsed_domain.scheme}://{parsed_domain.netloc}/v3.0'

        self.target_data = self.params['data']

        existing_services = list(self.conn.identity.services())
        existing_service_per_type = {k.type: k for k in existing_services}
        _used_services = set()
        _used_eps = set()
        results = dict(services=[], endpoints=[])
        log.append('test')
        for srv_type, target_srv in self.target_data.get(
                'services', {}).items():
            if limit_services and srv_type not in limit_services:
                log.append(f'Skipping processing of {srv_type}')
                continue
            else:
                log.append(f'Processing of {srv_type}')

            target_envs = target_srv.get('environments', {})
            if not (
                target_env in target_envs
                and target_envs.get(target_env) is not None
            ):
                log.append(f'Skipping service {srv_type} for {target_env}')
                continue
            current_srv = None
            current_eps = []
            target_name = target_srv.get('name')
            target_enabled = target_srv.get('enabled', True)
            target_description = target_srv.get('description')

            if srv_type and srv_type in existing_service_per_type:
                current_srv = existing_service_per_type.get(srv_type)
                if self._is_srv_update_necessary(
                        current_srv, target_name,
                        target_description, target_enabled):

                    changed = True
                    if not self.ansible.check_mode:
                        current_srv = self._update_service(
                            current_srv, target_name, target_description,
                            target_enabled)
                    results['services'].append({
                        'type': srv_type,
                        'operation': 'update',
                        'id': current_srv.id,
                        'current_name': current_srv.name,
                        'new_name': target_name,
                        'current_enabled': current_srv.is_enabled,
                        'new_enabled': target_enabled,
                        'current_description': current_srv.description,
                        'new_description': target_description,
                    })
            else:
                changed = True
                if not self.ansible.check_mode:
                    current_srv = self._create_service(
                        srv_type, target_name, target_description,
                        target_enabled)
                results['services'].append({
                    'type': srv_type,
                    'operation': 'create',
                    'new_name': target_name,
                    'new_enabled': target_enabled,
                    'new_description': target_description,
                })

            if hasattr(current_srv, 'id'):
                # make dry_run easier
                _used_services.add(current_srv.id)
                current_eps = list(self.conn.identity.endpoints(
                    service_id=current_srv.id))
            target_ep = target_envs.get(target_env, {})
            for region_id, target_eps in target_ep.get(
                    'endpoints', {}).items():
                for tep in target_eps:
                    target_interface = tep.get('interface', 'public')
                    target_url = tep['url']  # done explicitly to force
                    # presence
                    target_enabled = tep.get('enabled', True)
                    _ep_found = False
                    ep = None

                    for cep in current_eps:
                        # Dirty hack to compare region = None
                        cep_region = cep.region_id if cep.region_id \
                            is not None else ""

                        if (
                            region_id == cep_region
                            and target_interface == cep.interface
                        ):
                            # Found matching EP
                            _ep_found = True
                            if self._is_ep_update_necessary(cep,
                                                            target_url,
                                                            target_enabled):
                                changed = True
                                if not self.ansible.check_mode:
                                    ep = self._update_endpoint(
                                        cep, target_url,
                                        is_enabled=target_enabled)
                                else:
                                    ep = cep
                                results['endpoints'].append({
                                    'service_type': srv_type,
                                    'operation': 'update',
                                    'id': cep.id,
                                    'interface': target_interface,
                                    'current_url': cep.url,
                                    'new_url': target_url,
                                    'current_enabled': cep.is_enabled,
                                    'new_enabled': target_enabled,
                                })

                            else:
                                ep = cep
                            break  # no need to continue
                    if not _ep_found:
                        changed = True
                        if not self.ansible.check_mode:
                            ep = self._create_endpoint(
                                current_srv.id, target_interface,
                                target_url, region_id, target_enabled)
                        results['endpoints'].append({
                            'service_type': srv_type,
                            'operation': 'create',
                            'region_id': region_id,
                            'interface': target_interface,
                            'new_url': target_url,
                            'new_enabled': target_enabled,
                        })

                    if hasattr(ep, 'id'):
                        # Friendly dry_run
                        _used_eps.add(ep.id)

        if not limit_services:
            # NOTE(gtema): Can't do cleanup of unused when filter requested
            if not skip_delete:
                # Cleanup useless endpoints
                for existing_ep in self.conn.identity.endpoints():
                    if existing_ep.id not in _used_eps:
                        changed = True
                        if not self.ansible.check_mode:
                            self._delete_endpoint(existing_ep)
                        results['endpoints'].append({
                            'operation': 'delete',
                            'id': existing_ep.id,
                            'current_url': existing_ep.url,
                            'current_enabled': existing_ep.is_enabled
                        })

                # Cleanup of unused or duplicated entries
                for srv in existing_services:
                    if srv.id not in _used_services:
                        changed = True
                        if not self.ansible.check_mode:
                            self._delete_service(srv)
                        results['services'].append({
                            'type': srv.type,
                            'operation': 'delete',
                            'id': srv.id,
                            'current_name': srv.name,
                            'current_description': srv.description,
                            'current_enabled': srv.is_enabled
                        })
        self.exit(
            changed=changed,
            log=log,
            actions=results)


def main():
    module = SCModule()
    module()


if __name__ == '__main__':
    main()
