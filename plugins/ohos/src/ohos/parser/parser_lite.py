#!/usr/bin/env python3
# coding=utf-8

#
# Copyright (c) 2020-2022 Huawei Device Co., Ltd.
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

import copy
import re
import time
import datetime
from queue import Queue

from xdevice import IParser
from xdevice import Plugin
from xdevice import StateRecorder
from xdevice import TestDescription
from xdevice import LifeCycle
from xdevice import ResultCode
from xdevice import platform_logger
from xdevice import check_pub_key_exist

from ohos.constants import ParserType

__all__ = ["CppTestListParserLite", "CTestParser", "OpenSourceParser",
           "CppTestParserLite"]

_INFORMATIONAL_START = "[----------]"
_TEST_START_RUN_TAG = "[==========] Running"
_TEST_RUN_TAG = "[==========]"
_CPP_TEST_DRYRUN_TAG = "Running main() "
_TEST_START_TAG = "[ RUN      ]"
_TEST_OK_TAG = "[       OK ]"
_TEST_SKIPPED_TAG = "[  SKIPPED ]"
_TEST_FAILED_TAG = "[  FAILED  ]"
_ALT_OK_TAG = "[    OK    ]"
_TIMEOUT_TAG = "[ TIMEOUT  ]"

_CTEST_START_TEST_RUN_TAG = "Framework inited."
_CTEST_END_TEST_RUN_TAG = "Framework finished."
_CTEST_SUITE_TEST_RUN_TAG = "Start to run test suite:"
_CTEST_SUITE_TIME_RUN_TAG = "Run test suite "
_CTEST_SETUP_TAG = "setup"
_CTEST_RUN_TAG = "-----------------------"

_TEST_PASSED_LOWER = "pass"

_COMPILE_PASSED = "compile PASSED"
_COMPILE_PARA = r"(.* compile .*)"

_PRODUCT_PARA = r"(.*The .* is .*)"
_PRODUCT_PARA_START = r"To Obtain Product Params Start"
_PRODUCT_PARA_END = r"To Obtain Product Params End"

_START_JSUNIT_RUN_MARKER = "[start] start run suites"
_START_JSUNIT_SUITE_RUN_MARKER = "[suite start]"
_START_JSUNIT_SUITE_END_MARKER = "[suite end]"
_END_JSUNIT_RUN_MARKER = "[end] run suites end"
_PASS_JSUNIT_MARKER = "[%s]" % "pass"
_FAIL_JSUNIT_MARKER = "[fail]"
_ACE_LOG_MARKER = "[Console Info]"

LOG = platform_logger("ParserLite")


@Plugin(type=Plugin.PARSER, id=ParserType.cpp_test_lite)
class CppTestParserLite(IParser):
    def __init__(self):
        self.state_machine = StateRecorder()
        self.suite_name = ""
        self.listeners = []
        self.product_info = {}
        self.is_params = False

    def get_suite_name(self):
        return self.suite_name

    def get_listeners(self):
        return self.listeners

    def __process__(self, lines):
        if not self.state_machine.suites_is_started():
            self.state_machine.trace_logs.extend(lines)
        for line in lines:
            if not check_pub_key_exist():
                LOG.debug(line)
            self.parse(line)

    def __done__(self):
        suite_result = self.state_machine.suite()
        suite_result.is_completed = True
        for listener in self.get_listeners():
            suite = copy.copy(suite_result)
            listener.__ended__(LifeCycle.TestSuite, suite, is_clear=True)
        self.state_machine.running_test_index = 0

        suites_result = self.state_machine.get_suites()
        if not suites_result.suites_name:
            return
        for listener in self.get_listeners():
            suites = copy.copy(suites_result)
            listener.__ended__(LifeCycle.TestSuites, test_result=suites,
                               suites_name=suites.suites_name,
                               product_info=suites.product_info)
        self.state_machine.current_suites = None

    @staticmethod
    def _is_test_run(line):
        return True if _TEST_RUN_TAG in line else False

    @staticmethod
    def _is_test_start_run(line):
        return True if _TEST_START_RUN_TAG in line else False

    @staticmethod
    def _is_informational_start(line):
        return True if _INFORMATIONAL_START in line else False

    @staticmethod
    def _is_test_start(line):
        return True if _TEST_START_TAG in line else False

    def _process_informational_line(self, line):
        pattern = r"(.*) (\(\d+ ms total\))"
        message = line[len(_INFORMATIONAL_START):].strip()
        if re.match(pattern, line.strip()):
            self.handle_suite_ended_tag(message)
        elif re.match(r'(\d+) test[s]? from (.*)', message):
            self.handle_suite_started_tag(message)

    def _process_test_run_line(self, line):
        if not self.state_machine.suites_is_running():
            return
        message = line[len(_TEST_RUN_TAG):].strip()
        self.handle_suites_ended_tag(message)

    def parse(self, line):
        if _PRODUCT_PARA_START in line:
            self.is_params = True
        elif _PRODUCT_PARA_END in line:
            self.is_params = False
        if re.match(_PRODUCT_PARA, line) and self.is_params:
            handle_product_info(line, self.product_info)

        if self.state_machine.suites_is_started() or self._is_test_run(line):
            if self._is_test_start_run(line):
                self.handle_suites_started_tag(line)
            elif self._is_informational_start(line):
                self._process_informational_line(line)
            elif self._is_test_run(line):
                self._process_test_run_line(line)
            elif self._is_test_start(line):
                message = line[line.index(_TEST_START_TAG) +
                               len(_TEST_START_TAG):].strip()
                self.handle_test_started_tag(message)
            else:
                self.process_test(line)

    def process_test(self, line):
        if _TEST_SKIPPED_TAG in line:
            message = line[line.index(_TEST_SKIPPED_TAG) + len(
                _TEST_SKIPPED_TAG):].strip()
            if not self.state_machine.test_is_running():
                LOG.error(
                    "Found {} without {} before, wrong GTest log format".
                        format(line, _TEST_START_TAG), error_no="00405")
                return
            self.handle_test_ended_tag(message, ResultCode.SKIPPED)
        elif _TEST_OK_TAG in line:
            message = line[line.index(_TEST_OK_TAG) + len(
                _TEST_OK_TAG):].strip()
            if not self.state_machine.test_is_running():
                LOG.error(
                    "Found {} without {} before, wrong GTest log format".
                        format(line, _TEST_START_TAG), error_no="00405")
                return
            self.handle_test_ended_tag(message, ResultCode.PASSED)
        elif _ALT_OK_TAG in line:
            message = line[line.index(_ALT_OK_TAG) + len(
                _ALT_OK_TAG):].strip()
            self.fake_run_marker(message)
            self.handle_test_ended_tag(message, ResultCode.PASSED)
        elif _TEST_FAILED_TAG in line:
            message = line[line.index(_TEST_FAILED_TAG) + len(
                _TEST_FAILED_TAG):].strip()
            if not self.state_machine.suite_is_running():
                return
            if not self.state_machine.test_is_running():
                self.fake_run_marker(message)
            self.handle_test_ended_tag(message, ResultCode.FAILED)
        elif _TIMEOUT_TAG in line:
            message = line[line.index(_TIMEOUT_TAG) + len(
                _TIMEOUT_TAG):].strip()
            self.fake_run_marker(message)
            self.handle_test_ended_tag(message, ResultCode.FAILED)
        elif self.state_machine.test_is_running():
            self.append_test_output(line)

    def handle_test_started_tag(self, message):
        test_class, test_name, _ = self.parse_test_description(message)
        test_result = self.state_machine.test(reset=True)
        test_result.test_class = test_class
        test_result.test_name = test_name
        for listener in self.get_listeners():
            test_result = copy.copy(test_result)
            listener.__started__(LifeCycle.TestCase, test_result)

    @classmethod
    def parse_test_description(cls, message):
        run_time = 0
        matcher = re.match(r'(.*) \((\d+) ms\)(.*)', message)
        if matcher:
            test_class, test_name = matcher.group(1).rsplit(".", 1)
            run_time = int(matcher.group(2))
        else:
            test_class, test_name = message.rsplit(".", 1)
        return test_class.split(" ")[-1], test_name.split(" ")[0], run_time

    def handle_test_ended_tag(self, message, test_status):
        test_class, test_name, run_time = self.parse_test_description(
            message)
        test_result = self.state_machine.test()
        test_result.run_time = int(run_time)
        test_result.code = test_status.value
        if not test_result.is_running():
            LOG.error(
                "Test has no start tag when trying to end test: %s", message,
                error_no="00405")
            return
        found_unexpected_test = False
        if test_result.test_class != test_class:
            LOG.error(
                "Expected class: {} but got:{} ".format(test_result.test_class,
                                                        test_class),
                error_no="00405")
            found_unexpected_test = True
        if test_result.test_name != test_name:
            LOG.error(
                "Expected test: {} but got: {}".format(test_result.test_name,
                                                       test_name),
                error_no="00405")
            found_unexpected_test = True
        test_result.current = self.state_machine.running_test_index + 1
        self.state_machine.test().is_completed = True
        if found_unexpected_test:
            test_result.code = ResultCode.FAILED.value

        for listener in self.get_listeners():
            result = copy.copy(test_result)
            listener.__ended__(LifeCycle.TestCase, result)
        self.state_machine.running_test_index += 1

    def fake_run_marker(self, message):
        fake_marker = re.compile(" +").split(message)
        self.handle_test_started_tag(fake_marker)

    def handle_suites_started_tag(self, message):
        self.state_machine.get_suites(reset=True)
        matcher = re.match(r'.* Running (\d+) test[s]? from .*', message)
        expected_test_num = int(matcher.group(1)) if matcher else -1
        if expected_test_num >= 0:
            test_suites = self.state_machine.get_suites()
            test_suites.suites_name = self.get_suite_name()
            test_suites.test_num = expected_test_num
            test_suites.product_info = self.product_info
            for listener in self.get_listeners():
                suite_report = copy.copy(test_suites)
                listener.__started__(LifeCycle.TestSuites, suite_report)

    def handle_suite_started_tag(self, message):
        self.state_machine.suite(reset=True)
        matcher = re.match(r'(\d+) test[s]? from (.*)', message)
        expected_test_num = int(matcher.group(1)) if matcher else -1
        if expected_test_num >= 0:
            test_suite = self.state_machine.suite()
            test_suite.suite_name = matcher.group(2)
            test_suite.test_num = expected_test_num
            for listener in self.get_listeners():
                suite_report = copy.copy(test_suite)
                listener.__started__(LifeCycle.TestSuite, suite_report)

    def handle_suite_ended_tag(self, message):
        suite_result = self.state_machine.suite()
        matcher = re.match(r'.*\((\d+) ms total\)', message)
        if matcher:
            suite_result.run_time = int(matcher.group(1))
        suite_result.is_completed = True
        for listener in self.get_listeners():
            suite = copy.copy(suite_result)
            listener.__ended__(LifeCycle.TestSuite, suite, is_clear=True)
        self.state_machine.running_test_index = 0

    def handle_suites_ended_tag(self, message):
        suites = self.state_machine.get_suites()
        matcher = re.match(r'.*\((\d+) ms total\)', message)
        if matcher:
            suites.run_time = int(matcher.group(1))
        suites.is_completed = True
        for listener in self.get_listeners():
            copy_suites = copy.copy(suites)
            listener.__ended__(LifeCycle.TestSuites, test_result=copy_suites,
                               suites_name=suites.suites_name,
                               product_info=suites.product_info)

    def append_test_output(self, message):
        if self.state_machine.test().stacktrace:
            self.state_machine.test().stacktrace = "{}\r\n".format(
                self.state_machine.test().stacktrace)
        self.state_machine.test().stacktrace = "{}{}".format(
            self.state_machine.test().stacktrace, message)

    @staticmethod
    def handle_test_run_failed(error_msg):
        if not error_msg:
            error_msg = "Unknown error"
        if not check_pub_key_exist():
            LOG.debug("Error msg:%s" % error_msg)

    def mark_test_as_failed(self, test):
        if not self.state_machine.current_suite and not test.class_name:
            return
        suites_result = self.state_machine.get_suites(reset=True)
        suites_result.suites_name = self.get_suite_name()

        suite_name = self.state_machine.current_suite.suite_name if \
            self.state_machine.current_suite else None
        suite_result = self.state_machine.suite(reset=True)
        test_result = self.state_machine.test(reset=True)
        suite_result.suite_name = suite_name or test.class_name
        suite_result.suite_num = 1
        test_result.test_class = test.class_name
        test_result.test_name = test.test_name
        test_result.stacktrace = "error_msg: Unknown error"
        test_result.num_tests = 1
        test_result.run_time = 0
        test_result.code = ResultCode.FAILED.value
        for listener in self.get_listeners():
            suite_report = copy.copy(suites_result)
            listener.__started__(LifeCycle.TestSuites, suite_report)
        for listener in self.get_listeners():
            suite_report = copy.copy(suite_result)
            listener.__started__(LifeCycle.TestSuite, suite_report)
        for listener in self.get_listeners():
            test_result = copy.copy(test_result)
            listener.__started__(LifeCycle.TestCase, test_result)
        for listener in self.get_listeners():
            test_result = copy.copy(test_result)
            listener.__ended__(LifeCycle.TestCase, test_result)
        for listener in self.get_listeners():
            suite_report = copy.copy(suite_result)
            listener.__ended__(LifeCycle.TestSuite, suite_report,
                               is_clear=True)
        self.__done__()


@Plugin(type=Plugin.PARSER, id=ParserType.cpp_test_list_lite)
class CppTestListParserLite(IParser):
    def __init__(self):
        self.last_test_class_name = None
        self.state_machine = StateRecorder()
        self.listeners = []
        self.tests = []
        self.suites_name = ""
        self.class_result = None
        self.method_result = None

    def __process__(self, lines):
        for line in lines:
            if not check_pub_key_exist():
                LOG.debug(line)
            self.parse(line)

    def get_suite_name(self):
        return self.suites_name

    def get_listeners(self):
        return self.listeners

    def __done__(self):
        if self.state_machine.is_started():
            self.handle_suite_ended_tag()
        suites_result = self.state_machine.get_suites()
        if not suites_result.suites_name:
            return
        for listener in self.get_listeners():
            suites = copy.copy(suites_result)
            listener.__ended__(LifeCycle.TestSuites, test_result=suites,
                               suites_name=suites.suites_name)
        self.state_machine.current_suites = None

    def _is_class(self, line):
        self.class_result = re.compile('^([a-zA-Z]+.*)\\.$').match(line)
        return self.class_result

    def _is_method(self, line):
        self.method_result = re.compile(
            '\\s+([a-zA-Z_]+[\\S]*)(.*)?(\\s+.*)?$').match(line)
        return self.method_result

    def _process_class_line(self, line):
        del line
        if not self.state_machine.suites_is_started():
            self.handle_suites_started_tag()
        self.last_test_class_name = self.class_result.group(1)
        if self.state_machine.is_started():
            self.handle_suite_ended_tag()
        self.handle_suite_started_tag(self.class_result.group(1))

    def _process_method_line(self, line):
        if not self.last_test_class_name:
            LOG.error(
                "Parsed new test case name %s but no test class"
                " name has been set" % line, error_no="00405")
        else:
            test = TestDescription(self.last_test_class_name,
                                   self.method_result.group(1))
            self.tests.append(test)
            self.handle_test_tag(self.last_test_class_name,
                                 self.method_result.group(1))

    @staticmethod
    def _is_cpp_test_dryrun(line):
        return True if line.find(_CPP_TEST_DRYRUN_TAG) != -1 else False

    def parse(self, line):
        if self.state_machine.suites_is_started() or self._is_cpp_test_dryrun(
                line):
            if self._is_cpp_test_dryrun(line):
                self.handle_suites_started_tag()
            elif self._is_class(line):
                self._process_class_line(line)
            elif self._is_method(line):
                self._process_method_line(line)
            else:
                if not check_pub_key_exist():
                    LOG.debug("Line ignored: %s" % line)

    def handle_test_tag(self, test_class, test_name):
        test_result = self.state_machine.test(reset=True)
        test_result.test_class = test_class
        test_result.test_name = test_name
        for listener in self.get_listeners():
            test_result = copy.copy(test_result)
            listener.__started__(LifeCycle.TestCase, test_result)
        self.state_machine.test().is_completed = True
        test_result.code = ResultCode.SKIPPED.value
        for listener in self.get_listeners():
            result = copy.copy(test_result)
            listener.__ended__(LifeCycle.TestCase, result)
        self.state_machine.running_test_index += 1
        test_suites = self.state_machine.get_suites()
        test_suite = self.state_machine.suite()
        test_suites.test_num += 1
        test_suite.test_num += 1

    def handle_suites_started_tag(self):
        self.state_machine.get_suites(reset=True)
        test_suites = self.state_machine.get_suites()
        test_suites.suites_name = self.get_suite_name()
        test_suites.test_num = 0
        for listener in self.get_listeners():
            suite_report = copy.copy(test_suites)
            listener.__started__(LifeCycle.TestSuites, suite_report)

    def handle_suite_started_tag(self, class_name):
        self.state_machine.suite(reset=True)
        test_suite = self.state_machine.suite()
        test_suite.suite_name = class_name
        test_suite.test_num = 0
        for listener in self.get_listeners():
            test_suite_copy = copy.copy(test_suite)
            listener.__started__(LifeCycle.TestSuite, test_suite_copy)

    def handle_suite_ended_tag(self):
        suite_result = self.state_machine.suite()
        suite_result.is_completed = True
        for listener in self.get_listeners():
            suite = copy.copy(suite_result)
            listener.__ended__(LifeCycle.TestSuite, suite)

    def handle_suites_ended_tag(self):
        suites = self.state_machine.get_suites()
        suites.is_completed = True
        for listener in self.get_listeners():
            copy_suites = copy.copy(suites)
            listener.__ended__(LifeCycle.TestSuites, test_result=copy_suites,
                               suites_name=suites.suites_name)

    def mark_test_as_failed(self, test):
        if not self.state_machine.current_suite and not test.class_name:
            return
        suite_name = self.state_machine.current_suite.suite_name if \
            self.state_machine.current_suite else None
        suite_result = self.state_machine.suite(reset=True)
        test_result = self.state_machine.test(reset=True)
        suite_result.suite_name = suite_name or test.class_name
        suite_result.suite_num = 1
        test_result.test_class = test.class_name
        test_result.test_name = test.test_name
        test_result.stacktrace = "error_msg: Unknown error"
        test_result.num_tests = 1
        test_result.run_time = 0
        test_result.code = ResultCode.FAILED.value
        for listener in self.get_listeners():
            suite_report = copy.copy(suite_result)
            listener.__started__(LifeCycle.TestSuite, suite_report)
        for listener in self.get_listeners():
            test_result = copy.copy(test_result)
            listener.__started__(LifeCycle.TestCase, test_result)
        for listener in self.get_listeners():
            test_result = copy.copy(test_result)
            listener.__ended__(LifeCycle.TestCase, test_result)
        self.__done__()


@Plugin(type=Plugin.PARSER, id=ParserType.ctest_lite)
class CTestParser(IParser):
    last_line = ""
    pattern = r"(\d{4}-\d{1,2}-\d{1,2}\s\d{1,2}:\d{1,2}:\d{1,2}\.\d{3}) "

    def __init__(self):
        self.state_machine = StateRecorder()
        self.suites_name = ""
        self.listeners = []
        self.product_info = {}
        self.is_params = False
        self.result_lines = []

    def get_suite_name(self):
        return self.suites_name

    def get_listeners(self):
        return self.listeners

    def __process__(self, lines):
        if not self.state_machine.suites_is_started():
            self.state_machine.trace_logs.extend(lines)
        for line in lines:
            self.parse(line)

    def __done__(self):
        suites = self.state_machine.get_suites()
        suites.is_completed = True

        for listener in self.get_listeners():
            listener.__ended__(LifeCycle.TestSuites, test_result=suites,
                               suites_name=suites.suites_name,
                               product_info=suites.product_info)
        self.state_machine.current_suites = None

    @staticmethod
    def _is_ctest_start_test_run(line):
        return True if line.endswith(_CTEST_START_TEST_RUN_TAG) else False

    @staticmethod
    def _is_ctest_end_test_run(line):
        return True if line.endswith(_CTEST_END_TEST_RUN_TAG) else False

    @staticmethod
    def _is_ctest_run(line):
        return re.match(r"[\s\S]*(Tests)[\s\S]*(Failures)[\s\S]*(Ignored)[\s\S]*", line)

    def _is_ctest_suite_test_run(self, line):
        return re.match("{}{}".format(self.pattern, _CTEST_SUITE_TEST_RUN_TAG),
                        line)

    def is_ctest_suite_time_run(self, line):
        return re.match("{}{}".format(self.pattern, _CTEST_SUITE_TIME_RUN_TAG),
                        line)

    def _process_ctest_suite_test_run_line(self, line):
        _, message_index = re.match(
            "{}{}".format(self.pattern, _CTEST_SUITE_TEST_RUN_TAG),
            line).span()
        self.handle_suite_started_tag(line[message_index:].strip())

    @staticmethod
    def _is_execute_result_line(line):
        return re.match(
            r"(.*" + "\\.c:" + "\\d+:.*:(PASS|FAIL|OK|IGNORE"")\\.*)",
            line.strip())

    @staticmethod
    def _is_result_line(line):
        return line.find("PASS") != -1 or line.find("FAIL") != -1 or line.find(
            "IGNORE") != -1

    def parse(self, line):
        self._parse_product_info(line)

        if self.state_machine.suites_is_started() or \
                self._is_ctest_start_test_run(line):
            try:
                test_matcher = re.match(r".*(\d+ Tests).+", line)
                failed_matcher = \
                    re.match(r".*(Failures).*", line)
                ignore_matcher = \
                    re.match(r".*(Ignored).*", line)
                if (test_matcher or failed_matcher or ignore_matcher) and \
                        not self._is_ctest_run(line):
                    if test_matcher:
                        self.result_lines.append(test_matcher.group(1))
                    if failed_matcher:
                        self.result_lines.append(failed_matcher.group(1))
                    if ignore_matcher:
                        self.result_lines.append(ignore_matcher.group(1))
                        line = " ".join(self.result_lines)
                        self.result_lines.clear()
                if self._is_ctest_start_test_run(line):
                    self.handle_suites_started_tag()
                elif self._is_ctest_end_test_run(line):
                    self.process_suites_ended_tag()
                elif self._is_ctest_run(line):
                    self.handle_suite_ended_tag(line)
                elif self._is_ctest_suite_test_run(line) and \
                        not self.state_machine.suite_is_running():
                    self._process_ctest_suite_test_run_line(line)
                elif self.is_ctest_suite_time_run(line) and \
                        not self.state_machine.suite_is_running():
                    self.handle_suite_started_tag(line)
                elif self._is_result_line(line) and \
                        self.state_machine.suite_is_running():
                    if line.find(":") != -1 and line.count(
                            ":") >= 3 and self._is_execute_result_line(line):
                        self.handle_one_test_tag(line.strip(), False)
                    else:
                        self.handle_one_test_tag(line.strip(), True)
            except AttributeError as _:
                LOG.error("Parsing log: %s failed" % (line.strip()),
                          error_no="00405")
            self.last_line = line

    def _parse_product_info(self, line):
        if _PRODUCT_PARA_START in line:
            self.is_params = True
        elif _PRODUCT_PARA_END in line:
            self.is_params = False
        if self.is_params and re.match(_PRODUCT_PARA, line):
            handle_product_info(line, self.product_info)

    def parse_error_test_description(self, message):
        end_time = re.match(self.pattern, message).group().strip()
        start_time = re.match(self.pattern,
                              self.last_line.strip()).group().strip()
        start_timestamp = int(time.mktime(
            time.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f"))) * 1000 + int(
            start_time.split(".")[-1])
        end_timestamp = int(time.mktime(
            time.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f"))) * 1000 + int(
            end_time.split(".")[-1])
        run_time = end_timestamp - start_timestamp
        status_dict = {"PASS": ResultCode.PASSED, "FAIL": ResultCode.FAILED,
                       "IGNORE": ResultCode.SKIPPED}
        status = ""
        if message.find("PASS") != -1:
            status = "PASS"
        elif message.find("FAIL") != -1:
            status = "FAIL"
        elif message.find("IGNORE") != -1:
            status = "IGNORE"
        status = status_dict.get(status)
        return "", "", status, run_time

    def parse_test_description(self, message):

        test_class = message.split(".c:")[0].split(" ")[-1].split("/")[-1]
        message_index = message.index(".c:")
        end_time = re.match(self.pattern, message).group().strip()
        start_time = re.match(self.pattern,
                              self.last_line.strip()).group().strip()
        start_timestamp = int(time.mktime(
            time.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f"))) * 1000 + int(
            start_time.split(".")[-1])
        end_timestamp = int(time.mktime(
            time.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f"))) * 1000 + int(
            end_time.split(".")[-1])
        run_time = end_timestamp - start_timestamp
        message_list = message[message_index + 3:].split(":")
        test_name, status = message_list[1].strip(), message_list[2].strip()
        status_dict = {"PASS": ResultCode.PASSED, "FAIL": ResultCode.FAILED,
                       "IGNORE": ResultCode.SKIPPED}
        status = status_dict.get(status)
        return test_class, test_name, status, run_time

    def handle_one_test_tag(self, message, is_error):
        if is_error:
            test_class, test_name, status, run_time = \
                self.parse_error_test_description(message)
        else:
            test_class, test_name, status, run_time = \
                self.parse_test_description(message)
        test_result = self.state_machine.test(reset=True)
        test_result.test_class = test_class
        test_result.test_name = test_name
        test_result.run_time = run_time
        self.state_machine.running_test_index += 1
        test_result.current = self.state_machine.running_test_index
        test_result.code = status.value
        self.state_machine.suite().run_time += run_time
        for listener in self.get_listeners():
            test_result = copy.copy(test_result)
            listener.__started__(LifeCycle.TestCase, test_result)

        test_suite = self.state_machine.suite()
        test_suites = self.state_machine.get_suites()

        found_unexpected_test = False

        if found_unexpected_test or ResultCode.FAILED == status:
            if "FAIL:" in message and not message.endswith("FAIL:"):
                test_result.stacktrace = message[
                                         message.rindex("FAIL:") + len(
                                             "FAIL:"):]
            for listener in self.get_listeners():
                result = copy.copy(test_result)
                listener.__failed__(LifeCycle.TestCase, result)
        elif ResultCode.SKIPPED == status:
            for listener in self.get_listeners():
                result = copy.copy(test_result)
                listener.__failed__(LifeCycle.TestCase, result)

        self.state_machine.test().is_completed = True
        test_suite.test_num += 1
        test_suites.test_num += 1

        for listener in self.get_listeners():
            result = copy.copy(test_result)
            listener.__ended__(LifeCycle.TestCase, result)

    def handle_suites_started_tag(self):
        self.state_machine.get_suites(reset=True)
        test_suites = self.state_machine.get_suites()
        test_suites.suites_name = self.suites_name
        test_suites.product_info = self.product_info
        test_suites.test_num = 0
        for listener in self.get_listeners():
            suite_report = copy.copy(test_suites)
            listener.__started__(LifeCycle.TestSuites, suite_report)

    def handle_suite_started_tag(self, message):
        if re.match("{}{}".format(self.pattern, _CTEST_SUITE_TIME_RUN_TAG),
                    message.strip()):
            message = self.state_machine.suite().suite_name
        self.state_machine.suite(reset=True)
        test_suite = self.state_machine.suite()
        test_suite.suite_name = message
        test_suite.test_num = 0
        for listener in self.get_listeners():
            suite_report = copy.copy(test_suite)
            listener.__started__(LifeCycle.TestSuite, suite_report)

    def handle_suite_ended_tag(self, line):
        suite_result = self.state_machine.suite()
        suites = self.state_machine.get_suites()
        suite_result.run_time = suite_result.run_time
        suites.run_time += suite_result.run_time
        suite_result.is_completed = True

        for listener in self.get_listeners():
            suite = copy.copy(suite_result)
            listener.__ended__(LifeCycle.TestSuite, suite, is_clear=True)
        self.state_machine.running_test_index = 0

    def process_suites_ended_tag(self):
        suites = self.state_machine.get_suites()
        suites.is_completed = True

        for listener in self.get_listeners():
            listener.__ended__(LifeCycle.TestSuites, test_result=suites,
                               suites_name=suites.suites_name,
                               product_info=suites.product_info)

    def append_test_output(self, message):
        if self.state_machine.test().stacktrace:
            self.state_machine.test().stacktrace = "{}\r\n".format(
                self.state_machine.test().stacktrace)
        self.state_machine.test().stacktrace = "{}{}".format(
            self.state_machine.test().stacktrace, message)


@Plugin(type=Plugin.PARSER, id=ParserType.open_source_test)
class OpenSourceParser(IParser):
    def __init__(self):
        self.state_machine = StateRecorder()
        self.suite_name = ""
        self.test_name = ""
        self.test_num = 1
        self.listeners = []
        self.output = ""
        self.lines = []
        self.start_time = None

    def get_suite_name(self):
        return self.suite_name

    def get_listeners(self):
        return self.listeners

    def __process__(self, lines):
        if not self.start_time:
            self.start_time = datetime.datetime.now()
        self.lines.extend(lines)

    def __done__(self):
        if not self.state_machine.suites_is_started():
            self.state_machine.trace_logs.extend(self.lines)
        self.handle_suite_started_tag(self.test_num)

        test_result = self.state_machine.test(reset=True,
                                              test_index=self.test_name)
        test_result.run_time = 0
        test_result.test_class = self.suite_name
        test_result.test_name = self.test_name
        test_result.test_num = 1
        test_result.current = 1
        for listener in self.get_listeners():
            result = copy.copy(test_result)
            listener.__started__(LifeCycle.TestCase, result)
        for line in self.lines:
            self.output = "{}{}".format(self.output, line)
            if _TEST_PASSED_LOWER in line.lower():
                test_result.code = ResultCode.PASSED.value
                if self.start_time:
                    end_time = datetime.datetime.now()
                    run_time = (end_time - self.start_time).total_seconds()
                    test_result.run_time = int(run_time * 1000)
                for listener in self.get_listeners():
                    result = copy.copy(test_result)
                    listener.__ended__(LifeCycle.TestCase, result)
                break
        else:
            test_result.code = ResultCode.FAILED.value
            test_result.stacktrace = "\\n".join(self.lines)
            if self.start_time:
                end_time = datetime.datetime.now()
                run_time = (end_time - self.start_time).total_seconds()
                test_result.run_time = int(run_time * 1000)
            for listener in self.get_listeners():
                result = copy.copy(test_result)
                listener.__ended__(LifeCycle.TestCase, result)

        self.state_machine.test().is_completed = True
        self.handle_suite_ended_tag()

    def handle_suite_started_tag(self, test_num):
        test_suite = self.state_machine.suite()
        if test_num >= 0:
            test_suite.suite_name = self.suite_name
            test_suite.test_num = test_num
            for listener in self.get_listeners():
                suite_report = copy.copy(test_suite)
                listener.__started__(LifeCycle.TestSuite, suite_report)

    def handle_suite_ended_tag(self):
        suite_result = self.state_machine.suite()
        for listener in self.get_listeners():
            suite = copy.copy(suite_result)
            listener.__ended__(LifeCycle.TestSuite, suite,
                               suite_report=True)


@Plugin(type=Plugin.PARSER, id=ParserType.build_only_test)
class BuildOnlyParser(IParser):
    def __init__(self):
        self.state_machine = StateRecorder()
        self.suite_name = ""
        self.test_name = ""
        self.test_num = 0
        self.listeners = []
        self.output = ""

    def get_suite_name(self):
        return self.suite_name

    def get_listeners(self):
        return self.listeners

    def __process__(self, lines):
        if not self.state_machine.suites_is_started():
            self.state_machine.trace_logs.extend(lines)
        self.handle_suite_started_tag(self.test_num)

        self.state_machine.running_test_index = \
            self.state_machine.running_test_index + 1

        for line in lines:
            if re.match(_COMPILE_PARA, line):
                self.test_name = str(line).split('compile')[0].strip()
                test_result = self.state_machine.test(reset=True)
                test_result.run_time = 0
                test_result.test_class = self.suite_name
                test_result.test_name = self.test_name
                for listener in self.get_listeners():
                    result = copy.copy(test_result)
                    listener.__started__(LifeCycle.TestCase, result)
                if _COMPILE_PASSED in line:
                    test_result.code = ResultCode.PASSED.value
                    for listener in self.get_listeners():
                        result = copy.copy(test_result)
                        listener.__ended__(LifeCycle.TestCase, result)
                else:
                    test_result.code = ResultCode.FAILED.value
                    for listener in self.get_listeners():
                        result = copy.copy(test_result)
                        listener.__failed__(LifeCycle.TestCase, result)
        self.state_machine.test().is_completed = True

    def __done__(self):
        self.handle_suite_ended_tag()

    def handle_suite_started_tag(self, test_num):
        test_suite = self.state_machine.suite()
        if test_num >= 0:
            test_suite.suite_name = self.suite_name
            test_suite.test_num = test_num
            for listener in self.get_listeners():
                suite_report = copy.copy(test_suite)
                listener.__started__(LifeCycle.TestSuite, suite_report)

    def handle_suite_ended_tag(self):
        suite_result = self.state_machine.suite()
        for listener in self.get_listeners():
            suite = copy.copy(suite_result)
            listener.__ended__(LifeCycle.TestSuite, suite,
                               suite_report=True)


@Plugin(type=Plugin.PARSER, id=ParserType.jsuit_test_lite)
class JSUnitParserLite(IParser):
    last_line = ""
    pattern = r"(\d{1,2}-\d{1,2}\s\d{1,2}:\d{1,2}:\d{1,2}\.\d{3}) "

    def __init__(self):
        self.state_machine = StateRecorder()
        self.suites_name = ""
        self.listeners = []

    def get_listeners(self):
        return self.listeners

    def __process__(self, lines):
        if not self.state_machine.suites_is_started():
            self.state_machine.trace_logs.extend(lines)
        for line in lines:
            self.parse(line)

    def __done__(self):
        pass

    def parse(self, line):
        if (self.state_machine.suites_is_started() or
            line.find(_START_JSUNIT_RUN_MARKER) != -1) and \
                line.find(_ACE_LOG_MARKER) != -1:
            if line.find(_START_JSUNIT_RUN_MARKER) != -1:
                self.handle_suites_started_tag()
            elif line.endswith(_END_JSUNIT_RUN_MARKER):
                self.handle_suites_ended_tag()
            elif line.find(_START_JSUNIT_SUITE_RUN_MARKER) != -1:
                self.handle_suite_started_tag(line.strip())
            elif line.endswith(_START_JSUNIT_SUITE_END_MARKER):
                self.handle_suite_ended_tag()
            elif _PASS_JSUNIT_MARKER in line or _FAIL_JSUNIT_MARKER \
                    in line:
                self.handle_one_test_tag(line.strip())
            self.last_line = line

    def parse_test_description(self, message):
        pattern = r"\[(pass|fail)\]"
        year = time.strftime("%Y")
        filter_message = message.split("[Console Info]")[1].strip()
        end_time = "%s-%s" % \
                   (year, re.match(self.pattern, message).group().strip())
        start_time = "%s-%s" % \
                     (year, re.match(self.pattern,
                                     self.last_line.strip()).group().strip())
        start_timestamp = int(time.mktime(
            time.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f"))) * 1000 + int(
            start_time.split(".")[-1])
        end_timestamp = int(time.mktime(
            time.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f"))) * 1000 + int(
            end_time.split(".")[-1])
        run_time = end_timestamp - start_timestamp
        _, status_end_index = re.match(pattern, filter_message).span()
        status = filter_message[:status_end_index]
        test_name = filter_message[status_end_index:]
        status_dict = {"pass": ResultCode.PASSED, "fail": ResultCode.FAILED,
                       "ignore": ResultCode.SKIPPED}
        status = status_dict.get(status[1:-1])
        return test_name, status, run_time

    def handle_suites_started_tag(self):
        self.state_machine.get_suites(reset=True)
        test_suites = self.state_machine.get_suites()
        test_suites.suites_name = self.suites_name
        test_suites.test_num = 0
        for listener in self.get_listeners():
            suite_report = copy.copy(test_suites)
            listener.__started__(LifeCycle.TestSuites, suite_report)

    def handle_suites_ended_tag(self):
        suites = self.state_machine.get_suites()
        suites.is_completed = True

        for listener in self.get_listeners():
            listener.__ended__(LifeCycle.TestSuites, test_result=suites,
                               suites_name=suites.suites_name)

    def handle_one_test_tag(self, message):
        test_name, status, run_time = \
            self.parse_test_description(message)
        test_result = self.state_machine.test(reset=True)
        test_suite = self.state_machine.suite()
        test_result.test_class = test_suite.suite_name
        test_result.test_name = test_name
        test_result.run_time = run_time
        test_result.code = status.value
        test_result.current = self.state_machine.running_test_index + 1
        self.state_machine.suite().run_time += run_time
        for listener in self.get_listeners():
            test_result = copy.copy(test_result)
            listener.__started__(LifeCycle.TestCase, test_result)

        test_suites = self.state_machine.get_suites()
        found_unexpected_test = False

        if found_unexpected_test or ResultCode.FAILED == status:
            for listener in self.get_listeners():
                result = copy.copy(test_result)
                listener.__failed__(LifeCycle.TestCase, result)
        elif ResultCode.SKIPPED == status:
            for listener in self.get_listeners():
                result = copy.copy(test_result)
                listener.__skipped__(LifeCycle.TestCase, result)

        self.state_machine.test().is_completed = True
        test_suite.test_num += 1
        test_suites.test_num += 1
        for listener in self.get_listeners():
            result = copy.copy(test_result)
            listener.__ended__(LifeCycle.TestCase, result)
        self.state_machine.running_test_index += 1

    def fake_run_marker(self, message):
        fake_marker = re.compile(" +").split(message)
        self.processTestStartedTag(fake_marker)

    def handle_suite_started_tag(self, message):
        self.state_machine.suite(reset=True)
        test_suite = self.state_machine.suite()
        if re.match(r".*\[suite start\].*", message):
            _, index = re.match(r".*\[suite start\]", message).span()
        test_suite.suite_name = message[index:]
        test_suite.test_num = 0
        for listener in self.get_listeners():
            suite_report = copy.copy(test_suite)
            listener.__started__(LifeCycle.TestSuite, suite_report)

    def handle_suite_ended_tag(self):
        suite_result = self.state_machine.suite()
        suites = self.state_machine.get_suites()
        suite_result.run_time = suite_result.run_time
        suites.run_time += suite_result.run_time
        suite_result.is_completed = True

        for listener in self.get_listeners():
            suite = copy.copy(suite_result)
            listener.__ended__(LifeCycle.TestSuite, suite, is_clear=True)

    def append_test_output(self, message):
        if self.state_machine.test().stacktrace:
            self.state_machine.test().stacktrace = \
                "%s\r\n" % self.state_machine.test().stacktrace
        self.state_machine.test().stacktrace = \
            ''.join((self.state_machine.test().stacktrace, message))


def handle_product_info(message, product_info):
    message = message[message.index("The"):]
    items = message[len("The "):].split(" is ")
    product_info.setdefault(items[0].strip(),
                            items[1].strip().strip("[").strip("]"))
