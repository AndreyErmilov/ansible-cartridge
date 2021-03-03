#!/usr/bin/python

import pkgutil

if pkgutil.find_loader('ansible.module_utils.helpers'):
    import ansible.module_utils.helpers as helpers
else:
    import module_utils.helpers as helpers

argument_spec = {
    'hostvars': {'required': True, 'type': 'dict'},
    'play_hosts': {'required': True, 'type': 'list'},
    'console_sock': {'required': True, 'type': 'str'},
}

format_replicaset_func = '''
local function format_replicaset(r)
    local instances = {}
    for _, s in ipairs(r.servers) do
        if s.alias ~= nil then
            table.insert(instances, s.alias)
        end
    end

    return {
        uuid = r.uuid,
        alias = r.alias,
        roles = r.roles,
        all_rw = r.all_rw,
        weight = r.weight,
        vshard_group = r.vshard_group,
        instances = instances,
    }
end'''

format_server_func = '''
local function format_server(s)
    local replicaset_uuid
    if s.replicaset ~= nil then
        replicaset_uuid = s.replicaset.uuid
    end

    return {
        uuid = s.uuid,
        uri = s.uri,
        alias = s.alias,
        zone = s.zone,
        replicaset_uuid = replicaset_uuid,
    }
end'''

get_replicasets_func_body = '''
%s

local replicasets = require('cartridge').admin_get_replicasets()
local ret = {}

for _, r in ipairs(replicasets) do
    if r.alias ~= nil then
        ret[r.alias] = format_replicaset(r)
    end
end

return ret
''' % format_replicaset_func

get_instances_func_body = '''
%s

local servers = require('cartridge').admin_get_servers()
local ret = {}

for _, s in ipairs(servers) do
    if s.alias ~= nil then
        ret[s.alias] = format_server(s)
    end
end

return ret
''' % format_server_func

edit_topology_func_body = '''
%s
%s

local res, err = require('cartridge').admin_edit_topology(...)

if err ~= nil then
    return nil, err
end

local ret = {
    replicasets = setmetatable({}, {__serialize = 'map'}),
    servers = setmetatable({}, {__serialize = 'map'}),
}
for _, r in ipairs(res.replicasets or {}) do
    if r.alias ~= nil then
        ret.replicasets[r.alias] = format_replicaset(r)
    end
end

for _, s in ipairs(res.servers or {}) do
    if s.alias ~= nil then
        ret.servers[s.alias] = format_server(s)
    end
end
return ret
''' % (format_replicaset_func, format_server_func)


def get_cluster_instances(control_console):
    instances, _ = control_console.eval_res_err(get_instances_func_body)

    return instances


def get_configured_replicasets(hostvars, play_hosts):
    replicasets = {}
    for instance_name, instance_vars in hostvars.items():
        if instance_name not in play_hosts:
            continue

        if helpers.is_expelled(instance_vars) or helpers.is_stateboard(instance_vars):
            continue

        if 'replicaset_alias' in instance_vars:
            replicaset_alias = instance_vars['replicaset_alias']
            if replicaset_alias not in replicasets:
                replicasets.update({
                    replicaset_alias: {
                        'instances': [],
                        'roles': instance_vars.get('roles', None),
                        'failover_priority': instance_vars.get('failover_priority', None),
                        'all_rw': instance_vars.get('all_rw', None),
                        'weight': instance_vars.get('weight', None),
                        'vshard_group': instance_vars.get('vshard_group', None),
                        'alias': replicaset_alias,
                    }
                })
            replicasets[replicaset_alias]['instances'].append(instance_name)

    return replicasets


def get_instances_to_configure(hostvars, play_hosts):
    instances = {}

    for instance_name in play_hosts:
        instance_vars = hostvars[instance_name]
        if helpers.is_stateboard(instance_vars):
            continue

        instance = {
            'alias': instance_name,
        }

        if helpers.is_expelled(instance_vars):
            instance['expelled'] = True

        if 'zone' in instance_vars:
            instance['zone'] = instance_vars['zone']

        if instance:
            instances[instance_name] = instance

    return instances


def get_cluster_replicasets(control_console):
    cluster_replicasets, _ = control_console.eval_res_err(get_replicasets_func_body)

    if not cluster_replicasets:
        cluster_replicasets = dict()

    return cluster_replicasets


def add_edit_replicaset_param_if_required(edit_replicaset_params, replicaset, cluster_replicaset, param_name):
    if replicaset.get(param_name) is None:
        return

    if cluster_replicaset is not None:
        if param_name == 'roles':
            if set(replicaset.get('roles', [])) == set(cluster_replicaset.get('roles', [])):
                return

        if replicaset.get(param_name) == cluster_replicaset.get(param_name):
            return

    edit_replicaset_params[param_name] = replicaset.get(param_name)


def get_edit_replicaset_params(replicaset, cluster_replicaset, cluster_instances):
    """
    input EditReplicasetInput {
        uuid: String
        weight: Float
        vshard_group: String
        join_servers: [JoinServerInput]
        roles: [String!]
        alias: String!
        all_rw: Boolean
        failover_priority: [String!]
    }
    """

    edit_replicaset_params = {}

    if cluster_replicaset is not None:
        edit_replicaset_params['uuid'] = cluster_replicaset['uuid']
    else:
        edit_replicaset_params['alias'] = replicaset['alias']

    for param_name in ['weight', 'vshard_group', 'all_rw', 'roles']:
        add_edit_replicaset_param_if_required(
            edit_replicaset_params, replicaset, cluster_replicaset, param_name
        )

    current_instances = []
    if cluster_replicaset is not None:
        current_instances = cluster_replicaset.get('instances')

    instances_to_join = list(
        set(replicaset['instances']) - set(current_instances)
    )

    # generally, we always apply failover priority AFTER
    # all other changes
    # the only one optimization is to join new replicaset
    # with failover priority
    # and call second `edit_topology` only for replicasets that have
    # failover priority different from the specified

    if instances_to_join:
        if cluster_replicaset is None:
            # we create new replicaset - let's join instances in failover priority
            # to avoid second edit_toplogy call
            if replicaset['failover_priority']:
                if not all([s in cluster_instances for s in replicaset['failover_priority']]):
                    instances_not_in_cluster_str = ', '.join([
                        s for s in replicaset['failover_priority'] if s not in cluster_instances
                    ])
                    err = "Some of instances specified in failover_priority aren't found in cluster: %s"
                    return None, err % instances_not_in_cluster_str

                first_instances_to_join = [
                    instance_name for instance_name in replicaset['failover_priority']
                    if instance_name in instances_to_join
                ]

                instances_to_join = first_instances_to_join + [
                    instance for instance in instances_to_join if instance not in first_instances_to_join
                ]

        if not all([s in cluster_instances for s in instances_to_join]):
            instances_not_in_cluster_str = ', '.join([
                s for s in instances_to_join if s not in cluster_instances
            ])

            return None, "Some of replicaset instances aren't found in cluster: %s " % instances_not_in_cluster_str

        edit_replicaset_params['join_servers'] = [
            {'uri': cluster_instances[s]['uri']}
            for s in instances_to_join
        ]

    if 'uuid' in edit_replicaset_params and len(edit_replicaset_params) == 1:
        # replicaset is already exists
        # and all parameters are the same as configured
        return None, None

    return edit_replicaset_params, None


def get_edit_replicasets_params(replicasets, cluster_replicasets, cluster_instances):
    edit_replicasets_params = []

    for _, replicaset in replicasets.items():
        cluster_replicaset = cluster_replicasets.get(replicaset['alias'])

        edit_replicaset_params, err = get_edit_replicaset_params(
            replicaset, cluster_replicaset, cluster_instances
        )

        if err is not None:
            return None, "Failed to get edit topology params for replicaset %s: %s" % (
                replicaset['alias'], err
            )

        if edit_replicaset_params is not None:
            edit_replicasets_params.append(edit_replicaset_params)

    return edit_replicasets_params, None


def get_expel_servers_params(instances, cluster_instances):
    expel_servers_params = []
    for instance_name, instance_params in instances.items():
        if instance_params.get('expelled') is not True:
            continue

        if instance_name not in cluster_instances:
            continue

        if not cluster_instances[instance_name].get('uuid'):
            continue

        expel_servers_params.append({
            'uuid': cluster_instances[instance_name]['uuid'],
            'expelled': True,
        })

    return expel_servers_params, None


def get_edit_topology_params(replicasets, cluster_replicasets, instances, cluster_instances):
    edit_topology_params = {}

    edit_replicasets_params, err = get_edit_replicasets_params(replicasets, cluster_replicasets, cluster_instances)
    if err is not None:
        return None, err

    if edit_replicasets_params:
        edit_topology_params['replicasets'] = edit_replicasets_params

    expel_servers_params, err = get_expel_servers_params(instances, cluster_instances)
    if err is not None:
        return None, err

    if expel_servers_params:
        edit_topology_params['servers'] = expel_servers_params

    return edit_topology_params, None


def get_edit_failover_priority_params(replicasets, cluster_replicasets, cluster_instances):
    edit_topology_params = {}
    edit_replicasets_params = []

    for alias, cluster_replicaset in cluster_replicasets.items():
        if alias not in replicasets:
            continue

        failover_priority = replicasets[alias].get('failover_priority')
        if failover_priority is None:
            continue

        if cluster_replicaset['instances'][:len(failover_priority)] != failover_priority:
            failover_priority_uuids = [
                cluster_instances[instance_name]['uuid'] for instance_name in failover_priority
                if instance_name in cluster_instances  # false if instance is expelled
            ]

            edit_replicasets_params.append({
                'uuid': cluster_replicaset['uuid'],
                'failover_priority': failover_priority_uuids,
            })

    if edit_replicasets_params:
        edit_topology_params['replicasets'] = edit_replicasets_params

    return edit_topology_params, None


def add_edit_server_param_if_required(edit_server_params, instance_params, cluster_instance, param_name):
    if instance_params.get(param_name) is None:
        return

    if cluster_instance is not None:
        if instance_params.get(param_name) == cluster_instance.get(param_name):
            return

    edit_server_params[param_name] = instance_params.get(param_name)


def get_configure_instance_params(instance_params, cluster_instance):
    if not cluster_instance.get('uuid'):  # uuid is '' for unjoined instances
        return None, "Isn't joined to cluster"

    edit_server_params = {
        'uuid': cluster_instance.get('uuid'),
    }

    add_edit_server_param_if_required(edit_server_params, instance_params, cluster_instance, 'zone')

    if len(edit_server_params) == 1:
        # all instance parameters are the same as configured
        return None, None

    return edit_server_params, None


def get_configure_instances_params(instances, cluster_instances):
    edit_topology_params = {}

    edit_servers_params = []
    for instance_name, instance_params in instances.items():
        if instance_params.get('expelled'):
            # instance can be already expelled
            continue

        if instance_name not in cluster_instances:
            return None, "Instance %s isn't found in cluster" % instance_name

        cluster_instance = cluster_instances[instance_name]

        edit_server_params, err = get_configure_instance_params(instance_params, cluster_instance)
        if err is not None:
            return None, "Failed to get edit topology params for instance %s: %s" % (instance_name, err)

        if edit_server_params is not None:
            edit_servers_params.append(edit_server_params)

    if edit_servers_params:
        edit_topology_params['servers'] = edit_servers_params

    return edit_topology_params, None


def update_instances_and_replicasets(edit_topology_res, cluster_replicasets, cluster_instances):
    edited_replicasets = edit_topology_res['replicasets']
    edited_instances = edit_topology_res['servers']

    # update replicasets
    for alias, replicaset in edited_replicasets.items():
        cluster_replicasets[alias] = replicaset

    # update instances
    for alias, instance in edited_instances.items():
        cluster_instances[alias] = instance


def edit_topology(params):
    console_sock = params['console_sock']
    hostvars = params['hostvars']
    play_hosts = params['play_hosts']

    replicasets = get_configured_replicasets(hostvars, play_hosts)
    instances = get_instances_to_configure(hostvars, play_hosts)

    if not replicasets and not instances:
        return helpers.ModuleRes(changed=False)

    control_console = helpers.get_control_console(console_sock)
    cluster_instances = get_cluster_instances(control_console)

    # configure replicasets and expel instances
    cluster_replicasets = get_cluster_replicasets(control_console)
    edit_topology_params, err = get_edit_topology_params(
        replicasets, cluster_replicasets, instances, cluster_instances
    )
    if err is not None:
        return helpers.ModuleRes(
            failed=True,
            msg="Failed to collect edit topology params: %s" % err
        )

    topology_changed = False

    if edit_topology_params:
        res, err = control_console.eval_res_err(edit_topology_func_body, edit_topology_params)
        if err is not None:
            return helpers.ModuleRes(failed=True, msg="Failed to edit topology: %s" % err)

        topology_changed = True
        update_instances_and_replicasets(res, cluster_replicasets, cluster_instances)

    # change failover priority if needed
    edit_topology_params, err = get_edit_failover_priority_params(replicasets, cluster_replicasets, cluster_instances)
    if err is not None:
        return helpers.ModuleRes(
            failed=True,
            msg="Failed to collect edit topology params for changing failover_priority: %s" % err
        )

    if edit_topology_params:
        res, err = control_console.eval_res_err(edit_topology_func_body, edit_topology_params)
        if err is not None:
            return helpers.ModuleRes(failed=True, msg="Failed to edit failover priority: %s" % err)

        topology_changed = True
        update_instances_and_replicasets(res, cluster_replicasets, cluster_instances)

    # configure instances
    edit_topology_params, err = get_configure_instances_params(instances, cluster_instances)
    if err is not None:
        return helpers.ModuleRes(
            failed=True,
            msg="Failed to collect edit topology params for instances: %s" % err
        )

    if edit_topology_params:
        res, err = control_console.eval_res_err(edit_topology_func_body, edit_topology_params)
        if err is not None:
            return helpers.ModuleRes(failed=True, msg="Failed to configure instances: %s" % err)

        topology_changed = True
        update_instances_and_replicasets(res, cluster_replicasets, cluster_instances)

    return helpers.ModuleRes(changed=topology_changed)


if __name__ == '__main__':
    helpers.execute_module(argument_spec, edit_topology)
