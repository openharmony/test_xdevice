#!/usr/bin/env python3
# coding=utf-8

#
# Copyright (c) 2022 Huawei Device Co., Ltd.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import time

from xdevice import ParamError
from xdevice import IDriver
from xdevice import platform_logger
from xdevice import Plugin
from xdevice import get_plugin
from xdevice import JsonParser
from xdevice import ShellHandler
from xdevice import TestDescription
from xdevice import get_device_log_file
from xdevice import check_result_report
from xdevice import get_kit_instances
from xdevice import get_config_value
from xdevice import do_module_kit_setup
from xdevice import do_module_kit_teardown
from xdevice import DeviceTestType
from xdevice import CommonParserType
from xdevice import FilePermission
from xdevice import ShellCommandUnresponsiveException

from ohos.testkit.kit import oh_jsunit_para_parse
from ohos.executor.listener import CollectingPassListener

__all__ = ["OHJSUnitTestDriver", "OHKernelTestDriver"]

TIME_OUT = 300 * 1000

LOG = platform_logger("OpenHarmony")


@Plugin(type=Plugin.DRIVER, id=DeviceTestType.oh_kernel_test)
class OHKernelTestDriver(IDriver):
    """
        OpenHarmonyKernelTest
    """
    def __init__(self):
        self.timeout = 30 * 1000
        self.result = ""
        self.error_message = ""
        self.kits = []
        self.config = None
        self.runner = None

    def __check_environment__(self, device_options):
        pass

    def __check_config__(self, config):
        pass

    def __execute__(self, request):
        try:
            LOG.debug("Start to Execute OpenHarmony Kernel Test")

            self.config = request.config
            self.config.device = request.config.environment.devices[0]

            config_file = request.root.source.config_file

            self.result = "%s.xml" % \
                          os.path.join(request.config.report_path,
                                       "result", request.get_module_name())
            device_log = get_device_log_file(
                request.config.report_path,
                request.config.device.__get_serial__(),
                "device_log")

            hilog = get_device_log_file(
                request.config.report_path,
                request.config.device.__get_serial__(),
                "device_hilog")

            device_log_open = os.open(device_log, os.O_WRONLY | os.O_CREAT |
                                      os.O_APPEND, FilePermission.mode_755)
            hilog_open = os.open(hilog, os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                                 FilePermission.mode_755)
            with os.fdopen(device_log_open, "a") as log_file_pipe, \
                    os.fdopen(hilog_open, "a") as hilog_file_pipe:
                self.config.device.start_catch_device_log(log_file_pipe,
                                                          hilog_file_pipe)
                self._run_oh_kernel(config_file, request.listeners, request)
                log_file_pipe.flush()
                hilog_file_pipe.flush()
        except Exception as exception:
            self.error_message = exception
            if not getattr(exception, "error_no", ""):
                setattr(exception, "error_no", "03409")
            LOG.exception(self.error_message, exc_info=False, error_no="03409")
            raise exception
        finally:
            do_module_kit_teardown(request)
            self.config.device.stop_catch_device_log()
            self.result = check_result_report(
                request.config.report_path, self.result, self.error_message)

    def _run_oh_kernel(self, config_file, listeners=None, request=None):
        try:
            json_config = JsonParser(config_file)
            kits = get_kit_instances(json_config, self.config.resource_path,
                                     self.config.testcases_path)
            self._get_driver_config(json_config)
            do_module_kit_setup(request, kits)
            self.runner = OHKernelTestRunner(self.config)
            self.runner.suite_name = request.get_module_name()
            self.runner.run(listeners)
        finally:
            do_module_kit_teardown(request)

    def _get_driver_config(self, json_config):
        target_test_path = get_config_value('native-test-device-path',
                                            json_config.get_driver(), False)
        test_suite_name = get_config_value('test-suite-name',
                                           json_config.get_driver(), False)
        test_suites_list = get_config_value('test-suites-list',
                                            json_config.get_driver(), False)
        timeout_limit = get_config_value('timeout-limit',
                                         json_config.get_driver(), False)
        conf_file = get_config_value('conf-file',
                                     json_config.get_driver(), False)
        self.config.arg_list = {}
        if target_test_path:
            self.config.target_test_path = target_test_path
        if test_suite_name:
            self.config.arg_list["test-suite-name"] = test_suite_name
        if test_suites_list:
            self.config.arg_list["test-suites-list"] = test_suites_list
        if timeout_limit:
            self.config.arg_list["timeout-limit"] = timeout_limit
        if conf_file:
            self.config.arg_list["conf-file"] = conf_file
        timeout_config = get_config_value('shell-timeout',
                                          json_config.get_driver(), False)
        if timeout_config:
            self.config.timeout = int(timeout_config)
        else:
            self.config.timeout = TIME_OUT

    def __result__(self):
        return self.result if os.path.exists(self.result) else ""


class OHKernelTestRunner:
    def __init__(self, config):
        self.suite_name = None
        self.config = config
        self.arg_list = config.arg_list

    def run(self, listeners):
        handler = self._get_shell_handler(listeners)
        # hdc shell cd /data/local/tmp/OH_kernel_test;
        # sh runtest test -t OpenHarmony_RK3568_config
        # -n OpenHarmony_RK3568_skiptest -l 60
        command = "cd %s; chmod +x *; sh runtest test %s" % (
            self.config.target_test_path, self.get_args_command())
        self.config.device.execute_shell_command(
            command, timeout=self.config.timeout, receiver=handler, retry=0)

    def _get_shell_handler(self, listeners):
        parsers = get_plugin(Plugin.PARSER, CommonParserType.oh_kernel_test)
        if parsers:
            parsers = parsers[:1]
        parser_instances = []
        for parser in parsers:
            parser_instance = parser.__class__()
            parser_instance.suites_name = self.suite_name
            parser_instance.listeners = listeners
            parser_instances.append(parser_instance)
        handler = ShellHandler(parser_instances)
        return handler

    def get_args_command(self):
        args_commands = ""
        for key, value in self.arg_list.items():
            if key == "test-suite-name" or key == "test-suites-list":
                args_commands = "%s -t %s" % (args_commands, value)
            elif key == "conf-file":
                args_commands = "%s -n %s" % (args_commands, value)
            elif key == "timeout-limit":
                args_commands = "%s -l %s" % (args_commands, value)
        return args_commands


@Plugin(type=Plugin.DRIVER, id=DeviceTestType.oh_jsunit_test)
class OHJSUnitTestDriver(IDriver):
    """
       OHJSUnitTestDriver is a Test that runs a native test package on
       given device.
    """

    def __init__(self):
        self.timeout = 80 * 1000
        self.start_time = None
        self.result = ""
        self.error_message = ""
        self.kits = []
        self.config = None
        self.runner = None
        self.rerun = True
        self.rerun_all = True

    def __check_environment__(self, device_options):
        pass

    def __check_config__(self, config):
        pass

    def __execute__(self, request):
        try:
            LOG.debug("Start execute OpenHarmony JSUnitTest")
            self.result = os.path.join(
                request.config.report_path, "result",
                '.'.join((request.get_module_name(), "xml")))
            self.config = request.config
            self.config.device = request.config.environment.devices[0]

            config_file = request.root.source.config_file
            suite_file = request.root.source.source_file

            if not suite_file:
                raise ParamError(
                    "test source '%s' not exists" %
                    request.root.source.source_string, error_no="00110")
            LOG.debug("Test case file path: %s" % suite_file)
            self.config.device.set_device_report_path(request.config.report_path)

            hilog = get_device_log_file(request.config.report_path,
                                        request.config.device.__get_serial__() + "_" + request.
                                        get_module_name(),
                                        "device_hilog")

            hilog_open = os.open(hilog, os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                                 0o755)
            self.config.device.execute_shell_command(command="hilog -r")
            with os.fdopen(hilog_open, "a") as hilog_file_pipe:
                if hasattr(self.config.device, "clear_crash_log"):
                    self.config.device.clear_crash_log()
                self.config.device.start_catch_device_log(hilog_file_pipe=hilog_file_pipe)
                self._run_oh_jsunit(config_file, request)
        except Exception as exception:
            self.error_message = exception
            if not getattr(exception, "error_no", ""):
                setattr(exception, "error_no", "03409")
            LOG.exception(self.error_message, exc_info=True, error_no="03409")
            raise exception
        finally:
            serial = "{}_{}".format(str(self.config.device.__get_serial__()), time.time_ns())
            log_tar_file_name = "{}_{}".format(str(serial).replace(
                ":", "_"), request.get_module_name())
            if hasattr(self.config.device, "start_get_crash_log"):
                self.config.device.start_get_crash_log(log_tar_file_name)
            self.config.device.stop_catch_device_log()
            self.result = check_result_report(
                request.config.report_path, self.result, self.error_message)

    def __dry_run_execute__(self, request):
        LOG.debug("Start dry run xdevice JSUnit Test")
        self.config = request.config
        self.config.device = request.config.environment.devices[0]
        config_file = request.root.source.config_file
        suite_file = request.root.source.source_file

        if not suite_file:
            raise ParamError(
                "test source '%s' not exists" %
                request.root.source.source_string, error_no="00110")
        LOG.debug("Test case file path: %s" % suite_file)
        self._dry_run_oh_jsunit(config_file, request)

    def _dry_run_oh_jsunit(self, config_file, request):
        try:
            if not os.path.exists(config_file):
                LOG.error("Error: Test cases don't exist %s." % config_file)
                raise ParamError(
                    "Error: Test cases don't exist %s." % config_file,
                    error_no="00102")
            json_config = JsonParser(config_file)
            self.kits = get_kit_instances(json_config,
                                          self.config.resource_path,
                                          self.config.testcases_path)

            self._get_driver_config(json_config)
            self.config.device.connector_command("target mount")
            do_module_kit_setup(request, self.kits)
            self.runner = OHJSUnitTestRunner(self.config)
            self.runner.suites_name = request.get_module_name()
            # execute test case
            self._get_runner_config(json_config)
            oh_jsunit_para_parse(self.runner, self.config.testargs)

            test_to_run = self._collect_test_to_run()
            LOG.info("Collected suite count is: {}, test count is: {}".
                     format(len(self.runner.expect_tests_dict.keys()),
                            len(test_to_run) if test_to_run else 0))
        finally:
            do_module_kit_teardown(request)

    def _run_oh_jsunit(self, config_file, request):
        try:
            if not os.path.exists(config_file):
                LOG.error("Error: Test cases don't exist %s." % config_file)
                raise ParamError(
                    "Error: Test cases don't exist %s." % config_file,
                    error_no="00102")
            json_config = JsonParser(config_file)
            self.kits = get_kit_instances(json_config,
                                          self.config.resource_path,
                                          self.config.testcases_path)

            self._get_driver_config(json_config)
            self.config.device.connector_command("target mount")
            do_module_kit_setup(request, self.kits)
            self.runner = OHJSUnitTestRunner(self.config)
            self.runner.suites_name = request.get_module_name()
            if self.rerun:
                self.runner.retry_times = self.runner.MAX_RETRY_TIMES
            # execute test case
            self._get_runner_config(json_config)
            oh_jsunit_para_parse(self.runner, self.config.testargs)
            self._do_test_run(listener=request.listeners)

        finally:
            do_module_kit_teardown(request)

    def _get_driver_config(self, json_config):
        package = get_config_value('package-name',
                                   json_config.get_driver(), False)
        module = get_config_value('module-name',
                                  json_config.get_driver(), False)
        bundle = get_config_value('bundle-name',
                                  json_config. get_driver(), False)
        is_rerun = get_config_value('rerun', json_config.get_driver(), False)

        self.config.package_name = package
        self.config.module_name = module
        self.config.bundle_name = bundle
        self.rerun = True if is_rerun == 'true' else False

        if not package and not module:
            raise ParamError("Neither package nor module is found"
                             " in config file.", error_no="03201")
        timeout_config = get_config_value("shell-timeout",
                                          json_config.get_driver(), False)
        if timeout_config:
            self.config.timeout = int(timeout_config)
        else:
            self.config.timeout = TIME_OUT

    def _get_runner_config(self, json_config):
        test_timeout = get_config_value('test-timeout',
                                        json_config.get_driver(), False)
        if test_timeout:
            self.runner.add_arg("wait_time", int(test_timeout))

        testcase_timeout = get_config_value('testcase-timeout',
                                            json_config.get_driver(), False)
        if testcase_timeout:
            self.runner.add_arg("timeout", int(testcase_timeout))

    def _do_test_run(self, listener):
        test_to_run = self._collect_test_to_run()
        LOG.info("Collected suite count is: {}, test count is: {}".
                 format(len(self.runner.expect_tests_dict.keys()),
                        len(test_to_run) if test_to_run else 0))
        if not test_to_run or not self.rerun:
            self.runner.run(listener)
            self.runner.notify_finished()
        else:
            self._run_with_rerun(listener, test_to_run)

    def _collect_test_to_run(self):
        run_results = self.runner.dry_run()
        return run_results

    def _run_tests(self, listener):
        test_tracker = CollectingPassListener()
        listener_copy = listener.copy()
        listener_copy.append(test_tracker)
        self.runner.run(listener_copy)
        test_run = test_tracker.get_current_run_results()
        return test_run

    def _run_with_rerun(self, listener, expected_tests):
        LOG.debug("Ready to run with rerun, expect run: %s"
                  % len(expected_tests))
        test_run = self._run_tests(listener)
        self.runner.retry_times -= 1
        LOG.debug("Run with rerun, has run: %s" % len(test_run)
                  if test_run else 0)
        if len(test_run) < len(expected_tests):
            expected_tests = TestDescription.remove_test(expected_tests,
                                                         test_run)
            if not expected_tests:
                LOG.debug("No tests to re-run twice,please check")
                self.runner.notify_finished()
            else:
                self._rerun_twice(expected_tests, listener)
        else:
            LOG.debug("Rerun once success")
            self.runner.notify_finished()

    def _rerun_twice(self, expected_tests, listener):
        tests = []
        for test in expected_tests:
            tests.append("%s#%s" % (test.class_name, test.test_name))
        self.runner.add_arg("class", ",".join(tests))
        LOG.debug("Ready to rerun twice, expect run: %s" % len(expected_tests))
        test_run = self._run_tests(listener)
        self.runner.retry_times -= 1
        LOG.debug("Rerun twice, has run: %s" % len(test_run))
        if len(test_run) < len(expected_tests):
            expected_tests = TestDescription.remove_test(expected_tests,
                                                         test_run)
            if not expected_tests:
                LOG.debug("No tests to re-run third,please check")
                self.runner.notify_finished()
            else:
                self._rerun_third(expected_tests, listener)
        else:
            LOG.debug("Rerun twice success")
            self.runner.notify_finished()

    def _rerun_third(self, expected_tests, listener):
        tests = []
        for test in expected_tests:
            tests.append("%s#%s" % (test.class_name, test.test_name))
        self.runner.add_arg("class", ",".join(tests))
        LOG.debug("Rerun to rerun third, expect run: %s" % len(expected_tests))
        self._run_tests(listener)
        LOG.debug("Rerun third success")
        self.runner.notify_finished()

    def __result__(self):
        return self.result if os.path.exists(self.result) else ""


class OHJSUnitTestRunner:
    MAX_RETRY_TIMES = 3

    def __init__(self, config):
        self.arg_list = {}
        self.suites_name = None
        self.config = config
        self.rerun_attemp = 3
        self.suite_recorder = {}
        self.finished = False
        self.expect_tests_dict = dict()
        self.finished_observer = None
        self.retry_times = 1

    def dry_run(self):
        parsers = get_plugin(Plugin.PARSER, CommonParserType.oh_jsunit_list)
        if parsers:
            parsers = parsers[:1]
        parser_instances = []
        for parser in parsers:
            parser_instance = parser.__class__()
            parser_instances.append(parser_instance)
        handler = ShellHandler(parser_instances)
        command = self._get_dry_run_command()
        self.config.device.execute_shell_command(
            command, timeout=self.config.timeout, receiver=handler, retry=0)
        self.expect_tests_dict = parser_instances[0].tests_dict
        return parser_instances[0].tests

    def run(self, listener):
        handler = self._get_shell_handler(listener)
        command = self._get_run_command()
        self.config.device.execute_shell_command(
            command, timeout=self.config.timeout, receiver=handler, retry=0)

    def notify_finished(self):
        if self.finished_observer:
            self.finished_observer.notify_task_finished()
        self.retry_times -= 1

    def _get_shell_handler(self, listener):
        parsers = get_plugin(Plugin.PARSER, CommonParserType.oh_jsunit)
        if parsers:
            parsers = parsers[:1]
        parser_instances = []
        for parser in parsers:
            parser_instance = parser.__class__()
            parser_instance.suites_name = self.suites_name
            parser_instance.listeners = listener
            parser_instance.runner = self
            parser_instances.append(parser_instance)
            self.finished_observer = parser_instance
        handler = ShellHandler(parser_instances)
        return handler

    def add_arg(self, name, value):
        if not name or not value:
            return
        self.arg_list[name] = value

    def remove_arg(self, name):
        if not name:
            return
        if name in self.arg_list:
            del self.arg_list[name]

    def get_args_command(self):
        args_commands = ""
        for key, value in self.arg_list.items():
            if "wait_time" == key:
                args_commands = "%s -w %s " % (args_commands, value)
            else:
                args_commands = "%s -s %s %s " % (args_commands, key, value)
        return args_commands

    def _get_run_command(self):
        command = ""
        if self.config.package_name:
            # aa test -p ${packageName} -b ${bundleName}-s
            # unittest OpenHarmonyTestRunner
            command = "aa test -p %s -b %s -s unittest OpenHarmonyTestRunner" \
                      " %s" % (self.config.package_name,
                               self.config.bundle_name,
                               self.get_args_command())
        elif self.config.module_name:
            #  aa test -m ${moduleName}  -b ${bundleName}
            #  -s unittest OpenHarmonyTestRunner
            command = "aa test -m %s -b %s -s unittest OpenHarmonyTestRunner" \
                      " %s" % (self.config.module_name,
                               self.config.bundle_name,
                               self.get_args_command())
        return command

    def _get_dry_run_command(self):
        command = ""
        if self.config.package_name:
            command = "aa test -p %s -b %s -s unittest OpenHarmonyTestRunner" \
                      " %s -s dryRun true" % (self.config.package_name,
                                              self.config.bundle_name,
                                              self.get_args_command())
        elif self.config.module_name:
            command = "aa test -m %s -b %s -s unittest OpenHarmonyTestRunner" \
                      " %s -s dryRun true" % (self.config.module_name,
                                              self.config.bundle_name,
                                              self.get_args_command())

        return command
