"""Wrapper over version control systems used for generic lookup of the concrete implementations.

VCS module contains modules with concrete implementations of the wrappers over the concrete version
control systems. It tries to enforce simplicity and lightweight approach in an implementation of
the wrapper.

Inside the wrapper are defined function that are used for lookup of the concrete implementations
depending of the chosen type/module, like e.g. git, svn, etc.
"""

import perun.utils.log as perun_log
from perun.utils import dynamic_module_function_call

__author__ = 'Tomas Fiedor'


def get_minor_head(vcs_type, vcs_path):
    """Returns the string representation of head of current major version, i.e.
    for git this returns the massaged HEAD reference.

    This function is called mainly during the outputs of ``perun log`` and
    ``perun status`` but also during the automatic generation of profiles
    (either by ``perun run`` or ``perun collect``), where the retrieved
    identification is used as :preg:`origin`.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :returns: unique string representation of current head (usually in SHA)
    :raises ValueError: if the head cannot be retrieved from the current
        context
    """
    try:
        return dynamic_module_function_call(
            'perun.vcs', vcs_type, '_get_minor_head', vcs_path
        )
    except ValueError as value_error:
        perun_log.error(
            "could not obtain head minor version: {}".format(value_error)
        )


def init(vcs_type, vcs_path, vcs_init_params):
    """Calls the implementation of initialization of wrapped underlying version
    control system.

    The initialization should take care of both reinitialization of existing
    version control system instances and newly created instances. Init is
    called during the ``perun init`` command from command line interface.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: destination path of the initialized wrapped vcs
    :param dict vcs_init_params: dictionary of keyword arguments passed to
        initialization method of the underlying vcs module
    :return: true if the underlying vcs was successfully initialized
    """
    perun_log.msg_to_stdout("Initializing {} version control params {} and {}".format(
        vcs_type, vcs_path, vcs_init_params
    ), 1)
    return dynamic_module_function_call(
        'perun.vcs', vcs_type, '_init', vcs_path, vcs_init_params
    )


def walk_minor_versions(vcs_type, vcs_path, head_minor_version):
    """Generator of minor versions for the given major version, which yields
    the ``MinorVersion`` named tuples containing the following information:
    ``date``, ``author``, ``email``, ``checksum`` (i.e. the hash representation
    of the minor version), ``commit_description`` and ``commit_parents`` (i.e.
    other minor versions).

    Minor versions are walked through this function during the ``perun log``
    command.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :param str head_minor_version: the root minor versions which is the root
        of the walk.
    :returns: iterable stream of minor version representation
    """
    perun_log.msg_to_stdout("Walking minor versions of type {}".format(
        vcs_type
    ), 1)
    return dynamic_module_function_call(
        'perun.vcs', vcs_type, '_walk_minor_versions', vcs_path, head_minor_version
    )


def walk_major_versions(vcs_type, vcs_path):
    """Generator of major versions for the current wrapped repository.

    This function is currently unused, but will be needed in the future.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :returns: iterable stream of major version representation
    """
    perun_log.msg_to_stdout("Walking major versions of type {}".format(
        vcs_type
    ), 1)
    return dynamic_module_function_call(
        'perun.vcs', vcs_type, '_walk_major_versions', vcs_path
    )


def get_minor_version_info(vcs_type, vcs_path, minor_version):
    """Yields the specification of concrete minor version in form of
    the ``MinorVersion`` named tuples containing the following information:
    ``date``, ``author``, ``email``, ``checksum`` (i.e. the hash representation
    of the minor version), ``commit_description`` and ``commit_parents`` (i.e.
    other minor versions).

    This function is a non-generator alternative of
    :func:`perun.vcs.walk_minor_versions` and is used during the ``perun
    status`` output to display the specifics of minor version.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :param str minor_version: the specification of minor version (in form of
        sha e.g.) for which we are retrieving the details
    :returns: minor version named tuple
    """
    perun_log.msg_to_stdout("Getting minor version info of type {} and args {}, {}".format(
        vcs_type, vcs_path, minor_version
    ), 1)
    return dynamic_module_function_call(
        'perun.vcs', vcs_type, '_get_minor_version_info', vcs_path, minor_version
    )


def get_head_major_version(vcs_type, vcs_path):
    """Returns the string representation of current major version of the
    wrapped repository.

    Major version is displayed during the ``perun status`` output, which shows
    the current working major version of the project.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :returns: string representation of the major version
    """
    perun_log.msg_to_stdout("Getting head major version of type {}".format(
        vcs_type
    ), 1)
    return dynamic_module_function_call(
        'perun.vcs', vcs_type, '_get_head_major_version', vcs_path
    )


def check_minor_version_validity(vcs_type, vcs_path, minor_version):
    """Checks whether the given minor version specification corresponds to the
    wrapped version control system, and is not in wrong format.

    Minor version validity is mostly checked during the lookup of the minor
    versions from the command line interface.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :param str minor_version: the specification of minor version (in form of
        sha e.g.) for which we are checking the validity
    :raises VersionControlSystemException: when the given minor version is
        invalid in the context of the wrapped version control system.
    """
    dynamic_module_function_call(
        'perun.vcs', vcs_type, '_check_minor_version_validity', vcs_path, minor_version
    )


def massage_parameter(vcs_type, vcs_path, parameter, parameter_type=None):
    """Conversion function for massaging (or unifying different representations
    of objects) the parameters for version control systems.

    Massaging is mainly executed during from the command line interface, when
    one can e.g. use the references (like ``HEAD``) to specify concrete minor
    versions. Massing then unifies e.g. the references or proper hash
    representations, to just one representation for internal processing.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :param str parameter: vcs parameter (e.g. revision, minor or major version)
        which will be massaged, i.e. transformed to unified representation
    :param str parameter_type: more detailed type of the parameter
    :returns: string representation of parameter
    """
    return dynamic_module_function_call(
        'perun.vcs', vcs_type, '_massage_parameter', vcs_path, parameter, parameter_type
    )


def is_dirty(vcs_type, vcs_path):
    """Tests whether the wrapped repository is dirty.

    By dirty repository we mean a repository that has either a submitted changes to its index (i.e.
    we are in the middle of commit) or any unsubmitted changes to tracked files in the current
    working directory.

    Note that this is crucial for performance testing, as any uncommited changes may skew
    the profiled data and hence the resulting profiles would not correctly represent the performance
    of minor versions.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :return: whether the given repository is dirty or not
    """
    return dynamic_module_function_call(
        'perun.vcs', vcs_type, '_is_dirty', vcs_path
    )


class CleanState:
    """Helper with wrapper, which is used to execute instances of commands with clean state of VCS.

    This is needed e.g. when we are collecting new data, and the repository is dirty with changes,
    then we use this CleanState to keep those changes, have a clean state (or maybe even checkout
    different version) and then collect correctly the data. The previous state is then restored
    """
    def __init__(self, vcs_type, vcs_path):
        """Creates a with wrapper for a corresponding VCS

        :param str vcs_type: type of the underlying wrapped version control system
        :param str vcs_path: source path of the wrapped vcs
        """
        self.type = vcs_type
        self.path = vcs_path
        self.saved_state = False
        self.last_head = None

    def __enter__(self):
        """When entering saves the state of the repository

        We save the uncommited/unsaved changes (e.g. to stash) and also we remeber the previous
        head, which will be restored at the end.
        """
        self.saved_state, self.last_head = save_state(self.type, self.path)

    def __exit__(self, *_):
        """When exiting, restores the state of the repository

        Restores the previous commit and unstashes the changes made to working directory and index.

        :param _: not used params of exit handler
        """
        restore_state(self.type, self.path, self.saved_state, self.last_head)


def save_state(vcs_type, vcs_path):
    """Saves the state of the repository in case it is dirty.

    When saving the state of the repository one should store all of the uncommited changes to
    the working directory and index. Any issues while this process happens should be handled by
    user itself, hence no workarounds and mending should take place in this function.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :return:
    """
    # Todo: Check the vcs.fail_when_dirty and log error in the case
    return dynamic_module_function_call(
        'perun.vcs', vcs_type, '_save_state', vcs_path
    )


def restore_state(vcs_type, vcs_path, saved, state):
    """Restores the previous state of the the repository

    When restoring the state of the repository one should pop the stored changes from the stash
    and reapply them on the current directory. This make sure, that after the performance testing,
    the project is in the previous state and developer can continue with his work.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :param bool saved: whether the stashed was something
    :param str state: the previous state of the repository
    """
    dynamic_module_function_call(
        'perun.vcs', vcs_type, '_restore_state', vcs_path, saved, state
    )


def checkout(vcs_type, vcs_path, minor_version):
    """Checks out the new working directory corresponding to the given minor version.

    According to the supplied minor version, this command should remake the working directory
    so it corresponds to the state defined by the minor version.

    :param str vcs_type: type of the underlying wrapped version control system
    :param str vcs_path: source path of the wrapped vcs
    :param str minor_version: minor version that will be checked out
    """
    massaged_minor_version = massage_parameter(vcs_type, vcs_path, minor_version)
    dynamic_module_function_call(
        'perun.vcs', vcs_type, '_checkout', vcs_path, massaged_minor_version
    )