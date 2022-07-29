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

import pkg_resources

from .variables import Variables
from _core.plugin import Plugin
from _core.plugin import get_plugin
from _core.logger import platform_logger
from _core.interface import IDriver
from _core.interface import IDevice
from _core.interface import IDeviceManager
from _core.interface import IParser
from _core.interface import LifeCycle
from _core.interface import IShellReceiver
from _core.interface import ITestKit
from _core.interface import IListener
from _core.interface import IReporter
from _core.exception import ParamError
from _core.exception import DeviceError
from _core.exception import LiteDeviceError
from _core.exception import ExecuteTerminate
from _core.exception import ReportException
from _core.exception import HdcError
from _core.exception import HdcCommandRejectedException
from _core.exception import ShellCommandUnresponsiveException
from _core.exception import DeviceUnresponsiveException
from _core.exception import AppInstallError
from _core.exception import HapNotSupportTest
from _core.constants import DeviceTestType
from _core.constants import DeviceLabelType
from _core.constants import ManagerType
from _core.constants import DeviceOsType
from _core.constants import ProductForm
from _core.constants import TestType
from _core.constants import CKit
from _core.constants import ConfigConst
from _core.constants import ModeType
from _core.constants import TestExecType
from _core.constants import ListenerType
from _core.constants import GTestConst
from _core.constants import CommonParserType
from _core.constants import FilePermission
from _core.constants import HostDrivenTestType
from _core.constants import DeviceConnectorType
from _core.config.config_manager import UserConfigManager
from _core.config.resource_manager import ResourceManager
from _core.executor.listener import CaseResult
from _core.executor.listener import SuiteResult
from _core.executor.listener import SuitesResult
from _core.executor.listener import StateRecorder
from _core.executor.listener import TestDescription
from _core.executor.listener import CollectingTestListener
from _core.testkit.json_parser import JsonParser
from _core.testkit.kit import junit_para_parse
from _core.testkit.kit import gtest_para_parse
from _core.testkit.kit import reset_junit_para
from _core.driver.parser_lite import ShellHandler
from _core.report.encrypt import check_pub_key_exist
from _core.utils import get_file_absolute_path
from _core.utils import check_result_report
from _core.utils import get_device_log_file
from _core.utils import get_kit_instances
from _core.utils import get_config_value
from _core.utils import exec_cmd
from _core.utils import check_device_name
from _core.utils import do_module_kit_setup
from _core.utils import do_module_kit_teardown
from _core.utils import convert_serial
from _core.utils import convert_ip
from _core.utils import convert_port
from _core.utils import check_mode
from _core.utils import get_filename_extension
from _core.utils import get_test_component_version
from _core.utils import get_local_ip
from _core.utils import create_dir
from _core.utils import is_proc_running
from _core.utils import check_path_legal
from _core.utils import modify_props
from _core.utils import get_shell_handler
from _core.utils import get_decode
from _core.utils import start_standing_subprocess
from _core.utils import stop_standing_subprocess
from _core.environment.manager_env import DeviceSelectionOption
from _core.environment.manager_env import EnvironmentManager
from _core.environment.device_state import DeviceEvent
from _core.environment.device_state import TestDeviceState
from _core.environment.device_state import DeviceState
from _core.environment.device_state import \
    handle_allocation_event
from _core.environment.device_state import \
    DeviceAllocationState
from _core.environment.device_monitor import DeviceStateListener
from _core.environment.device_monitor import DeviceStateMonitor
from _core.executor.scheduler import Scheduler
from _core.report.suite_reporter import SuiteReporter
from _core.report.suite_reporter import ResultCode
from _core.report.reporter_helper import ExecInfo
from _core.report.result_reporter import ResultReporter
from _core.report.reporter_helper import DataHelper
from _core.report.__main__ import main_report
from _core.command.console import Console
from adapter.xdevice_adapter.constants import UsbConst
from adapter.xdevice_adapter.constants import AppConst
from adapter.xdevice_adapter.constants import AppConst
__all__ = [
    "Variables",
    "Console",
    "platform_logger",
    "Plugin",
    "get_plugin",
    "IDriver",
    "IDevice",
    "IDeviceManager",
    "IParser",
    "LifeCycle",
    "IShellReceiver",
    "ITestKit",
    "IListener",
    "IReporter",
    "ParamError",
    "DeviceError",
    "LiteDeviceError",
    "ExecuteTerminate",
    "ReportException",
    "HdcError",
    "HdcCommandRejectedException",
    "ShellCommandUnresponsiveException",
    "DeviceUnresponsiveException",
    "AppInstallError",
    "HapNotSupportTest",
    "DeviceTestType",
    "DeviceLabelType",
    "ManagerType",
    "DeviceOsType",
    "ProductForm",
    "TestType",
    "CKit",
    "ConfigConst",
    "ModeType",
    "TestExecType",
    "ListenerType",
    "GTestConst",
    "CommonParserType",
    "FilePermission",
    "HostDrivenTestType",
    "DeviceConnectorType",
    "UserConfigManager",
    "ResourceManager",
    "CaseResult",
    "SuiteResult",
    "SuitesResult",
    "StateRecorder",
    "TestDescription",
    "CollectingTestListener",
    "Scheduler",
    "SuiteReporter",
    "DeviceSelectionOption",
    "EnvironmentManager",
    "DeviceEvent",
    "TestDeviceState",
    "DeviceState",
    "handle_allocation_event",
    "DeviceAllocationState",
    "DeviceStateListener",
    "DeviceStateMonitor",
    "JsonParser",
    "junit_para_parse",
    "gtest_para_parse",
    "reset_junit_para",
    "ShellHandler",
    "ResultCode",
    "check_pub_key_exist",
    "check_result_report",
    "get_file_absolute_path",
    "get_device_log_file",
    "get_kit_instances",
    "get_config_value",
    "exec_cmd",
    "check_device_name",
    "do_module_kit_setup",
    "do_module_kit_teardown",
    "convert_serial",
    "convert_ip",
    "convert_port",
    "check_mode",
    "get_filename_extension",
    "get_test_component_version",
    "get_local_ip",
    "create_dir",
    "is_proc_running",
    "check_path_legal",
    "modify_props",
    "get_shell_handler",
    "get_decode",
    "start_standing_subprocess",
    "stop_standing_subprocess",
    "ExecInfo",
    "ResultReporter",
    "DataHelper",
    "main_report",
    "UsbConst",
    "AppConst"
]


def _load_external_plugins():
    plugins = [Plugin.SCHEDULER, Plugin.DRIVER, Plugin.DEVICE, Plugin.LOG,
               Plugin.PARSER, Plugin.LISTENER, Plugin.TEST_KIT, Plugin.MANAGER,
               Plugin.REPORTER]
    for plugin_group in plugins:
        for entry_point in pkg_resources.iter_entry_points(group=plugin_group):
            entry_point.load()
    return


_load_external_plugins()
del _load_external_plugins
