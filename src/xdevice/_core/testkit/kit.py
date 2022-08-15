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
import re
import stat
import json
import time
import platform
import subprocess
import signal
from threading import Timer

from _core.utils import get_file_absolute_path
from _core.logger import platform_logger
from _core.exception import ParamError
from _core.constants import DeviceTestType
from _core.constants import FilePermission
from _core.constants import DeviceConnectorType

LOG = platform_logger("Kit")

TARGET_SDK_VERSION = 22

__all__ = ["get_app_name_by_tool", "junit_para_parse", "gtest_para_parse",
           "get_install_args", "reset_junit_para", "remount", "disable_keyguard",
           "timeout_callback", "unlock_screen", "unlock_device", "get_class"]


def remount(device):
    device.enable_hdc_root()
    cmd = "target mount" \
        if device.usb_type == DeviceConnectorType.hdc else "remount"
    device.connector_command(cmd)
    device.execute_shell_command("remount")
    device.execute_shell_command("mount -o rw,remount /cust")
    device.execute_shell_command("mount -o rw,remount /product")
    device.execute_shell_command("mount -o rw,remount /hw_product")
    device.execute_shell_command("mount -o rw,remount /version")
    device.execute_shell_command("mount -o rw,remount /%s" % "system")


def get_class(junit_paras, prefix_char, para_name):
    if not junit_paras.get(para_name):
        return ""

    result = ""
    if prefix_char == "-e":
        result = " %s class " % prefix_char
    elif prefix_char == "--":
        result = " %sclass " % prefix_char
    elif prefix_char == "-s":
        result = " %s class " % prefix_char
    test_items = []
    for test in junit_paras.get(para_name):
        test_item = test.split("#")
        if len(test_item) == 1 or len(test_item) == 2:
            test_item = "%s" % test
            test_items.append(test_item)
        elif len(test_item) == 3:
            test_item = "%s#%s" % (test_item[1], test_item[2])
            test_items.append(test_item)
        else:
            raise ParamError("The parameter %s %s is error" % (
                             prefix_char, para_name))
    if not result:
        LOG.debug("There is unsolved prefix char: %s ." % prefix_char)
    return result + ",".join(test_items)


def junit_para_parse(device, junit_paras, prefix_char="-e"):
    """To parse the para of junit
    Args:
        device: the device running
        junit_paras: the para dict of junit
        prefix_char: the prefix char of parsed cmd
    Returns:
        the new para using in a command like -e testFile xxx
        -e coverage true...
    """
    ret_str = []
    path = "/%s/%s/%s" % ("data", "local", "ajur")
    include_file = "%s/%s" % (path, "includes.txt")
    exclude_file = "%s/%s" % (path, "excludes.txt")

    if not isinstance(junit_paras, dict):
        LOG.warning("The para of junit is not the dict format as required")
        return ""
    # Disable screen keyguard
    disable_key_guard = junit_paras.get('disable-keyguard')
    if not disable_key_guard or disable_key_guard[0].lower() != 'false':
        disable_keyguard(device)

    for para_name in junit_paras.keys():
        path = "/%s/%s/%s/" % ("data", "local", "ajur")
        if para_name.strip() == 'test-file-include-filter':
            for file_name in junit_paras[para_name]:
                device.push_file(file_name, include_file)
                device.execute_shell_command(
                    'chown -R shell:shell %s' % path)
            ret_str.append(" ".join([prefix_char, 'testFile', include_file]))
        elif para_name.strip() == "test-file-exclude-filter":
            for file_name in junit_paras[para_name]:
                device.push_file(file_name, exclude_file)
                device.execute_shell_command(
                    'chown -R shell:shell %s' % path)
            ret_str.append(" ".join([prefix_char, 'notTestFile',
                                     exclude_file]))
        elif para_name.strip() == "test" or para_name.strip() == "class":
            result = get_class(junit_paras, prefix_char, para_name.strip())
            ret_str.append(result)
        elif para_name.strip() == "include-annotation":
            ret_str.append(" ".join([prefix_char, "annotation",
                                     ",".join(junit_paras[para_name])]))
        elif para_name.strip() == "exclude-annotation":
            ret_str.append(" ".join([prefix_char, "notAnnotation",
                                     ",".join(junit_paras[para_name])]))
        else:
            ret_str.append(" ".join([prefix_char, para_name,
                                     ",".join(junit_paras[para_name])]))

    return " ".join(ret_str)


def gtest_para_parse(gtest_paras, runner, request):
    """To parse the para of gtest
    Args:
        gtest_paras: the para dict of gtest
    Returns:
        the new para using in gtest
    """
    ret_str = []
    if not isinstance(gtest_paras, dict):
        LOG.warning("The para of gtest is not the dict format as required")
        return ""

    for para in gtest_paras.keys():
        if para.strip() == 'test-file-include-filter':
            case_list = []
            files = gtest_paras.get(para)
            for case_file in files:
                flags = os.O_RDONLY
                modes = stat.S_IWUSR | stat.S_IRUSR
                with os.fdopen(os.open(case_file, flags, modes),
                               "r") as file_desc:
                    case_list.extend(file_desc.read().splitlines())

            runner.add_instrumentation_arg("gtest_filter", ":".join(case_list))

        if para.strip() == 'all-test-file-exclude-filter':
            json_file_list = gtest_paras.get("all-test-file-exclude-filter")
            if json_file_list:
                flags = os.O_RDONLY
                modes = stat.S_IWUSR | stat.S_IRUSR
                with os.fdopen(os.open(json_file_list[0], flags, modes),
                               "r") as file_handler:
                    json_data = json.load(file_handler)
                exclude_list = json_data.get(DeviceTestType.cpp_test)
                for exclude in exclude_list:
                    if request.get_module_name() in exclude:
                        case_list = exclude.get(request.get_module_name())
                        runner.add_instrumentation_arg(
                            "gtest_filter",
                            "%s%s" % ("-", ":".join(case_list)))
    return " ".join(ret_str)


def reset_junit_para(junit_para_str, prefix_char="-e", ignore_keys=None):
    if not ignore_keys and not isinstance(ignore_keys, list):
        ignore_keys = ["class", "test"]
    lines = junit_para_str.split("%s " % prefix_char)
    normal_lines = []
    for line in lines:
        line = line.strip()
        if line:
            items = line.split()
            if items[0].strip() in ignore_keys:
                continue
            normal_lines.append("{} {}".format(prefix_char, line))
    return " ".join(normal_lines)


def get_install_args(device, app_name, original_args=None):
    """To obtain all the args of app install
    Args:
        original_args: the argus configure in .config file
        device : the device will be installed app
        app_name : the name of the app which will be installed
    Returns:
        All the args
    """
    if original_args is None:
        original_args = []
    new_args = original_args[:]
    try:
        sdk_version = device.get_property("ro.build.version.sdk")
        if int(sdk_version) > TARGET_SDK_VERSION:
            new_args.append("-g")
    except TypeError as type_error:
        LOG.error("Obtain the sdk version failed with exception {}".format(
            type_error))
    except ValueError as value_error:
        LOG.error("Obtain the sdk version failed with exception {}".format(
            value_error))
    if app_name.endswith(".apex"):
        new_args.append("--apex")
    return " ".join(new_args)


def get_app_name_by_tool(app_path, paths):
    """To obtain the app name by using tool
    Args:
        app_path: the path of app
        paths:
    Returns:
        The Pkg Name if found else None
    """
    rex = "^package:\\s+name='(.*?)'.*$"
    aapt_tool_name = "aapt.exe" if os.name == "nt" else "aapt"
    if app_path:
        proc_timer = None
        try:
            tool_file = get_file_absolute_path(os.path.join(
                "tools", aapt_tool_name), paths)
            LOG.debug("Aapt file is %s" % tool_file)

            if platform.system() == "Linux":
                if not oct(os.stat(tool_file).st_mode)[-3:] == "755":
                    os.chmod(tool_file, FilePermission.mode_755)

            cmd = [tool_file, "dump", "badging", app_path]
            timeout = 300
            LOG.info("Execute command %s with %s" % (" ".join(cmd), timeout))

            sub_process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
            proc_timer = Timer(timeout, timeout_callback, [sub_process])
            proc_timer.start()
            # The package name must be return in first line
            output = sub_process.stdout.readline()
            error = sub_process.stderr.readline()
            LOG.debug("The output of aapt is {}".format(output))
            if error:
                LOG.debug("The error of aapt is {}".format(error))
            if output:
                pkg_match = re.match(rex, output.decode("utf8", 'ignore'))
                if pkg_match is not None:
                    LOG.info(
                        "Obtain the app name {} successfully by using "
                        "aapt".format(pkg_match.group(1)))
                    return pkg_match.group(1)
            return None
        except (FileNotFoundError, ParamError) as error:
            LOG.debug("Aapt error: %s", error.args)
            return None
        finally:
            if proc_timer:
                proc_timer.cancel()
    else:
        LOG.error("get_app_name_by_tool error.")
        return None


def timeout_callback(proc):
    try:
        LOG.error("Error: execute command timeout.")
        LOG.error(proc.pid)
        if platform.system() != "Windows":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            subprocess.call(
                ["C:\\Windows\\System32\\taskkill", "/F", "/T", "/PID",
                 str(proc.pid)], shell=False)
    except (FileNotFoundError, KeyboardInterrupt, AttributeError) as error:
        LOG.exception("Timeout callback exception: %s" % error, exc_info=False)


def disable_keyguard(device):
    unlock_screen(device)
    unlock_device(device)


def unlock_screen(device):
    device.execute_shell_command("svc power stayon true")
    time.sleep(1)


def unlock_device(device):
    device.execute_shell_command("input keyevent 82")
    time.sleep(1)
    device.execute_shell_command("wm dismiss-keyguard")
    time.sleep(1)
