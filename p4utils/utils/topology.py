import json
import copy
import pprint
from ipaddress import ip_interface
import networkx as nx

from p4utils.logger import log


class TopologyDB(object):
    """A convenience storage for auto-allocated mininet properties.

    Based on Olivie Tilmans TopologyDB from fibbing project:
    https://github.com/Fibbing/FibbingNode/blob/master/fibbingnode/misc/mininetlib/ipnet.py
    """
    def __init__(self, db=None, net=None, *args, **kwargs):
        super(TopologyDB, self).__init__(*args, **kwargs)
        """
        dict keyed by node name ->
            dict keyed by - properties -> val
                          - neighbor   -> interface properties
        """
        self._network = {}

        if net:
            self.parse_net(net)

        elif db:
            self.load(db)

        else:
            log.warning('Topology instantiated without any data')

    def __iter__(self):
        return self._network.iteritems()

    def __repr__(self):
        return pprint.pformat(self._network)

    def load(self, fpath):
        """Load a topology database from the given filename."""
        with open(fpath, 'r') as f:
            self._network = json.load(f)

    def save(self, fpath):
        """Save the topology database to the given filename."""
        with open(fpath, 'w') as f:
            json.dump(self._network, f)

    def _node(self, node):
        try:
            return self._network[node]
        except KeyError:
            raise ValueError('No node named %s in the network' % node)

    def __getitem__(self, item):
        return self._node(item)

    def _interface(self, node1, node2):
        return self._network[node1][node2]

    def interface(self, node1, node2):
        """Return the ip_interface for node1 facing node2."""
        return ip_interface(self._interface(node1, node2)['ip'])

    def interface_bandwidth(self, node1, node2):
        """Return the bandwidth capacity of the interface on node1 facing node2.
        If it is unlimited, return -1."""
        connected_to = self._network[node1]["interfaces_to_node"][node2]
        return self._interface(node1, connected_to)['bw']

    def subnet(self, node1, node2):
        """Return the subnet linking node1 and node2."""
        return self.interface(node1, node2).network.with_prefixlen

    def get_router_id(self, node):
        """Return the OSPF router id for router node."""
        if self._network[node]['type'] != 'router':
            raise TypeError('%s is not a router' % node)
        return self._network[node].get('routerid')

    def interface_ip(self, node, interface):
        """Return the IP address of a given interface and node."""
        connected_to = self._network[node]["interfaces_to_node"][interface]
        return self._interface(node, connected_to)['ip'].split("/")[0]

    def get_node_type(self, node):
        """Return the node type, e.g. 'switch' or 'host'."""
        return self._network[node]['type']

    def get_thrift_port(self, switch):
        """Return the Thrift port used to communicate with the P4 switch."""
        if self._network[switch]['type'] != 'switch':
            raise TypeError('%s is not a P4 switch' % switch)
        return self._network[switch]['thrift_port']

    def get_neighbors(self, node):
        return self._network[node]["interfaces_to_node"].itervalues()

    def get_interfaces(self, node):
        return self._network[node]["interfaces_to_node"].iterkeys()

    @staticmethod
    def other_intf(intf):
        """Get the interface on the other end of a link."""
        link = intf.link
        if link:
            if link.intf2 == intf:
                return link.intf1
            else:
                return link.intf2
        else:
            return None

    def parse_net(self, net):
        """Stores the content of the given network in the TopologyDB object."""
        for host in net.hosts:
            self.add_host(host)
        for switch in net.switches:
            self.add_switch(switch)
        if hasattr(net, "routers"):
            for router in net.routers:
                self.add_router(router)
        for controller in net.controllers:
            self.add_controller(controller)

    def _add_node(self, node, props):
        """Register a network node.

        Args:
            node: mininet.node.Node object
            props: properties (dictionary)
        """
        # does not add nodes that have inTopology set to false
        if 'inTopology' in node.params:
            if not node.params['inTopology']:
                return

        interfaces_to_nodes = {}
        interfaces_to_port = {}

        for port, port_id in node.ports.iteritems():
            interfaces_to_port[port.name] = port_id

        for itf in node.intfList():
            nh = TopologyDB.other_intf(itf)
            if not nh:
                continue  # Skip loopback and the likes

            # do not create connection
            # TODO: check who adds inTopology -> can this be removed?
            if 'inTopology' in nh.node.params:
                if not nh.node.params['inTopology']:
                    continue

            props[nh.node.name] = {
                'ip': '%s/%s' % (itf.ip, itf.prefixLen),
                'mac' : '%s' % (itf.mac),
                'intf': itf.name,
                'bw': itf.params.get('bw', -1),
                'weight': itf.params.get('weight', 1)
            }
            interfaces_to_nodes[itf.name] = nh.node.name

        # add an interface to node mapping
        props['interfaces_to_node'] = interfaces_to_nodes
        props['interfaces_to_port'] = interfaces_to_port
        self._network[node.name] = props

    def add_host(self, node):
        """Register a host."""
        attributes = {'type': 'host'}
        # node.gateway attribute only exists in my custom mininet
        if hasattr(node, "gateway"):
            attributes.update({'gateway': node.gateway})
        elif 'defaultRoute' in node.params:
            attributes.update({'gateway': node.params['defaultRoute']})
        self._add_node(node, attributes)

    def add_controller(self, node):
        """Register a controller."""
        self._add_node(node, {'type': 'controller'})

    def add_switch(self, node):
        """Register a switch."""
        self._add_node(node, {'type': 'switch', 'thrift_port': node.thrift_port})

    def add_router(self, node):
        """Register a router."""
        self._add_node(node, {'type': 'router', 'routerid': node.id})
        # We overwrite the router id using our own function.
        self._network[node.name]["routerid"] = self.get_router_id(node.name)


class NetworkGraph(nx.Graph):
    def __init__(self, topology_db, *args, **kwargs):
        """Initialize the NetworkGraph object.

        Args:
            topology_db: TopologyDB object
        """
        super(NetworkGraph, self).__init__(*args, **kwargs)

        self.topology_db = topology_db
        self = self.load_graph_from_db()

    def load_graph_from_db(self):
        for node, attributes in self.topology_db._original_network.iteritems():
            if node not in self.nodes():
                super(NetworkGraph, self).add_node(node)
                self.node[node]['type'] = self.topology_db.get_node_type(node)

                for neighbor in self.topology_db.get_neighbors(node):
                    if neighbor in self.nodes():
                        super(NetworkGraph, self).add_edge(node, neighbor)
        return self

    def add_edge(self, node1, node2):
        if node1 in self.node and node2 in self.node:
            super(NetworkGraph, self).add_edge(node1, node2)

    def add_node(self, node):
        super(NetworkGraph, self).add_node(node)
        self.node[node]['type'] = self.topology_db.get_node_type(node)

        for neighbor_node in self.topology_db.get_neighbors(node):
            if neighbor_node in self.node:
                super(NetworkGraph, self).add_edge(node, neighbor_node)

    def keep_only_switches(self):
        to_keep = [x for x in self.node if self.node[x]['type'] == 'switch']
        return self.subgraph(to_keep)

    def set_node_shape(self, node, shape):
        self.node[node]['node_shape'] = shape

    def set_node_color(self, node, color):
        self.node[node]['node_color'] = color

    def set_node_type_shape(self, type, shape):
        for node in self.node:
            if self.node[node]['type'] == type:
                self.set_node_shape(node, shape)

    def set_node_type_color(self, type, color):
        for node in self.node:
            if self.node[node]['type'] == type:
                self.set_node_color(node, color)

    # TODO: implement functionality
    def set_edge_weights(self, link_loads={}):
        pass

    def get_hosts(self):
        return [x for x in self.node if self.node[x]['type'] == 'host']

    def get_switches(self):
        return [x for x in self.node if self.node[x]["type"] == "switch"]

    def are_neighbors(self, node1, node2):
        """Returns True if node1 and node2 are neighbors, False otherwise."""
        return node1 in self.adj[node2]

    def get_neighbors(self, node):
        """Return all neighbors for a given node."""
        return self.adj[node].keys()

    def total_number_of_paths(self):
        total_paths = 0
        for host in self.get_hosts():
            for host_pair in self.get_hosts():
                if host == host_pair:
                    continue

                # compute the number of paths
                npaths = sum(1 for _ in nx.all_shortest_paths(self.graph, host, host_pair))
                total_paths += npaths

        return total_paths

    def get_paths_between_nodes(self, node1, node2):
        """Compute the paths between two nodes."""
        paths = nx.all_shortest_paths(self.graph, node1, node2)
        paths = [tuple(x) for x in paths]
        return paths


class Topology(TopologyDB):
    """
    Structure:
        self._network: topology database
        self._original_network: original topology database
        self.hosts_ip_mapping: dictionary with mapping from host name to IP address and vice versa
        self.network_graph: NetworkGraph object
    """
    def __init__(self, loadNetworkGraph=True, hostsMappings=True, *args, **kwargs):
        super(Topology, self).__init__(*args, **kwargs)

        # Save network startup state:
        # In case of link removal, we use this objects to remember the state of links and nodes
        # before the removal. This assumes that the topology will not be enhanced, i.e., links and
        # nodes can be removed and added, but new links or devices cannot be added.
        self._original_network = copy.deepcopy(self._network)

        try:
            if loadNetworkGraph:
                self.network_graph = NetworkGraph(self)
        except:
            import traceback
            traceback.print_exc()

        # Creates hosts to IP and IP to hosts mappings
        self.hosts_ip_mapping = {}
        if hostsMappings:
            self.create_hosts_ip_mapping()

    def create_hosts_ip_mapping(self):
        """Creates a mapping between host names and IP addresses, and vice versa."""
        self.hosts_ip_mapping = {}
        hosts = self.get_hosts()
        self.hosts_ip_mapping["ipToName"] = {}
        self.hosts_ip_mapping["nameToIp"] = {}
        for host in hosts:
            ip = self.interface_ip(host, self.get_host_first_interface(host).format(host))
            self.hosts_ip_mapping["ipToName"][ip] = host
            self.hosts_ip_mapping["nameToIp"][host] = ip

    def get_host_first_interface(self, name):
        return self._network[name]["interfaces_to_node"].keys()[0]

    def get_host_name(self, ip):
        """Returns the host name to an IP address."""
        name = self.hosts_ip_mapping.get("ipToName").get(ip)
        if name:
            return name
        raise InvalidIP("No host in the network has the IP {0}".format(ip))

    def get_host_ip(self, name):
        """Returns the IP to a host name."""
        ip = self.hosts_ip_mapping.get("nameToIp").get(name)
        if ip:
            return ip
        raise HostDoesNotExist("No host in the network has the name {0}".format(name))

    def are_neighbors(self, node1, node2):
        return self.network_graph.are_neighbors(node1, node2)

    def get_routers(self):
        "Gets the routers from the topologyDB"
        return {node: self._network[node] for node in self._network if self._network[node]["type"] == "router"}

    def get_hosts(self):
        "Gets the routers from the topologyDB"
        return {node: self._network[node] for node in self._network if self._network[node]["type"] == "host"}

    def get_switches(self):
        return {node: self._network[node] for node in self._network if self._network[node]["type"] == "switch"}



if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        db = sys.argv[1]
    else:
        db = "./topology.db"

    topo = Topology(db=db)
