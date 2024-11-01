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

import datetime
import os

from _core.constants import ModeType
from _core.constants import ConfigConst
from _core.exception import ParamError
from _core.executor.source import TestSource
from _core.logger import platform_logger
from _core.plugin import Config
from _core.plugin import Plugin
from _core.plugin import get_plugin
from _core.testkit.json_parser import JsonParser
from _core.utils import get_kit_instances

__all__ = ["Descriptor", "Task", "Request"]
LOG = platform_logger("Request")


class Descriptor:
    """
    The descriptor for a test or suite
    """

    def __init__(self, uuid=None, name=None, source=None, container=False):
        self.unique_id = uuid
        self.display_name = name
        self.tags = {}
        self.source = source
        self.parent = None
        self.children = []
        self.container = container

    def get_container(self):
        return self.container

    def get_unique_id(self):
        return self.unique_id


class Task:
    """
    TestTask describes the tree of tests and suites
    """
    EMPTY_TASK = "empty"
    TASK_CONFIG_SUFFIX = ".json"
    TASK_CONFIG_DIR = "config"

    def __init__(self, root=None, drivers=None, config=None):
        self.root = root
        self.test_drivers = drivers or []
        self.config = config or Config()

    def init(self, config):
        from xdevice import Variables
        from xdevice import Scheduler
        start_time = datetime.datetime.now()
        LOG.debug("StartTime=%s" % start_time.strftime("%Y-%m-%d %H:%M:%S"))

        self.config.update(config.__dict__)
        if getattr(config, ConfigConst.report_path, "") == "":
            Variables.task_name = start_time.strftime('%Y-%m-%d-%H-%M-%S')
        else:
            Variables.task_name = config.report_path

        # create a report folder to store test report
        report_path = os.path.join(Variables.exec_dir,
                                   Variables.report_vars.report_dir,
                                   Variables.task_name)
        os.makedirs(report_path, exist_ok=True)
        self._check_report_path(report_path)

        log_path = os.path.join(report_path, Variables.report_vars.log_dir)
        os.makedirs(log_path, exist_ok=True)

        self.config.kits = []
        if getattr(config, "task", ""):
            task_file = config.task + self.TASK_CONFIG_SUFFIX
            task_dir = self._get_task_dir(task_file)
            self._load_task(task_dir, task_file)

        self.config.top_dir = Variables.top_dir
        self.config.exec_dir = Variables.exec_dir
        self.config.report_path = report_path
        self.config.log_path = log_path
        self.config.start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
        Scheduler.start_task_log(self.config.log_path)
        Scheduler.start_encrypt_log(self.config.log_path)
        LOG.info("Report path: %s", report_path)

    def _get_task_dir(self, task_file):
        from xdevice import Variables
        exec_task_dir = os.path.abspath(
            os.path.join(Variables.exec_dir, self.TASK_CONFIG_DIR))
        if not os.path.exists(os.path.join(exec_task_dir, task_file)):
            if os.path.normcase(Variables.exec_dir) == \
                    os.path.normcase(Variables.top_dir):
                raise ParamError("task file %s not exists, please add task "
                                 "file to '%s'" % (task_file, exec_task_dir),
                                 error_no="00101")

            top_task_dir = os.path.abspath(
                os.path.join(Variables.top_dir, self.TASK_CONFIG_DIR))
            if not os.path.exists(os.path.join(top_task_dir, task_file)):
                raise ParamError("task file %s not exists, please add task "
                                 "file to '%s' or '%s'" % (
                                     task_file, exec_task_dir, top_task_dir),
                                 error_no="00101")
            else:
                return top_task_dir
        else:
            return exec_task_dir

    def _load_task(self, task_dir, file_name):
        task_file = os.path.join(task_dir, file_name)
        if not os.path.exists(task_file):
            raise ParamError("task file %s not exists" % task_file,
                             error_no="00101")

        # add kits to self.config
        json_config = JsonParser(task_file)
        kits = get_kit_instances(json_config, self.config.resource_path,
                                 self.config.testcases_path)
        self.config.kits.extend(kits)

    def set_root_descriptor(self, root):
        if not isinstance(root, Descriptor):
            raise TypeError("need 'Descriptor' type param")

        self.root = root
        self._init_driver(root)
        if not self.test_drivers:
            LOG.error("No test driver to execute", error_no="00106")

    def _init_driver(self, test_descriptor):
        from xdevice import Scheduler

        plugin_id = None
        source = test_descriptor.source
        ignore_test = ""
        if isinstance(source, TestSource):
            if source.test_type is not None:
                plugin_id = source.test_type
            else:
                ignore_test = source.module_name
                LOG.error("'%s' no test driver specified" % source.test_name,
                          error_no="00106")

        drivers = get_plugin(plugin_type=Plugin.DRIVER, plugin_id=plugin_id)
        if plugin_id is not None:
            if len(drivers) == 0:
                ignore_test = source.module_name
                error_message = "'%s' can not find test driver '%s'" % (
                    source.test_name, plugin_id)
                LOG.error(error_message, error_no="00106")
                if Scheduler.mode == ModeType.decc:
                    error_message = "Load Error[00106]"
                    Scheduler.report_not_executed(self.config.report_path, [
                        ("", test_descriptor)], error_message)
            else:
                check_result = False
                for driver in drivers:
                    driver_instance = driver.__class__()
                    device_options = Scheduler.get_device_options(
                        self.config.__dict__, source)
                    check_result = driver_instance.__check_environment__(
                        device_options)
                    if check_result or check_result is None:
                        self.test_drivers.append(
                            (driver_instance, test_descriptor))
                        break
                if check_result is False:
                    LOG.error("'%s' can not find suitable test driver '%s'" %
                              (source.test_name, plugin_id), error_no="00106")
        if ignore_test and hasattr(self.config, ConfigConst.component_mapper):
            getattr(self.config, ConfigConst.component_mapper).pop(ignore_test)

        for desc in test_descriptor.children:
            self._init_driver(desc)

    @classmethod
    def _check_report_path(cls, report_path):
        for _, _, files in os.walk(report_path):
            for _file in files:
                if _file.endswith(".xml"):
                    raise ParamError("xml file exists in '%s'" % report_path,
                                     error_no="00105")


class Request:
    """
    Provides the necessary information for TestDriver to execute its tests.
    """

    def __init__(self, uuid=None, root=None, listeners=None, config=None):
        self.uuid = uuid
        self.root = root
        self.listeners = listeners if listeners else []
        self.config = config

    def get_listeners(self):
        return self.listeners

    def get_config(self):
        return self.config

    def get(self, key=None, default=""):
        # get value from self.config
        if not key:
            return default
        return getattr(self.config, key, default)

    def get_devices(self):
        if self.config is None:
            return []
        if not hasattr(self.config, "environment"):
            return []
        if not hasattr(self.config.environment, "devices"):
            return []
        return getattr(self.config.environment, "devices", [])

    def get_config_file(self):
        return self._get_source_value("config_file")

    def get_source_file(self):
        return self._get_source_value("source_file")

    def get_test_name(self):
        return self._get_source_value("test_name")

    def get_source_string(self):
        return self._get_source_value("source_string")

    def get_test_type(self):
        return self._get_source_value("test_type")

    def get_module_name(self):
        return self._get_source_value("module_name")

    def _get_source(self):
        if not hasattr(self.root, "source"):
            return ""
        return getattr(self.root, "source", "")

    def _get_source_value(self, key=None, default=""):
        if not key:
            return default
        source = self._get_source()
        if not source:
            return default
        return getattr(source, key, default)
