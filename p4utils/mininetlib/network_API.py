import os
import time
from ipaddress import ip_interface, IPv4Network
from networkx import MultiGraph, Graph
from networkx.readwrite.json_graph import node_link_data
from mininet.link import TCIntf
from mininet.nodelib import LinuxBridge
from mininet.topo import Topo
from mininet.cli import CLI
from mininet.log import setLogLevel, info, output, debug, warning

from p4utils.utils.helper import *
from p4utils.utils.client import ThriftClient
from p4utils.utils.compiler import *
from p4utils.utils.topology import NetworkGraph
from p4utils.mininetlib.node import *
from p4utils.mininetlib.net import P4Mininet
from p4utils.mininetlib.cli import P4CLI
from p4utils.utils.task_client import TaskClient


class NetworkAPI(Topo):
    """
    Network definition and initialization API.
    """
    def __init__(self, *args, **params):
        # Init superclass
        super().__init__(*args, **params)
        # Set log level
        setLogLevel('output')
        # Name of the CPU bridge
        self.cpu_bridge = None
        # Whether to enable the client or not
        self.cli_enabled = True
        # Topology data file
        self.topoFile = './topology.json'
        # IP default generator
        self.ipv4_net = IPv4Network('10.0.0.0/8')
        # Gateway static ARP
        self.auto_gw_arp = True
        # Static ARP entries
        self.auto_arp_tables = True
        # List of scripts to execute in
        # the main namespace
        self.scripts = []
        # Dictionary of scheduled tasks
        self.tasks = {}

        ## External modules default configuration dictionary
        self.modules = {}

        # Network module
        self.modules['net'] = {}
        self.modules['net']['class'] = P4Mininet
        # Default kwargs
        self.modules['net']['kwargs'] = {}
        # Network is instantiated in self.startNetwork
        self.net = None
        
        # Compiler module
        self.modules['comp'] = {}
        self.modules['comp']['class'] = P4C
        # Default kwargs
        self.modules['comp']['kwargs'] = {}
        # List of compilers
        self.compilers = []

        # Switch client module
        self.modules['sw_cli'] = {}
        self.modules['sw_cli']['class'] = ThriftClient
        # Default kwargs
        self.modules['sw_cli']['kwargs'] = {
                                              'log_dir': './log'
                                           }
        # List of switch clients
        self.sw_clients = []

## Utils
    def cleanup(self):
        """
        Removes old Mininet files and processes.
        """
        # Mininet cleanup
        cleanup()

    def is_multigraph(self):
        """
        Check whether the graph is a multigraph, i.e. it has multiple parallel
        links.
        """
        multigraph = False
        for node1 in self.nodes():
            for node2 in self.nodes():
                if self.areNeighbors(node1, node2):
                    if len(self._linkEntry(node1, node2)[0]) > 1:
                        multigraph = True
                        break
        return multigraph

    def save_topology(self):
        """
        Saves mininet topology to a JSON file.

        Notice that multigraphs are not supported yet by p4utils.utils.Topology
        """
        # This function return None for each not serializable
        # obect so that no TypeError is thrown.
        def default(obj):
            return None

        info('Saving mininet topology to database: {}\n'.format(self.topoFile))

        # Check whether the graph is a multigraph or not
        multigraph = self.is_multigraph()

        if multigraph:
            debug('Multigraph topology selected.\n')
            graph = self.g.convertTo(MultiGraph, data=True, keys=True)
        else:
            debug('Simple graph topology selected.\n')
            graph = self.g.convertTo(NetworkGraph, data=True, keys=False)
            
            for _, _, params in graph.edges(data=True):
                
                edge = graph[params['node1']][params['node2']]
                params1 = edge.pop('params1', {})
                params2 = edge.pop('params2', {})

                # Move parameters in subdictionaries outside
                # and append number to identify them.
                for key in params1.keys():
                    edge[key+'1'] = params1[key]

                for key in params2.keys():
                    edge[key+'2'] = params2[key]

                # Fake switches' IPs
                if 'sw_ip1' in edge.keys():
                    edge['ip1'] = edge['sw_ip1']
                    del edge['sw_ip1']
                
                if 'sw_ip2' in edge.keys():
                    edge['ip2'] = edge['sw_ip2']
                    del edge['sw_ip2']

            # If you want to retrieve informations directly from the network istead of trusting
            # the information contained in the Mininet topology, use the following lines.

            ## Add additional informations to the graph which are not loaded automatically
            # Add links informations
            # for _, _, params in graph.edges(data=True):
            #     node1_name = params['node1']
            #     node2_name = params['node2']
            #     node1 = self.net[node1_name]
            #     node2 = self.net[node2_name]
            #     edge = graph[node1_name][node2_name]

            #     # Get link
            #     link = self.net.linksBetween(node1, node2)[0]

            #     # Get interfaces
            #     intf1 =  getattr(link, 'intf1')
            #     intf2 =  getattr(link, 'intf2')

            #     # Get interface names
            #     edge['intfName1'] = getattr(intf1, 'name')
            #     edge['intfName2'] = getattr(intf2, 'name')
                
            #     # Get interface addresses
            #     try:
            #         # Fake switch IP
            #         edge['ip1'] = edge['sw_ip1']
            #         del edge['sw_ip1']
            #     except KeyError:
            #         # Real IP
            #         ip1, prefixLen1 = getattr(intf1, 'ip'), getattr(intf1, 'prefixLen')
            #         if ip1 and prefixLen1:
            #             edge['ip1'] = ip1 + '/' + prefixLen1

            #     try:
            #         # Fake switch IP
            #         edge['ip2'] = edge['sw_ip2']
            #         del edge['sw_ip2']
            #     except KeyError:
            #         # Real IP
            #         ip2, prefixLen2 = getattr(intf2, 'ip'), getattr(intf2, 'prefixLen')
            #         if ip2 and prefixLen2:
            #             edge['ip2'] = ip2 + '/' + prefixLen2

            #     mac1 = getattr(intf1, 'mac')
            #     if mac1:
            #         edge['addr1'] = mac1

            #     mac2 = getattr(intf2, 'mac')
            #     if mac1:
            #         edge['addr2'] = mac2

        graph_dict = node_link_data(graph)
        with open(self.topoFile,'w') as f:
            json.dump(graph_dict, f, default=default)

    def compile(self):
        """
        Compile all the required P4 files.
        """
        for p4switch in self.p4switches():
            p4_src = self.getNode(p4switch).get('p4_src')
            if p4_src is not None:
                if not is_compiled(os.path.realpath(p4_src), self.compilers):
                    compiler = self.module('comp', p4_src)
                    compiler.compile()
                    self.compilers.append(compiler)
                else:
                    compiler = get_by_attr('p4_src', os.path.realpath(p4_src), self.compilers)
                # Retrieve json_path
                self.updateNode(p4switch, json_path=compiler.get_json_out())
                # Try to retrieve p4 runtime info file path
                try:
                    self.updateNode(p4switch, p4rt_path=compiler.get_p4rt_out())
                except P4InfoDisabled:
                    pass

    def program_switches(self):
        """
        If any command files were provided for the switches, this method will start up the
        CLI on each switch and use the contents of the command files as input.

        Assumes:
            A mininet instance is stored as self.net.
            self.net.start() has been called.
        """
        for p4switch, info in self.p4switches(withInfo=True):
            cli_input = info.get('cli_input')
            thrift_port = info.get('thrift_port')
            if cli_input is not None:
                sw_client = self.module('sw_cli', thrift_port, p4switch, cli_input=cli_input)
                sw_client.configure()
                self.sw_clients.append(sw_client)

    def program_hosts(self):
        """
        Adds static and default routes ARP entries to each mininet host.
        Multihomed hosts are allowed.

        Assumes:
            Only switches and hosts are allowed.
            No duplicated IP addresses exist in the Network (e.g. no NAT allowed
            for the same subnet).
            A mininet instance is stored as self.net.
            self.net.start() has been called.
        """
        for host1, info in self.hosts(withInfo=True):
            # Get mininet node
            h1 = self.net.get(host1)
            # Set gateway static ARP
            if self.auto_gw_arp:
                # If there is gateway assigned
                if 'defaultRoute' in h1.params:
                    # Get gateway IP
                    gw_ip = h1.params['defaultRoute'].split()[-1]
                    for node in self.nodes():
                        if host1 == node:
                            continue
                        n = self.net.get(node)
                        # If it is a switch, handle fake IPs
                        if self.isSwitch(node):
                            for intf in n.intfs.values():
                                # Skip loopback interface
                                if intf.name == 'lo':
                                    continue
                                # Get link from interface
                                link = intf.link
                                # Get fake IP
                                n_ip = intf.params.get('sw_ip1') if intf == link.intf1 else intf.params.get('sw_ip2')
                                if n_ip is not None:
                                    n_ip = n_ip.split('/')[0]
                                    # Check if the IPs match and set ARP
                                    if n_ip == gw_ip:
                                        h1.setARP(gw_ip, intf.mac)
                        else:
                            for intf in n.intfs.values():
                                # Skip loopback interface
                                if intf.name == 'lo':
                                    continue
                                n_ip = intf.ip
                                if n_ip is not None:
                                    n_ip = n_ip.split('/')[0]
                                    # Check if the IPs match and set ARP
                                    if n_ip == gw_ip:
                                        h1.setARP(gw_ip, intf.mac)
            
            # Set static ARP entries
            if self.auto_arp_tables:
                for intf1 in h1.intfs.values():
                    # Skip loopback interface
                    if intf1.name == 'lo':
                        continue
                    # Set arp rules for all the hosts in the same subnet
                    h1_intf_ip = ip_interface('{}/{}'.format(intf1.ip, intf1.prefixLen))
                    for host2 in self.hosts():
                        if host1 == host2:
                            continue
                        h2 = self.net.get(host2) 
                        for intf2 in h2.intfs.values():
                            # Skip loopback interface
                            if intf2.name == 'lo':
                                continue
                            # Get the other interface's IP
                            h2_intf_ip = ip_interface('{}/{}'.format(intf2.ip, intf2.prefixLen))
                            # Check if the subnet is the same
                            if h1_intf_ip.network.compressed == h2_intf_ip.network.compressed:
                                h1.setARP(intf2.ip, intf2.mac)

            # Set DHCP autoconfiguration
            if info.get('dhcp', False):
                for intf1 in h1.intfs.values():
                    # Skip loopback interface
                    if intf1.name == 'lo':
                        continue
                    h1.cmd('dhclient -r {}'.format(intf1.name))
                    h1.cmd('dhclient {} &'.format(intf1.name))

    def exec_scripts(self):
        """
        Executes the scripts in the main namespace after network boot.
        """
        for script in self.scripts:
            info('Exec Script: {}\n'.format(script['cmd']))
            run_command(script['cmd'])

    def start_scheduler(self, node):
        """
        Start the task scheduler on node if enabled.

        Arguments:
            node (string): name of the node

        Assumes:
            A mininet instance is stored as self.net.
            self.net.start() has been called.
        """
        if self.hasScheduler(node):
            unix_path = self.getNode(node).get('unix_path', '/tmp')
            unix_socket = unix_path + '/' + node + '_socket'
            info('Node {} task scheduler listens on {}.\n'.format(node, unix_socket))
            node_info = self.getNode(node)
            log_enabled = node_info.get('log_enabled', False)
            log_dir = node_info.get('log_dir')
            if log_enabled:
                self.net[node].cmd('python3 -m p4utils.utils.task_scheduler "{}" > "{}/{}_scheduler.log" 2>&1 &'.format(unix_socket, log_dir, node))
            else:
                self.net[node].cmd('python3 -m p4utils.utils.task_scheduler "{}" > /dev/null 2>&1 &'.format(unix_socket))

    def start_schedulers(self):
        """
        Start all the required task schedulers.

        Assumes:
            A mininet instance is stored as self.net.
            self.net.start() has been called.
        """
        for node in self.nodes():
            if self.hasScheduler(node):
                self.start_scheduler(node)
            else:
                # Remove node if it has no scheduler
                self.tasks.pop(node, None)

    def distribute_tasks(self):
        """
        Distribute all the tasks to the schedulers.

        Assumes:
            All the nodes in self.tasks have an active scheduler.
            A mininet instance is stored as self.net.
            self.net.start() has been called.
        """
        for node, tasks in self.tasks.items():
            unix_path = self.getNode(node).get('unix_path', '/tmp')
            unix_socket = unix_path + '/' + node + '_socket'
            info('Tasks for node {} distributed to socket {}.\n'.format(node, unix_socket))
            task_client = TaskClient(unix_socket)
            task_client.send(tasks, retry=True)

        # Remove all the tasks once they are sent
        self.tasks = {}

    def start_net_cli(self):
        """
        Starts up the mininet CLI and prints some helpful output.

        Assumes:
            A mininet instance is stored as self.net.
            self.net.start() has been called.
        """
        for switch in self.net.switches:
            if self.isP4Switch(switch.name):
                switch.describe()
        for host in self.net.hosts:
            host.describe()
        info("Starting mininet CLI...\n")
        # Generate a message that will be printed by the Mininet CLI to make
        # interacting with the simple switch a little easier.
        output('\n')
        output('======================================================================\n')
        output('Welcome to the P4 Utils Mininet CLI!\n')
        output('======================================================================\n')
        output('Your P4 program is installed into the BMV2 software switch\n')
        output('and your initial configuration is loaded. You can interact\n')
        output('with the network using the mininet CLI below.\n')
        output('\n')
        output('To inspect or change the switch configuration, connect to\n')
        output('its CLI from your host operating system using this command:\n')
        output('  {} --thrift-port <switch thrift port>\n'.format(ThriftClient.cli_bin))
        output('\n')
        output('To view a switch log, run this command from your host OS:\n')
        output('  tail -f <log_dir>/<switchname>.log\n')
        output('By default log directory is "./log".\n')
        output('\n')
        output('To view the switch output pcap, check the pcap files in <pcap_dir>:\n')
        output('  for example run:  sudo tcpdump -xxx -r s1-eth1.pcap\n')
        output('By default pcap directory is "./pcap".\n')
        output('\n')

        P4CLI(self)

    def module(self, mod_name, *args, **kwargs):
        """
        Create object from external modules configurations.

        Arguments:
            mod_name (string): module name (possible values are
                               'topo', 'comp', 'net', 'sw_cli')
            args             : positional arguments to pass to the object
            kwargs           : keyword arguments to pass to the object in addition to
                               the default ones
        
        Returns:
            configured instance of the class of the module
        """
        default_kwargs = self.modules[mod_name]['kwargs']
        default_class = self.modules[mod_name]['class']
        for key, value in default_kwargs.items():
            kwargs.setdefault(key, value)
        return default_class(*args, **kwargs)

    def node_ports(self):
        """
        Build a dictionary from the links and store the ports
        of every node and its destination node.
        """
        ports = {}
        for _, _, key, info in self.links(withKeys=True, withInfo=True):
            ports.setdefault(info['node1'], {})
            ports.setdefault(info['node2'], {})
            port1 = info.get('port1')
            if port1 is not None:
                ports[info['node1']].update({port1 : (info['node1'], info['node2'], key)})
            port2 = info.get('port2')
            if port2 is not None:
                ports[info['node2']].update({port2 : (info['node2'], info['node1'], key)})
        return ports

    def node_intfs(self):
        """
        Build a dictionary from the links and store the interfaces
        of every node and its destination node.
        """
        ports = {}
        for _, _, key, info in self.links(withKeys=True, withInfo=True):
            ports.setdefault(info['node1'], {})
            ports.setdefault(info['node2'], {})
            intfName1 = info.get('intfName1')
            if intfName1 is not None:
                ports[info['node1']].update({intfName1 : (info['node1'], info['node2'], key)})
            intfName2 = info.get('intfName2')
            if intfName2 is not None:
                ports[info['node2']].update({intfName2 : (info['node2'], info['node1'], key)})     
        return ports

    def switch_ids(self):
        """
        Return a set containing all the switch IDs.
        """
        ids = set()

        for switch, info in self.switches(withInfo=True):
            if self.isP4Switch(switch):
                device_id = info.get('device_id')
                if device_id is not None:
                    ids.add(device_id)
            else:
                dpid = info.get('dpid')
                if dpid is not None:
                    ids.add(int(dpid, 16))

        return ids

    def thrift_ports(self):
        """
        Return a set containing all the switches' thrift ports.
        """
        thrift_ports = set()

        for switch, info in self.p4switches(withInfo=True):
            thrift_port = info.get('thrift_port')
            if thrift_port is not None:
                thrift_ports.add(thrift_port)

        return thrift_ports

    def grpc_ports(self):
        """
        Return a set containing all the switches' grpc ports.
        """
        grpc_ports = set()

        for switch, info in self.p4rtswitches(withInfo=True):
            grpc_port = info.get('grpc_port')
            if grpc_port is not None:
                grpc_ports.add(grpc_port)
        
        return grpc_ports

    def mac_addresses(self):
        """
        Return a set containing all the MAC addresses.
        """
        macs = set()

        for node1, node2, info in self.links(withInfo=True):
            mac1 = info.get('addr1')
            if mac1 is not None:
                macs.add(mac1)
            mac2 = info.get('addr2')
            if mac2 is not None:
                macs.add(mac2)

        return macs

    def ip_addresses(self):
        """
        Return a set containing all the IPv4 addresses of L3 nodes,
        i.e. of all non-switch nodes. The fake IPs assigned to the
        switches are not considered.
        """
        ips = set()

        for node1, node2, info in self.links(withInfo=True):
            if not self.isSwitch(node1):
                params = info.get('params1')
                if params is not None:
                    ip = params.get('ip')
                    if ip is not None:
                        ips.add(ip.split('/')[0])

            if not self.isSwitch(node2):
                params = info.get('params2')
                if params is not None:
                    ip = params.get('ip')
                    if ip is not None:
                        ips.add(ip.split('/')[0])

        return ips

    def check_host_valid_ip_from_name(self, host):
        """
        Util for assignment strategies.

        Arguments:
            host (string): name of the host
        """
        valid = True
        if host[0] == 'h':
            try:
                int(host[1:])
            except:
                valid = False
        else:
            valid = False
        
        return valid

    def intf_name(self, name, port):
        """
        Construct a canonical interface name node-ethN for interface port.

        Arguments:
            name (string): name of the Mininet node
            port (int)   : port number

        Returns:
            the chosen interface name (string)
        """
        return name + '-eth' + repr(port)

    def auto_switch_id(self, base=1):
        """
        Compute an available switch id that can be assigned.

        Arguments:
            base (int): starting switch id

        Returns:
            the computed switch id (int)
        """
        switch_ids = self.switch_ids().union(self.grpc_ports())
        return next_element(switch_ids, minimum=base)

    def auto_grpc_port(self, base=9559):
        """
        Compute an available grpc port that can be assigned.

        Arguments:
            base (int): starting grpc port

        Returns:
            the computed grpc port (int)
        """
        grpc_ports = self.grpc_ports().union(self.thrift_ports())
        return next_element(grpc_ports, minimum=base)

    def auto_thrift_port(self, base=9090):
        """
        Compute an available thrift port that can be assigned.

        Arguments:
            base (int): starting thrift port

        Returns:
            the computed thrift port (int)
        """
        thrift_ports = self.thrift_ports()
        return next_element(thrift_ports, minimum=base)

    def auto_port_num(self, node, base=0):
        """
        Compute the next port number that can be used on the node.

        Arguments:
            node (string)    : name of the node
            base (int)       : starting port number

        Returns:
            available port number (int)
        """
        ports = self.node_ports().get(node)
        if ports is not None:
            ports_list = list(ports.keys())
            return next_element(ports_list, minimum=base)
        else:
            return base

    def auto_mac_address(self):
        """
        Generate a MAC address, different from anyone already generated.
        """
        mac = rand_mac()
        mac_addresses = self.mac_addresses()
        while mac in mac_addresses:
            mac = rand_mac()
        return mac

    def auto_ip_address(self):
        """
        Generate an IP address, different from anyone already generated.
        """
        ip_generator = self.ipv4_net.hosts()
        ip = str(next(ip_generator))
        prefixLen = str(self.ipv4_net.prefixlen)
        ip_addresses = self.ip_addresses()
        while ip in ip_addresses:
            ip = str(next(ip_generator))
        return ip + '/' + prefixLen

    def auto_assignment(self):
        """
        This function automatically assigns unique MACs, IPs, interface 
        names and port numbers to all the interfaces which require them.
        It also assigns unique device ids, grpc ports and thrift ports
        to the devices which require them. When a default interface is
        encountered, the respective device entry is updated.
        """
        # Set nodes' parameters automatically
        for node, info in self.nodes(sort=True, withInfo=True):

            if self.isP4Switch(node):
                
                # Device IDs
                device_id = info.get('device_id')
                if device_id is None:
                    device_id = self.auto_switch_id()
                    self.setP4SwitchId(node, device_id)

                # Thrift ports
                thrift_port = info.get('thrift_port')
                if thrift_port is None:
                    thrift_port = self.auto_thrift_port()
                    self.setThriftPort(node, thrift_port)

                if self.isP4RuntimeSwitch(node):

                    # GRPC ports
                    grpc_port = info.get('grpc_port')
                    if grpc_port is None:
                        grpc_port = self.auto_grpc_port()
                        self.setGrpcPort(node, grpc_port)

            elif self.isSwitch(node):
                
                # DPIDs
                dpid = info.get('dpid')
                if dpid is None:
                    device_id = self.auto_switch_id()
                    dpid = dpidToStr(device_id)
                    self.setSwitchDpid(node, dpid)

        # Set links' parameters automatically
        for node1, node2, key, info in self.links(sort=True, withKeys=True, withInfo=True):

            # Port numbers
            port1 = info.get('port1')
            if port1 is None:
                if self.isSwitch(node1):
                    port1 = self.auto_port_num(node1, base=1)
                else:
                    port1 = self.auto_port_num(node1)
                self.setIntfPort(node1, node2, port1, key=key)

            port2 = info.get('port2')
            if port2 is None:
                if self.isSwitch(node2):
                    port2 = self.auto_port_num(node2, base=1)
                else:
                    port2 = self.auto_port_num(node2)
                self.setIntfPort(node2, node1, port2, key=key)

            # Interface names
            intfName1 = info.get('intfName1')
            if intfName1 is None:
                intfName1 = self.intf_name(node1, port1)
                self.setIntfName(node1, node2, intfName1, key=key)
            
            intfName2 = info.get('intfName2')
            if intfName2 is None:
                intfName2 = self.intf_name(node2, port2)
                self.setIntfName(node2, node1, intfName2, key=key)

            # MACs
            addr1 = info.get('addr1')
            if addr1 is None:
                addr1 = self.auto_mac_address()
                self.setIntfMac(node1, node2, addr1, key=key)

            addr2 = info.get('addr2')
            if addr2 is None:
                addr2 = self.auto_mac_address()
                self.setIntfMac(node2, node1, addr2, key=key)

            # IPs
            if not self.isSwitch(node1):
                params1 = info.get('params1')
                if params1 is None:
                    ip1 = self.auto_ip_address()
                    self.setIntfIp(node1, node2, ip1, key=key)
                else:
                    ip1 = params1.get('ip')
                    if ip1 is None:
                        ip1 = self.auto_ip_address()
                        self.setIntfIp(node1, node2, ip1, key=key)

            if not self.isSwitch(node2):
                params2 = info.get('params2')
                if params2 is None:
                    ip2 = self.auto_ip_address()
                    self.setIntfIp(node2, node1, ip2, key=key)
                else:
                    ip2 = params2.get('ip')
                    if ip2 is None:
                        ip2 = self.auto_ip_address()
                        self.setIntfIp(node2, node1, ip2, key=key)
            
        # Update hosts' default interfaces (from links' parameters to hosts' parameters)
        for node1, node2, key, info in self.links(withKeys=True, withInfo=True):

            if self.isHost(node1):
                # Check if it is a default interfaces
                if self.is_default_intf(node1, node2, key=key):
                    self.updateNode(node1, mac=info['addr1'])
                    self.updateNode(node1, ip=info['params1']['ip'])

            if self.isHost(node2):
                 # Check if it is a default interfaces
                if self.is_default_intf(node2, node1, key=key):
                    self.updateNode(node2, mac=info['addr2'])
                    self.updateNode(node2, ip=info['params2']['ip'])

    def get_default_intf(self, node1):
        """
        Return the tuple (node1, node2, key) identifying the
        default interface.
        """
        if self.isNode(node1):
            node_ports = self.node_ports()
            ports = node_ports.get(node1)
            if ports is not None:
                return ports[min(node_ports[node1].keys())]
            else:
                warning('node {} has no incident links.\n'.format(node1))
                return None, None, None
        else:
            raise Exception('"{}" does not exist.'.format(node1))

    def is_default_intf(self, node1, node2, key=None):
        """
        Check if the specified interface is the default one for node1.
        
        Arguments:
            node1, node2 (string): nodes linked together
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)

        Returns:
            True if the interface is default, False else

        Notice:
            Since interfaces can be removed, the default interface
            may change during the definition of the network. So this is
            reliable only if no other interfaces are added/removed afterwards.
        """
        assert self.isNode(node1)
        assert self.isNode(node2)
        def_intf = self.get_default_intf(node1)
        _, key = self._linkEntry(node1, node2, key=key)
        intf = (node1, node2, key)
        return def_intf == intf

### API
## External modules management
    def setLogLevel(self, logLevel):
        """
        Set the log level for the execution.

        Arguments:
            logLevel (string): possible values are debug', 'info', 'output',
                               'warning', 'error', 'critical'.
        """
        setLogLevel(logLevel)

    def setIpBase(self, ipBase):
        """
        Set the network in which all the L3 devices will be placed,
        if no explicit assignment is performed (e.g. assignment strategies
        or manual assignment).

        Arguments:
            ipBase (string): IP address/mask (e.g. '10.0.0.0/8')

        Notice:
            Remember that setting the IP base won't automatically change
            the already assigned IP. If you want to specify a network
            different from '10.0.0.0/8' (default one), please use this method
            before any node is added to the network.
        """
        self.ipv4_net = IPv4Network(ipBase)

    def setCompiler(self, compilerClass=None, **kwargs):
        """
        Set the default P4 compiler class and options.
        """
        if compilerClass is not None:
            self.modules['comp']['class'] = compilerClass
        self.modules['comp']['kwargs'].update(kwargs)

    def setNet(self, netClass=None, **kwargs):
        """
        Set the default Mininet class and options.
        """
        if netClass is not None:
            self.modules['net']['class'] = netClass
        self.modules['net']['kwargs'].update(kwargs)

    def setSwitchClient(self, swclientClass=None, **kwargs):
        """
        Set the default switch client class and options.
        """
        if swclientClass is not None:
            self.modules['sw_cli']['class'] = swclientClass
        self.modules['sw_cli']['kwargs'].update(kwargs)

## Generic methods
    def printPortMapping(self):
        """
        Print the port mapping of all the devices.
        """
        output('Port mapping:\n')
        node_ports = self.node_ports()
        for node1 in sorted(node_ports.keys()):
            output('{}:  '.format(node1))
            for port1, intf in sorted(node_ports[node1].items(), key=lambda x: x[0]):
                output('{}:{}\t '.format(port1, intf[1]))
            output('\n')

    def execScript(self, cmd, reboot=True):
        """
        Execute the given command in the main namespace after
        the network boot.

        Arguments:
            cmd (string) : command to execute
            reboot (bool): whether to rerun the script every time
                           all the P4 switches are rebooted.
        """
        self.scripts.append({'cmd': cmd, 'reboot_run': reboot})

    def describeP4Nodes(self):
        """
        Print a description for the P4 nodes in the network.
        """
        for switch in self.net.switches:
            if self.isP4Switch(switch.name):
                switch.describe()
        for host in self.net.hosts:
            host.describe()
    
    def setTopologyFile(self, topoFile):
        """
        Set the file where the topology will be saved for subsequent
        queries in the exercises.
        """
        self.topoFile = topoFile

    def enableCli(self):
        """
        Enable the Mininet client.
        """
        self.cli_enabled = True

    def disableCli(self):
        """
        Disable the Mininet client.
        """
        self.cli_enabled = False

    def enableArpTables(self):
        """
        Enable the static ARP entries for hosts in the
        same network.
        """
        self.auto_arp_tables = True

    def disableArpTables(self):
        """
        Disable the static ARP entries for hosts in the
        same network.
        """
        self.auto_arp_tables = False
    
    def enableGwArp(self):
        """
        Enable the static ARP entry in hosts
        for the gateway only.
        """
        self.auto_gw_arp = True

    def disableGwArp(self):
        """
        Disable the static ARP entry in hosts
        for the gateway only.
        """
        self.auto_gw_arp = False

    def startNetwork(self):
        """
        Once the topology has been created, create and start the Mininet network.
        If enabled, start the client.
        """
        debug('Cleanup old files and processes...\n')
        self.cleanup()

        debug('Auto configuration of not configured interfaces...\n')
        self.auto_assignment()
        
        info('Compiling P4 files...\n')
        self.compile()
        output('P4 Files compiled!\n')

        self.printPortMapping()

        info('Creating network...\n')
        self.net = self.module('net', topo=self, controller=None)
        output('Network created!\n')

        info('Starting network...\n')
        self.net.start()
        output('Network started!\n')

        info('Starting schedulers...\n')
        self.start_schedulers()
        output('Schedulers started correctly!\n')

        info('Saving topology to disk...\n')
        self.save_topology()
        output('Topology saved to disk!\n')

        info('Programming switches...\n')
        self.program_switches()
        output('Switches programmed correctly!\n')

        info('Programming hosts...\n')
        self.program_hosts()
        output('Hosts programmed correctly!\n')
        
        info('Executing scripts...\n')
        self.exec_scripts()
        output('All scripts executed correctly!\n')

        info('Distributing tasks...\n')
        self.distribute_tasks()
        output('All tasks distributed correctly!\n')

        if self.cli_enabled:
            self.start_net_cli()
            # Stop right after the CLI is exited
            info('Stopping network...\n')
            self.net.stop()
            output('Network stopped!\n')

### Links
## Link setter
    def addLink(self, node1, node2, port1=None, port2=None,
                key=None, **opts):
        """
        Add link between two nodes. If key is None, then the next
        ordinal number is used.

        Arguments:
            node1, node2 (string)        : nodes to link together
            port1, port2 (int)           : ports (optional)
            key (int)                    : id used to identify multiple edges which
                                           link two same nodes (optional)
            opts                         : link options as listed below (optional)
    
        Link options:
            intfName1, intfName2 (string): names of the interfaces (optional)
            addr1, addr2 (string)        : MAC addresses (optional)
            
            weight (int)                 : weight used to compute shortest paths
        
        Returns:
            key (int)

        Notice:
            If not specified, all the optional fields are assigned automatically
            by the method self.auto_assignment before the network is started.
            The interface names must not be in the canonical format (i.e. 'node-ethN'
            where N is the port number of the interface) because the automatic
            assignment uses it.
        """
        node_ports = self.node_ports()
        node_intfs = self.node_intfs()
        mac_addresses = self.mac_addresses()
        ip_addresses = self.ip_addresses()
        
        # Sanity check
        assert self.isNode(node1)
        assert self.isNode(node2)

        # Ports
        if port1 is not None:
            if node1 in node_ports.keys():
                if port1 in node_ports[node1].keys():
                    raise Exception('port {} already present on node "{}".'.format(port1, node1))

        if port2 is not None:
            if node2 in node_ports.keys():
                if port2 in node_ports[node2].keys():
                    raise Exception('port {} already present on node "{}".'.format(port2, node2))

        # Interface names
        intfName1 = opts.get('intfName1')
        if intfName1 is not None:
            if node1 in node_intfs.keys():
                if intfName1 in node_intfs[node1].keys():
                    raise Exception('interface "{}" already present on node "{}".'.format(intfName1, node1))

        intfName2 = opts.get('intfName2')
        if intfName2 is not None:
            if node2 in node_intfs.keys():
                if intfName2 in node_intfs[node2].keys():
                    raise Exception('interface "{}" already present on node "{}".'.format(intfName2, node2))

        # MACs
        addr1 = opts.get('addr1')
        if addr1 is not None:
            if addr1 in mac_addresses:
                warning('Node "{}": MAC {} has been already assigned.\n'.format(node1, addr1))

        addr2 = opts.get('addr2')
        if addr2 is not None:
            if addr2 in mac_addresses or addr1 == addr2:
                warning('Node "{}": MAC {} has been already assigned.\n'.format(node2, addr2))

        # IPs
        if self.isSwitch(node1):
            ip1 = opts.get('sw_ip1')
            if ip1 is not None:
                ip1 = ip1.split('/')[0]
                if ip1 in ip_addresses:
                    warning('Node "{}": IP {} has been already assigned.\n'.format(node1, ip1))
        else:
            params1 = opts.get('params1')
            ip1 = None
            if params1 is not None:
                ip1 = params1.get('ip')
                if ip1 is not None:
                    ip1 = ip1.split('/')[0]
                    if ip1 in ip_addresses:
                        warning('Node "{}": IP {} has been already assigned.\n'.format(node1, ip1))

        if self.isSwitch(node2):
            ip2 = opts.get('sw_ip2')
            if ip2 is not None:
                ip2 = ip2.split('/')[0]
                if ip2 in ip_addresses or ip1 == ip2:
                    warning('Node "{}": IP {} has been already assigned.\n'.format(node2, ip2))
        else:
            params2 = opts.get('params2')
            ip2 = None
            if params2 is not None:
                ip2 = params2.get('ip')
                if ip2 is not None:
                    ip2 = ip2.split('/')[0]
                    if ip2 in ip_addresses or ip1 == ip2:
                        warning('Node "{}": IP {} has been already assigned.\n'.format(node2, ip2))

        # Modified version of the mininet addLink. Built-in port numbering removed.
        # (see https://github.com/mininet/mininet/blob/master/mininet/topo.py#L151)
        if not opts and self.lopts:
            opts = self.lopts
        opts = dict(opts)

        # Set default options
        opts.setdefault('intf', TCIntf)
        opts.setdefault('weight', 1)

        opts.update(node1=node1, node2=node2, port1=port1, port2=port2)
        return self.g.add_edge(node1, node2, key, opts)

## Link getter
    def getLink(self, node1, node2, key=None):
        """
        Return link metadata dict. If key is None, then the 
        link with the lowest key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            key (int)        : id used to identify multiple edges which
                               link two same nodes (optional)

        Returns:
            (link metadata dict, key)
        """
        entry, key = self._linkEntry(node1, node2, key=key)
        return entry[key], key

## Link updater
    def updateLink(self, node1, node2, key=None, **opts):
        """
        Update link metadata dict. In fact, delete the node
        and create a new one with the updated information. 
        If key is None, then the link with the lowest key 
        value is considered.

        Arguments:
            node1, node2 (string): nodes to link together
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
            opts                 : link options to update (optional)

        Returns:
            key (int)
        """
        info, key = self.popLink(node1, node2, key=key)
        # Check if the edge is in the opposite direction and
        # change all the fields accordingly
        if node1 == info['node2']:
            assert node2 == info['node1']
            opts_new = {}
            for k, value in opts.items():
                if '1' in k:
                    opts_new[k.replace('1','2')] = value
                elif '2' in k:
                    opts_new[k.replace('2','1')] = value
                else:
                    opts_new[k] = value
        else:
            opts_new = opts
        # Remove 'node1' and 'node2' fields from link's information
        node1 = info.pop('node1')
        node2 = info.pop('node2')
        merge_dict(info, opts_new)
        return self.addLink(node1, node2, key=key, **info)

## Link deleter
    def deleteLink(self, node1, node2, key=None):
        """
        Delete link.

        Arguments:
            node1, node2 (string): nodes to link together
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        """
        entry1, key = self._linkEntry(node1, node2, key=key)
        entry1.pop(key)
        if len(entry1.keys()) == 0:
            self.g.edge[node1].pop(node2)
            if len(self.g.edge[node1].keys()) == 0:
                self.g.edge.pop(node1)
            self.g.edge[node2].pop(node1)
            if len(self.g.edge[node2].keys()) == 0:
                self.g.edge.pop(node2)

    def popLink(self, node1, node2, key=None):
        """
        Pop link. If key is None, then the link with the lowest
        key value is considered.

        Arguments:
            node1, node2 (string): nodes to link together
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)

        Returns:
            (link metadata dict, key)
        """
        link, key = self.getLink(node1, node2, key=key)
        self.deleteLink(link['node1'], link['node2'], key=key)
        return link, key

## Method to check neighbors
    def areNeighbors(self, node1, node2):
        """
        Check whether two node are neighbors.

        Arguments:
            node1, node2 (string): names of the nodes

        Returns:
            True if node1 and node2 are neighbors, False else.
        """
        if node1 in self.g.edge.keys():
            if node2 in self.g.edge[node1].keys():
                return True
        return False

## List of links
    def links(self, sort=False, withKeys=False, withInfo=False):
        """
        Return links only preserving (src, dst) order, i.e. no duplicated 
        edges are listed.

        Arguments:
            sort (bool)    : sort links alphabetically, preserving (src, dst) order
            withKeys (bool): return link keys
            withInfo (bool): return link info

        Returns: 
            list of (src, dst [,key, info ])
        """
        return super().links(sort, withKeys, withInfo)

### Nodes
## Node setters
    def addNode(self, name, **opts):
        """
        Add Node to graph.

        Arguments:
            name (string): name
            opts (kwargs): node options

        Returns:
            node name
        """
        return super().addNode(name, **opts)

    def addHost(self, name, **opts):
        """
        Add P4 host node to Mininet topology.
        If the node is already present, overwrite it.

        Arguments:
            name (string): switch name
            opts (kwargs): switch options (optional)

        Returns:
            P4 host name (string)
        """
        opts.setdefault('cls', P4Host)
        opts.update(isHost = True)
        return super().addHost(name, **opts)

    def addSwitch(self, name, **opts):
        """
        Add switch node to Mininet topology.
        If the node is already present, overwrite it.

        Arguments:
            name (string): switch name
            opts (kwargs): switch options

        Returns:
            switch name (string)
        """
        dpid = opts.get('dpid')
        if dpid is not None:
            switch_id = int(dpid, 16)
            if switch_id in self.switch_ids():
                raise Exception('dpid {} already in use.'.format(dpid))

        if not opts and self.sopts:
            opts = self.sopts
        opts.update(isSwitch = True)
        return self.addNode(name, **opts)

    def addP4Switch(self, name, **opts):
        """
        Add P4 switch node to Mininet topology.
        If the node is already present, overwrite it.

        Arguments:
            name (string): switch name
            opts (kwargs): switch options

        Returns:
            P4 switch name (string)
        """
        switch_id = opts.get('device_id')
        if switch_id is not None:
            if switch_id in self.switch_ids():
                raise Exception('switch ID {} already in use.'.format(switch_id))

        opts.setdefault('cls', P4Switch)
        opts.update(isP4Switch = True)
        return self.addSwitch(name, **opts)

    def addP4RuntimeSwitch(self, name, **opts):
        """
        Add P4 runtime switch node to Mininet topology.
        If the node is already present, overwrite it.

        Arguments:
            name (string): switch name
            opts (kwargs): switch options

        Returns:
            P4 runtime switch name (string)
        """

        opts.setdefault('cls', P4RuntimeSwitch)
        opts.update(isP4RuntimeSwitch = True)
        return self.addP4Switch(name, **opts)

## Node getter
    def getNode(self, name):
        """
        Get node information.

        Arguments:
            node (string): Mininet node name

        Returns:
            node metadata dict
        """
        return self.nodeInfo(name)

## Node updaters
    def updateNode(self, name, **opts):
        """
        Update node metadata dict. In fact, delete the node
        and create a new one with the updated information.

        Arguments:
            name (string): node name
            opts         : node options to update (optional)
        
        Returns:
            node name
        """
        if self.isHost(name):
            node_setter = self.addHost
        elif self.isP4RuntimeSwitch(name):
            node_setter = self.addP4RuntimeSwitch
        elif self.isP4Switch(name):
            node_setter = self.addP4Switch
        elif self.isSwitch(name):
            node_setter = self.addSwitch
        else:
            node_setter = self.addNode

        info = self.popNode(name, remove_links=False)
        merge_dict(info, opts)
        return node_setter(name, **info)

## Node deleter
    def deleteNode(self, node, remove_links=True):
        """
        Delete node.

        Arguments:
            node         (string): Mininet node name
            remove_links (bool)  : whether to remove all the incident
                                   links
        """
        # Delete incident links
        if remove_links:
            self.g.edge.pop(node, None)
            for n in self.g.edge.keys():
                self.g.edge[n].pop(node, None)

        # Delete node
        self.g.node.pop(node) 

    def popNode(self, name, remove_links=True):
        """
        Pop node.

        Arguments:
            node1 (string)     : nodes to link together
            remove_links (bool): whether to remove all the incident
                                 links

        Returns:
            node metadata dict
        """
        node = self.getNode(name)
        self.deleteNode(name, remove_links=remove_links)
        return node

## Methods to check the node type
    def isNode(self, node):
        """
        Check if node exists.

        Arguments:
            node (string): node name

        Returns:
            True if node exists, else False (bool)
        """
        return node in self.g.nodes()

    def isHost(self, node):
        """
        Check if node is a host.

        Arguments:
            node (string): node name

        Returns:
            True if node is a host, else False (bool)
        """
        return self.g.node[node].get('isHost', False)

    def isSwitch(self, name):
        """
        Check if node is a switch.

        Arguments:
            node (string): Mininet node name

        Returns:
            True if node is a switch, else False (bool)
        """
        return super().isSwitch(name)

    def isP4Switch(self, node):
        """
        Check if node is a P4 switch.

        Arguments:
            node (string): node name

        Returns:
            True if node is a P4 switch, else False (bool)
        """
        return self.g.node[node].get('isP4Switch', False)

    def isP4RuntimeSwitch(self, node):
        """
        Check if node is a P4 runtime switch.

        Arguments:
            node (string): node name

        Returns:
            True if node is a P4 switch, else False (bool)
        """
        return self.g.node[node].get('isP4RuntimeSwitch', False)

    def hasCpuPort(self, node):
        """
        Check if node has a CPU port.

        Arguments:
            node (string): Mininet node name

        Returns:
            True if node has a CPU port, else False (bool)
        """
        return self.getNode(node).get('cpu_port', False)

## Lists of node names by type
    def nodes(self, sort=True, withInfo=False):
        """
        Return nodes in graph.

        Arguments:
            sort (bool)    : sort nodes alphabetically
            withInfo (bool): retrieve node information
        """
        nodes = self.g.nodes(data=withInfo)
        if not sort:
            return nodes
        else:
            # Ignore info when sorting
            tupleSize = 2
            return sorted(nodes, key=(lambda l: naturalSeq(l[:tupleSize])))

    def hosts(self, sort=True, withInfo=False):
        """
        Return hosts.
        
        Arguments:
            sort (bool)    : sort hosts alphabetically
            withInfo (bool): retrieve node information

        Returns:
            list of hosts
        """
        if withInfo:
            return [n for n in self.nodes(sort=sort, withInfo=True) if self.isHost(n[0])]
        else:
            return [n for n in self.nodes(sort=sort, withInfo=False) if self.isHost(n)]

    def switches(self, sort=True, withInfo=False):
        """
        Return switches.

        Arguments:
            sort (bool)    : sort switches alphabetically
            withInfo (bool): retrieve node information
           
        Returns: 
            list of switches
        """
        if withInfo:
            return [n for n in self.nodes(sort=sort, withInfo=True) if self.isSwitch(n[0])]
        else:
            return [n for n in self.nodes(sort=sort, withInfo=False) if self.isSwitch(n)]

    def p4switches(self, sort=True, withInfo=False):
        """
        Return P4 switches.

        Arguments:
            sort (bool)    : sort switches alphabetically
            withInfo (bool): retrieve node information

        Returns:
            list of P4 switches
        """
        if withInfo:
            return [n for n in self.nodes(sort=sort, withInfo=True) if self.isP4Switch(n[0])]
        else:
            return [n for n in self.nodes(sort=sort, withInfo=False) if self.isP4Switch(n)]

    def p4rtswitches(self, sort=True, withInfo=False):
        """
        Return P4 runtime switches.

        Arguments:
            sort (bool)    : sort switches alphabetically
            withInfo (bool): retrieve node information

        Returns:
            list of P4 runtime switches
        """
        if withInfo:
            return [n for n in self.nodes(sort=sort, withInfo=True) if self.isP4RuntimeSwitch(n[0])]
        else:
            return [n for n in self.nodes(sort=sort, withInfo=False) if self.isP4RuntimeSwitch(n)]

## Nodes
    def enableLog(self, name, log_dir='./log'):
        """
        Enable log for node (also for the task scheduler).

        Arguments:
            name (string)   : name of the node
            log_dir (string): where to save log files
        """            
        if self.isNode(name):
            self.updateNode(name, log_enabled=True, log_dir=log_dir)
        else:
            raise Exception('"{}" does not exists.'.format(name))

    def disableLog(self, name):
        """
        Disable log for node (also for the task scheduler).

        Arguments:
            name (string): name of the node
        """            
        if self.isNode(name):
            self.updateNode(name, log_enabled=False)
        else:
            raise Exception('"{}" does not exists.'.format(name))

    def enableLogAll(self, log_dir='./log'):
        """
        Enable log for all the nodes (also for the task schedulers).

        Arguments:
            log_dir (string): where to save log files
        """
        for node in self.nodes():
            self.enableLog(node, log_dir=log_dir)

    def disableLogAll(self):
        """
        Disable log for all the nodes (also for the task schedulers).
        """
        for node in self.nodes():
            self.disableLog(node)

    def enableScheduler(self, name, path='/tmp'):
        """
        Enable the task scheduler server for the node.

        Arguments:
            name (string): name of the node
            path (string): name of the directory where the
                           socket file will be placed
        """
        if self.isNode(name):
            self.updateNode(name, scheduler=True, socket_path=path)
        else:
            raise Exception('"{}" does not exists.'.format(name))

    def disableScheduler(self, name):
        """
        Disable the task scheduler server for the node.

        Arguments:
            name (string): name of the node
        """
        if self.isNode(name):
            self.updateNode(name, scheduler=False)
        else:
            raise Exception('"{}" does not exists.'.format(name))

    def hasScheduler(self, name):
        """
        Whether a host has an active scheduler or not.
        """
        return self.getNode(name).get('scheduler', False)

    def enableSchedulerAll(self, path='/tmp'):
        """
        Enable the task scheduler server for all the nodes.

        Arguments:
            path (string): name of the directory where the
                           socket file will be placed
        """
        for node in self.nodes():
            self.enableScheduler(node, path)

    def disableSchedulerAll(self):
        """
        Disable the task scheduler server for all the nodes.
        """
        for node in self.nodes():
            self.disableScheduler(node, path)

    def addTaskFile(self, filepath, def_mod='p4utils.utils.traffic_utils'):
        """
        Add the tasks to the node.

        Arguments:
            filepath (string): tasks file path
            def_mod (string) : default module where to look for exe functions

        Notice:
            The file has to be a set of lines, where each has
            the following syntax.
            <node> <start> <duration> <exe> [--mod <module>] [<arg1>] ... [<argN>] [--<key1> <kwarg1>] ... [--<keyM> <kwargM>]
        """
        with open(filepath, 'r') as f:
            lines = f.readlines()
            for line in lines:
                args, kwargs = parse_task_line(line, def_mod=def_mod)
                self.addTask(*args, **kwargs)

    def addTask(self, node, exe, *args, start=0, duration=0, enableScheduler=True, **kwargs):
        """
        Add a task to the node. It can automatically enable the TaskScheduler
        on that node with the socket lacated in the default path, if no
        TaskScheduler has been previously enabled.

        Arguments:
            node (string)         : name of the node
            exe                   : executable to run (either a shell string 
                                    command or a python function)
            args                  : positional arguments for the passed function
            start (float)         : task starting time with respect to the current
                                    time in seconds.
            duration (float)      : task duration time in seconds (if duration is 
                                    lower than or equal to 0, then the task has no 
                                    time limitation)
            enableScheduler (bool): whether to automatically enable the TaskScheduler or not
            kwargs                : key-word arguments for the passed function
        """
        if self.isNode(node):
            # If the TaskScheduler is not enabled, enable it.
            if not self.hasScheduler(node) and enableScheduler:
                self.enableScheduler(node)
            elif not self.hasScheduler(node) and not enableScheduler:
                raise Exception('"{}" does not have a scheduler.'. format(node))
            self.tasks.setdefault(node, [])
            # Parse execution parameters to pass to the server
            kwargs.update(start=start+time.time(), duration=duration)
            args = list(args)
            args.insert(0, exe)
            params = (args, kwargs)
            # Append task to tasks
            self.tasks[node].append(params)
        else:
            raise Exception('"{}" does not exists.'.format(name))

    def setDefaultRoute(self, name, default_route):
        """
        Set the node's default route.

        Arguments:
            name (string)         : name of the node
            default_route (string): default route IP
        """
        if self.isNode(name):
            self.updateNode(name, defaultRoute='via {}'.format(default_route))
        else:
            raise Exception('"{}" does not exists.'.format(name))

## Hosts
    def enableDhcp(self, name):
        """
        Enable DHCP server in hosts.
        """
        if self.isHost(name):
            self.updateNode(name, dhcp=True)
        else:
            raise Exception('"{}" is not a host.'.format(name))

    def disableDhcp(self, name):
        """
        Disable DHCP server in hosts.
        """
        if self.isHost(name):
            self.updateNode(name, dhcp=False)
        else:
            raise Exception('"{}" is not a host.'.format(name))

    def enableDhcpAll(self):
        """
        Enable DHCP for all the hosts.
        """
        for host in self.hosts():
            self.enableDhcp(host)
    
    def disableDhcpAll(self):
        """
        Disable DHCP for all the hosts.
        """
        for host in self.hosts():
            self.disableDhcp(host)

    def disableDhcpAll(self):
        """
        Disable DHCP for all the hosts.
        """
        for host in self.hosts():
            self.disableDhcp(host)

## Switches
    def setSwitchDpid(self, name, dpid):
        """
        Set Switch DPID. Only applies to non P4 switches
        since their DPID is determined by their ID.

        Arguments:
            name (string): name of the P4 switch
            dpid (string): switch DPID (16 hexadecimal characters)
        """
        if self.isSwitch(name):
            if self.isP4Switch(name):
                raise Exception('cannot set DPID to P4 switches.')
            else:
                self.updateNode(name, dpid=dpid)
        else:
            raise Exception('"{}" is not a switch.'.format(name))

## P4 Switches
    def setP4Source(self, name, p4_src):
        """
        Set the P4 source for the switch.

        Arguments:
            name (string)  : name of the P4 switch
            p4_src (string): path to the P4 fil
        """
        if self.isP4Switch(name):
            self.updateNode(name, p4_src=p4_src)
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def setP4SourceAll(self, p4_src):
        """
        Set the same P4 source for all the P4 switches.

        Arguments:
            name (string)  : name of the P4 switch
            p4_src (string): path to the P4 file
        """
        for p4switch in self.p4switches():
            self.setP4Source(p4switch, p4_src)

    def setP4CliInput(self, name, cli_input):
        """
        Set the path to the command line configuration file for
        the Thrift capable switch.

        Arguments:
            name (string)     : name of the P4 switch
            cli_input (string): path to the command line configuration
                                file
        """
        if self.isP4Switch(name):
            self.updateNode(name, cli_input=cli_input)
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def setP4SwitchId(self, name, id):
        """
        Set P4 Switch ID.

        Arguments:
            name (string): name of the P4 switch
            id (int)     : P4 switch ID
        """
        if self.isP4Switch(name):
            self.updateNode(name, device_id=id)
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def setThriftPort(self, name, port):
        """
        Set the thrift port number for the P4 switch.

        Arguments:
            name (string): name of the P4 switch
            port (int)   : thrift port number
        """
        if self.isP4Switch(name):
            self.updateNode(name, thrift_port=port)
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def enableDebugger(self, name):
        """
        Enable debugger for switch.

        Arguments:
            name (string): name of the P4 switch
        """
        if self.isP4Switch(name):
            self.updateNode(name, enable_debugger=True)
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def disableDebugger(self, name):
        """
        Disable debugger for switch.

        Arguments:
            name (string): name of the P4 switch
        """            
        if self.isP4Switch(name):
            self.updateNode(name, enable_debugger=False)
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def enableDebuggerAll(self):
        """
        Enable debugger for all the switches.
        """
        for switch in self.p4switches():
            self.enableDebugger(switch)

    def disableDebuggerAll(self):
        """
        Disable debugger for all the switches.
        """
        for switch in self.p4switches():
            self.disableDebugger(switch)

    def enablePcapDump(self, name, pcap_dir='./pcap'):
        """
        Enable pcap dump for switch.

        Arguments:
            name (string)    : name of the P4 switch
            pcap_dir (string): where to save pcap files
        """            
        if self.isP4Switch(name):
            self.updateNode(name, pcap_dump=True, pcap_dir=pcap_dir)
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def disablePcapDump(self, name):
        """
        Disable pcap dump for switch.

        Arguments:
            name (string): name of the P4 switch
        """
        if self.isP4Switch(name):
            self.updateNode(name, pcap_dump=False)
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def enablePcapDumpAll(self, pcap_dir='./pcap'):
        """
        Enable pcap dump for all the switches.

        Arguments:
            pcap_dir (string): where to save pcap files
        """
        for switch in self.p4switches():
            self.enablePcapDump(switch, pcap_dir=pcap_dir)

    def disablePcapDumpAll(self):
        """
        Disable pcap dump for all the switches.
        """
        for switch in self.p4switches():
            self.disablePcapDump(switch)

    def enableCpuPort(self, name):
        """
        Enable CPU port on switch.

        Arguments:
            name (string): name of the P4 switch
        """
        if self.isP4Switch(name):
            # We use the bridge but at the same time we use the bug it has so the
            # interfaces are not added to it, but at least we can clean easily thanks to that.
            if self.cpu_bridge is None:
                self.cpu_bridge = self.addSwitch('sw-cpu', cls=LinuxBridge, dpid='1000000000000000')
            self.addLink(name, self.cpu_bridge, intfName1='{}-cpu-eth0'.format(name), intfName2= '{}-cpu-eth1'.format(name), deleteIntfs=True)
            self.updateNode(name, cpu_port=True)
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def disableCpuPort(self, name):
        """
        Disable CPU port on switch.

        Arguments:
            name (string): name of the P4 switch
        """
        if self.isP4Switch(name):
            self.popLink(name, sw)
            self.updateNode(name, cpu_port=False)
            delete_cpu_bridge = True
            for node in self.nodes():
                if self.hasCpuPort(node):
                    delete_cpu_bridge = False
                    break
            if delete_cpu_bridge:
                self.popNode(self.cpu_bridge)
                self.cpu_bridge = None
        else:
            raise Exception('"{}" is not a P4 switch.'.format(name))

    def enableCpuPortAll(self):
        """
        Enable CPU port on all the P4 switches.

        Notice:
            This applies only to already defined switches. If other
            switches are added after this command, they won't have
            any CPU port enabled.
        """
        for switch in self.p4switches():
            self.enableCpuPort(switch)

    def disableCpuPortAll(self):
        """
        Disable CPU port on all the P4 switches.
        """
        for switch in self.p4switches():
            self.popLink(name, sw)
            self.updateNode(name, cpu_port=False)
        self.popNode(self.cpu_bridge)
        self.cpu_bridge = None

## P4 Runtime Switches
    def setGrpcPort(self, name, port):
        """
        Set the grpc port number for the P4 runtime switch.

        Arguments:
            name (string): name of the P4 runtime switch
            port (int)   : thrift port number
        """
        if self.isP4RuntimeSwitch(name):
            self.updateNode(name, grpc_port=port)
        else:
            raise Exception('"{}" is not a P4 runtime switch.'.format(name))

## Links
    def setBw(self, node1, node2, bw, key=None):
        """
        Set link bandwidth. If key is None, then the link with the lowest
        key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            bw (float, int)      : bandwidth (in Mbps)
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)

        Returns:
            key (int)
        """
        if isinstance(bw, float) or isinstance(bw, int):
            return self.updateLink(node1, node2, key=key, bw=bw)
        else:
            raise TypeError('bw is not a float nor int.')

    def setDelay(self, node1, node2, delay, key=None):
        """
        Set link delay. If key is None, then the link with the lowest
        key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            delay (int)          : transmission delay (in ms)
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        
        Returns:
            key (int)
        """
        if isinstance(delay, int):
            return self.updateLink(node1, node2, key=key, delay=str(delay)+'ms')
        else:
            raise TypeError('delay is not an integer.')

    def setLoss(self, node1, node2, loss, key=None):
        """
        Set link loss. If key is None, then the link with the lowest
        key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            loss (float)         : packet loss rate (e.g. 0.5 means that 50% of
                                   packets will exeperience a loss)
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        
        Returns:
            key (int)
        """
        if isinstance(loss, float):
            if loss <= 1 and loss >= 0:
                loss *= 100
                return self.updateLink(node1, node2, key=key, loss=loss)
            else:
                raise Exception('the selected loss rate is not allowed.')
        else:
            raise TypeError('bw is not an integer.')

    def setMaxQueueSize(self, node1, node2, max_queue_size, key=None):
        """
        Set link max queue size. If key is None, then the link with the lowest
        key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            max_queue_size (int) : maximum number of packets the qdisc may hold queued at a time.
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)

        Returns:
            key (int)
        """
        if isinstance(max_queue_size, int):
            return self.updateLink(node1, node2, key=key, max_queue_size=max_queue_size)
        else:
            raise TypeError('max_queue_size is not an integer.')

    def setIntfName(self, node1, node2, intfName, key=None):
        """
        Set name of node1's interface facing node2 with the specified key. if key is None,
        then the link with lowest key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            intfName (string)    : name of the interface
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        
        Returns:
            key (int)
        """
        if intfName not in self.node_intfs()[node1].keys():
            return self.updateLink(node1, node2, key=key, intfName1=intfName)
        else:
            raise Exception('interface "{}" already present on node "{}"'.format(intfName, node1))

    def setIntfPort(self, node1, node2, port, key=None):
        """
        Set port number of node1's interface facing node2 with the specified key.
        if key is None, then the link with lowest key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            port (int)           : name of the interface
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        
        Returns:
            key (int)
        """
        if port not in self.node_ports()[node1].keys():
            return self.updateLink(node1, node2, key=key, port1=port)
        else:
            raise Exception('port {} already present on node "{}"'.format(port, node1))

    def setIntfIp(self, node1, node2, ip, key=None):
        """
        Set IP of node1's interface facing node2 with the specified key. If key is None,
        then the link with the lowest key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            ip (string)          : IP address/mask to configure
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        
        Returns:
            key (int)
        """
        if self.isSwitch(node1):
            # Set fake IP for switches
            return self.updateLink(node1, node2, key=key, sw_ip1=ip)
        else:
            # Set real IP for other devices
            return self.updateLink(node1, node2, key=key, params1={'ip': ip})

    def setIntfMac(self, node1, node2, mac, key=None):
        """
        Set MAC of node1's interface facing node2 with the specified key. If key is None,
        then the link with the lowest key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            mac (string)         : MAC address to configure
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)

        Returns:
            key (int)
        """
        return self.updateLink(node1, node2, key=key, addr1=mac)

    def setBwAll(self, bw):
        """
        Set bandwidth for all the links currently in the network.

        Arguments:
            bw (float): bandwidth (in Mbps)
        """
        for node1, node2, key in self.links(withKeys=True):
            self.setBw(node1, node2, bw, key=key)

    def setDelayAll(self, delay):
        """
        Set delay for all the links currently in the network.

        Arguments:
            delay (int): transmission delay (in ms)
        """
        for node1, node2, key in self.links(withKeys=True):
            self.setDelay(node1, node2, delay, key=key)

    def setLossAll(self, loss):
        """
        Set loss for all the links currently in the network.

        Arguments:
            loss (float): packet loss rate (e.g. 0.5 means that 50% of
                          packets will exeperience a loss)
        """
        for node1, node2, key in self.links(withKeys=True):
            self.setLoss(node1, node2, loss, key=key)
    
    def setMaxQueueSizeAll(self, max_queue_size):
        """
        Set max queue size for all the links currently in the network.

        Arguments:
            max_queue_size (int): maximum number of packets the qdisc may hold queued at a time.
        """
        for node1, node2, key in self.links(withKeys=True):
            self.setMaxQueueSize(node1, node2, max_queue_size, key=key)

## Assignment strategies
    def l2(self):
        """
        Automated IP/MAC assignment strategy for already initialized 
        links and nodes. All the devices are placed inside the same
        IPv4 network (10.0.0.0/16).

        Assumptions:
            Each host is connected to one switch only.
            Only switches and hosts are allowed.
            Parallel links are not allowed.
        """
        output('"l2" assignment strategy selected.\n')
        ip_generator = IPv4Network('10.0.0.0/16').hosts()
        reserved_ips = {}
        assigned_ips = set()

        for node in self.nodes():
            # Skip CPU switch
            if node == 'sw-cpu':
                continue
            if self.isHost(node):
                # Reserve IPs for normal hosts
                if self.check_host_valid_ip_from_name(node):
                    host_num = int(node[1:])
                    upper_byte = (host_num & 0xff00) >> 8
                    lower_byte = (host_num & 0x00ff)
                    host_ip = '10.0.%d.%d' % (upper_byte, lower_byte)
                    reserved_ips[node] = host_ip
            else:
                # If it is not a host, it must be a switch
                assert self.isSwitch(node)

        # Check whether the graph is a multigraph
        assert not self.is_multigraph()

        for node1, node2 in self.links():
            # Skip CPU switch
            if node1 == 'sw-cpu' or node2 == 'sw-cpu':
                continue
            # Node-switch link
            if self.isHost(node1):
                host_name = node1
                direct_sw = node2
                assert self.isSwitch(node2)
            # Switch-node link
            elif self.isHost(node2):
                host_name = node2
                direct_sw = node1
                assert self.isSwitch(node1)
            # Switch-switch link
            else:
                continue

            if self.check_host_valid_ip_from_name(host_name):
                host_ip = reserved_ips[host_name]
                # We check if for some reason the ip was already given by the ip_generator. 
                # This can only happen if the host naming is not <h_x>.
                # This should not be possible anymore since we reserve ips for h_x hosts.
                if host_ip in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(host_ip))
                assigned_ips.add(host_ip)
            else:
                host_ip = next(ip_generator).compressed
                # We check if for some reason the ip was already given by the ip_generator. 
                # This can only happen if the host naming is not <h_x>.
                # This should not be possible anymore since we reserve ips for h_x hosts.
                while host_ip in assigned_ips or host_ip in list(reserved_ips.values()):
                    host_ip = str(next(ip_generator).compressed)
                assigned_ips.add(host_ip)

            host_mac = ip_address_to_mac(host_ip) % (0)
            direct_sw_mac = ip_address_to_mac(host_ip) % (1)

            self.setIntfMac(host_name, direct_sw, host_mac)
            self.setIntfMac(direct_sw, host_name, direct_sw_mac)
            self.setIntfIp(host_name, direct_sw, host_ip + '/16')

    def mixed(self):
        """
        Automated IP/MAC assignment strategy for already initialized 
        links and nodes. All the hosts linked to a switch are placed
        in the same subnetwork. Different switches (even those linked
        together) are placed in different subnetworks.

        Assumptions:
            Each host is connected to one switch only.
            Only switches and hosts are allowed.
            Parallel links are not allowed.
        """
        output('"mixed" assignment strategy selected.\n')
        reserved_ips = {}
        assigned_ips = set()
        sw_to_generator = {}
        sw_to_id = {}

        for node, info in self.nodes(withInfo=True):
            # Skip CPU switch
            if node == 'sw-cpu':
                continue
            if self.isSwitch(node):
                # Generate a subnetwork per each switch
                if self.isP4Switch(node):
                    sw_id = info.get('device_id')
                    if sw_id is None:
                        sw_id = self.auto_switch_id()
                        self.setP4SwitchId(node, sw_id)
                else:
                    dpid = info.get('dpid')
                    if dpid is None:
                        sw_id = self.auto_switch_id()
                        self.setSwitchDpid(node, sw_id)
                    else:
                        sw_id = int(dpid, 16)
                upper_bytex = (sw_id & 0xff00) >> 8
                lower_bytex = (sw_id & 0x00ff)
                net = '10.%d.%d.0/24' % (upper_bytex, lower_bytex)
                sw_to_generator[node] = IPv4Network(str(net)).hosts()
                sw_to_id[node] = sw_id
            else:
                # If it is not a switch, it must be a host
                assert self.isHost(node)
        
        # Check whether the graph is a multigraph
        assert not self.is_multigraph()

        for node1, node2 in self.links():
            # Skip CPU switch
            if node1 == 'sw-cpu' or node2 == 'sw-cpu':
                continue
            # Node-switch link
            if self.isHost(node1):
                host_name = node1
                direct_sw = node2
                assert self.isSwitch(node2)
            # Switch-node link
            elif self.isHost(node2):
                host_name = node2
                direct_sw = node1
                assert self.isSwitch(node1)
            # Switch-switch link
            else:
                continue

            sw_id = sw_to_id[direct_sw]
            upper_byte = (sw_id & 0xff00) >> 8
            lower_byte = (sw_id & 0x00ff)

            # Reserve IPs for normal hosts
            if self.check_host_valid_ip_from_name(host_name):
                host_num = int(host_name[1:])
                assert host_num < 254
                host_ip = '10.%d.%d.%d' % (upper_byte, lower_byte, host_num)
                reserved_ips[host_name] = host_ip

        for node1, node2 in self.links():
            # Skip CPU switch
            if node1 == 'sw-cpu' or node2 == 'sw-cpu':
                continue
            # Node-switch link
            if self.isHost(node1):
                host_name = node1
                direct_sw = node2
                assert self.isSwitch(node2)
            # Switch-node link
            elif self.isHost(node2):
                host_name = node2
                direct_sw = node1
                assert self.isSwitch(node1)
            # Switch-switch link
            else:
                continue

            sw_id = sw_to_id[direct_sw]
            upper_byte = (sw_id & 0xff00) >> 8
            lower_byte = (sw_id & 0x00ff)
            ip_generator = sw_to_generator[direct_sw]

            if self.check_host_valid_ip_from_name(host_name):
                host_ip = reserved_ips[host_name]
                # We check if for some reason the ip was already given by the ip_generator. 
                # This can only happen if the host naming is not <h_x>.
                # This should not be possible anymore since we reserve ips for h_x hosts.
                if host_ip in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(host_ip))
                assigned_ips.add(host_ip)
            else:
                host_ip = next(ip_generator).compressed
                # We check if for some reason the ip was already given by the ip_generator. 
                # This can only happen if the host naming is not <h_x>.
                # This should not be possible anymore since we reserve ips for h_x hosts.
                while host_ip in assigned_ips or host_ip in list(reserved_ips.values()):
                    host_ip = str(next(ip_generator).compressed)
                assigned_ips.add(host_ip)

            host_gw = '10.%d.%d.254' % (upper_byte, lower_byte)
            host_mac = ip_address_to_mac(host_ip) % (0)
            direct_sw_mac = ip_address_to_mac(host_ip) % (1)

            self.setIntfMac(host_name, direct_sw, host_mac)
            self.setIntfMac(direct_sw, host_name, direct_sw_mac)
            self.setIntfIp(host_name, direct_sw, host_ip + '/24')
            self.setIntfIp(direct_sw, host_name, host_gw + '/24')

            self.setDefaultRoute(host_name, host_gw)

        for node1, node2 in self.links():
            # Skip CPU switch
            if node1 == 'sw-cpu' or node2 == 'sw-cpu':
                continue
            # Switch-switch link
            if self.isSwitch(node1) and self.isSwitch(node2):
                sw1_ip = '20.%d.%d.1/24' % (sw_to_id[node1], sw_to_id[node2])
                sw2_ip = '20.%d.%d.2/24' % (sw_to_id[node1], sw_to_id[node2])
                if sw1_ip in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(sw1_ip))
                assigned_ips.add(sw1_ip)
                if sw2_ip in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(sw2_ip))
                assigned_ips.add(sw2_ip)

                self.setIntfIp(node1, node2, sw1_ip) # Fake and real IPs are handled by the same method setIntfIp.
                self.setIntfIp(node2, node1, sw2_ip) # Fake and real IPs are handled by the same method setIntfIp.

    def l3(self):
        """
        Automated IP/MAC assignment strategy for already initialized 
        links and nodes. All the hosts have a different subnetwork shared
        with the fake IP address of the switch port they are connected to.

        Assumptions:
            Each host is connected to one switch only.
            Only switches and hosts are allowed.
            Parallel links are not allowed.
        """
        output('"l3" assignment strategy selected.\n')
        reserved_ips = {}
        assigned_ips = set()
        sw_to_next_available_host_id = {}
        sw_to_id = {}

        for node, info in self.nodes(withInfo=True):
            # Skip CPU switch
            if node == 'sw-cpu':
                continue
            if self.isSwitch(node):
                if self.isP4Switch(node):
                    sw_id = info.get('device_id')
                    if sw_id is None:
                        sw_id = self.auto_switch_id()
                        self.setP4SwitchId(node, sw_id)
                else:
                    dpid = info.get('dpid')
                    if dpid is None:
                        sw_id = self.auto_switch_id()
                        self.setSwitchDpid(node, sw_id)
                    else:
                        sw_id = int(dpid, 16)
                sw_to_next_available_host_id[node] = []
                sw_to_id[node] = sw_id

        # Check whether the graph is a multigraph
        assert not self.is_multigraph()

        for node1, node2 in self.links():
            # Skip CPU switch
            if node1 == 'sw-cpu' or node2 == 'sw-cpu':
                continue
            # Node-switch link
            if self.isHost(node1):
                host_name = node1
                direct_sw = node2
                assert self.isSwitch(node2)
            # Switch-node link
            elif self.isHost(node2):
                host_name = node2
                direct_sw = node1
                assert self.isSwitch(node1)
            # Switch-switch link
            else:
                continue

            # Reserve IPs for normal hosts
            if self.check_host_valid_ip_from_name(host_name):
                sw_id = sw_to_id[direct_sw]
                host_num = int(host_name[1:])
                assert host_num < 254
                host_ip = '10.%d.%d.2' % (sw_id, host_num)
                reserved_ips[host_name] = host_ip
                sw_to_next_available_host_id[direct_sw].append(host_num)

        for node1, node2 in self.links():
            # Skip CPU switch
            if node1 == 'sw-cpu' or node2 == 'sw-cpu':
                continue
            # Node-switch link
            if self.isHost(node1):
                host_name = node1
                direct_sw = node2
                assert self.isSwitch(node2)
            # Switch-node link
            elif self.isHost(node2):
                host_name = node2
                direct_sw = node1
                assert self.isSwitch(node1)
            # Switch-switch link
            else:
                continue

            sw_id = sw_to_id[direct_sw]
            assert sw_id < 254

            if self.check_host_valid_ip_from_name(host_name):
                host_num = int(host_name[1:])
                assert host_num < 254
                host_ip = '10.%d.%d.2' % (sw_id, host_num)
                host_gw = '10.%d.%d.1' % (sw_id, host_num)
                # We check if for some reason the ip was already given by the ip_generator. 
                # This can only happen if the host naming is not <h_x>.
                # This should not be possible anymore since we reserve ips for h_x hosts.
                if host_ip in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(host_ip))
                assigned_ips.add(host_ip)
                if host_gw in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(host_gw))
                assigned_ips.add(host_gw)
            else:
                host_num = next_element(sw_to_next_available_host_id[direct_sw], minimum=1, maximum=254)
                host_ip = '10.%d.%d.2' % (sw_id, host_num)
                host_gw = '10.%d.%d.1' % (sw_id, host_num)
                # We check if for some reason the ip was already given by the ip_generator. 
                # This can only happen if the host naming is not <h_x>.
                # This should not be possible anymore since we reserve ips for h_x hosts.
                if host_ip in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(host_ip))
                assigned_ips.add(host_ip)
                if host_gw in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(host_gw))
                assigned_ips.add(host_gw)
                sw_to_next_available_host_id[direct_sw].append(host_num)

            host_mac = ip_address_to_mac(host_ip) % (0)
            direct_sw_mac = ip_address_to_mac(host_ip) % (1)

            self.setIntfMac(host_name, direct_sw, host_mac)
            self.setIntfMac(direct_sw, host_name, direct_sw_mac)
            self.setIntfIp(host_name, direct_sw, host_ip + '/24')
            self.setIntfIp(direct_sw, host_name, host_gw + '/24')

            self.setDefaultRoute(host_name, host_gw)

        for node1, node2 in self.links():
            # Skip CPU switch
            if node1 == 'sw-cpu' or node2 == 'sw-cpu':
                continue
            # Switch-switch link
            if self.isSwitch(node1) and self.isSwitch(node2):
                sw1_ip = '20.%d.%d.1/24' % (sw_to_id[node1], sw_to_id[node2])
                sw2_ip = '20.%d.%d.2/24' % (sw_to_id[node1], sw_to_id[node2])
                if sw1_ip in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(sw1_ip))
                assigned_ips.add(sw1_ip)
                if sw2_ip in assigned_ips:
                    raise Exception('IP {} has been already assigned to a host.'.format(sw2_ip))
                assigned_ips.add(sw2_ip)

                self.setIntfIp(node1, node2, sw1_ip) # Fake and real IPs are handled by the same method setIntfIp.
                self.setIntfIp(node2, node1, sw2_ip) # Fake and real IPs are handled by the same method setIntfIp.