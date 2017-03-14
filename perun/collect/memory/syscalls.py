"""This module provides simple wrappers over some linux command line tools"""
import os
import subprocess

__author__ = "Radim Podola"


def demangle(name):
    """
    Arguments:
        name(string): name to demangle

    Returns:
        string: demangled name
    """
    sys_call = ['c++filt']
    sys_call.append(name)
    output = subprocess.check_output(sys_call)

    return output.decode("utf-8").strip()


def get_extern_funcs(filename):
    """
    Arguments:
        filename(string): name of file to inspect for functions

    Returns:
        list: list of functions from dynamic section
    """
    sys_call = ['nm', '-D', '-C']
    sys_call.append(filename)
    output = subprocess.check_output(sys_call)
    output = output.decode("utf-8").splitlines()
    functions = []
    for line in output:
        line = line.strip()
        if line[0] == 'U':
            functions.append(line[2:])

    return functions


def address_to_line(ip, filename):
    """
    Arguments:
        ip(string): instruction pointer value
        filename(string): name of file to inspect for debug information

    Returns:
        list: list of two objects, 1st is the name of the source file,
              2nd is the line number
    """
    sys_call = ['addr2line']
    sys_call.append(ip)
    sys_call.append('-e')
    sys_call.append(filename)
    output = subprocess.check_output(sys_call)

    return output.decode("utf-8").strip().split(':')


def run(cmd, params, workload):
    """
    Arguments:
        cmd(string): binary file to profile
        params(string): executing arguments
        workload(string): file that has to be provided to binary

    Returns:
        int: return code of executed binary
    """
    pwd = os.path.dirname(os.path.abspath(__file__))
    sys_call = ('LD_PRELOAD="' + pwd + '/malloc.so" ' + cmd +
                ' ' + params + ' ' + workload)

    with open('ErrorCollectLog', 'w') as error_log:
        ret = subprocess.call(sys_call, shell=True, stderr=error_log)

    return ret


if __name__ == "__main__":
    pass
