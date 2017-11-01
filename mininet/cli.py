from mininet.cli import CLI
from mininet.log import info, output, error, warn, debug
from utils import *

class P4CLI(CLI):

    def __init__(self,*args,**kwargs):

        self.config = kwargs.get("config", None)
        if not self.config:
            log("Any configuration was given to the CLI and therefore p4 functionalities are disabled")
        else:
            #normal CLI is not  any config parameter
            kwargs.__delitem__("config")

        CLI.__init__(self,*args,**kwargs)


    def do_reload_conf(self, line=""):
        pass

    def do_p4switch_stop(self,line=""):

        """stop simple switch from switch namespace"""
        switch_name = line.split()
        if not switch_name or len(switch_name) > 1:
            error('usage: p4switch_stop <p4switch name>\n')
        else:
            switch_name = switch_name[0]
            if switch_name not in self.mn:
                error("p4switch %s not in the network\n" % switch_name)
            else:
                p4switch = self.mn[switch_name]
                p4switch.stop_p4switch()

    def do_p4switch_start(self,line=""):

        #import ipdb
        #ipdb.set_trace()

        """start again simple switch from namespace"""
        args = line.split()

        #check args validity
        if len(args) > 5:
            error('usage: p4switch_start <p4switch name> [--p4source <path>] [--cmd path]\n')
            return

        switch_name = args[0]
        if switch_name not in self.mn:
            error('usage: p4switch_start <p4switch name> [--p4source <path>] [--cmd path]\n')
            return

        p4switch = self.mn[switch_name]

        #check if switch is running
        if p4switch.check_switch_started():
            error('P4 Switch already running, stop first: p4switch_stop %s \n' % switch_name)

        try:
            p4source_path = args[args.index("--p4source")+1]
            #check if file exists
            if not os.path.exists(p4source_path):
                warn('File Error: p4source does not exist %s\n' % p4source_path)
                return

        except ValueError:
            p4source_path = self.config["targets"]["multiswitch"]["switches"][switch_name].get("program", False)
            if not p4source_path:
                p4source_path = self.config["program"]


        #compile if needed
        output_file = p4source_path.replace(".p4", "") + ".json"
        compile_flag = last_modified(p4source_path, output_file)
        if compile_flag:
            language = self.config.get("language",None)
            if not language:
                language = "p4-16"
            compile_config = {"language": language, "program_file": p4source_path}
            #compile program
            compile_p4_to_bmv2(compile_config)
            #update output program
            p4switch.json_path = output_file

        #start switch
        p4switch.start_p4switch()

        #load command entries
        try:
            commands_path = args[args.index("--cmd")+1]
            #check if file exists
            if not os.path.exists(commands_path):
                error('File Error: commands does not exist %s\n' % commands_path)
                return

        except ValueError:
            commands_path= self.config["targets"]["multiswitch"]["switches"][switch_name]["entries"]

        entries = read_entries(commands_path)

        #add entries
        add_entries(p4switch.thrift_port, entries)

    def do_printSwitches(self, line=""):
        for sw in self.mn.p4switches:
            print sw.name


    def do_p4switches_reboot(self, line=""):
        """reboot all p4 switches with new program: if you provide a p4 source code or cmd all switches
        will have the same code.
        """
        for sw in self.mn.p4switches:
            switch_name = sw.name
            self.do_p4switch_stop(line=switch_name)

            line = switch_name + " " +line
            self.do_p4switch_start(line=line)


    def do_p4switch_reboot(self,line=""):

        """reboot a p4 switch with new program"""
        if not line or len(line.split()) > 1:
            error('usage: p4switch_stop <p4switch name>\n')
        else:
            switch_name = line.split[0]
            self.do_p4switch_stop(line=switch_name)
            self.do_p4switch_start(line=line)
