import re
from ipaddress import IPv4Network
from mininet.topo import Topo
from mininet.nodelib import LinuxBridge
from mininet.log import setLogLevel, info, output, debug, warning

from p4utils.utils.helper import *
from p4utils.mininetlib.node import *


class P4Topo(Topo):
    """Extension of the mininet topology class with P4 switches."""

    def addHost(self, name, **opts):
        """
        Add P4 host node to Mininet topology.

        Arguments:
            name (string): switch name
            opts (kwargs): switch options

        Returns:
            P4 host name (string)
        """
        if not opts and self.hopts:
            opts = self.hopts
        opts.update(isHost = True)
        return super().addHost(name, **opts)

    def isHost(self, node):
        """
        Check if node is a host.

        Arguments:
            node (string): node name

        Returns:
            True if node is a host, else False (bool)
        """
        return self.g.node[node].get('isHost', False)

    def addSwitch( self, name, **opts ):
        """
        Add switch to graph.
            name (string): switch name
            opts (kwargs): switch options

        Returns:
            switch name (string)
        """
        if not opts and self.sopts:
            opts = self.sopts
        opts.update(isSwitch = True)
        return super().addNode(name, **opts)

    def addP4Switch(self, name, **opts):
        """
        Add P4 switch node to Mininet topology.

        Arguments:
            name (string): switch name
            opts (kwargs): switch options

        Returns:
            P4 switch name (string)
        """
        if not opts and self.sopts:
            opts = self.sopts
        opts.update(isP4Switch = True)
        return self.addSwitch(name, **opts)

    def isP4Switch(self, node):
        """
        Check if node is a P4 switch.

        Arguments:
            node (string): node name

        Returns:
            True if node is a P4 switch, else False (bool)
        """
        return self.g.node[node].get('isP4Switch', False)

    def addP4RuntimeSwitch(self, name, **opts):
        """
        Add P4 runtime switch node to Mininet topology.

        Arguments:
            name (string): switch name
            opts (kwargs): switch options

        Returns:
            P4 switch name (string)
        """
        if not opts and self.sopts:
            opts = self.sopts
        opts.update(isP4Switch = True, isP4RuntimeSwitch = True)
        return self.addSwitch(name, **opts)

    def isP4RuntimeSwitch(self, node):
        """
        Check if node is a P4 runtime switch.

        Arguments:
            node (string): node name

        Returns:
            True if node is a P4 switch, else False (bool)
        """
        return self.g.node[node].get('isP4RuntimeSwitch', False)

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

class AppTopo(P4Topo):
    """
    Configuration class for P4Topo.

    Attributes:
        hosts (dict)                   : dictionary containing all the hosts
        switches (dict)                : dictionary containing all the switches
        links (dict)                   : dictionary containing all the links
        assignment_strategy (dict)     : IP and MAC addressing strategy
    """

    def __init__(self, hosts=None, switches=None, links=None, assignment_strategy="l2"):

        super().__init__()
        self.assignment_strategy = assignment_strategy
        self._hosts = hosts
        self._switches = switches
        self._links = links

        self.sw_port_mapping = {}
        self.hosts_info = {}
        self.already_assigned_ips = set()
        self.reserved_ips = {}
        self.make_topo()

    def make_topo(self):

        if self.assignment_strategy == "l2":
            self.l2_assignment_strategy()

        elif self.assignment_strategy == "mixed":
            self.mixed_assignment_strategy()

        elif self.assignment_strategy == "l3":
            self.l3_assignment_strategy()

        elif self.assignment_strategy == "manual":
            self.manual_assignment_strategy()
        # Fallback strategy
        else:
            warning('"{}" is not a valid assignment strategy, falling back to "mixed"\n'.format(self.assignment_strategy))
            self.mixed_assignment_strategy()

    def node_sorting(self, node):

        index = re.findall(r'\d+', node)
        if index:
            index = int(index[0])
        else:
            index = 0
            for i, c in enumerate(node):
                index += ord(c) * (255*(len(node)-i))
        return index

    def add_switches(self):
        sw_to_id = {}
        sw_id = 1

        for sw in self._switches.keys():
            id = re.findall(r'\d+', sw)
            if id and sw[0] == 's':
                id = int(id[0])
                sw_to_id[sw] = id

        for sw in self._switches.keys():
            id = sw_to_id.get(sw, None)
            if not id:
                while sw_id in list(sw_to_id.values()):
                    sw_id +=1
                id = sw_id
            
            sw_attributes = self._switches[sw]
            if issubclass(sw_attributes['cls'], P4Switch):
                if issubclass(sw_attributes['cls'], P4RuntimeSwitch):
                    self.addP4RuntimeSwitch(sw,
                                    device_id=id,
                                    **sw_attributes)
                else:
                    self.addP4Switch(sw,
                                    device_id=id,
                                    **sw_attributes)
            else:
                self.addSwitch(sw,
                               device_id=id,
                               **sw_attributes)

            sw_to_id[sw] = id

        return sw_to_id

    def is_host_link(self, link):

        return link[0] in self._hosts or link[1] in self._hosts

    def get_host_position(self, link):

        return 0 if link[0] in self._hosts else 1

    def get_sw_position(self, link):

        return 0 if link[0] in self._switches else 1

    def check_host_valid_ip_from_name(self, host):

        valid = True
        if host[0] == 'h':
            try:
                int(host[1:])
            except:
                valid = False
        else:
            valid = False
        
        return valid

    def add_cpu_port(self):
        add_bridge = True # We use the bridge but at the same time we use the bug it has so the interfaces are not added to it, but at least we can clean easily thanks to that.
        for switch, params in self._switches.items():
            if self.g.node[switch].get('isP4Switch', False):
                if params['cpu_port']:
                    if add_bridge:
                        sw = self.addSwitch('sw-cpu', cls=LinuxBridge, dpid='1000000000000000')
                        self.addSwitchPort(switch, sw)
                        add_bridge = False
                    self.addLink(switch, sw, intfName1='{}-cpu-eth0'.format(switch), intfName2= '{}-cpu-eth1'.format(switch), deleteIntfs=True)

    def l2_assignment_strategy(self):

        info('"l2" assignment strategy selected.\n')
        
        self.add_switches()
        ip_generator = IPv4Network('10.0.0.0/16').hosts()

        #add links and configure them: ips, macs, etc
        #assumes hosts are connected to one switch only

        #reserve ips for normal hosts
        for host_name in self._hosts:
            if self.check_host_valid_ip_from_name(host_name):
                host_num = int(host_name[1:])
                upper_byte = (host_num & 0xff00) >> 8
                lower_byte = (host_num & 0x00ff)
                host_ip = '10.0.%d.%d' % (upper_byte, lower_byte)
                self.reserved_ips[host_name] = host_ip

        for link in self._links:

            if self.is_host_link(link):
                host_name = link[self.get_host_position(link)]
                direct_sw = link[self.get_sw_position(link)]

                if self.check_host_valid_ip_from_name(host_name):
                    host_ip = self.reserved_ips[host_name]
                    #we check if for some reason the ip was already given by the ip_generator. This
                    #can only happen if the host naming is not <h_x>
                    #this should not be possible anymore since we reserve ips for h_x hosts
                    while host_ip in self.already_assigned_ips:
                        host_ip = str(next(ip_generator).compressed)
                    self.already_assigned_ips.add(host_ip)
                else:
                    host_ip = next(ip_generator).compressed
                    #we check if for some reason the ip was already given by the ip_generator. This
                    #can only happen if the host naming is not <h_x>
                    while host_ip in self.already_assigned_ips or host_ip in list(self.reserved_ips.values()):
                        host_ip = str(next(ip_generator).compressed)
                    self.already_assigned_ips.add(host_ip)

                host_mac = ip_address_to_mac(host_ip) % (0)
                direct_sw_mac = ip_address_to_mac(host_ip) % (1)

                link_ops = link[2]
                link_ops['addr1'] = host_mac
                link_ops['addr2'] = direct_sw_mac

                host_ops = self._hosts[host_name]
                host_ops['ip'] = host_ip + '/16'
                host_ops['mac'] = host_mac

                self.addHost(host_name, **host_ops)
                self.addLink(host_name, direct_sw, **link_ops)
                self.addSwitchPort(direct_sw, host_name)
                self.hosts_info[host_name] = {'sw': direct_sw, 'ip': host_ip, 'mac': host_mac, 'mask': 24}

            #switch to switch link
            else:
                self.addLink(link[0], link[1], **link[2])
                self.addSwitchPort(link[0], link[1])
                self.addSwitchPort(link[1], link[0])

        self.add_cpu_port()
        self.printPortMapping()

    def mixed_assignment_strategy(self):

        info('"mixed" assignment strategy selected.\n')

        sw_to_id = self.add_switches()
        sw_to_generator = {}
        #change the id to a generator for that subnet
        for sw, sw_id in list(sw_to_id.items()):
            upper_bytex = (sw_id & 0xff00) >> 8
            lower_bytex = (sw_id & 0x00ff)
            net = '10.%d.%d.0/24' % (upper_bytex, lower_bytex)
            sw_to_generator[sw] = IPv4Network(str(net)).hosts()

        #reserve ips
        for link in self._links:
            if self.is_host_link(link):
                host_name = link[self.get_host_position(link)]
                direct_sw = link[self.get_sw_position(link)]

                sw_id = sw_to_id[direct_sw]
                upper_byte = (sw_id & 0xff00) >> 8
                lower_byte = (sw_id & 0x00ff)
                if self.check_host_valid_ip_from_name(host_name):
                    host_num = int(host_name[1:])
                    assert host_num < 254
                    host_ip = '10.%d.%d.%d' % (upper_byte, lower_byte, host_num)
                    self.reserved_ips[host_name] = host_ip

        #add links and configure them: ips, macs, etc
        #assumes hosts are connected to one switch only
        for link in self._links:

            if self.is_host_link(link):
                host_name = link[self.get_host_position(link)]
                direct_sw = link[self.get_sw_position(link)]

                sw_id = sw_to_id[direct_sw]
                upper_byte = (sw_id & 0xff00) >> 8
                lower_byte = (sw_id & 0x00ff)
                ip_generator = sw_to_generator[direct_sw]

                if self.check_host_valid_ip_from_name(host_name):
                    host_ip = self.reserved_ips[host_name]
                    #we check if for some reason the ip was already given by the ip_generator. This
                    #can only happen if the host naming is not <h_x>
                    while host_ip in self.already_assigned_ips:
                        host_ip = str(next(ip_generator).compressed)
                    self.already_assigned_ips.add(host_ip)
                else:
                    host_ip = next(ip_generator).compressed
                    #we check if for some reason the ip was already given by the ip_generator. This
                    #can only happen if the host naming is not <h_x>
                    while host_ip in self.already_assigned_ips or host_ip in list(self.reserved_ips.values()):
                        host_ip = str(next(ip_generator).compressed)
                    self.already_assigned_ips.add(host_ip)

                host_gw = '10.%d.%d.254' % (upper_byte, lower_byte)
                host_mac = ip_address_to_mac(host_ip) % (0)
                direct_sw_mac = ip_address_to_mac(host_ip) % (1)

                host_ops = self._hosts[host_name]
                host_ops['ip'] = host_ip + '/24'
                host_ops['mac'] = host_mac
                host_ops['defaultRoute'] = 'via {}'.format(host_gw)

                link_ops = link[2]
                link_ops['addr1'] = host_mac
                link_ops['addr2'] = direct_sw_mac

                self.addHost(host_name, **host_ops)
                self.addLink(host_name, direct_sw, **link_ops)
                self.addSwitchPort(direct_sw, host_name)
                self.hosts_info[host_name] = {'sw': direct_sw, 'ip': host_ip, 'mac': host_mac, 'mask': 24}

            #switch to switch link
            else:
                self.addLink(link[0], link[1], **link[2])
                self.addSwitchPort(link[0], link[1])
                self.addSwitchPort(link[1], link[0])

        self.add_cpu_port()
        self.printPortMapping()

    def l3_assignment_strategy(self):

        info('"l3" assignment strategy selected.\n')

        sw_to_id = self.add_switches()
        sw_to_next_available_host_id = {}
        for sw in list(sw_to_id.keys()):
            sw_to_next_available_host_id[sw] = 1

        #reserve ips for normal named hosts and switches
        for link in self._links:
            if self.is_host_link(link):
                host_name = link[self.get_host_position(link)]
                if self.check_host_valid_ip_from_name(host_name):

                    direct_sw = link[self.get_sw_position(link)]
                    sw_id = sw_to_id[direct_sw]
                    host_num = int(host_name[1:])
                    assert host_num < 254
                    host_ip = '10.%d.%d.2' % (sw_id, host_num)
                    self.reserved_ips[host_name] = host_ip

        # add links and configure them: ips, macs, etc
        # assumes hosts are connected to one switch only
        for link in self._links:

            if self.is_host_link(link):
                host_name = link[self.get_host_position(link)]
                direct_sw = link[self.get_sw_position(link)]

                sw_id = sw_to_id[direct_sw]
                assert sw_id < 254

                if self.check_host_valid_ip_from_name(host_name):
                    host_num = int(host_name[1:])
                    assert host_num < 254
                    host_ip = '10.%d.%d.2' % (sw_id, host_num)
                    host_gw = '10.%d.%d.1' % (sw_id, host_num)

                else:
                    host_num = sw_to_next_available_host_id[direct_sw]
                    while ('10.%d.%d.2' % (sw_id, host_num)) in list(self.reserved_ips.values()):
                        host_num +=1
                    assert host_num < 254
                    host_ip = '10.%d.%d.2' % (sw_id, host_num)
                    host_gw = '10.%d.%d.1' % (sw_id, host_num)

                host_mac = ip_address_to_mac(host_ip) % (0)
                direct_sw_mac = ip_address_to_mac(host_ip) % (1)

                host_ops = self._hosts[host_name]
                host_ops['ip'] = host_ip + '/24'
                host_ops['mac'] = host_mac
                host_ops['defaultRoute'] = 'via {}'.format(host_gw)

                link_ops = link[2]
                link_ops['addr1'] = host_mac
                link_ops['addr2'] = direct_sw_mac
                link_ops.setdefault('params2', {})
                link_ops['sw_ip2'] = host_gw + '/24' # Fake IP since it is a switch interface

                self.addHost(host_name, **host_ops)
                self.addLink(host_name, direct_sw, **link_ops)
                self.addSwitchPort(direct_sw, host_name)
                self.hosts_info[host_name] = {'sw': direct_sw, 'ip': host_ip, 'mac': host_mac, 'mask': 24}

            # switch to switch link
            else:
                sw1_name = link[0]
                sw2_name = link[1]

                sw1_ip = '20.%d.%d.1' % (sw_to_id[sw1_name], sw_to_id[sw2_name])
                sw2_ip = '20.%d.%d.2' % (sw_to_id[sw1_name], sw_to_id[sw2_name])

                link_ops = link[2]
                link_ops.setdefault('params1', {})
                link_ops.setdefault('params2', {})
                link_ops['sw_ip1'] = sw1_ip+'/24' # Fake IP since it is a switch interface
                link_ops['sw_ip2'] = sw2_ip+'/24' # Fake IP since it is a switch interface

                self.addLink(link[0], link[1], **link_ops)
                self.addSwitchPort(link[0], link[1])
                self.addSwitchPort(link[1], link[0])

        self.add_cpu_port()
        self.printPortMapping()

    def manual_assignment_strategy(self):

        info('"manual" assignment strategy selected.\n')

        #adds switches to the topology and sets an ID
        sw_to_id = self.add_switches()

        # add links and configure them: ips, macs, etc
        # assumes hosts are connected to one switch only
        for link in self._links:

            if self.is_host_link(link):

                host_name = link[self.get_host_position(link)]
                direct_sw = link[self.get_sw_position(link)]

                sw_id = sw_to_id[direct_sw]
                assert sw_id < 254

                #host_gw = None
                host_mac = None

                host_ops = self._hosts[host_name]
                assert host_ops['ip'], 'Host does not have an IP assigned or "auto" assignment'

                if host_ops['ip'] == 'auto':
                    host_ops['ip'] = None
                    host_ops['auto'] = True

                if host_ops['ip'] and not '/' in host_ops['ip']:
                    host_ops['ip'] += '/24'

                # Get mac address from ip address
                if host_ops['ip'] and not host_ops['mac']:
                    host_mac = ip_address_to_mac(host_ops['ip']) % (0)
                    host_ops['mac'] = host_mac

                self.addHost(host_name, **host_ops)

                link_ops = link[2]
                link_ops['addr1'] = host_mac

                self.addLink(host_name, direct_sw, **link_ops)
                self.addSwitchPort(direct_sw, host_name)
                plane_ip = host_ip.split("/")[0] if host_ip else None
                self.hosts_info[host_name] = {"sw": direct_sw, "ip":  plane_ip, "mac": host_mac, "mask": 24}

            # switch to switch link
            else:
                link_ops = link[2]
                # Get mac address from ip address
                if link_ops['sw_ip1'] and not link_ops['addr1']:
                    link_ops['addr1'] = ip_address_to_mac(link_ops['sw_ip1']) % (1)
                if link_ops['sw_ip2'] and not link_ops['addr2']:
                    link_ops['addr2'] = ip_address_to_mac(link_ops['sw_ip2']) % (1)

                self.addLink(link[0], link[1], **link_ops)
                self.addSwitchPort(link[0], link[1])
                self.addSwitchPort(link[1], link[0])

        self.add_cpu_port()
        self.printPortMapping()

    def addSwitchPort(self, sw, node2):
        if sw not in self.sw_port_mapping:
            self.sw_port_mapping[sw] = []
        portno = len(self.sw_port_mapping[sw]) + 1
        self.sw_port_mapping[sw].append((portno, node2))

    def printPortMapping(self):
        print('Switch port mapping:')
        for sw in sorted(self.sw_port_mapping.keys()):
            print('{}: '.format(sw), end=' ')
            for portno, node2 in self.sw_port_mapping[sw]:
                print('{}:{}\t'.format(portno, node2), end=' ')
            print()

#AppTopo Alias
AppTopoStrategies = AppTopo