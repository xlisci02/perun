""" Module contains functions dedicated for various operations over files and directories in 
file system, helpful for fuzzing process."""

__author__ = 'Matus Liscinsky'

import os
import os.path as path

def get_corpus(workloads):
    """ Iteratively search for files to fill input corpus.

    :param list workloads: list of paths to sample files or directories of sample files
    :return list: list of dictonaries, dictionary contains information about file
    """
    init_seeds = []

    for w in workloads:
        if path.isdir(w) and os.access(w, os.R_OK):
            for root, _, files in os.walk(w):
                if files:
                    init_seeds.extend(
                        [{"path": path.abspath(root) + "/" + filename, "history": [], "cov": 0,
                          "deg_ratio": 0, "predecessor": None} for filename in files])
        else:
            init_seeds.append({"path": path.abspath(w), "history": [],
                               "cov": 0, "deg_ratio": 0, "predecessor": None})
    return init_seeds

def move_file_to(filename, dir):
    """Useful function for moving file to the special output directory.

    :param str filename: path to a file
    :param str dir: path of destination directory, where file should be moved
    """
    _, file = path.split(filename)
    os.rename(filename, dir + "/" + file)


def make_output_dirs(output_dir):
    """Creates special output directories for diffs and mutations causing fault or hang.

    :param str output_dir: path to user-specified output directory
    :return tuple: paths to newly created directories 
    """
    os.makedirs(output_dir + "/hangs", exist_ok=True)
    os.makedirs(output_dir + "/faults", exist_ok=True)
    os.makedirs(output_dir + "/diffs", exist_ok=True)
    return output_dir + "/hangs", output_dir + "/faults", output_dir + "/diffs"

def del_temp_files(final_results, output_dir):
    """ Deletes temporary files that are not positive results of fuzz testing

    :param list final_results: succesfully mutated files causing degradation, yield of testing
    :param str output_dir: path to directory, where fuzzed files are stored
    """
    final_results_paths = [mutation["path"] for mutation in final_results]
    for file in os.listdir(output_dir):
        f = path.abspath(path.join(output_dir, file))
        if path.isfile(f) and f not in final_results_paths:
            os.remove(f)