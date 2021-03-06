"""Basic tests for running the cli interface of the Perun

Note that the functionality of the commands themselves are not tested,
this is done in appropriate test files, only the API is tested."""

import os
import git
import re
import shutil
import time
import glob

import pytest
from click.testing import CliRunner

import perun.cli as cli
import perun.utils as utils
import perun.utils.log as log
import perun.utils.decorators as decorators
import perun.logic.config as config
import perun.logic.store as store
import perun.collect.trace.systemtap as stap
import perun.collect.trace.strategy as strategy
import perun.utils.exceptions as exceptions
import perun.check.factory as check
import perun.vcs as vcs

__author__ = 'Tomas Fiedor'


def _mocked_stap(**_):
    """System tap mock, provide OK code and pre-fabricated collection output"""
    return 0, os.path.join(os.path.dirname(__file__), 'collect_trace', 'tst_stap_record.txt')


def _mocked_stap_extraction(_):
    return ('process("/home/jirka/perun/tests/collect_trace/tst").mark("BEFORE_CYCLE")\n'
            'process("/home/jirka/perun/tests/collect_trace/tst").mark("BEFORE_CYCLE_end")\n'
            'process("/home/jirka/perun/tests/collect_trace/tst").mark("INSIDE_CYCLE")\n')


def _mocked_stap_extraction_empty(_):
    return 'Tip: /usr/share/doc/systemtap/README.Debian should help you get started.'


def _get_latest_collect_script(script_dir):
    """Return name of the latest collect script from given script directory

    :param str script_dir: path to the directory where multiple (or single)
                           collect scripts are located
    :return str: path to the latest trace collector script
    """
    # Get all stap script in the directory and find the last one,
    # which will be then analyzed for correctness
    scripts = glob.glob(os.path.join(script_dir, 'collect_script_*.stp'))
    # Find the newest script in the directory
    latest = scripts[0]
    # Extract timestamp from the first script
    latest_timestamp = int(''.join(scripts[0][-23:-4].split('-')))
    for script in scripts:
        # Check every script file and find the biggest timestamp
        timestamp = int(''.join(script[-23:-4].split('-')))
        if timestamp >= latest_timestamp:
            latest_timestamp = timestamp
            latest = script
    return latest


def _compare_collect_scripts(new_script, reference_script):
    """Compares collect script with its reference scripts

    :param str new_script: path to the script to compare
    :param str reference_script: path to the reference script
    :return bool: True if scripts are the same (except machine specific values in the script),
                  False otherwise
    """
    # Replace the machine-specific path to the binary with some generic text to allow for comparison
    with open(new_script, 'r') as script:
        content = script.read()
    sub_content = re.sub(r' process\(\".*?/tst\"\)\.', ' process("cmp").', content)
    with open(reference_script, 'r') as cmp:
        cmp_content = cmp.read()
    return sub_content == cmp_content


def test_cli(pcs_full):
    """Generic tests for cli, such as testing verbosity setting etc."""
    runner = CliRunner()

    log.VERBOSITY = log.VERBOSE_RELEASE
    runner.invoke(cli.cli, ['-v', '-v', 'log'])
    assert log.VERBOSITY == log.VERBOSE_DEBUG

    # Restore the verbosity
    log.VERBOSITY = log.VERBOSE_RELEASE
    log.SUPPRESS_PAGING = True

    result = runner.invoke(cli.cli, ['--version'])
    assert result.output.startswith('Perun')
    assert result.exit_code == 0


def run_non_param_test(runner, test_params, expected_exit_code, expected_output):
    result = runner.invoke(cli.postprocessby, test_params)
    assert result.exit_code == expected_exit_code
    assert expected_output in result.output


def test_regressogram_incorrect(pcs_full):
    """
    Test various failure scenarios for regressogram cli.

    Expecting no exceptions, all tests should end with status code 2.
    """
    incorrect_tests = [
        # Test the lack of arguments
        {'params': [], 'output': 'Usage'},
        # Test non-existing argument
        {'params': ['-a'], 'output': 'no such option: -a'},
        # Test malformed bucket_number argument
        {'params': ['--buckets_numbers'], 'output': 'no such option: --buckets_numbers'},
        # Test missing bucket_number value
        {'params': ['-bn'], 'output': '-bn option requires an argument'},
        # Test invalid bucket_number value
        {'params': ['-bn', 'user'], 'output': 'Invalid value for "--bucket_number"'},
        # Test malformed bucket_method argument
        {'params': ['--buckets_methods'], 'output': 'no such option: --buckets_methods'},
        # Test missing bucket_method value
        {'params': ['--bucket_method'], 'output': '--bucket_method option requires an argument'},
        # Test invalid bucket_method value
        {'params': ['-bm', 'user'], 'output': 'Invalid value for "--bucket_method"'},
        # Test malformed statistic_function argument
        {'params': ['--statistic_functions'], 'output': 'no such option: --statistic_functions'},
        # Test missing statistic_function value
        {'params': ['--statistic_function'], 'output': '--statistic_function option requires an argument'},
        # Test invalid model name
        {'params': ['-sf', 'max'], 'output': 'Invalid value for "--statistic_function"'}
    ]
    # TODO: multiple values check

    # Instantiate the runner fist
    runner = CliRunner()

    # Set stable parameters at all tests
    regressogram_params = ['1@i', 'regressogram']
    # Executing the testing
    for incorrect_test in incorrect_tests:
        run_non_param_test(runner, regressogram_params + incorrect_test['params'], 2, incorrect_test['output'])


def test_regressogram_correct(pcs_full):
    """
    Test correct usages of the regressogram cli.

    Expecting no exceptions and errors, all tests should end with status code 0.
    """
    # Instantiate the runner first
    runner = CliRunner()

    result = runner.invoke(cli.status, [])
    match = re.search(r'([0-9]+@i).*mixed', result.output)
    assert match
    cprof_idx = match.groups(1)[0]

    correct_tests = [
        # Test the help printout first
        {'params': ['--help'], 'output': 'Usage'},
        # Test default values of parameters (buckets, statistic_function)
        {'params': []},
        # Test first acceptable value for statistic_function parameter (mean)
        {'params': ['--statistic_function', 'mean']},
        # Test second acceptable value for statistic_function parameter (median)
        {'params': ['-sf', 'median']},
        # Test integer variant as value for bucket_number parameter
        {'params': ['--bucket_number', '10']},
        # Test 'auto' method as value for bucket_method parameter
        {'params': ['-bm', 'auto']},
        # Test 'fd' method as value for bucket_method parameter
        {'params': ['-bm', 'fd']},
        # Test 'doane' method as value for bucket_method parameter
        {'params': ['--bucket_method', 'doane']},
        # Test 'scott' method as value for bucket_method parameter
        {'params': ['--bucket_method', 'scott']},
        # Test 'sturges' method as value for bucket_method parameter
        {'params': ['-bm', 'sturges']},
        # Test 'rice' method as value for bucket_method parameter
        {'params': ['-bm', 'rice']},
        # Test 'sqrt' method as value for bucket_method parameter
        {'params': ['--bucket_method', 'sqrt']},
        # Test complex variant for regressogram method
        {'params': ['--bucket_method', 'doane', '--statistic_function', 'mean']},
        # Test bucket_method and bucket_number parameters common
        {'params': ['--bucket_method', 'sqrt', '--bucket_number', 10]},
    ]

    # Set stable parameters at all tests
    regressogram_params = [cprof_idx, 'regressogram']
    # Performing tests
    for idx, correct_test in enumerate(correct_tests):
        run_non_param_test(runner, regressogram_params + correct_test['params'], 0,
                           correct_test.get('output', 'Successfully postprocessed'))


def moving_average_runner_test(runner, tests_set, tests_edge, exit_code, cprof_idx):
    def call_test_runner(params, test_sample):
        run_non_param_test(runner, params, exit_code, test_sample.get('output', 'Successfully postprocessed'))

    # Set stable parameters at all tests
    moving_average_params = [cprof_idx, 'moving_average']
    # Set the supported methods at moving average postprocessor
    moving_average_methods = {0: ['sma'], 1: ['smm'], 2: ['ema']}
    # Executing the testing
    for idx, test in enumerate(tests_set):
        # tests moving average cli commands
        if idx < tests_edge[0]:
            call_test_runner(moving_average_params + test['params'], test)
        # test common options for SMA command and SMM command
        elif idx < tests_edge[1]:
            for n in range(0, len(moving_average_methods) - 1):
                call_test_runner(moving_average_params + moving_average_methods[n] + test['params'], test)
        # test individual options for Simple Moving Average command: SMA
        elif idx < tests_edge[2]:
            call_test_runner(moving_average_params + moving_average_methods[0] + test['params'], test)
        # test individual options for Exponential Moving Average command: EMA
        elif idx < tests_edge[3]:
            call_test_runner(moving_average_params + moving_average_methods[2] + test['params'], test)
        # test complex combinations of options and commands
        elif idx < tests_edge[4]:
            call_test_runner(moving_average_params + test['params'], test)


def test_moving_average_incorrect(pcs_full):
    """
    Test various failure scenarios for moving average cli.

    Expecting no exceptions, all tests should end with status code 2.
    """
    incorrect_tests = [
        # TESTS MOVING AVERAGE COMMAND AND OPTIONS
        # 1. Test non-existing argument
        {'params': ['--abcd'], 'output': 'no such option: --abcd'},
        # 2. Test non-existing command
        {'params': ['cma'], 'output': 'No such command "cma"'},
        # 3. Test non-existing argument
        {'params': ['-b'], 'output': 'no such option: -b'},
        # 4. Test malformed min_periods argument
        {'params': ['--min_period'], 'output': 'no such option: --min_period'},
        # 5. Test missing min_period value
        {'params': ['-mp'], 'output': '-mp option requires an argument'},
        # 6. Test invalid range min_periods value
        {'params': ['--min_periods', 0], 'output': 'Invalid value for "--min_periods"'},
        # 7. Test invalid value type min_periods value
        {'params': ['-mp', 'A'], 'output': 'Invalid value for "--min_periods"'},
        # 8. Test malformed per_key argument
        {'params': ['--dependings-on'], 'output': 'no such option: --dependings-on'},
        # 9. Test missing per_key value
        {'params': ['-dp'], 'output': '-dp option requires an argument'},
        # 10. Test invalid value per_key arguments
        {'params': ['-dp', 'unknown'], 'output': 'Invalid value for "--depending-on"'},
        # 11. Test malformed of_key argument
        {'params': ['--off'], 'output': 'no such option: --off'},
        # 12. Test missing of_key value
        {'params': ['--of'], 'output': '-of option requires an argument'},
        # 13. Test invalid value of_key arguments
        {'params': ['-o', 'unknown'], 'output': 'Invalid value for "--of"'},

        # TESTS SIMPLE MOVING AVERAGE COMMAND AND SIMPLE MOVING MEDIAN COMMAND
        # 14. Test malformed window-width argument
        {'params': ['--window_widh'], 'output': 'no such option: --window_widh'},
        # 15. Test missing window-width value
        {'params': ['-ww'], 'output': '-ww option requires an argument'},
        # 16. Test invalid range window-width argument
        {'params': ['-ww', -1], 'output': 'Invalid value for "--window_width"'},
        # 17. Test invalid value type window-width argument
        {'params': ['--window_width', 0.5], 'output': 'Invalid value for "--window_width"'},
        # 18. Test malformed center argument
        {'params': ['--centers'], 'output': 'no such option: --centers'},
        # 19. Test malformed no-center argument
        {'params': ['--mo-center'], 'output': 'no such option: --mo-center'},
        # 20. Test value for center argument
        {'params': ['--center', 'True'], 'output': 'Got unexpected extra argument (True)'},
        # 21. Test value for no-center argument
        {'params': ['--no-center', 'False'], 'output': 'Got unexpected extra argument (False)'},

        # TESTS SIMPLE MOVING AVERAGE COMMAND
        # 22. Test malformed window-type argument
        {'params': ['--windov_type'], 'output': 'no such option: --windov_type'},
        # 23. Test missing window-type value
        {'params': ['--window_type'], 'output': '--window_type option requires an argument'},
        # 24. Test invalid range window-type argument
        {'params': ['-wt', "boxcars"], 'output': 'Invalid value for "--window_type"'},

        # TESTS EXPONENTIAL MOVING AVERAGE COMMAND
        # 25. Test malformed decay argument
        {'params': ['--decays'], 'output': 'no such option: --decays'},
        # 26. Test missing decay value
        {'params': ['-d'], 'output': '-d option requires 2 arguments'},
        # 27. Test invalid type of first value in decay argument
        {'params': ['--decay', 'spam', 3], 'output': 'Invalid value for "--decay"'},
        # 28. Test invalid type of second value in decay argument
        {'params': ['--decay', 'span', "A"], 'output': 'Invalid value for "--decay"'},
        # 29. Test invalid range for `com` value in decay argument
        {'params': ['--decay', 'com', -1], 'output': ' Invalid value for com'},
        # 30. Test invalid range for `span` value in decay argument
        {'params': ['--decay', 'span', 0], 'output': ' Invalid value for span'},
        # 31. Test invalid range for `halflife` value in decay argument
        {'params': ['--decay', 'halflife', 0], 'output': 'Invalid value for halflife'},
        # 32. Test invalid range for `com` value in decay argument
        {'params': ['--decay', 'alpha', 0], 'output': ' Invalid value for alpha'},
    ]
    # edge of test groups for different commands group or individual commands
    tests_edge = [13, 21, 24, 32]

    # Instantiate the runner first
    runner = CliRunner()

    result = runner.invoke(cli.status, [])
    match = re.search(r'([0-9]+@i).*mixed', result.output)
    assert match
    cprof_idx = match.groups(1)[0]

    # Perform the testing
    moving_average_runner_test(runner, incorrect_tests, tests_edge, 2, cprof_idx)


def test_moving_average_correct(pcs_full):
    """
    Test correct usages of the moving average cli.

    Expecting no exceptions and errors, all tests should end with status code 0.
    """
    correct_tests = [
        # TESTS MOVING AVERAGE COMMAND AND OPTIONS
        # 1. Test the help printout first
        {'params': ['--help'], 'output': 'Usage'},
        # 2. Test default command
        {'params': []},
        # 3. Test the help printout firsts
        {'params': ['--help'], 'output': 'Usage'},
        # 4. Test default value of parameters
        {'params': []},
        # 5. Test the value of min_periods parameter
        {'params': ['--min_periods', 1]},
        # 6. Test the value of per_key parameter
        {'params': ['--depending-on', 'amount']},
        # 7. Test the value of of_key parameter
        {'params': ['-o', 'structure-unit-size']},

        # TESTS SIMPLE MOVING AVERAGE COMMAND AND SIMPLE MOVING MEDIAN COMMAND
        # 8. Test the value of window_width_parameter
        {'params': ['--window_width', 10]},
        # 9. Test center parameter
        {'params': ['--center']},
        # 10. Test no-center parameter
        {'params': ['--no-center']},

        # TESTS SIMPLE MOVING AVERAGE COMMAND
        # 11. Test `boxcar` as value for window-type parameter
        {'params': ['--window_type', 'boxcar']},
        # 12. Test `triang` as value for window-type parameter
        {'params': ['-wt', 'triang']},
        # 13. Test `blackman` as value for window-type parameter
        {'params': ['-wt', 'blackman']},
        # 14. Test `hamming` as value for window-type parameter
        {'params': ['--window_type', 'hamming']},
        # 15. Test `bartlett` as value for window-type parameter
        {'params': ['--window_type', 'bartlett']},
        # 16. Test `parzen` as value for window-type parameter
        {'params': ['-wt', 'parzen']},
        # 17. Test `blackmanharris` as value for window-type parameter
        {'params': ['--window_type', 'blackmanharris']},
        # 18. Test `bohman` as value for window-type parameter
        {'params': ['-wt', 'bohman']},
        # 19. Test `nuttall` as value for window-type parameter
        {'params': ['--window_type', 'nuttall']},
        # 20. Test `barthann` as value for window-type parameter
        {'params': ['-wt', 'barthann']},
        # 21. Test complex combination of parameters no.1
        {'params': ['--window_type', 'blackmanharris', '-ww', 10]},
        # 22. Test complex combination of parameters no.2
        {'params': ['--no-center', '--window_type', 'triang']},
        # 23. Test complex combination of parameters no.3
        {'params': ['--window_width', 5, '--center', '-wt', 'parzen']},

        # TESTS EXPONENTIAL MOVING AVERAGE COMMAND
        # 24. Test valid value for `com` value in decay argument
        {'params': ['--decay', 'com', 2]},
        # 25. Test valid value for `span` value in decay argument
        {'params': ['--decay', 'span', 2]},
        # 26. Test valid value for `halflife` value in decay argument
        {'params': ['--decay', 'halflife', 2]},
        # 27. Test valid value for `com` value in decay argument
        {'params': ['--decay', 'alpha', .5]},

        # COMPLEX TESTS - addition of 'min_periods' argument
        # 28. test complex combination of parameters no.1 - EMA
        {'params': ['--min_periods', 5, 'ema', '--decay', 'alpha', .5]},
        # 29. test complex combination of parameters no.2 - EMA
        {'params': ['-mp', 2, 'ema', '--decay', 'com', 5]},
        # 30. Test complex combination of parameters no.1 - SMA
        {'params': ['-mp', 1, 'sma', '--window_type', 'blackmanharris']},
        # 31. Test complex combination of parameters no.2 - SMA
        {'params': ['--min_periods', 1, 'sma', '--no-center', '--window_type', 'triang']},
        # 32. Test complex combination of parameters no.3 - SMA
        {'params': ['--min_periods', 3, 'sma', '--window_width', 5, '--center', '-wt', 'parzen']},
        # 33. Test complex combination of parameters no.1 - SMM
        {'params': ['-mp', 2, 'smm', '--window_width', 5, '--center']},
        # 34. Test complex combination of parameters no.1 - SMM
        {'params': ['--min_periods', 3, 'smm', '--no-center', '--window_width', 15]},
    ]
    tests_edge = [7, 10, 23, 27, 33]

    # Instantiate the runner first
    runner = CliRunner()

    result = runner.invoke(cli.status, [])
    match = re.search(r'([0-9]+@i).*mixed', result.output)
    assert match
    cprof_idx = match.groups(1)[0]

    # Perform the testing
    moving_average_runner_test(runner, correct_tests, tests_edge, 0, cprof_idx)


def test_reg_analysis_incorrect(pcs_full):
    """Test various failure scenarios for regression analysis cli.

    Expecting no exceptions, all tests should end with status code 2.
    """
    # TODO: Cycle and dictionary reduction?

    # Instantiate the runner fist
    runner = CliRunner()

    # Test the lack of arguments
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis'])
    assert result.exit_code == 2
    assert 'Usage' in result.output

    # Test non-existing argument
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '-f'])
    assert result.exit_code == 2
    assert 'no such option: -f' in result.output

    # Test malformed method argument
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '--metod', 'full'])
    assert result.exit_code == 2
    assert 'no such option: --metod' in result.output

    # Test missing method value
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '-m'])
    assert result.exit_code == 2
    assert '-m option requires an argument' in result.output

    # Test invalid method name
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '--method', 'extra'])
    assert result.exit_code == 2
    assert 'Invalid value for "--method"' in result.output

    # Test malformed model argument
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '--method', 'full',
                                               '--regresion_models'])
    assert result.exit_code == 2
    assert 'no such option: --regresion_models' in result.output

    # Test missing model value
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '--method', 'full',
                                               '-r'])
    assert result.exit_code == 2
    assert '-r option requires an argument' in result.output

    # Test invalid model name
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '-m', 'full', '-r',
                                               'ultimastic'])
    assert result.exit_code == 2
    assert 'Invalid value for "--regression_models"' in result.output

    # Test multiple models specification with one invalid value
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '-m', 'full',
                                               '-r', 'linear', '-r', 'fail'])
    assert result.exit_code == 2
    assert 'Invalid value for "--regression_models"' in result.output

    # Test malformed steps argument
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '-m', 'full',
                                               '-r', 'all', '--seps'])
    assert result.exit_code == 2
    assert ' no such option: --seps' in result.output

    # Test missing steps value
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '-m', 'full',
                                               '-r', 'all', '-s'])
    assert result.exit_code == 2
    assert '-s option requires an argument' in result.output

    # Test invalid steps type
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '-m', 'full', '-r',
                                               'all', '-s', '0.5'])
    assert result.exit_code == 2
    assert '0.5 is not a valid integer' in result.output

    # Test multiple method specification resulting in extra argument
    result = runner.invoke(cli.postprocessby, ['1@i', 'regression_analysis', '-dp', 'snapshots',
                                               '-m', 'full', 'iterative'])
    assert result.exit_code == 2
    assert 'Got unexpected extra argument (iterative)' in result.output


def test_reg_analysis_correct(pcs_full):
    """Test correct usages of the regression analysis cli.

    Expecting no exceptions and errors, all tests should end with status code 0.
    """
    # TODO: Cycle and dictionary reduction?

    # Instantiate the runner first
    runner = CliRunner()

    result = runner.invoke(cli.status, [])
    match = re.search(r"([0-9]+@i).*mixed", result.output)
    assert match
    cprof_idx = match.groups(1)[0]

    # Test the help printout first
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '--help'])
    assert result.exit_code == 0
    assert 'Usage' in result.output

    # Test multiple method specifications -> the last one is chosen
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'full',
                                               '-m', 'iterative'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test the full computation method with all models set as a default value
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'full'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test the iterative method with all models
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'iterative'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test the interval method with all models
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'interval'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test the initial guess method with all models
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis',
                                               '-m', 'initial_guess'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test the bisection method with all models
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'bisection'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test explicit models specification on full computation
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'full',
                                               '-r', 'all'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test explicit models specification for multiple models
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'full',
                                               '-r', 'linear', '-r', 'logarithmic', '-r',
                                               'exponential'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test explicit models specification for all models
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'full',
                                               '-r', 'linear', '-r', 'logarithmic', '-r', 'power',
                                               '-r', 'exponential'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test explicit models specification for all models values (also with 'all' value)
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'full',
                                               '-r', 'linear', '-r', 'logarithmic', '-r', 'power',
                                               '-r', 'exponential', '-r', 'all'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test steps specification for full computation which has no effect
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'full',
                                               '-r', 'all', '-s', '100'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test reasonable steps value for iterative method
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'iterative',
                                               '-r', 'all', '-s', '4'])
    assert result.exit_code == 0
    assert result.output.count('Too few points') == 5
    assert 'Successfully postprocessed' in result.output

    # Test too many steps output
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'iterative',
                                               '-r', 'all', '-s', '1000'])
    assert result.exit_code == 0
    assert result.output.count('Too few points') == 7
    assert 'Successfully postprocessed' in result.output

    # Test steps value clamping with iterative method
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-m', 'iterative',
                                               '-r', 'all', '-s', '-1'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output

    # Test different arguments positions
    result = runner.invoke(cli.postprocessby, [cprof_idx, 'regression_analysis', '-s', '2',
                                               '-r', 'all', '-m', 'full'])
    assert result.exit_code == 0
    assert 'Successfully postprocessed' in result.output


def test_status_correct(pcs_full):
    """Test running perun status in perun directory, without any problems.

    Expecting no exceptions, zero status.
    """
    # Try running status without anything
    runner = CliRunner()
    result = runner.invoke(cli.status, [])
    assert result.exit_code == 0
    assert "On major version" in result.output

    short_result = runner.invoke(cli.status, ['--short'])
    assert short_result.exit_code == 0
    assert len(short_result.output.split("\n")) == 6
    assert config.lookup_key_recursively('format.sort_profiles_by') == 'time'

    # Try that the sort order changed
    short_result = runner.invoke(cli.status, ['--short', '--sort-by', 'source'])
    assert short_result.exit_code == 0
    assert pcs_full.local_config().get('format.sort_profiles_by') == 'source'

    # The sort order is kept the same
    short_result = runner.invoke(cli.status, ['--short'])
    assert short_result.exit_code == 0
    assert pcs_full.local_config().get('format.sort_profiles_by') == 'source'


@pytest.mark.usefixtures('cleandir')
def test_init_correct():
    """Test running init from cli, without any problems

    Expecting no exceptions, no errors, zero status.
    """
    runner = CliRunner()
    dst = str(os.getcwd())
    result = runner.invoke(cli.init, [dst, '--vcs-type=git'])
    assert result.exit_code == 0


@pytest.mark.usefixtures('cleandir')
def test_init_correct_with_edit(monkeypatch):
    """Test running init from cli, without any problems

    Expecting no exceptions, no errors, zero status.
    """
    runner = CliRunner()
    dst = str(os.getcwd())

    def donothing(*_):
        pass

    monkeypatch.setattr('perun.utils.run_external_command', donothing)
    result = runner.invoke(cli.init, [dst, '--vcs-type=git', '--configure'])
    assert result.exit_code == 0


@pytest.mark.usefixtures('cleandir')
def test_init_correct_with_incorrect_edit(monkeypatch):
    """Test running init from cli, without any problems

    Expecting no exceptions, no errors, zero status.
    """
    runner = CliRunner()
    dst = str(os.getcwd())

    def raiseexc(*_):
        raise exceptions.ExternalEditorErrorException("", "")

    monkeypatch.setattr('perun.utils.run_external_command', raiseexc)
    result = runner.invoke(cli.init, [dst, '--vcs-type=git', '--configure'])
    assert result.exit_code == 1
    monkeypatch.undo()

    for stuff in os.listdir(dst):
        shutil.rmtree(stuff)

    def raiseexc(*_):
        raise PermissionError('')

    monkeypatch.setattr('perun.logic.config.write_config_to', raiseexc)
    result = runner.invoke(cli.init, [dst, '--vcs-type=git'])
    assert result.exit_code == 1
    monkeypatch.undo()

    for stuff in os.listdir(dst):
        shutil.rmtree(stuff)

    def raiseexc(*_):
        raise exceptions.UnsupportedModuleFunctionException('git', 'shit')

    monkeypatch.setattr('perun.vcs.git._init', raiseexc)
    result = runner.invoke(cli.init, [dst, '--vcs-type=git'])
    assert result.exit_code == 1


@pytest.mark.usefixtures('cleandir')
def test_init_correct_with_params():
    """Test running init from cli with parameters for git, without any problems

    Expecting no exceptions, no errors, zero status.
    """
    runner = CliRunner()
    dst = str(os.getcwd())
    result = runner.invoke(cli.init, [dst, '--vcs-type=git', '--vcs-flag', 'bare'])
    assert result.exit_code == 0
    assert 'config' in os.listdir(os.getcwd())
    with open(os.path.join(os.getcwd(), 'config'), 'r') as config_file:
        assert "bare = true" in "".join(config_file.readlines())


@pytest.mark.usefixtures('cleandir')
def test_init_correct_with_params_and_flags(helpers):
    """Test running init from cli with parameters and flags for git, without any problems

    Expecting no exceptions, no errors, zero status.
    """
    runner = CliRunner()
    dst = str(os.getcwd())
    result = runner.invoke(cli.init, [dst, '--vcs-type=git', '--vcs-flag', 'quiet',
                                      '--vcs-param', 'separate-git-dir', 'sepdir'])
    assert result.exit_code == 0
    assert 'sepdir' in os.listdir(os.getcwd())
    initialized_dir = os.path.join(os.getcwd(), 'sepdir')
    dir_content = os.listdir(initialized_dir)

    # Should be enough for sanity check
    assert 'HEAD' in dir_content
    assert 'refs' in dir_content
    assert 'branches' in dir_content


def test_add_correct(helpers, pcs_full, valid_profile_pool):
    """Test running add from cli, without any problems

    Expecting no exceptions, no errors, zero status.
    """
    runner = CliRunner()
    added_profile = helpers.prepare_profile(
        pcs_full.get_job_directory(), valid_profile_pool[0],
        vcs.get_minor_head()
    )
    result = runner.invoke(cli.add, ['--keep-profile', '{}'.format(added_profile)])
    assert result.exit_code == 0
    assert os.path.exists(added_profile)


@pytest.mark.usefixtures('cleandir')
def test_cli_outside_pcs(helpers, valid_profile_pool):
    """Test running add from cli, with problems"""
    # Calling add outside of the perun repo
    runner = CliRunner()
    dst_dir = os.getcwd()
    added_profile = helpers.prepare_profile(dst_dir, valid_profile_pool[0], "")
    result = runner.invoke(cli.add, ['--keep-profile', '{}'.format(added_profile)])
    assert result.exit_code == 1

    result = runner.invoke(cli.remove, ['{}'.format(added_profile)])
    assert result.exit_code == 1

    result = runner.invoke(cli.log, [])
    assert result.exit_code == 1

    result = runner.invoke(cli.status, [])
    assert result.exit_code == 1


def test_rm_correct(helpers, pcs_full, stored_profile_pool):
    """Test running rm from cli, without any problems

    Expecting no exceptions, no errors, zero status
    """
    runner = CliRunner()
    deleted_profile = os.path.split(stored_profile_pool[1])[-1]
    result = runner.invoke(cli.remove, ['{}'.format(deleted_profile)])
    assert result.exit_code == 0


def test_log_correct(pcs_full):
    """Test running log from cli, without any problems

    Expecting no exceptions, no errors, zero status
    """
    runner = CliRunner()
    result = runner.invoke(cli.log, [])
    assert result.exit_code == 0

    short_result = runner.invoke(cli.log, ['--short'])
    assert short_result.exit_code == 0
    assert len(result.output.split('\n')) > len(short_result.output.split('\n'))


def test_collect_correct(pcs_full):
    """Test running collector from cli, without any problems

    Expecting no exceptions, no errors, zero status
    """
    runner = CliRunner()
    result = runner.invoke(cli.collect, ['-c echo', '-w hello', 'time'])
    assert result.exit_code == 0


def test_collect_trace(monkeypatch, pcs_full, trace_collect_job):
    """Test running the trace collector from the CLI with parameter handling

    Expecting no errors
    """
    monkeypatch.setattr(stap, 'systemtap_collect', _mocked_stap)
    runner = CliRunner()

    script_dir = os.path.join(os.path.split(__file__)[0], 'collect_trace')
    target = os.path.join(script_dir, 'tst')
    job_params = trace_collect_job[5]['collector_params']['trace']

    func = ['-f{}'.format(func) for func in job_params['func']]
    func_sampled = []
    for f in job_params['func_sampled']:
        func_sampled.append('-fs')
        func_sampled.append(f[0])
        func_sampled.append(f[1])
    static = ['-s{}'.format(rule) for rule in job_params['static']]
    binary = ['-b{}'.format(target)]

    result = runner.invoke(cli.collect, ['-c{}'.format(target),
                                         'trace'] + func + func_sampled + static + binary)

    assert result.exit_code == 0

    # Test running the job from the params using the job file
    # Fixme: yaml parameters applied after the cli, thus cli reports missing parameters
    # script_dir = os.path.split(__file__)[0]
    # source_dir = os.path.join(script_dir, 'collect_trace')
    # job_config_file = os.path.join(source_dir, 'job.yml')
    # result = runner.invoke(cli.collect, ['-c{}'.format(target), '-p{}'.format(job_config_file),
    #                                      'trace'])
    # assert result.exit_code == 0

    # Test running the job from the params using the yaml string
    result = runner.invoke(cli.collect, ['-c{}'.format(target),
                                         '-p\"global_sampling: 2\"',
                                         'trace'] + func + func_sampled + static + binary)
    assert result.exit_code == 0

    # Try different template
    result = runner.invoke(cli.collect, [
        '-ot', '%collector%-profile',
        '-c{}'.format(target),
        '-p\"method: custom\"',
        'trace',
    ] + func + func_sampled + static + binary)
    del config.runtime().data['format']
    decorators.remove_from_function_args_cache("lookup_key_recursively")
    assert result.exit_code == 0
    pending_profiles = os.listdir(os.path.join(os.getcwd(), ".perun", "jobs"))
    assert "trace-profile.perf" in pending_profiles

    # Test duplicity detection and pairing
    result = runner.invoke(cli.collect,
                           ['-c{}'.format(target), 'trace', '-f', 'main', '-f', 'main', '-fs',
                            'main', 2, '-fs', 'main', 2, '-s', 'BEFORE_CYCLE', '-ss',
                            'BEFORE_CYCLE', 3, '-s', 'BEFORE_CYCLE_end', '-s',
                            'BEFORE_CYCLE#BEFORE_CYCLE_end', '-ss', 'TEST_SINGLE', 4, '-s',
                            'TEST_SINGLE2', '-fs', 'test', -3] + binary)
    assert result.exit_code == 0
    # Compare the created script with the correct one
    assert _compare_collect_scripts(_get_latest_collect_script(script_dir),
                                    os.path.join(script_dir, 'cmp_script.txt'))

    # Test negative global sampling
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-g -2'] + binary)
    assert result.exit_code == 0

    # Try missing parameter -c
    # Fixme: before fails but still produces 0?
    result = runner.invoke(cli.collect, ['trace'] + binary)
    assert result.exit_code == 0

    # Try invalid parameter --method
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-minvalid'] + binary)
    assert result.exit_code == 2

    # Try binary parameter that is actually not executable ELF
    target = os.path.join(script_dir, 'cpp_sources', 'tst.cpp')
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace'])
    assert result.exit_code == 0
    assert 'is not an executable ELF file.' in result.output


def test_collect_trace_strategies(monkeypatch, pcs_full):
    """Test various trace collector strategies

    Expecting no errors and correctly generated scripts
    """
    monkeypatch.setattr(stap, 'systemtap_collect', _mocked_stap)
    monkeypatch.setattr(strategy, '_static_stap_extractor', _mocked_stap_extraction)
    runner = CliRunner()

    script_dir = os.path.join(os.path.split(__file__)[0], 'collect_trace')
    target = os.path.join(script_dir, 'tst')

    # Test simple userspace strategy without external modification or sampling
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-m', 'userspace'])
    assert result.exit_code == 0
    assert _compare_collect_scripts(_get_latest_collect_script(script_dir),
                                    os.path.join(script_dir, 'strategy1_script.txt'))
    # Test simple u_sampled strategy without external modification
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-m', 'u_sampled'])
    assert result.exit_code == 0
    assert _compare_collect_scripts(_get_latest_collect_script(script_dir),
                                    os.path.join(script_dir, 'strategy2_script.txt'))
    # Test simple all strategy without external modification or sampling
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-m', 'all'])
    assert result.exit_code == 0
    assert _compare_collect_scripts(_get_latest_collect_script(script_dir),
                                    os.path.join(script_dir, 'strategy3_script.txt'))
    # Test simple a_sampled strategy without external modification
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-m', 'a_sampled'])
    assert result.exit_code == 0
    assert _compare_collect_scripts(_get_latest_collect_script(script_dir),
                                    os.path.join(script_dir, 'strategy4_script.txt'))
    # Change the mocked static extractor to empty one
    monkeypatch.setattr(strategy, '_static_stap_extractor', _mocked_stap_extraction_empty)
    # Test userspace strategy without static probes and added global_sampling
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-m', 'userspace',
                                         '--no-static', '-g', '10'])
    assert result.exit_code == 0
    assert _compare_collect_scripts(_get_latest_collect_script(script_dir),
                                    os.path.join(script_dir, 'strategy5_script.txt'))
    # Test u_sampled strategy without static probes and overriden global_sampling
    # The output should be exactly the same as the previous
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-m', 'u_sampled',
                                         '--no-static', '-g', '10'])
    assert result.exit_code == 0
    assert _compare_collect_scripts(_get_latest_collect_script(script_dir),
                                    os.path.join(script_dir, 'strategy5_script.txt'))
    # Test userspace strategy with overridden function, respecified function and invalid function
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-m', 'userspace', '-fs',
                                         'main', '4', '-f', '_Z12QuickSortBadPii', '-f', 'invalid'])
    assert result.exit_code == 0
    assert _compare_collect_scripts(_get_latest_collect_script(script_dir),
                                    os.path.join(script_dir, 'strategy6_script.txt'))
    # Test userspace strategy with invalid static probe (won't be detected as --no-static is used)
    result = runner.invoke(cli.collect, ['-c{}'.format(target), 'trace', '-m', 'userspace',
                                         '--no-static', '-s', 'INVALID'])
    assert result.exit_code == 0
    assert _compare_collect_scripts(_get_latest_collect_script(script_dir),
                                    os.path.join(script_dir, 'strategy7_script.txt'))


def test_show_help(pcs_full):
    """Test running show to see if there are registered modules for showing

    Expecting no error and help outputed, where the currently supported modules will be shown
    """
    runner = CliRunner()
    result = runner.invoke(cli.show, ['--help'])
    assert result.exit_code == 0
    assert 'heapmap' in result.output
    assert 'raw' in result.output


def test_add_massaged_head(helpers, pcs_full, valid_profile_pool):
    """Test running add with tags instead of profile

    Expecting no errors and profile added as it should, or errors for incorrect revs
    """
    git_repo = git.Repo(os.path.split(pcs_full.get_path())[0])
    head = str(git_repo.head.commit)
    helpers.populate_repo_with_untracked_profiles(pcs_full.get_path(), valid_profile_pool)
    first_tagged = os.path.relpath(
        helpers.prepare_profile(
            pcs_full.get_job_directory(), valid_profile_pool[0], head
        )
    )

    runner = CliRunner()
    result = runner.invoke(cli.add, ['0@p', '--minor=HEAD'])
    assert result.exit_code == 0
    assert "'{}' successfully registered".format(first_tagged) in result.output

    runner = CliRunner()
    result = runner.invoke(cli.add, ['0@p', r"--minor=HEAD^{d"])
    assert result.exit_code == 2
    assert "Missing closing brace"

    runner = CliRunner()
    result = runner.invoke(cli.add, ['0@p', r"--minor=HEAD^}"])
    assert result.exit_code == 2

    runner = CliRunner()
    result = runner.invoke(cli.add, ['0@p', '--minor=tag2'])
    assert result.exit_code == 2
    assert "Ref 'tag2' did not resolve to object"


def test_add_tag(helpers, pcs_full, valid_profile_pool):
    """Test running add with tags instead of profile

    Expecting no errors and profile added as it should
    """
    git_repo = git.Repo(os.path.split(pcs_full.get_path())[0])
    head = str(git_repo.head.commit)
    parent = str(git_repo.head.commit.parents[0])
    helpers.populate_repo_with_untracked_profiles(pcs_full.get_path(), valid_profile_pool)
    first_sha = os.path.relpath(helpers.prepare_profile(
        pcs_full.get_job_directory(), valid_profile_pool[0], head)
    )
    os.path.relpath(helpers.prepare_profile(
        pcs_full.get_job_directory(), valid_profile_pool[1], parent)
    )

    runner = CliRunner()
    result = runner.invoke(cli.add, ['0@p'])
    assert result.exit_code == 0
    assert "'{}' successfully registered".format(first_sha) in result.output

    runner = CliRunner()
    result = runner.invoke(cli.add, ['0@p'])
    assert result.exit_code == 1
    assert "originates from minor version '{}'".format(parent) in result.output

    result = runner.invoke(cli.add, ['10@p'])
    assert result.exit_code == 2
    assert '0@p' in result.output


def test_add_tag_range(helpers, pcs_full, valid_profile_pool):
    """Test running add with tags instead of profile

    Expecting no errors and profile added as it should
    """
    git_repo = git.Repo(os.path.split(pcs_full.get_path())[0])
    head = str(git_repo.head.commit)
    helpers.populate_repo_with_untracked_profiles(pcs_full.get_path(), valid_profile_pool)
    os.path.relpath(helpers.prepare_profile(
        pcs_full.get_job_directory(), valid_profile_pool[0], head)
    )
    os.path.relpath(helpers.prepare_profile(
        pcs_full.get_job_directory(), valid_profile_pool[1], head)
    )

    runner = CliRunner()
    result = runner.invoke(cli.add, ['10@p-0@p'])
    assert result.exit_code == 0
    assert 'successfully registered 0 profiles in index'

    result = runner.invoke(cli.add, ['0@p-10@p'])
    print(result.output)
    assert result.exit_code == 0
    assert 'successfully registered 2 profiles in index'

    # Nothing should remain!
    result = runner.invoke(cli.status, [])
    assert "no untracked" in result.output


def test_remove_tag(pcs_full):
    """Test running remove with tags instead of profile

    Expecting no errors and profile removed as it should
    """
    runner = CliRunner()
    result = runner.invoke(cli.remove, ['0@i'])
    assert result.exit_code == 0
    assert "removed" in result.output


def test_remove_tag_range(helpers, pcs_full):
    """Test running remove with range of tags instead of profile

    Expecting no errors and profile removed as it should
    """
    runner = CliRunner()
    result = runner.invoke(cli.remove, ['10@i-0@i'])
    assert result.exit_code == 0
    assert "removed 0 from index" in result.output

    result = runner.invoke(cli.remove, ['0@i-10@i'])
    assert result.exit_code == 0
    assert "removed 2 from index" in result.output

    # Nothing should remain!
    result = runner.invoke(cli.status, [])
    assert "no tracked" in result.output
    assert result.exit_code == 0


def test_postprocess_tag(helpers, pcs_full, valid_profile_pool):
    """Test running postprocessby with various valid and invalid tags

    Expecting no errors (or caught errors), everything postprocessed as it should be
    """
    helpers.populate_repo_with_untracked_profiles(pcs_full.get_path(), valid_profile_pool)
    pending_dir = os.path.join(pcs_full.get_path(), 'jobs')
    assert len(os.listdir(pending_dir)) == 2

    runner = CliRunner()
    result = runner.invoke(cli.postprocessby, ['0@p', 'normalizer'])
    assert result.exit_code == 0
    assert len(os.listdir(pending_dir)) == 3

    # Try incorrect tag -> expect failure and return code 2 (click error)
    result = runner.invoke(cli.postprocessby, ['666@p', 'normalizer'])
    assert result.exit_code == 2
    assert len(os.listdir(pending_dir)) == 3

    # Try correct index tag
    result = runner.invoke(cli.postprocessby, ['1@i', 'normalizer'])
    assert result.exit_code == 0
    assert len(os.listdir(pending_dir)) == 4

    # Try incorrect index tag -> expect failure and return code 2 (click error)
    result = runner.invoke(cli.postprocessby, ['1337@i', 'normalizer'])
    assert result.exit_code == 2
    assert len(os.listdir(pending_dir)) == 4

    # Try absolute postprocessing
    first_in_jobs = os.listdir(pending_dir)[0]
    absolute_first_in_jobs = os.path.join(pending_dir, first_in_jobs)
    result = runner.invoke(cli.postprocessby, [absolute_first_in_jobs, 'normalizer'])
    assert result.exit_code == 0

    # Try lookup postprocessing
    result = runner.invoke(cli.postprocessby, [first_in_jobs, 'normalizer'])
    assert result.exit_code == 0


def test_show_tag(helpers, pcs_full, valid_profile_pool, monkeypatch):
    """Test running show with several valid and invalid tags

    Expecting no errors (or caught errors), everythig shown as it should be
    """
    helpers.populate_repo_with_untracked_profiles(pcs_full.get_path(), valid_profile_pool)
    pending_dir = os.path.join(pcs_full.get_path(), 'jobs')

    runner = CliRunner()
    result = runner.invoke(cli.show, ['0@p', 'raw'])
    assert result.exit_code == 0

    # Try incorrect tag -> expect failure and return code 2 (click error)
    result = runner.invoke(cli.show, ['1337@p', 'raw'])
    assert result.exit_code == 2

    # Try correct index tag
    result = runner.invoke(cli.show, ['0@i', 'raw'])
    assert result.exit_code == 0

    # Try incorrect index tag
    result = runner.invoke(cli.show, ['666@i', 'raw'])
    assert result.exit_code == 2

    # Try absolute showing
    first_in_jobs = os.listdir(pending_dir)[0]
    absolute_first_in_jobs = os.path.join(pending_dir, first_in_jobs)
    result = runner.invoke(cli.show, [absolute_first_in_jobs, 'raw'])
    assert result.exit_code == 0

    # Try lookup showing
    result = runner.invoke(cli.show, [first_in_jobs, 'raw'])
    assert result.exit_code == 0

    # Try iterating through files
    monkeypatch.setattr('click.confirm', lambda *_: True)
    result = runner.invoke(cli.show, ['prof', 'raw'])
    assert result.exit_code == 0

    # Try iterating through files, but none is confirmed to be true
    monkeypatch.setattr('click.confirm', lambda *_: False)
    result = runner.invoke(cli.show, ['prof', 'raw'])
    assert result.exit_code == 1

    # Try getting something from index
    result = runner.invoke(cli.show, ['prof-2-2017-03-20-21-40-42.perf', 'raw'])
    assert result.exit_code == 0


def test_config(pcs_full, monkeypatch):
    """Test running config

    Expecting no errors, everything shown as it should be
    """
    runner = CliRunner()

    # OK usage
    result = runner.invoke(cli.config, ['--local', 'get', 'vcs.type'])
    assert result.exit_code == 0

    result = runner.invoke(cli.config, ['--local', 'set', 'vcs.remote', 'url'])
    assert result.exit_code == 0

    # Error cli usage
    result = runner.invoke(cli.config, ['--local', 'get'])
    assert result.exit_code == 2

    result = runner.invoke(cli.config, ['--local', 'get', 'bogus.key'])
    assert result.exit_code == 1

    result = runner.invoke(cli.config, ['--local', 'set', 'key'])
    assert result.exit_code == 2

    result = runner.invoke(cli.config, ['--local', 'get', 'wrong,key'])
    assert result.exit_code == 2
    assert "invalid format" in result.output

    # Try to run the monkey-patched editor
    def donothing(*_):
        pass

    monkeypatch.setattr('perun.utils.run_external_command', donothing)
    result = runner.invoke(cli.config, ['--local', 'edit'])
    assert result.exit_code == 0

    def raiseexc(*_):
        raise exceptions.ExternalEditorErrorException

    monkeypatch.setattr('perun.utils.run_external_command', raiseexc)
    result = runner.invoke(cli.config, ['--local', 'edit'])
    assert result.exit_code == 1


@pytest.mark.usefixtures('cleandir')
def test_reset_outside_pcs(monkeypatch):
    """Tests resetting of configuration outside of the perun scope

    Excepts error when resetting local config, and no error when resetting global config
    """
    runner = CliRunner()
    result = runner.invoke(cli.config, ['--local', 'reset'])
    assert result.exit_code == 1
    assert "could not reset" in result.output

    monkeypatch.setattr('perun.logic.config.lookup_shared_config_dir', lambda: os.getcwd())
    result = runner.invoke(cli.config, ['--shared', 'reset'])
    assert result.exit_code == 0


def test_reset(pcs_full):
    """Tests resetting of configuration within the perun scope

    Excepts no error at all
    """
    runner = CliRunner()
    pcs_path = os.getcwd()
    with open(os.path.join(pcs_path, '.perun', 'local.yml'), 'r') as local_config:
        contents = "".join(local_config.readlines())
        assert '#     - make' in contents
        assert '#   collect_before_check' in contents

    result = runner.invoke(cli.config, ['--local', 'reset', 'developer'])
    assert result.exit_code == 0

    with open(os.path.join(pcs_path, '.perun', 'local.yml'), 'r') as local_config:
        contents = "".join(local_config.readlines())
        assert 'make' in contents
        assert 'collect_before_check' in contents


def test_check_profiles(helpers, pcs_with_degradations):
    """Tests checking degradation between two profiles"""
    pool_path = os.path.join(os.path.split(__file__)[0], 'degradation_profiles')
    profiles = [
        os.path.join(pool_path, 'linear_base.perf'),
        os.path.join(pool_path, 'linear_base_degradated.perf'),
        os.path.join(pool_path, 'quad_base.perf')
    ]
    helpers.populate_repo_with_untracked_profiles(pcs_with_degradations.get_path(), profiles)

    runner = CliRunner()
    for tag in ("0@p", "1@p", "2@p"):
        result = runner.invoke(cli.check_profiles, ["0@i", tag])
        assert result.exit_code == 0


def test_check_head(pcs_with_degradations, monkeypatch):
    """Test checking degradation for one point of history

    Expecting correct behaviours
    """
    runner = CliRunner()

    # Initialize the matrix for the further collecting
    matrix = config.Config('local', '', {
        'vcs': {'type': 'git', 'url': '../'},
        'cmds': ['ls'],
        'args': ['-al'],
        'workloads': ['.', '..'],
        'collectors': [
            {'name': 'time', 'params': {}}
        ],
        'postprocessors': [],
    })
    monkeypatch.setattr("perun.logic.config.local", lambda _: matrix)

    result = runner.invoke(cli.check_head, [])
    assert result.exit_code == 0

    # Try the precollect and various combinations of options
    result = runner.invoke(cli.check_group, ['-c', 'head'])
    assert result.exit_code == 0
    assert config.runtime().get('degradation.collect_before_check')
    config.runtime().data.clear()

    # Try to sink it to black hole
    log_dir = pcs_with_degradations.get_log_directory()
    shutil.rmtree(log_dir)
    store.touch_dir(log_dir)
    config.runtime().set('degradation', {})
    config.runtime().set('degradation.collect_before_check', 'true')
    config.runtime().set('degradation.log_collect', 'false')
    result = runner.invoke(cli.cli, ['--no-pager', 'check', 'head'])
    assert len(os.listdir(log_dir)) == 0
    assert result.exit_code == 0

    # First lets clear all the objects
    object_dir = pcs_with_degradations.get_object_directory()
    shutil.rmtree(object_dir)
    store.touch_dir(object_dir)
    # Clear the pre_collect_profiles cache
    check.pre_collect_profiles.minor_version_cache.clear()
    assert len(os.listdir(object_dir)) == 0
    # Collect for the head commit
    result = runner.invoke(cli.run, ['matrix'])
    assert result.exit_code == 0

    config.runtime().set('degradation.log_collect', 'true')
    result = runner.invoke(cli.cli, ['--no-pager', 'check', 'head'])
    assert len(os.listdir(log_dir)) >= 1
    assert result.exit_code == 0
    config.runtime().data.clear()


def test_check_all(pcs_with_degradations):
    """Test checking degradation for whole history

    Expecting correct behaviours
    """
    runner = CliRunner()
    result = runner.invoke(cli.check_group, [])
    assert result.exit_code == 0

    result = runner.invoke(cli.check_all, [])
    assert result.exit_code == 0


@pytest.mark.usefixtures('cleandir')
def test_utils_create(monkeypatch, tmpdir):
    """Tests creating stuff in the perun"""
    # Prepare different directory
    monkeypatch.setattr('perun.utils.script_helpers.__file__', os.path.join(str(tmpdir), "utils", "script_helpers.py"))
    monkeypatch.chdir(str(tmpdir))

    runner = CliRunner()
    result = runner.invoke(cli.create, ['postprocess', 'mypostprocessor', '--no-edit'])
    assert result.exit_code == 1
    assert "cannot use" in result.output and "as target developer directory" in result.output

    # Now correctly initialize the directory structure
    tmpdir.mkdir('collect')
    tmpdir.mkdir('postprocess')
    tmpdir.mkdir('view')
    tmpdir.mkdir('check')

    # Try to successfully create the new postprocessor
    result = runner.invoke(cli.create, ['postprocess', 'mypostprocessor', '--no-edit'])
    assert result.exit_code == 0
    target_dir = os.path.join(str(tmpdir), 'postprocess', 'mypostprocessor')
    created_files = os.listdir(target_dir)
    assert '__init__.py' in created_files
    assert 'run.py' in created_files

    # Try to successfully create the new collector
    result = runner.invoke(cli.create, ['collect', 'mycollector', '--no-edit'])
    assert result.exit_code == 0
    target_dir = os.path.join(str(tmpdir), 'collect', 'mycollector')
    created_files = os.listdir(target_dir)
    assert '__init__.py' in created_files
    assert 'run.py' in created_files

    # Try to successfully create the new collector
    result = runner.invoke(cli.create, ['view', 'myview', '--no-edit'])
    assert result.exit_code == 0
    target_dir = os.path.join(str(tmpdir), 'view', 'myview')
    created_files = os.listdir(target_dir)
    assert '__init__.py' in created_files
    assert 'run.py' in created_files

    # Try to successfully create the new collector
    result = runner.invoke(cli.create, ['check', 'mycheck', '--no-edit'])
    assert result.exit_code == 0
    target_dir = os.path.join(str(tmpdir), 'check')
    created_files = os.listdir(target_dir)
    assert 'mycheck.py' in created_files

    # Try to run the monkey-patched editor
    def donothing(*_):
        pass

    monkeypatch.setattr('perun.utils.run_external_command', donothing)
    result = runner.invoke(cli.create, ['check', 'mydifferentcheck'])
    assert result.exit_code == 0

    def raiseexc(*_):
        raise exceptions.ExternalEditorErrorException

    monkeypatch.setattr('perun.utils.run_external_command', raiseexc)
    result = runner.invoke(cli.create, ['check', 'mythirdcheck'])
    assert result.exit_code == 1


def test_run(pcs_full, monkeypatch):
    matrix = config.Config('local', '', {
        'vcs': {'type': 'git', 'url': '../'},
        'cmds': ['ls'],
        'args': ['-al'],
        'workloads': ['.', '..'],
        'collectors': [
            {'name': 'time', 'params': {}}
        ],
        'postprocessors': [],
        'execute': {
            'pre_run': [
                'ls | grep "."',
            ]
        }
    })
    monkeypatch.setattr("perun.logic.config.local", lambda _: matrix)
    runner = CliRunner()
    result = runner.invoke(cli.run, ['-c', 'matrix'])
    assert result.exit_code == 0

    # Test unsupported option
    result = runner.invoke(cli.run, ['-f', 'matrix'])
    assert result.exit_code == 1
    assert "is unsupported" in result.output

    job_dir = pcs_full.get_job_directory()
    job_profiles = os.listdir(job_dir)
    assert len(job_profiles) >= 2

    config.runtime().set('profiles.register_after_run', 'true')
    # Try to store the generated crap not in jobs
    jobs_before = len(os.listdir(job_dir))
    # Need to sleep, since in travis this could rewrite the stuff
    time.sleep(1)
    result = runner.invoke(cli.run, ['matrix'])
    jobs_after = len(os.listdir(job_dir))
    assert result.exit_code == 0
    assert jobs_before == jobs_after
    config.runtime().set('profiles.register_after_run', 'false')

    script_dir = os.path.split(__file__)[0]
    source_dir = os.path.join(script_dir, 'collect_trace')
    job_config_file = os.path.join(source_dir, 'job.yml')
    result = runner.invoke(cli.run, [
        'job',
        '--cmd', 'ls',
        '--args', '-al',
        '--workload', '.',
        '--collector', 'time',
        '--collector-params', 'time', 'param: key',
        '--collector-params', 'time', '{}'.format(job_config_file)
    ])
    assert result.exit_code == 0
    job_profiles = os.listdir(job_dir)
    assert len(job_profiles) >= 3

    # Run the matrix with error in prerun phase
    saved_func = utils.run_safely_external_command

    def run_wrapper(cmd):
        if cmd == 'ls | grep "."':
            return b"hello", b"world"
        else:
            return saved_func(cmd)

    monkeypatch.setattr('perun.utils.run_safely_external_command', run_wrapper)
    matrix.data['execute']['pre_run'].append('ls | grep dafad')
    result = runner.invoke(cli.run, ['matrix'])
    assert result.exit_code == 1


def test_fuzzing(pcs_full):
    """Runs basic tests for fuzzing CLI """
    runner = CliRunner()
    result = runner.invoke(cli.fuzz_cmd, [
        '--cmd', 'ls',
        '--args', '-al',
        '--initial-workload', '.',
        '--collector', 'time'
    ])
    assert result.exit_code == 0


def test_error_runs(pcs_full, monkeypatch):
    """Try various error states induced by job matrix"""
    matrix = config.Config('local', '', {
        'vcs': {'type': 'git', 'url': '../'},
        'args': ['-al'],
        'workloads': ['.', '..'],
        'postprocessors': [
            {'name': 'fokume', 'params': {}}
        ],
        'execute': {
            'pre_run': [
                'ls | grep "."',
            ]
        }
    })
    monkeypatch.setattr("perun.logic.config.local", lambda _: matrix)
    runner = CliRunner()
    result = runner.invoke(cli.run, ['matrix'])
    assert result.exit_code == 1
    assert "missing 'collectors'" in result.output

    matrix.data['collectors'] = [
        {'name': 'tome', 'params': {}}
    ]

    result = runner.invoke(cli.run, ['matrix'])
    assert result.exit_code == 1
    assert "missing 'cmds'" in result.output
    matrix.data['cmds'] = ['ls']

    result = runner.invoke(cli.run, ['matrix', '-q'])
    assert result.exit_code == 0
    assert "tome does not exist" in result.output
    matrix.data['collectors'][0]['name'] = 'time'

    result = runner.invoke(cli.run, ['matrix', '-q'])
    assert result.exit_code == 0
    assert "fokume does not exist" in result.output
