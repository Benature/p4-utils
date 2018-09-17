# P4-Utils

P4-utils is an extension to Mininet that makes P4 networks easier to build, run and debug. P4-utils is strongly
inspired by [p4app](https://github.com/p4lang/p4app).

### Installation

First clone this repository:

```bash
git clone https://github.com/nsg-ethz/p4-utils.git
```

Run the installation script:

```bash
sudo ./install.sh
````

The install script will use `pip -e` to install the project in editable mode, meaning that every time you update the files
in this repository, either by pulling or doing local edits, the changes will automatically take place without the need of
installing the package again.

#### Uninstall

If you want to uninstall run:

```bash
sudo ./uninstall
```

This will remove all the scripts that were added to `/user/bin` as well as uninstall the python package using `pip`.

### How does it work ?

P4-utils creates virtual networks using mininet and extended nodes that run p4-enabled switches. To create hosts,
mininet uses a bash process running in a network namespace, in order words, all the processes that run within the
network namespaces have an isolated network stack. Switches are software-based switches like Open vSwitch, Linux Bridge,
or BMV2 switches. Mininet uses virtual ethernet pairs, which live in the Linux kernel to connect the emulated hosts and switches.

For more information see:

 * [Mininet](http://mininet.org/)
 * [Linux Namespaces]((https://blogs.igalia.com/dpino/2016/04/10/network-namespaces/))
 * [Virtual ethernet interfaces](http://man7.org/linux/man-pages/man4/veth.4.html)
 * [BMV2](https://github.com/p4lang/behavioral-model), [OVS](https://www.openvswitch.org/), [LinuxBridge](https://cloudbuilder.in/blogs/2013/12/02/linux-bridge-virtual-networking/).

### Features

P4-utils adds on top of minininet:

 * A command-line launcher (`p4run`) to instantiate networks.
 * A helper script (`mx`) to run processes in namespaces
 * Custom `P4Host` and `P4Switch` nodes (based on the ones provided in the [`p4lang`](https://github.com/p4lang) repo)
 * A very simple way of defining networks using json files (`p4app.json`).
 * Enhances mininet command-line interface: adding the ability of rebooting switches with updated p4 programs and configurations, without the need
 of restarting the entire network.
 * Saves the topology and features in an object that can be loded and queried to extract meaningful information (also build a `networkx` object out of the
 topology)
 * Re-implementation of the `runtime_CLI` and `simple_switch_CLI` as python objects to use in controller code.

### Usage

P4-utils can be executed by running the `p4run` command in a terminal. By default `p4run` will try to find a
topology description called `p4app.json` in your current path. However you can change that by using the `--config` option:

```bash
p4run --config <path_to_json_configuration>
```

You can see the complete list of options with the `-h` or `--help` options.

## Documentation

### Topology Description

To run any topology p4-utils needs a configuration file (`*.json`) that is used by `p4run` to know how to build and configure a
virtual network. All the possible options are listed below:

#### Global Configuration

##### `program:`

   * Type: String
   * Value: Path to p4 program
   * Default: None (required if not all switches have a p4 program defined).

   > Program that will be loaded onto all the switches unless a switch has another program specified.

##### `switch:`

   * Type: String
   * Value: path to bmv2 switch executable
   * Default: "simple_switch"

##### `compiler:`

   * Type: String
   * Value: P4 compiler to be used
   * Default: "p4c"

##### `options:`

   * Type: String
   * Value: Compiler options
   * Default: "--target bmv2 --arch v1model --std p4-16"

##### `switch_cli:`

   * Type: String
   * Value: Path to the switch CLI executable
   * Default: 'simple_switch_CLI'

##### `cli:`

   * Type: bool
   * Value: Enables the enhanced mininet CLI. If disabled, the topology will be destroyed right after being created.
   * Default: false

##### `pcap_dump:`

   * Type: bool
   * Value: if enabled a pcap file for each interfaced is saved at `./pcap`
   * Default: false

##### `enable_log:`

   * Type: bool
   * Value: if enabled a directory with CLI and switch logs is created at `.log`
   * Default: false

##### `topo_module`
##### `controller_module`
##### `topodb_module`
##### `mininnet_module`

#### Topology

##### `assignment_strategy`

##### `auto_arp_tables`

##### `links`

##### `hosts`

##### `switches`

### Control Plane API

### Topology Object
