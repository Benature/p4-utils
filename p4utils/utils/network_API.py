import os
from copy import deepcopy
from ipaddress import IPv4Network
from networkx import MultiGraph, Graph
from networkx.readwrite.json_graph import node_link_data
from mininet.link import TCIntf
from mininet.nodelib import LinuxBridge
from mininet.cli import CLI
from mininet.log import setLogLevel, info, output, debug, warning

from p4utils.utils.helper import *
from p4utils.utils.client import ThriftClient
from p4utils.utils.compiler import P4C
from p4utils.utils.topology import NetworkGraph
from p4utils.mininetlib.node import *
from p4utils.mininetlib.net import P4Mininet
from p4utils.mininetlib.topo import P4Topo


class NetworkAPI:
    """
    Network definition and initialization API.
    """
    def __init__(self):
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

        ## External modules default configuration dictionary
        self.modules = {}

        # Topology module
        self.modules['topo'] = {}
        self.modules['topo']['class'] = P4Topo
        # Default kwargs
        self.modules['topo']['kwargs'] = {}
        # Topology is instantiated right at the beginning
        self.topo = self.module('topo')

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

        # Clean up old Mininet processes
        cleanup()

## Utils
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
        multigraph = False
        for node1 in self.nodes():
            for node2 in self.nodes():
                if self.areNeighbors(node1, node2):
                    if len(self.topo._linkEntry(node1, node2)[0]) > 1:
                        multigraph = True
                        break

        if multigraph:
            debug('Multigraph topology selected.\n')
            graph = self.topo.g.convertTo(MultiGraph, data=True, keys=True)
        else:
            debug('Simple graph topology selected.\n')
            graph = self.topo.g.convertTo(NetworkGraph, data=True, keys=False)
            
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
        for p4switch in self.p4switches():
            p4_src = self.getNode(p4switch).get('p4_src')
            if p4_src is not None:
                if not is_compiled(os.path.realpath(p4_src), self.compilers):
                    compiler = self.module('comp', p4_src)
                    compiler.compile()
                    self.compilers.append(compiler)
                else:
                    compiler = get_by_attr('p4_src', os.path.realpath(params['p4_src']), self.compilers)
                # Retrieve json_path
                self.updateNode(p4switch, json_path=compiler.get_json_out())
                # Try to retrieve p4 runtime info file path
                try:
                    self.updateNode(p4switch, p4rt_path=compiler.get_p4rt_out())
                except P4InfoDisabled:
                    pass

    def start_net_cli(self):
        """
        Starts up the mininet CLI and prints some helpful output.

        Assumes:
            A mininet instance is stored as self.net and self.net.start() has been called.
        """
        for switch in self.net.switches:
            if self.topo.isP4Switch(switch.name):
                switch.describe()
        for host in self.net.hosts:
            host.describe()
        info("Starting mininet CLI...\n")
        # Generate a message that will be printed by the Mininet CLI to make
        # interacting with the simple switch a little easier.
        print('')
        print('======================================================================')
        print('Welcome to the P4 Utils Mininet CLI!')
        print('======================================================================')
        print('Your P4 program is installed into the BMV2 software switch')
        print('and your initial configuration is loaded. You can interact')
        print('with the network using the mininet CLI below.')
        print('')
        # print('To inspect or change the switch configuration, connect to')
        # print('its CLI from your host operating system using this command:')
        # print('  {} --thrift-port <switch thrift port>'.format(DEFAULT_CLIENT.cli_bin))
        # print('')
        # print('To view a switch log, run this command from your host OS:')
        # print('  tail -f {}/<switchname>.log'.format(self.log_dir))
        # print('')
        # print('To view the switch output pcap, check the pcap files in \n {}:'.format(self.pcap_dir))
        # print(' for example run:  sudo tcpdump -xxx -r s1-eth1.pcap')
        # print('')

        CLI(self.net)

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
        default_kwargs = deepcopy(self.modules[mod_name]['kwargs'])
        default_class = self.modules[mod_name]['class']
        default_kwargs.update(kwargs)
        return default_class(*args, **default_kwargs)

    def node_ports(self):
        """
        Build a dictionary from the links and store the ports
        of every node and its destination node.
        """
        ports = {}
        for _, _, key, info in self.links(withKeys=True, withInfo=True):
            ports.setdefault(info['node1'], {})
            ports.setdefault(info['node2'], {})
            ports[info['node1']].update({info['port1'] : (info['node1'], info['node2'], key)})
            ports[info['node2']].update({info['port2'] : (info['node2'], info['node1'], key)})
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
            ports[info['node1']].update({info['intfName1'] : (info['node1'], info['node2'], key)})
            ports[info['node2']].update({info['intfName2'] : (info['node2'], info['node1'], key)})     
        return ports            

    def switch_ids(self):
        """
        Return a list containing all the switch IDs.
        """
        ids = []
        for switch, info in self.switches(withInfo=True):
            if self.isP4Switch(switch):
                ids.append(info['device_id'])
            else:
                ids.append(int(info['dpid'], 16))
        return ids

    def mac_addresses(self):
        """
        Return a list containing all the MAC addresses.
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
        Return a list containing all the IPv4 addresses.
        """
        ips = set()

        for node1, node2, info in self.links(withInfo=True):
            if self.isSwitch(node1):
                ip = info.get('sw_ip1')
                if ip is not None:
                    ips.add(ip.split('/')[0])
            else:
                params = info.get('params1')
                if params is not None:
                    ip = params.get('ip')
                    if ip is not None:
                        ips.add(ip.split('/')[0])

            if self.isSwitch(node2):
                ip = info.get('sw_ip2')
                if ip is not None:
                    ips.add(ip.split('/')[0])
            else:
                params = info.get('params2')
                if params is not None:
                    ip = params.get('ip')
                    if ip is not None:
                        ips.add(ip.split('/')[0])

        return ips

    def check_host_valid_ip_from_name(self, host):
        """
        Util for assignment strategies.
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
        """
        return name + '-eth' + repr(port)

    def next_switch_id(self, base=1):
        """
        Compute the next switch id that can be used.
        """
        switch_ids = self.switch_ids()
        if len(switch_ids) == 0:
            return base
        else:
            return next_element(switch_ids, minimum=base)

    def next_port_num(self, node, node_ports, base=0):
        """
        Compute the next port number that can be used on the node.

        Arguments:
            node (string)    : name of the node
            node_ports (dict): port information as generated by self.node_ports
        """
        ports = node_ports.get(node)
        if ports is not None:
            ports_list = list(ports.keys())
            if len(ports_list) == 0:
                return base
            else:
                return next_element(ports_list, minimum=base)
        else:
            return base

    def auto_mac_address(self):
        """
        Generate a MAC address, different from anyone already generated.
        """
        mac = rand_mac()
        while mac in self.mac_addresses():
            mac = rand_mac()
        return mac

    def auto_ip_address(self):
        """
        Generate an IP address, different from anyone already generated.
        """
        ip_generator = self.ipv4_net.hosts()
        ip = str(next(ip_generator))
        prefixLen = str(self.ipv4_net.prefixlen)
        while ip in self.ip_addresses():
            ip = str(next(ip_generator))
        return ip + '/' + prefixLen

    def auto_assignment(self):
        """
        This function automatically assigns unique MACs and IPs to
        all the devices which requires them (i.e. L2 and L3 devices
        respectively). When a default interface is encountered, the
        respective device entry is updated.
        """
        for node1, node2, key, info in self.links(withKeys=True, withInfo=True):
            
            # Check if there are default interfaces
            def_intf1 = self.isDefaultIntf(node1, node2, key=key)
            def_intf2 = self.isDefaultIntf(node2, node1, key=key)

            # MACs
            addr1 = info.get('addr1')
            if addr1 is None:
                mac1 = self.auto_mac_address()
                self.setIntfMAC(node1, node2, mac1, key=key)
                if def_intf1:
                    self.setDefaultIntfMAC(node1, mac1)
            
            addr2 = info.get('addr2')
            if addr2 is None:
                mac2 = self.auto_mac_address()
                self.setIntfMAC(node2, node1, mac2, key=key)
                if def_intf2:
                    self.setDefaultIntfMAC(node2, mac2)

            # IPs
            if not self.isSwitch(node1):
                params1 = info.get('params1')
                if params1 is None:
                    ip1 = self.auto_ip_address()
                    self.setIntfIP(node1, node2, ip1, key=key)
                    if def_intf1:
                        self.setDefaultIntfIP(node1, ip1)
                else:
                    ip1 = params1.get('ip')
                    if ip1 is None:
                        ip1 = self.auto_ip_address()
                        self.setIntfIP(node1, node2, ip1, key=key)
                        if def_intf1:
                            self.setDefaultIntfIP(node1, ip1)

            if not self.isSwitch(node2):
                params2 = info.get('params2')
                if params2 is None:
                    ip2 = self.auto_ip_address()
                    self.setIntfIP(node2, node1, ip2, key=key)
                    if def_intf2:
                        self.setDefaultIntfIP(node2, ip2)
                else:
                    ip2 = params2.get('ip')
                    if ip2 is None:
                        ip2 = self.auto_ip_address()
                        self.setIntfIP(node2, node1, ip2, key=key)
                        if def_intf2:
                            self.setDefaultIntfIP(node2, ip2)

    def update_default_intfs(self):
        """
        If a default interface parameter has been set, set the corresponding
        link parameter.
        """
        for node, info in self.nodes(withInfo=True):
            def_mac = info.get('mac')
            node1, node2, key = self.getDefaultIntf(node)
            if def_mac is not None:
                self.setIntfMAC(node1, node2, def_mac, key=key)
            def_ip = info.get('ip')
            if def_ip is not None:
                self.setIntfIP(node1, node2, def_ip, key=key)

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

    def setTopo(self, topoClass=None, **kwargs):
        """
        Set the default topology class and options.
        This deletes all the informations (links, nodes) previously
        added.
        """
        if topoClass is not None:
            self.modules['topo']['class'] = topoClass
        self.modules['topo']['kwargs'].update(kwargs)
        # Topology is instantiated right at the beginning
        self.topo = self.module('topo')

    def setIPBase(self, ipBase):
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
        print('Port mapping:')
        node_ports = self.node_ports()
        for node1 in sorted(node_ports.keys()):
            print('{}: '.format(node1), end=' ')
            for port1, intf in node_ports[node1].items():
                print('{}:{}\t'.format(port1, intf[1]), end=' ')
            print()

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

    def enableCLI(self):
        """
        Enable the Mininet client.
        """
        self.cli_enabled = True

    def disableCLI(self):
        """
        Disable the Mininet client.
        """
        self.cli_enabled = False

    def startNetwork(self):
        """
        Once the topology has been created, create and start the Mininet network.
        If enabled, start the client.
        """
        debug('Updating default interfaces...\n')
        self.update_default_intfs()

        debug('Auto configuration of not configured interfaces...\n')
        self.auto_assignment()
        
        info('Compiling P4 files...\n')
        self.compile()
        output('P4 Files compiled!\n')

        self.printPortMapping()

        info('Creating network...\n')
        self.net = self.module('net', topo=self.topo, controller=None)
        output('Network created!\n')

        info('Starting network...\n')
        self.net.start()
        output('Network started!\n')

        info('Saving topology to disk...\n')
        self.save_topology()
        output('Topology saved to disk!\n')

        if self.cli_enabled:
            self.start_net_cli()
            # Stop right after the CLI is exited
            info('Stopping network...\n')
            self.net.stop()
            output('Network stopped!\n')

### Links
## Link setter
    def addLink(self, node1, node2, port1=None, port2=None,
                intfName1=None, intfName2=None, addr1=None,
                addr2=None, key=None, weight=1, **opts):
        """
        Add link between two nodes. If key is None, then the next
        ordinal number is used.

        Arguments:
            node1, node2 (string): nodes to link together
            port1, port2 (int)   : ports (optional)
            addr1, addr2 (string): MAC addresses
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
            weight (int)         : weight used to compute shortest paths
            opts                 : link options (optional)
        
        Returns:
           link info key
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
                    raise Exception('port {} already present on node {}.'.format(port1, node1))
        else:
            if self.isSwitch(node1):
                port1 = self.next_port_num(node1, node_ports, base=1)
            else:
                port1 = self.next_port_num(node1, node_ports)

        if port2 is not None:
            if node2 in node_ports.keys():
                if port2 in node_ports[node2].keys():
                    raise Exception('port {} already present on node {}.'.format(port2, node2))
        else:
            if self.isSwitch(node2):
                port2 = self.next_port_num(node2, node_ports, base=1)
            else:
                port2 = self.next_port_num(node2, node_ports)

        # Interface names
        if intfName1 is not None:
            if node1 in node_intfs.keys():
                if intfName1 in node_intfs[node1].keys():
                    raise Exception('interface {} already present on node {}.'.format(intfName1, node1))
        else:
            intfName1 = self.intf_name(node1, port1)

        if intfName2 is not None:
            if node2 in node_intfs.keys():
                if intfName2 in node_intfs[node2].keys():
                    raise Exception('interface {} already present on node {}.'.format(intfName2, node2))
        else:
            intfName2 = self.intf_name(node2, port2)

        # MACs
        if addr1 is not None:
            if addr1 in mac_addresses:
                warning('Node {}: MAC {} has been already assigned.\n'.format(node1, addr1))

        if addr2 is not None:
            if addr2 in mac_addresses or addr1 == addr2:
                warning('Node {}: MAC {} has been already assigned.\n'.format(node2, addr2))

        # IPs
        if self.isSwitch(node1):
            ip1 = opts.get('sw_ip1')
            if ip1 is not None:
                ip1 = ip1.split('/')[0]
                if ip1 in ip_addresses:
                    warning('Node {}: IP {} has been already assigned.\n'.format(node1, ip1))
        else:
            params1 = opts.get('params1')
            ip1 = None
            if params1 is not None:
                ip1 = params1.get('ip')
                if ip1 is not None:
                    ip1 = ip1.split('/')[0]
                    if ip1 in ip_addresses:
                        warning('Node {}: IP {} has been already assigned.\n'.format(node1, ip1))

        if self.isSwitch(node2):
            ip2 = opts.get('sw_ip2')
            if ip2 is not None:
                ip2 = ip2.split('/')[0]
                if ip2 in ip_addresses or ip1 == ip2:
                    warning('Node {}: IP {} has been already assigned.\n'.format(node2, ip2))
        else:
            params2 = opts.get('params2')
            ip2 = None
            if params2 is not None:
                ip2 = params2.get('ip')
                if ip2 is not None:
                    ip2 = ip2.split('/')[0]
                    if ip2 in ip_addresses or ip1 == ip2:
                        warning('Node {}: IP {} has been already assigned.\n'.format(node2, ip2))

        opts.setdefault('intf', TCIntf)
        return self.topo.addLink(node1, node2, port1=port1, port2=port2,
                                 intfName1=intfName1, intfName2=intfName2,
                                 addr1=addr1, addr2=addr2, key=key,
                                 weight=weight, **opts)

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
            link metadata dict
        """
        return self.topo.linkInfo(node1, node2, key=key)

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
            link metadata dict
        """
        info = self.popLink(node1, node2, key=key)
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
    def popLink(self, node1, node2, key=None):
        """
        Pop link. If key is None, then the link with the lowest
        key value is considered.

        Arguments:
            node1, node2 (string): nodes to link together
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)

        Returns:
            link metadata dict
        """
        link = self.getLink(node1, node2, key=key)
        self.topo.deleteLink(link['node1'], link['node2'], key=key)
        return link

## Method to check neighbors
    def areNeighbors(self, node1, node2):
        """
        Check whether two node are neighbors.

        Arguments:
            node1, node2 (string): names of the nodes

        Returns:
            True if node1 and node2 are neighbors, False else.
        """
        if node1 in self.topo.g.edge.keys():
            if node2 in self.topo.g.edge[node1].keys():
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
        return self.topo.links(sort, withKeys, withInfo)

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
        return self.topo.addNode(name, **opts)

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
        return self.topo.addHost(name, **opts)

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
        else:
            switch_id = self.next_switch_id()
            dpid = dpidToStr(switch_id)
            opts['dpid'] = dpid

        return self.topo.addSwitch(name, **opts)

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
        else:
            switch_id = self.next_switch_id()
            opts['device_id'] = switch_id

        opts.setdefault('cls', P4Switch)
        return self.topo.addP4Switch(name, **opts)

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
        switch_id = opts.get('device_id')
        if switch_id is not None:
            if switch_id in self.switch_ids():
                raise Exception('switch ID {} already in use.'.format(switch_id))
        else:
            switch_id = self.next_switch_id()
            opts['device_id'] = switch_id

        opts.setdefault('cls', P4RuntimeSwitch)
        return self.topo.addP4RuntimeSwitch(name, **opts)

## Node getter
    def getNode(self, name):
        """
        Get node information.

        Arguments:
            node (string): Mininet node name

        Returns:
            node metadata dict
        """
        return self.topo.nodeInfo(name)

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
        self.topo.deleteNode(name, remove_links=remove_links)
        return node

## Methods to check the node type
    def isNode(self, name):
        """
        Check if node exists.

        Arguments:
            node (string): node name

        Returns:
            True if node exists, else False (bool)
        """
        return self.topo.isNode(name)

    def isHost(self, name):
        """
        Check if node is a host.

        Arguments:
            node (string): Mininet node name

        Returns:
            True if node is a host, else False (bool)
        """
        return self.topo.isHost(name)

    def isSwitch(self, name):
        """
        Check if node is a switch.

        Arguments:
            node (string): Mininet node name

        Returns:
            True if node is a switch, else False (bool)
        """
        return self.topo.isSwitch(name)

    def isP4Switch(self, node):
        """
        Check if node is a P4 switch.

        Arguments:
            node (string): Mininet node name

        Returns:
            True if node is a P4 switch, else False (bool)
        """
        return self.topo.isP4Switch(node)

    def isP4RuntimeSwitch(self, node):
        """
        Check if node is a P4 runtime switch.

        Arguments:
            node (string): Mininet node name

        Returns:
            True if node is a P4 switch, else False (bool)
        """
        return self.topo.isP4RuntimeSwitch(node)

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
        Return nodes.
        
        Arguments:
           sort (bool): sort nodes alphabetically

        Returns:
           list of node names
        """
        return self.topo.nodes(sort=sort, withInfo=withInfo)

    def hosts(self, sort=True, withInfo=False):
        """
        Return hosts.
        
        Arguments:
           sort (bool): sort hosts alphabetically

        Returns:
           list of host names
        """
        return self.topo.hosts(sort=sort, withInfo=withInfo)

    def switches(self, sort=True, withInfo=False):
        """
        Return switches.

        Arguments:
           sort (bool): sort switches alphabetically

        Returns:
            list of switch names    
        """
        return self.topo.switches(sort=sort, withInfo=withInfo)

    def p4switches(self, sort=True, withInfo=False):
        """
        Return P4 switches.

        Arguments:
           sort (bool): sort P4 switches alphabetically

        Returns:
           list of P4 switch names
        """
        return self.topo.p4switches(sort)

    def p4rtswitches(self, sort=True, withInfo=False):
        """
        Return P4 runtime switches.

        Arguments:
           sort (bool): sort P4 runtime switches alphabetically

        Returns:
           list of P4 runtime switch names
        """
        return self.topo.p4rtswitches(sort=sort, withInfo=withInfo)

## Nodes
    def setDefaultIntfMAC(self, name, mac):
        """
        Set MAC address of the node's default interface.
        This method leads to predictable configuration only if
        the node has only one interface (not considering the
        loopback interface). For multihomed nodes, use the method
        self.setIntfMAC. This method overrides self.setIntfMAC.

        Arguments:
            name (string): name of the host
            mac (string) : MAC address to configure
        """
        if self.isNode(name):
            self.updateNode(name, mac=mac)
        else:
            raise Exception('{} does not exists.'.format(name))

    def setDefaultIntfIP(self, name, ip):
        """
        Set IP address of the node's default interface.
        This method leads to predictable configuration only if
        the node has only one interface (not considering the
        loopback interface). For multihomed nodes, use the method
        self.setIntfIP. This method overrides self.setIntfIP.

        Arguments:
            name (string): name of the host
            ip (string)  : IP address/mask to configure
        """
        if self.isNode(name):
            self.updateNode(name, ip=ip)
        else:
            raise Exception('{} does not exists.'.format(name))

# Hosts
    def setHostDefaultRoute(self, name, default_route):
        """
        Set the host's default route.

        Arguments:
            name (string)         : name of the host
            default_route (string): default route IP
        """
        if self.isHost(name):
            self.updateNode(name, defaultRoute='via {}'.format(default_route))
        else:
            raise Exception('{} is not a host.'.format(name))

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
            raise Exception('{} is not a switch.'.format(name))

## P4 Switches
    def setP4Source(self, name, p4_src):
        """
        Set p4 source for the switch and specify the options
        for the P4C compiler.

        Arguments:
            name (string)  : name of the P4 switch
            p4_src (string): path to the P4 file
            kwargs (string): other options to pass to P4C class
        """
        if self.isP4Switch(name):
            self.updateNode(name, p4_src=p4_src)
        else:
            raise Exception('{} is not a P4 switch.'.format(name))

    def setP4SwitchID(self, name, id):
        """
        Set P4 Switch ID.

        Arguments:
            name (string): name of the P4 switch
            id (int)     : P4 switch ID
        """
        if self.isP4Switch(name):
            self.updateNode(name, device_id=id)
        else:
            raise Exception('{} is not a P4 switch.'.format(name))

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
            raise Exception('{} is not a P4 switch.'.format(name))

    def enableDebugger(self, name):
        """
        Enable debugger for switch.

        Arguments:
            name (string): name of the P4 switch
        """
        if self.isP4Switch(name):
            self.updateNode(name, enable_debugger=True)
        else:
            raise Exception('{} is not a P4 switch.'.format(name))

    def disableDebugger(self, name):
        """
        Disable debugger for switch.

        Arguments:
            name (string): name of the P4 switch
        """            
        if self.isP4Switch(name):
            self.updateNode(name, enable_debugger=False)
        else:
            raise Exception('{} is not a P4 switch.'.format(name))

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

    def enableLog(self, name, log_dir='./log'):
        """
        Enable log for switch.

        Arguments:
            name (string)   : name of the P4 switch
            log_dir (string): where to save log files
        """            
        if self.isP4Switch(name):
            self.updateNode(name, log_enabled=True, log_dir=log_dir)
        else:
            raise Exception('{} is not a P4 switch.'.format(name))

    def disableLog(self, name):
        """
        Disable log for switch.

        Arguments:
            name (string): name of the P4 switch
        """            
        if self.isP4Switch(name):
            self.updateNode(name, log_enabled=False)
        else:
            raise Exception('{} is not a P4 switch.'.format(name))

    def enableLogAll(self, log_dir='./log'):
        """
        Enable log for all the switches.

        Arguments:
            log_dir (string): where to save log files
        """
        for switch in self.p4switches():
            self.enableLog(switch, log_dir=log_dir)

    def disableLogAll(self):
        """
        Disable log for all the switches.
        """
        for switch in self.p4switches():
            self.disableLog(switch)

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
            raise Exception('{} is not a P4 switch.'.format(name))

    def disablePcapDump(self, name):
        """
        Disable pcap dump for switch.

        Arguments:
            name (string): name of the P4 switch
        """
        if self.isP4Switch(name):
            self.updateNode(name, pcap_dump=False)
        else:
            raise Exception('{} is not a P4 switch.'.format(name))

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
            if not self.cpu_bridge:
                self.cpu_bridge = self.addSwitch('sw-cpu', cls=LinuxBridge, dpid='1000000000000000')
            self.addLink(name, self.cpu_bridge, intfName1='{}-cpu-eth0'.format(name), intfName2= '{}-cpu-eth1'.format(name), deleteIntfs=True)
            self.updateNode(name, cpu_port=True)
        else:
            raise Exception('{} is not a P4 switch.'.format(name))

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
            raise Exception('{} is not a P4 switch.'.format(name))

    def enableCpuPortAll(self):
        """
        Enable CPU port on all the P4 switches.
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
            raise Exception('{} is not a P4 runtime switch.'.format(name))

## Links
    def getDefaultIntf(self, node1):
        """
        Return the tuple (node1, node2, key) identifying the
        default interface.
        """
        if self.isNode(node1):
            node_ports = self.node_ports()
            return node_ports[node1][min(node_ports[node1].keys())]
        else:
            raise Exception('{} does not exist.'.format(node1))

    def isDefaultIntf(self, node1, node2, key=None):
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
        def_intf = self.getDefaultIntf(node1)
        _, key = self.topo._linkEntry(node1, node2, key=key)
        intf = (node1, node2, key)
        return def_intf == intf

    def setBw(self, node1, node2, bw, key=None):
        """
        Set link bandwidth. If key is None, then the link with the lowest
        key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            bw (float)           : bandwidth (in Mbps)
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        """
        if isinstance(bw, float):
            self.updateLink(node1, node2, key=key, bw=bw)
        else:
            raise TypeError('bw is not an integer.')

    def setDelay(self, node1, node2, delay, key=None):
        """
        Set link delay. If key is None, then the link with the lowest
        key value is considered.

        Arguments:
            node1, node2 (string): nodes linked together
            delay (int)          : transmission delay (in ms)
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        """
        if isinstance(delay, int):
            self.updateLink(node1, node2, key=key, delay=str(delay)+'ms')
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
        """
        if isinstance(loss, float):
            if loss <= 1 and loss >= 0:
                loss *= 100
                self.updateLink(node1, node2, key=key, loss=loss)
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
        """
        if isinstance(max_queue_size, int):
            self.updateLink(node1, node2, key=key, max_queue_size=max_queue_size)
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
        """
        if intfName not in self.node_intfs[node1].keys():
            self.updateLink(node1, node2, intfName1=intfName)
        else:
            raise Exception('interface {} already present on node {}'.format(intfName, node1))

    def setIntfIP(self, node1, node2, ip, key=None):
        """
        Set IP of node1's interface facing node2 with the specified key. If key is None,
        then the link with the lowest key value is considered. It is overridden by 
        self.setDefaultIntfIP for the default interface.

        Arguments:
            node1, node2 (string): nodes linked together
            ip (string)          : IP address/mask to configure
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        """
        if self.isSwitch(node1):
            # Set fake IP for switches
            self.updateLink(node1, node2, key=key, sw_ip1=ip)
        else:
            # Set real IP for other devices
            self.updateLink(node1, node2, key=key, params1={'ip': ip})

    def setIntfMAC(self, node1, node2, mac, key=None):
        """
        Set MAC of node1's interface facing node2 with the specified key. If key is None,
        then the link with the lowest key value is considered. It is overridden by 
        self.setDefaultIntfMAC for the default interface.

        Arguments:
            node1, node2 (string): nodes linked together
            mac (string)         : MAC address to configure
            key (int)            : id used to identify multiple edges which
                                   link two same nodes (optional)
        """
        self.updateLink(node1, node2, key=key, addr1=mac)

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
        """
        output('"l2" assignment strategy selected.\n')
        ip_generator = IPv4Network('10.0.0.0/16').hosts()
        reserved_ips = {}
        assigned_ips = set()

        for node in self.nodes():
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

        for node1, node2, key in self.links(withKeys=True):
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
                while host_ip in assigned_ips:
                    host_ip = str(next(ip_generator).compressed)
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

            self.setIntfMAC(host_name, direct_sw, host_mac)
            self.setIntfMAC(direct_sw, host_name, direct_sw_mac)

            self.setDefaultIntfIP(host_name, host_ip+'/16')
            self.setDefaultIntfMAC(host_name, host_mac)
