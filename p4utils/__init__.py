class HostDoesNotExist(Exception):

    def __init__(self, node):
        self.message = "No host in the network has the name {0}" % node
        super(HostDoesNotExist, self).__init__('HostDoesNotExist: {0}'.format(self.message))

    def __str__(self):
        return self.message


class InvalidIP(Exception):

    def __init__(self, ip):
        super(InvalidIP, self).__init__('InvalidIP: {0}'.format(message))
        self.message = message

    def __str__(self):
        return self.message

FAILED_STATUS = 100
SUCCESS_STATUS = 200

DEFAULT_COMPILER = "p4c-bm2-ss -I /usr/local/share/p4c/p4include/"
DEFAULT_CLI = "simple_switch_CLI"
DEFAULT_SWITCH = "simple_switch"