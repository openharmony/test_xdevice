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
import platform
import subprocess
from subprocess import Popen, PIPE, STDOUT
import sys
import uuid

from xdevice import platform_logger
from xdevice import IDriver
from xdevice import Plugin
from xdevice import get_config_value
from xdevice import ConfigConst

KUNPENG_TEST = "KunpengTest"
LOG = platform_logger(KUNPENG_TEST)


@Plugin(type=Plugin.DRIVER, id=KUNPENG_TEST)
class KunpengTest(IDriver):
    """
    KunpengTest is a Test that runs a host-driven test on given kunpeng
    servers.
    """
    # test driver config
    config = None
    result = ""

    def __check_environment__(self, device_options):
        pass

    def __check_config__(self, config):
        pass

    def __execute__(self, request):
        self.config = request.config
        result_dir = os.path.join(request.config.report_path, "result")
        # status.db dir
        log_dir = os.path.join(request.config.report_path, "log")
        if not os.path.exists(result_dir):
            os.makedirs(result_dir)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        self.result = os.path.join(result_dir, 'result.xml')

        testargs = request.get(ConfigConst.testargs)
        mainconfig_file = testargs.get("main_config_path", [None])[0]
        project_src_path = testargs.get("main_config_path", [None])[1]
        if not mainconfig_file:
            LOG.info('can not find mainconfig_file in '
                     'testargs!!, use default mainconfig_file')
            return
        tmp_id = str(uuid.uuid1())
        tmp_folder = os.path.join(self.config.report_path, "temp")
        self.config.tmp_sub_folder = os.path.join(tmp_folder, "task_" + tmp_id)
        os.makedirs(self.config.tmp_sub_folder, exist_ok=True)

        # 3.test execution
        # mainconfig_file
        self._start_kunpengtest_with_cmd(mainconfig_file, project_src_path,
                                         log_dir)
        return

    def _get_driver_config(self, json_config):
        self.config.main_config = get_config_value(
            'main_config', json_config.get_driver(), False)
        self.config.test_bed = get_config_value(
            'test_bed', json_config.get_driver(), False)
        self.config.test_set = get_config_value(
            'test_set', json_config.get_driver(), False)

    def _start_kunpengtest_with_cmd(self, mainconfig_file, project_src_path,
                                    log_dir):  # , mainconfig_file
        sys.path.append(project_src_path)
        cmd_parts = []
        if platform.system() == "Windows":
            cmd_parts.append("python")
        else:
            cmd_parts.append("python3")
        start_script_path = os.path.join(project_src_path, 'bin', 'kprun.py')
        cmd_parts.append(start_script_path)
        cmd_parts.append("-c")
        cmd_parts.append(mainconfig_file)
        cmd_parts.append("-rp")
        cmd_parts.append(self.result)
        cmd_parts.append("-le")
        cmd_parts.append(log_dir)
        cmd = " ".join(cmd_parts)
        LOG.info("start kunpengtest with cmd: %s" % cmd)
        try:
            with Popen(cmd, shell=False, stdout=PIPE, stderr=STDOUT) as p:
                for line in p.stdout:
                    if line:
                        LOG.info(line.strip().decode('utf-8'))
                    else:
                        break
        except (subprocess.CalledProcessError, FileNotFoundError) as error:
            LOG.error("kunpeng test error: %s" % error)

    def __result__(self):
        return self.result if os.path.exists(self.result) else ""
