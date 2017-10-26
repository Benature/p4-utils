from __future__ import print_function
from mininet import log
import sys, os
import subprocess

def last_modified(input_file, output_file):
    """

    :param input_file:
    :param output_file:
    :return: true if input_file is newer than output_file or if output file does not exist.
    """

    if (not os.path.exists(input_file)):
        log.error("input file does not exist")

    if (not os.path.exists(output_file)):
        return True

    return os.path.getmtime(input_file) >  os.path.getmtime(output_file)

def log_error(*items):
    print(*items, file=sys.stderr)

def run_command(command):
    log('>', command)
    return os.WEXITSTATUS(os.system(command))

def compile_p4_to_bmv2(config):

    compiler_args = []

    language = config.get("language", None)
    if language == 'p4-14':
        compiler_args.append('--p4v 14')
    elif language == 'p4-16':
        compiler_args.append('--p4v 16')
    else:
        log_error('Unknown language:', language)
        sys.exit(1)

    # Compile the program.
    program_file = config.get("program_file", None)
    if program_file:
        output_file = program_file.replace(".p4","") + '.json'
        compiler_args.append('"%s"' % program_file)
    compiler_args.append('-o "%s"' % output_file)

    rv = run_command('p4c-bm2-ss %s' % ' '.join(compiler_args))

    if rv != 0:
        log_error('Compile failed.')
        sys.exit(1)

    return output_file

def add_entries(thrift_port=9090, entries=None):
    assert entries

    if type(entries) == str:
        entries = entries.split("\n")

    print('\n'.join(entries))
    p = subprocess.Popen(['simple_switch_CLI', '--thrift-port', str(thrift_port)], stdin=subprocess.PIPE)
    p.communicate(input='\n'.join(entries))

def read_register(register, idx, thrift_port=9090):
    p = subprocess.Popen(['simple_switch_CLI', '--thrift-port', str(thrift_port)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate(input="register_read %s %d" % (register, idx))
    reg_val = filter(lambda l: ' %s[%d]' % (register, idx) in l, stdout.split('\n'))[0].split('= ', 1)[1]
    return long(reg_val)
