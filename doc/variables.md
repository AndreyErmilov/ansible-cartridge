# Role variables


Configuration format is described in detail in the
[configuration format](#configuration-format) section.

Role variables are used to configure started instances, cluster topology,
vshard bootstrapping, and failover.
All variables are groupped by ???.

## Common variables

* `cartridge_app_name` (`string`): application name, required;
* `cartridge_cluster_cookie` (`string`, required): cluster cookie for all
  cluster instances;
* `cartridge_multiversion` (`boolean`, default: `false`): use multiversion
  approach for TGZ package.

## Role scenario configuration

For more details see [scenario documentation](/doc/scenario.md).

* `cartridge_scenario` (`list-of-strings`): list of steps to be launched
  (see [change scenario](#using-scenario) for more details)
* `cartridge_custom_steps_dir` (`string`, default: `null`): path to directory
  containing YAML files of custom steps (see [change scenario](#using-scenario) for more details)
* `cartridge_custom_steps` (`list-of-dicts`, default: `[]`): list of custom steps
  (see [change scenario](#using-scenario) for more details)

## Application package configuration

* `cartridge_package_path` (`string`): path to application package;
* `cartridge_enable_tarantool_repo` (`boolean`, default: `true`):
  indicates if the Tarantool repository should be enabled (for packages with
  open-source Tarantool dependency);

## TGZ-specific configuration:

* `cartridge_multiversion` (`boolean`, default: `false`): use [multiversion
  approach](/doc/multiversion.md) for TGZ package.

* `cartridge_install_tarantool_for_tgz` (`boolean`, default: `false`): flag indicates
  that Tarantool should be installed if application distribution doesn't contain `tarantool`
  binary; Tarantool version is got from `VERSION` file that is placed in distribution
  by Cartridge CLI;

* `cartridge_app_user` (`string`, default: `tarantool`): application user;
* `cartridge_app_group` (`string`, default: `tarantool`): application group;

* `cartridge_data_dir` (`string`, default: `/var/lib/tarantool`): directory
  where instances working directorieas are placed;
* `cartridge_run_dir`(`string`, default: `/var/run/tarantool`): directory where
  PID and socket files are stored;
* `cartridge_conf_dir` (`string`, default: `/etc/tarantool/conf.d`): path to
  instances configuration;
* `cartridge_app_install_dir` (`string`, default: `/usr/share/tarantool`): directory
  where application distributions are placed;
* `cartridge_app_instances_dir` (`string`, default: `/usr/share/tarantool`): directory
  where instances distributions are placed in case of multiversion approcah.

* `cartridge_configure_systemd_unit_files` (`boolean`, default: `true`): flag indicates that
  systemd unit files should be configured;
* `cartridge_systemd_dir` (`string`, default: `/etc/systemd/system`): directory where
  systemd-unit files should be placed;

* `cartridge_configure_tmpfiles` (`boolean`, default: `true`): flag indicates that tmpfiles
  config should be configured for application run dir;
* `cartridge_tmpfiles_dir` (`string`, default: `/usr/lib/tmpfiles.d/`): a directory where
  tmpfile sonfiguration should be placed;

## Instances configuration:

* `config` (`dict`, required): [instance configuration](#instances);
* `cartridge_defaults` (`dict`, default: `{}`): default configuration
  parameters values for instances;
* `restarted` (`boolean`): flag indicates if instance should be
  restarted or not (if this flag isn't specified, instance will be restarted if
  it's needed to apply configuration changes);
* `expelled` (`boolean`, default: `false`): boolean flag that indicates if instance must be expelled from topology;
* `stateboard` (`boolean`, default: `false`): boolean flag that indicates
   that the instance is a [stateboard](#stateboard-instance);
* `instance_start_timeout` (`number`, default: 60): time in seconds to wait for instance to be started;
* `cartridge_wait_buckets_discovery` (`boolean`, default: `true`): boolean
  flag that indicates if routers should wait for buckets discovery after vshard bootstrap;
* `instance_discover_buckets_timeout` (`number`, default: 60): time in seconds
  to wait for instance to discover buckets;

## Replicasets configuration

* `replicaset_alias` (`string`): replicaset alias, will be displayed in Web UI;
* `failover_priority` (`list-of-strings`): failover priority;
* `roles` (`list-of-strings`, required if `replicaset_alias` specified): roles to be enabled on the replicaset;
* `all_rw` (`boolean`): indicates that that all servers in the replicaset should be read-write;
* `weight` (`number`): vshard replicaset weight (matters only if `vshard-storage` role is enabled);

## Cluster configuration

* `cartridge_bootstrap_vshard` (`boolean`, default: `false`): boolean
  flag that indicates if vshard should be bootstrapped;
* `cartridge_app_config` (`dict`): application config sections to patch;
* `cartridge_auth`: (`dict`): [authorization configuration](#cartridge-authorization);
* `cartridge_failover_params` (`dict`): [failover](#failover) parameters;
* [DEPRECATED] `cartridge_failover` (`boolean`): boolean flag that
  indicates if eventual failover should be enabled or disabled;