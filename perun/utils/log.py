"""Set of helper function for logging and printing warnings or errors"""

import builtins
import collections
import operator
import logging
import sys
import itertools
import io
import pydoc
import functools

import termcolor

from perun.utils.helpers import first_index_of_attr
from perun.utils.decorators import static_variables
from perun.utils.helpers import COLLECT_PHASE_ATTRS, COLLECT_PHASE_ATTRS_HIGH, CHANGE_COLOURS, \
    CHANGE_STRINGS, DEGRADATION_ICON, OPTIMIZATION_ICON, CHANGE_CMD_COLOUR, CHANGE_TYPE_COLOURS
from perun.utils.structs import PerformanceChange

__author__ = 'Tomas Fiedor'
VERBOSITY = 0

# Enum of verbosity levels
VERBOSE_DEBUG = 2
VERBOSE_INFO = 1
VERBOSE_RELEASE = 0

SUPPRESS_WARNINGS = False
SUPPRESS_PAGING = True

# set the logging for the perun
logging.basicConfig(filename='perun.log', level=logging.DEBUG)


def is_verbose_enough(verbosity_peak):
    """Tests if the current verbosity of the log is enough

    :param int verbosity_peak: peak of the verbosity we are testing
    :return: true if the verbosity is enough
    """
    return VERBOSITY >= verbosity_peak


def page_function_if(func, paging_switch):
    """Adds paging of the output to standard stream

    This decorator serves as a pager for long outputs to the standard stream. As a pager currently,
    'less -R' is used. Further extension to Windows and weird terminals without less -R is planned.

    Fixme: Try the paging on windows
    Fixme: Uhm, what about standard error?

    Note that this should be used by itself but by @paged_function() decorator

    :param function func: original wrapped function that will be paged
    :param bool paging_switch: external paging condition, if set to tru the function will not be
        paged
    """
    def wrapper(*args, **kwargs):
        """Wrapper for the original function whose output will be paged

        :param list args: list of positional arguments for original function
        :param dict kwargs: dictionary of key:value arguments for original function
        """
        if SUPPRESS_PAGING or not paging_switch:
            return func(*args, **kwargs)

        # Replace the original standard output with string buffer
        sys.stdout = io.StringIO()

        # Run the original input with positional and key-value arguments
        result = func(*args, **kwargs)

        # Read the caught standard output and then restore the original stream
        sys.stdout.seek(0)
        stdout_str = "".join(sys.stdout.readlines())
        sys.stdout = sys.__stdout__
        pydoc.pipepager(stdout_str, "less -R")

        return result
    return wrapper


def paged_function(paging_switch):
    """The wrapper of the ``page_function_if`` to serve as a decorator, which partially applies the
    paging_switch. This way the function will accept only the function as parameter and can serve as
    decorator.

    :param bool paging_switch: external paging condition, if set to tru the function will not be
    :return: wrapped paged function
    """
    return functools.partial(page_function_if, paging_switch=paging_switch)


def _log_msg(stream, msg, msg_verbosity, log_level):
    """
    If the @p msg_verbosity is smaller than the set verbosity of the logging
    module, the @p msg is printed to the log with the given @p log_level

    Attributes:
        stream(function): streaming function of the type void f(log_level, msg)
        msg(str): message to be logged if certain verbosity is set
        msg_verbosity(int): level of the verbosity of the message
        log_level(int): log level of the message
    """
    if msg_verbosity <= VERBOSITY:
        stream(log_level, msg)


def msg_to_stdout(message, msg_verbosity, log_level=logging.INFO):
    """
    Helper function for the log_msg, prints the @p msg to the stdout,
    if the @p msg_verbosity is smaller or equal to actual verbosity.
    """
    _log_msg(lambda lvl, msg: print("{}".format(msg)), message, msg_verbosity, log_level)


def msg_to_file(msg, msg_verbosity, log_level=logging.INFO):
    """
    Helper function for the log_msg, prints the @p msg to the log,
    if the @p msg_verbosity is smaller or equal to actual verbosity
    """
    _log_msg(logging.log, msg, msg_verbosity, log_level)


def info(msg):
    """
    :param str msg: info message that will be printed only when there is at least lvl1 verbosity
    """
    print("info: {}".format(msg))


def quiet_info(msg):
    """
    :param str msg: info message to the stream that will be always shown
    """
    msg_to_stdout(msg, VERBOSE_RELEASE)


def error(msg, recoverable=False):
    """
    :param str msg: error message printe to standard output
    :param bool recoverable: whether we can recover from the error
    """
    print(termcolor.colored("fatal: {}".format(msg), 'red'), file=sys.stderr)

    # If we cannot recover from this error, we end
    if not recoverable:
        exit(1)


def warn(msg):
    """
    :param str msg: warn message printed to standard output
    """
    if not SUPPRESS_WARNINGS:
        print("warn: {}".format(msg))


def print_current_phase(phase_msg, phase_unit, phase_colour):
    """Print helper coloured message for the current phase

    :param str phase_msg: message that will be printed to the output
    :param str phase_unit: additional parameter that is passed to the phase_msg
    :param str phase_colour: phase colour defined in helpers.py
    """
    print(termcolor.colored(
        phase_msg.format(
            termcolor.colored(phase_unit, attrs=COLLECT_PHASE_ATTRS_HIGH)
        ), phase_colour, attrs=COLLECT_PHASE_ATTRS
    ))


@static_variables(current_job=1)
def print_job_progress(overall_jobs):
    """Print the tag with the percent of the jobs currently done

    :param int overall_jobs: overall number of jobs to be done
    """
    percentage_done = round((print_job_progress.current_job / overall_jobs) * 100)
    print("[{}%] ".format(
        str(percentage_done).rjust(3, ' ')
    ), end='')
    print_job_progress.current_job += 1


def cprint(string, colour, attrs=None, flush=True):
    """Wrapper over coloured print without adding new line

    :param str string: string that is printed with colours
    :param str colour: colour that will be used to colour the string
    :param list attrs: list of additional attributes for the colouring
    :param bool flush: set True to immediately perform print operation
    """
    attrs = attrs or []
    print(termcolor.colored(string, colour, attrs=attrs), end='', flush=flush)


def cprintln(string, colour, attrs=None, ending='\n'):
    """Wrapper over coloured print with added new line or other ending

    :param str string: string that is printed with colours and newline
    :param str colour: colour that will be used to colour the stirng
    :param list attrs: list of additional attributes for the colouring
    :param str ending: ending of the string, be default new line
    """
    attrs = attrs or []
    print(termcolor.colored(string, colour, attrs=attrs), end=ending)


def done(ending='\n'):
    """Helper function that will print green done to the terminal

    :param str ending: end of the string, by default new line
    """
    print('[', end='')
    cprint("DONE", 'green', attrs=['bold'])
    print(']', end=ending)


def failed(ending='\n'):
    """
    :param str ending: end of the string, by default new line
    """
    print('[', end='')
    cprint("FAILED", 'red', attrs=['bold'])
    print(']', end=ending)


def count_degradations_per_group(degradation_list):
    """Counts the number of optimizations and degradations

    :param list degradation_list: list of tuples of (degradation info, cmdstr, minor version)
    :return: dictionary mapping change strings to its counts
    """
    # Get only degradation results
    changes = map(operator.attrgetter('result'), map(operator.itemgetter(0), degradation_list))
    # Transform the enum into a string
    change_names = list(map(operator.attrgetter('name'), changes))
    counts = dict(collections.Counter(change_names))
    return counts


def get_degradation_change_colours(degradation_result):
    """Returns the tuple of two colours w.r.t degradation results.

    If the change was optimization (or possible optimization) then we print the first model as
    red and the other by green (since we went from better to worse model). On the other hand if the
    change was degradation, then we print the first one green (was better) and the other as red
    (is now worse). Otherwise (for Unknown and no change) we keep the stuff yellow, though this
    is not used at all

    :param PerformanceChange degradation_result: change of the performance
    :returns: tuple of (from model string colour, to model string colour)
    """
    if degradation_result in (
            PerformanceChange.Optimization, PerformanceChange.MaybeOptimization
    ):
        return 'red', 'green'
    elif degradation_result in (
            PerformanceChange.Degradation, PerformanceChange.MaybeDegradation
    ):
        return 'green', 'red'
    else:
        return 'yellow', 'yellow'


def print_short_summary_of_degradations(degradation_list):
    """Prints a short string representing the summary of the found changes.

    This prints a short statistic of found degradations and short summary string.

    :param list degradation_list:
        list of tuples (degradation info, command string, source minor version)
    """
    counts = count_degradations_per_group(degradation_list)

    print_short_change_string(counts)
    optimization_count = counts.get('Optimization', 0)
    degradation_count = counts.get('Degradation', 0)
    print("{} optimization{}({}), {} degradation{}({})".format(
        optimization_count, "s" if optimization_count != 1 else "", OPTIMIZATION_ICON,
        degradation_count, "s" if degradation_count != 1 else "", DEGRADATION_ICON
    ))


def change_counts_to_string(counts, width=0):
    """Transforms the counts to a single coloured string

    :param dict counts: dictionary with counts of degradations
    :param int width: width of the string justified to left
    :return: string representing the counts of found changes
    """
    width = max(width - counts.get('Optimization', 0) - counts.get('Degradation', 0), 0)
    change_str = termcolor.colored(
        str(OPTIMIZATION_ICON*counts.get('Optimization', 0)),
        CHANGE_COLOURS[PerformanceChange.Optimization],
        attrs=['bold']
    )
    change_str += termcolor.colored(
        str(DEGRADATION_ICON*counts.get('Degradation', 0)),
        CHANGE_COLOURS[PerformanceChange.Degradation],
        attrs=['bold']
    )
    return change_str + width*' '


def print_short_change_string(counts):
    """Prints short string representing a summary of the given degradation list.

    This prints a short string of form representing a summary of found optimizations (+) and
    degradations (-) in the given degradation list. Uncertain optimizations and degradations
    are omitted. The string can e.g. look as follows:

    ++++-----

    :param dict counts: dictionary mapping found string changes into their counts
    """
    overall_changes = sum(counts.values())
    print("{} change{}".format(
        overall_changes, "s" if overall_changes != 1 else ""
    ), end='')
    if overall_changes > 0:
        change_string = change_counts_to_string(counts)
        print(" | {}".format(change_string), end='')
    print("")


def print_list_of_degradations(degradation_list):
    """Prints list of found degradations grouped by location

    Currently this is hardcoded and prints the list of degradations as follows:

    at {loc}:
      {result} from {from} -> to {to}

    :param list degradation_list: list of found degradations
    """
    def keygetter(item):
        """Returns the location of the degradation from the tuple

        :param tuple item: tuple of (degradation result, cmd string, source minor version)
        :return: location of the degradation used for grouping
        """
        return item[0].location

    # Group by location
    degradation_list.sort(key=keygetter)
    for location, changes in itertools.groupby(degradation_list, keygetter):
        # Print the location
        print("at", end='')
        cprint(' {}'.format(location), 'white', attrs=['bold'])
        print(":")
        # Iterate and print all of the infos
        for deg_info, cmd, __ in changes:
            print('\u2514 ', end='')
            cprint(deg_info.type, CHANGE_TYPE_COLOURS.get(deg_info.type, 'white'), attrs=[])
            print(' ', end='')
            cprint(
                '{}'.format(CHANGE_STRINGS[deg_info.result]),
                CHANGE_COLOURS[deg_info.result], attrs=['bold']
            )
            if deg_info.result != PerformanceChange.NoChange:
                from_colour, to_colour = get_degradation_change_colours(deg_info.result)
                print(' from: ', end='')
                cprint('{}'.format(deg_info.from_baseline), from_colour, attrs=[])
                print(' -> to: ', end='')
                cprint('{}'.format(deg_info.to_target), to_colour, attrs=[])
                if deg_info.confidence_type != 'no':
                    print(' (with confidence ', end='')
                    cprint(
                        '{} = {}'.format(
                            deg_info.confidence_type, deg_info.confidence_rate),
                        'white', attrs=['bold']
                    )
                    print(')', end='')
            # Print information about command that was executed
            print(" (", end='')
            cprint("$ {}".format(cmd), CHANGE_CMD_COLOUR, attrs=['bold'])
            print(')')
    print("")


class History(object):
    """Helper with wrapper, which is used when one wants to visualize the version control history
    of the project, printing specific stuff corresponding to a git history

    :ivar list unresolved_edges: list of parents that needs to be resolved in the vcs graph,
        for each such parent, we keep one column.
    :ivar bool auto_flush_with_border: specifies whether in auto-flushing the border should be
        included in the output
    :ivar object _original_stdout: original standard output that is saved and restored when leaving
    :ivar function _saved_print: original print function which is replaced with flushed function
        and is restored when leaving the history
    """
    class Edge(object):
        """Represents one edge of the history

        :ivar str next: the parent of the edge, i.e. the previously processed sha
        :ivar str colour: colour of the edge (red for deg, yellow for deg+opt, green for opt)
        :ivar str prev: the child of the edge, i.e. the not yet processed sha
        """
        def __init__(self, n, colour='white', prev=None):
            """Initiates one edge of the history

            :param str n: the next sha that will be processed
            :param str colour: colour of the edge
            :param str prev: the "parent" of the n
            """
            self.next = n
            self.colour = colour
            self.prev = prev

        def to_ascii(self, char):
            """Converts the edge to ascii representation

            :param str char: string that represents the edge
            :return: string representing the edge in ascii
            """
            return char if self.colour == 'white' \
                else termcolor.colored(char, self.colour, attrs=['bold'])

    def __init__(self, head):
        """Creates a with wrapper, which keeps and prints the context of the current vcs
        starting at head

        :param str head: head minor version
        """
        self.unresolved_edges = [History.Edge(head)]
        self.auto_flush_with_border = False
        self._original_stdout = None
        self._saved_print = None

    def __enter__(self):
        """When entering, we create a new string io object to catch standard output

        :return: the history object
        """
        # We will get the original standard output with string buffer and handle writing ourselves
        self._original_stdout = sys.stdout
        sys.stdout = io.StringIO()
        self._saved_print = builtins.print

        def flushed_print(print_function, history):
            """Decorates the print_function with automatic flushing of the output.

            Whenever a newline is included in the output, the stream will be automatically flushed

            :param function print_function: function that will include the flushing
            :param History history: history object that takes care of flushing
            :return: decorated flushed print
            """
            def wrapper(*args, **kwargs):
                """Decorator function for flushed print

                :param list args: list of positional arguments for print
                :param dict kwargs: list of keyword arguments for print
                """
                print_function(*args, **kwargs)
                end_specified = 'end' in kwargs.keys()
                if not end_specified or kwargs['end'] == '\n':
                    history.flush(history.auto_flush_with_border)
            return wrapper
        builtins.print = flushed_print(builtins.print, self)
        return self

    def __exit__(self, *_):
        """Restores the stdout to the original state

        :param list _: list of unused parameters
        """
        # Restore the stdout and printing function
        self.flush(self.auto_flush_with_border)
        builtins.print = self._saved_print
        sys.stdout = sys.__stdout__

    def get_left_border(self):
        """Returns the string representing the currently unresolved branches.

        Each unresolved branch is represented as a '|' characters

        The left border can e.g. look as follows:

        | | | | |

        :return: string representing the columns of the unresolved branches
        """
        return " ".join(edge.to_ascii("|") for edge in self.unresolved_edges) + "  "

    def _merge_parents(self, merged_parent):
        """Removes the duplicate instances of the merge parent.

        E.g. given the following parents:

            [p1, p2, p3, p2, p4, p2]

        End we merge the parent p2, the we will obtain the following:

            [p1, p2, p3, p4]

        This is used, when we are outputing the parent p2, and first we merged the branches, print
        the information about p2 and then actualize the unresolved parents with parents of p2.

        :param str merged_parent: sha of the parent that is going to be merged in the unresolved
        """
        filtered_unresolved = []
        already_found_parent = False
        for parent in self.unresolved_edges:
            if parent.next == merged_parent and already_found_parent:
                continue
            already_found_parent = already_found_parent or parent.next == merged_parent
            filtered_unresolved.append(parent)
        self.unresolved_edges = filtered_unresolved

    def _print_minor_version(self, minor_version_info):
        """Prints the information about minor version.

        The minor version is visualized as follows:

         | * | {sha:6} {desc}

        I.e. all of the unresolved parents are output as | and the printed parent is output as *.
        The further we print first six character of minor version checksum and first line of desc

        :param MinorVersion minor_version_info: printed minor version
        """
        minor_str = " ".join(
            "*" if p.next == minor_version_info.checksum else p.to_ascii("|")
            for p in self.unresolved_edges
        )
        print(minor_str, end='')
        cprint(" {}".format(
            minor_version_info.checksum[:6]
        ), 'yellow', attrs=[])
        print(": {} | ".format(
            minor_version_info.desc.split("\n")[0].strip()
        ), end='')

    def progress_to_next_minor_version(self, minor_version_info):
        """Progresses the history of the VCS to next minor version

        This flushes the current caught buffer, resolves the fork points (i.e. when we forked the
        history from the minor_version), prints the information about minor version and the resolves
        the merges (i.e. when the minor_version is spawned from the merge). Finally this updates the
        unresolved parents with parents of minor_version.

        Prints the following:

        | | | |/ / /
        | | | * | | sha: desc
        | | | |\ \ \

        :param MinorVersion minor_version_info: information about minor version
        """
        minor_sha = minor_version_info.checksum
        self.flush(with_border=True)
        self.auto_flush_with_border = False
        self._process_fork_point(minor_sha)
        self._merge_parents(minor_sha)
        self._print_minor_version(minor_version_info)

    def finish_minor_version(self, minor_version_info, degradation_list):
        """Notifies that we have processed the minor version.

        Updates the unresolved parents, taints those where we found degradations and processes
        the merge points. Everything is flushed.

        :param MinorVersion minor_version_info: name of the finished minor version
        :param list degradation_list: list of found degradations
        """
        # Update the unresolved parents
        minor_sha = minor_version_info.checksum
        version_index = first_index_of_attr(self.unresolved_edges, 'next', minor_sha)
        self.unresolved_edges[version_index:version_index+1] = [
            History.Edge(p, 'white', minor_sha) for p in minor_version_info.parents
        ]
        self._taint_parents(minor_sha, degradation_list)
        self._process_merge_point(version_index, minor_version_info.parents)

        # Flush the history
        self.flush()
        self.auto_flush_with_border = True

    def flush(self, with_border=False):
        """Flushes the stdout optionally with left border of unresolved parent columns

        If the current stdout is not readable, the flushing is skipped

        :param bool with_border: if true, then every line is printed with the border of unresolved
            parents
        """
        # Unreadable stdouts are skipped, since we are probably in silent mode
        if sys.stdout.readable():
            # flush the stdout
            sys.stdout.seek(0)
            for line in sys.stdout.readlines():
                if with_border:
                    self._original_stdout.write(self.get_left_border())
                self._original_stdout.write(line)

            # create new stringio
            sys.stdout = io.StringIO()

    def _taint_parents(self, target, degradation_list):
        """According to the given list of degradation, sets the parents either as tainted
        or fixed.

        Tainted parents are output with red colour, while fixed parents with green colour.

        :param str target: target minor version
        :param list degradation_list: list of found degradations
        """
        # First we process all of the degradations and optimization
        taints = set()
        fixes = set()
        for deg, _, baseline in degradation_list:
            if deg.result.name == "Degradation":
                taints.add(baseline)
            elif deg.result.name == "Optimization":
                fixes.add(baseline)

        # At last we colour the edges; edges that contain both optimizations and degradations
        # are coloured yellow
        for edge in self.unresolved_edges:
            if edge.prev == target:
                tainted = edge.next in taints
                fixed = edge.next in fixes
                if tainted and fixed:
                    edge.colour = 'yellow'
                elif tainted:
                    edge.colour = 'red'
                elif fixed:
                    edge.colour = 'green'

    def _process_merge_point(self, merged_at, merged_parents):
        """Updates the printed tree after we merged list of parents in the given merge_at index.

        This prints up to merged_at unresolved parents, and then creates a merge point (|\) that
        branches of to the length of the merged_parents columns.

        Prints the following:

        | | | * | | sha: desc
        | | | | \ \
        | | | |\ \ \
        | | | | | \ \
        | | | | |\ \ \
        | | | | | | \ \
        | | | | | |\ \ \
        | | | | | | | | |

        :param int merged_at: index, where the merged has happened
        :param list merged_parents: list of merged parents
        """
        parent_num = len(merged_parents)
        rightmost_branches_num = len(self.unresolved_edges) - merged_at - parent_num

        # We output one additional line for better readability; if we process some merges,
        # then we will have plenty of space left, so no need to do the newline
        if parent_num == 1:
            print(self.get_left_border())
        else:
            for _ in range(1, parent_num):
                merged_at += 1
                left_str = " ".join(
                    e.to_ascii("|") for e in self.unresolved_edges[:merged_at]
                )
                right_str = " ".join(
                    e.to_ascii("\\") for e in self.unresolved_edges[-rightmost_branches_num:]
                ) if rightmost_branches_num else ""
                print(left_str + right_str)
                print(left_str + " ".join(
                    [self.unresolved_edges[merged_at].to_ascii('\\'), right_str]
                ))

    def _process_fork_point(self, fork_point):
        """Updates the printed tree after we forked from the given sha.

        Prints the following:

        | | | | | | |
        | | | |/ / /
        | | | * | |

        :param str fork_point: sha of the point, where we are forking
        """
        ulen = len(self.unresolved_edges)
        forked_index = first_index_of_attr(self.unresolved_edges, 'next', fork_point)
        src_index_map = list(range(0, ulen))
        tgt_index_map = [
            forked_index if self.unresolved_edges[i].next == fork_point else i
            for i in range(0, ulen)
        ]

        while src_index_map != tgt_index_map:
            line = list(" "*(max(src_index_map)+1)*2)
            triple_zip = zip(src_index_map, self.unresolved_edges, tgt_index_map)
            for i, (lhs, origin, rhs) in enumerate(triple_zip):
                # for this index we are moving to the left
                diff = -1 if rhs - lhs else 0
                if diff == 0:
                    line[2*lhs] = origin.to_ascii('|')
                else:
                    line[2*lhs-1] = origin.to_ascii('/')
                src_index_map[i] += diff
            print("".join(line))
