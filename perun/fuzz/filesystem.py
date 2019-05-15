""" Module contains functions dedicated for various operations over files and directories in 
file system, helpful for fuzzing process."""

__author__ = 'Matus Liscinsky'

import os
import os.path as path
import re

def get_corpus(workloads, pattern):
    """ Iteratively search for files to fill input corpus.

    :param list workloads: list of paths to sample files or directories of sample files
    :param str pattern: regular expression for filtering the workloads
    :return list: list of dictonaries, dictionary contains information about file
    """
    init_seeds = []

    try:
        filter_regexp = re.compile(pattern)
    except re.error:
        filter_regexp = re.compile("", flags=re.IGNORECASE)

    for w in workloads:
        if path.isdir(w) and os.access(w, os.R_OK):
            for root, _, files in os.walk(w):
                if files:
                    init_seeds.extend(
                        [{"path": path.abspath(root) + "/" + filename, "history": [], "cov": 0,
                          "deg_ratio": 0, "predecessor": None} for filename in files if filter_regexp.match(filename)])
        else:
            init_seeds.append({"path": path.abspath(w), "history": [],
                               "cov": 0, "deg_ratio": 0, "predecessor": None})
    return init_seeds

def move_file_to(filename, dir):
    """Useful function for moving file to the special output directory.

    :param str filename: path to a file
    :param str dir: path of destination directory, where file should be moved
    :return str: new path of the moved file
    """
    _, file = path.split(filename)
    os.rename(filename, dir + "/" + file)
    return dir + "/" + file

def make_output_dirs(output_dir, new_dirs):
    """Creates special output directories for diffs and mutations causing fault or hang.

    :param str output_dir: path to user-specified output directory
    :param list new_dirs: names of new directories
    :return list: paths to newly created directories 
    """
    dirs_dict = {}
    for dir_name in new_dirs:
        os.makedirs(output_dir + "/"+ dir_name, exist_ok=True) 
        dirs_dict[dir_name] = output_dir + "/"+ dir_name
    return dirs_dict
    # os.makedirs(output_dir + "/hangs", exist_ok=True)
    # os.makedirs(output_dir + "/faults", exist_ok=True)
    # os.makedirs(output_dir + "/diffs", exist_ok=True)
    # return output_dir + "/hangs", output_dir + "/faults", output_dir + "/diffs"

def del_temp_files(final_results, hangs, faults, output_dir):
    """ Deletes temporary files that are not positive results of fuzz testing

    :param list final_results: succesfully mutated files causing degradation, yield of testing
    :param list hangs: mutations that couses reaching timeout
    :param list faults: mutations that couses error
    :param str output_dir: path to directory, where fuzzed files are stored
    """

    print("Removing remaining mutations ...")
    waste = [mut for mut in final_results if mut not in hangs and mut not in faults]
    for mut in waste:
        if path.isfile(mut["path"]):
            os.remove(mut["path"])